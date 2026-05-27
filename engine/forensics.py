import asyncio
import os
import sys
import json
import re
import httpx
import logging
import random
from datetime import datetime
from collections import defaultdict

class StealthNetwork:
    @classmethod
    def get_headers(cls):
        return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", "Accept": "*/*", "Referer": "https://www.google.com/"}

class SourceRateLimiter:
    """Ensures no two workers hit the same source in the same second."""
    def __init__(self, interval=1.2): # 1.2s buffer
        self.interval = interval
        self.last_call = 0
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = asyncio.get_event_loop().time()
            wait = self.last_call + self.interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self.last_call = asyncio.get_event_loop().time()

class ForensicSource:
    def __init__(self, n, limiter=None):
        self.n = n
        self.limiter = limiter or SourceRateLimiter()

    async def fetch(self, d):
        try:
            # SOURCE ISOLATION: Wait for the per-source turn
            await self.limiter.acquire()
            return await self._execute_fetch(d)
        except Exception as e:
            logging.debug(f"[SOURCE][{self.n}] Error: {e}")
            return []

class WaybackSource(ForensicSource):
    async def _execute_fetch(self, domain):
        results = []
        eras = [("2016", "2026", 400), ("2006", "2015", 300), ("1995", "2005", 200)]
        async with httpx.AsyncClient(timeout=45, verify=False, headers=StealthNetwork.get_headers()) as client:
            for start, end, limit in eras:
                try:
                    params = {"url": domain, "output": "json", "limit": limit, "matchType": "prefix", "from": f"{start}0101000000", "to": f"{end}1231235959", "collapse": "digest", "filter": ["statuscode:200|301|302", "mimetype:text/html"]}
                    resp = await client.get("https://web.archive.org/cdx/search/cdx", params=params)
                    if resp.status_code == 200:
                        data = resp.json()
                        if len(data) <= 1: continue
                        h = data[0]
                        for line in data[1:]:
                            item = dict(zip(h, line))
                            results.append({"url": f"https://web.archive.org/web/{item['timestamp']}id_/{item['original']}", "timestamp": item["timestamp"], "source": "Wayback", "digest": item["digest"], "length": int(item.get("length", 0)), "is_root": item['original'].strip("/").count("/") <= 2})
                except: continue
        return results

class CommonCrawlSource(ForensicSource):
    async def _execute_fetch(self, d):
        results = []
        indices = ["CC-MAIN-2024-10", "CC-MAIN-2023-50", "CC-MAIN-2023-23"]
        async with httpx.AsyncClient(timeout=30, verify=False, headers=StealthNetwork.get_headers()) as client:
            for idx in indices:
                try:
                    resp = await client.get(f"https://index.commoncrawl.org/{idx}-index", params={"url": f"{d}/*", "output": "json", "limit": 100})
                    if resp.status_code == 200:
                        for line in resp.text.splitlines():
                            item = json.loads(line)
                            results.append({"url": f"https://commoncrawl.s3.amazonaws.com/{item['filename']}", "timestamp": item["timestamp"], "source": f"CC-{idx}", "digest": item["digest"], "length": int(item.get("length", 0)), "is_root": True})
                except: continue
        return results

class RegionalSource(ForensicSource):
    def __init__(self, n, e, p, l):
        super().__init__(n, l); self.e, self.p = e, p
    async def _execute_fetch(self, d):
        async with httpx.AsyncClient(timeout=30, verify=False, headers=StealthNetwork.get_headers()) as client:
            resp = await client.get(self.e, params={"url": d, "matchType": "prefix", "output": "json", "limit": 500, "collapse": "digest"})
            if resp.status_code == 200:
                data = resp.json()
                if len(data) <= 1: return []
                h = data[0]
                return [{"url": self.p.format(ts=i[h.index('timestamp')], url=i[h.index('original')]), "timestamp": i[h.index('timestamp')], "source": self.n, "digest": i[h.index('digest')], "length": int(i[h.index('length')]), "is_root": True} for i in data[1:]]
        return []

class ForensicEngine:
    def __init__(self, base_dir=None):
        # Global Limiters shared across workers
        self.wayback_limiter = SourceRateLimiter(1.5)
        self.cc_limiter = SourceRateLimiter(1.0)
        self.regional_limiter = SourceRateLimiter(2.0) # Regional nodes are more sensitive
        
        self.sources = [
            WaybackSource("Wayback", self.wayback_limiter),
            CommonCrawlSource("CommonCrawl", self.cc_limiter),
            RegionalSource("Arquivo.pt", "https://arquivo.pt/textsearch", "https://arquivo.pt/wayback/{ts}/{url}", self.regional_limiter),
            RegionalSource("UK WA", "https://webarchive.nationalarchives.gov.uk/ukgwa/cdx", "https://webarchive.nationalarchives.gov.uk/ukgwa/{ts}/{url}", self.regional_limiter),
            RegionalSource("Australia NLA", "https://webarchive.nla.gov.au/awa/timemap/cdx", "https://webarchive.nla.gov.au/awa/{ts}/{url}", self.regional_limiter)
        ]

    async def search_all_archives(self, d):
        logging.info(f"[GHOST][Forensics] Universal Era-Aware discovery (Source-Isolated) for {d}...")
        all_hits = []
        targets = [d, f"www.{d}"] if not d.startswith("www.") else [d]
        random.shuffle(self.sources)
        for t in targets:
            tasks = [s.fetch(t) for s in self.sources]
            results = await asyncio.gather(*tasks)
            for res in results: all_hits.extend(res)
        
        if not all_hits: return [], [], "None", 0
        vibrancy = defaultdict(lambda: {"c": 0, "l": 0})
        for s in all_hits:
            y = s["timestamp"][:4]
            vibrancy[y]["c"] += 1; vibrancy[y]["l"] += s.get("length", 0)
        
        era_scores = {y: (v["c"] * 10) + (v["l"] / v["c"] / 100) for y, v in vibrancy.items()}
        final_pool = []
        seen_urls = set()
        for s in all_hits:
            if s["url"] in seen_urls: continue
            seen_urls.add(s["url"])
            y = s["timestamp"][:4]
            score = era_scores.get(y, 0)
            if s.get("is_root"): score += 250
            score += min(700, s.get("length", 0) // 70)
            if int(y) >= 2022 and s.get("length", 0) < 5000: score -= 300
            s["_score"] = score
            final_pool.append(s)
            
        final_pool.sort(key=lambda x: x["_score"], reverse=True)
        dedup = []; seen_dig = set()
        for s in final_pool:
            if s["digest"] not in seen_dig or not s["digest"]:
                dedup.append(s); seen_dig.add(s["digest"])
                if len(dedup) >= 200: break
                
        return dedup, [s["source"] for s in dedup[:10]], "Era-Aware-Isolated", len(all_hits)
