import asyncio
import re
import httpx
import random
import logging
import warnings
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# --- NATURAL STEALTH PROVIDER ---
class StealthProvider:
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 6.1; WOW64; Trident/7.0; rv:11.0) like Gecko"
    ]
    @classmethod
    def get_headers(cls, referer=None):
        ua = random.choice(cls.USER_AGENTS)
        headers = {"User-Agent": ua, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.5", "Connection": "keep-alive"}
        if referer: headers["Referer"] = referer
        return headers

# --- GLOBAL BROWSER ---
_BROWSER_INSTANCE = None
_BROWSER_LOCK = asyncio.Lock()
page_semaphore = asyncio.Semaphore(12)

async def get_global_browser():
    global _BROWSER_INSTANCE
    async with _BROWSER_LOCK:
        if _BROWSER_INSTANCE is None or not _BROWSER_INSTANCE.is_connected():
            pw = await async_playwright().start()
            _BROWSER_INSTANCE = await pw.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        return _BROWSER_INSTANCE

async def close_global_browser():
    global _BROWSER_INSTANCE
    async with _BROWSER_LOCK:
        if _BROWSER_INSTANCE:
            await _BROWSER_INSTANCE.close()
            _BROWSER_INSTANCE = None

# --- CONTENT EXTRACTION ---
def html_to_markdown(html):
    if not html: return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        
        # SURGICAL STRIP: Remove Wayback Machine UI, Headers, and Sitemap Footers
        for ia_ui in soup.select("#wm-ipp-base, #wm-ipp-print, #don-reg, .wm-ipp-base, #wayback-header, .archive-footer, .footer-sitemap, #sitemap-content, .wb-nav, #wm-ipp-inside, #wm-ipp-container"):
            ia_ui.decompose()
            
        for tag in soup(["script", "style", "svg", "canvas", "nav", "footer"]):
            tag.decompose()
            
        # Handle Frames (But skip IA internal frames and ad frames if possible)
        for frame in soup.find_all(["frame", "iframe"]):
            src = frame.get("src", "")
            if src and "archive.org" not in src: # Only mark external business frames
                # Prune dynamic ads, safeframe token parameter feeds, and trustpilot widgets
                if any(ad in src for ad in ["findresultsquick.com", "widget.trustpilot.com", "safeframe"]) or len(src) > 180:
                    frame.decompose()
                    continue
                frame.insert_after(soup.new_string(f"\n[FRAME: {src}]\n"))
                
        text = soup.get_text(separator="\n", strip=True)
        # Final cleanup of any lingering IA patterns
        text = re.sub(r'Wayback Machine.*?\n', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Hard signature safety block for Internet Archive sitemap page leaks
        c_lower = text.lower()
        if "ask the publishers" in c_lower and "grateful dead" in c_lower and "internet archive audio" in c_lower:
            return ""
            
        return text
    except: return ""

def is_parked_content(content: str, title: str = "") -> bool:
    if not content:
        return False
    c_lower = content.lower()
    t_lower = title.lower() if title else ""
    
    # High-confidence explicit parked indicators (direct block)
    direct_parked_phrases = [
        "domain is for sale", "domain name for sale", "buy this domain", "buy domain",
        "huge domains", "hugedomains", "sedo", "parked free", "expired on",
        "domain expired", "domain name expired", "this domain has expired",
        "dns parking", "parked domain", "domainparking", "parking page", "parked page",
        "this domain is parked", "this page is parked", "purchase this domain",
        "renew this domain", "renew domain", "domain name is available", "domain is available",
        "parking services", "parked on", "available for sale",
        "parallels plesk panel", "cpanel holding page", "zen internet | cpanel", 
        "hosted by one.com", "attention required! | cloudflare", "findresultsquick.com"
    ]
    
    if any(phrase in c_lower or phrase in t_lower for phrase in direct_parked_phrases):
        return True
        
    # Contextual indicators: Registrar/Provider keywords that only mean parked if the page is extremely short
    registrar_keywords = ["godaddy", "namecheap", "registrar", "backorder", "domain host", "registered at"]
    word_count = len(c_lower.split())
    
    # If page is extremely brief (under 400 words), perform contextual check for registrar and coming-soon placeholders
    if word_count < 400:
        # 1. Standard registrar placeholder pages
        if any(kw in c_lower or kw in t_lower for kw in registrar_keywords):
            if "coming soon" in c_lower or "under construction" in c_lower:
                return True
            if "parked" in c_lower or "parking" in c_lower:
                return True
            if "registered" in c_lower or "registration" in c_lower:
                return True
                
        # 2. Free-standing placeholders (e.g., coming soon / under construction / maintenance)
        free_standing_placeholders = [
            "coming soon", "under construction", "site is under construction",
            "website under construction", "check back soon", "launching soon",
            "new website coming soon", "will be back soon", "maintenance mode",
            "down for maintenance", "temporary maintenance", "check back later"
        ]
        if any(phrase in c_lower or phrase in t_lower for phrase in free_standing_placeholders):
            return True
            
    return False


async def check_adversarial_parking(page):
    try:
        content = (await page.content()).lower()
        title = (await page.title()).lower()
        if any(kw in content or kw in title for kw in ["blocked by robots.txt", "robots.txt exclusion", "retroactively excluded"]):
            return "BLOCK: ROBOTS"
        if is_parked_content(content, title):
            return "BLOCK: PARKED"
        return False
    except: return False

async def stealth_probe(url): return await scrape_url(url)
async def is_parked(page): return await check_adversarial_parking(page)

async def scrape_url(url, browser=None):
    """SOURCE-BYPASS FORENSIC SCRAPER WITH VERBOSE LOGGING"""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
        
    is_ia = "web.archive.org/web/" in url
    ref = "https://web.archive.org/" if is_ia else "https://www.google.com/"
    
    # PASS 1: Raw id_ bypass (HTTPX)
    furl = url
    if is_ia and "id_/" not in url: furl = re.sub(r"/web/(\d+)/", r"/web/\1id_/", url)
    
    try:
        async with httpx.AsyncClient(timeout=30, verify=False, follow_redirects=True, headers=StealthProvider.get_headers(ref)) as client:
            resp = await client.get(furl)
            if resp.status_code == 200:
                c = html_to_markdown(resp.text)
                if "blocked by robots.txt" in c.lower():
                    return "BLOCK: ROBOTS"
                if is_parked_content(resp.text, "") or is_parked_content(c, ""):
                    return "BLOCK: PARKED"
                if len(c) > 300:
                    return {"html": resp.text, "text": c}
            else:
                logging.info(f"[SCRAPER][FastPath] HTTP {resp.status_code} for {furl}")
    except Exception as e:
        logging.info(f"[SCRAPER][FastPath] Error: {e}")

    # PASS 2: Deep Frame Penetration (Playwright)
    if not browser: browser = await get_global_browser()
    async with page_semaphore:
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        try:
            std_url = furl.replace("id_/", "/")
            await page.goto(std_url, timeout=45000, wait_until="load")
            
            # Check for blocks
            block = await check_adversarial_parking(page)
            if block: 
                await ctx.close(); return block
            
            all_content = []
            all_html = []
            for frame in page.frames:
                try:
                    f_content = await frame.content()
                    if "blocked by robots.txt" not in f_content.lower():
                        all_content.append(html_to_markdown(f_content))
                        all_html.append(f_content)
                except: continue
            
            combined_text = "\n".join(all_content)
            if len(combined_text) > 400:
                combined_html = "\n\n<!-- FRAME -->\n\n".join(all_html)
                await ctx.close(); return {"html": combined_html, "text": combined_text}
            else:
                logging.info(f"[SCRAPER][HeavyPath] Insufficient content ({len(combined_text)}) for {std_url}")
                
            # PASS 3: Legacy UA
            await ctx.close()
            ctx = await browser.new_context(user_agent="Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.1; Trident/4.0)")
            page = await ctx.new_page()
            await page.goto(std_url, timeout=60000, wait_until="networkidle")
            await asyncio.sleep(5)
            html_content = await page.content()
            c = html_to_markdown(html_content)
            if "blocked by robots.txt" in c.lower():
                await ctx.close(); return "BLOCK: ROBOTS"
            if is_parked_content(html_content, await page.title()) or is_parked_content(c, ""):
                await ctx.close(); return "BLOCK: PARKED"
            if len(c) > 300:
                await ctx.close(); return {"html": html_content, "text": c}
            else:
                logging.info(f"[SCRAPER][ExtremePath] Insufficient content ({len(c)}) for {std_url}")
        except Exception as e:
            logging.info(f"[SCRAPER][HeavyPath] Exception for {url}: {e}")
        finally: await ctx.close()
    return ""
