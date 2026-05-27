import httpx
import os
import logging
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

class SearchClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("SERPER_API_KEY", "")
        self.url = "https://google.serper.dev/search"
        
    async def search(self, query: str) -> list[dict]:
        # Pass 1: Try Serper Google Search if an API key is available
        if self.api_key:
            headers = {
                "X-API-KEY": self.api_key,
                "Content-Type": "application/json"
            }
            payload = {"q": query}
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    resp = await client.post(self.url, headers=headers, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        return data.get("organic", [])
            except Exception as e:
                logging.error(f"[SEARCH_CLIENT] Serper search error, falling back to DuckDuckGo: {e}")

        # Pass 2: Completely FREE DuckDuckGo HTML Fallback
        logging.info(f"[SEARCH_CLIENT] Querying DuckDuckGo (Free Fallback) for: {query}")
        
        # Suppress XMLParsedAsHTMLWarning if triggered during HTML/XML parsing
        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.post("https://html.duckduckgo.com/html/", headers=headers, data={"q": query})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    results = []
                    for result in soup.find_all("div", class_="result"):
                        title_a = result.find("a", class_="result__a")
                        snippet_div = result.find("a", class_="result__snippet") or result.find("div", class_="result__snippet")
                        if title_a:
                            title = title_a.text.strip()
                            link = title_a["href"]
                            snippet = snippet_div.text.strip() if snippet_div else ""
                            results.append({
                                "title": title,
                                "link": link,
                                "snippet": snippet
                            })
                    logging.info(f"[SEARCH_CLIENT] DuckDuckGo fallback found {len(results)} free results.")
                    return results
        except Exception as e:
            logging.error(f"[SEARCH_CLIENT] DuckDuckGo search fallback error: {e}")
            
        return []
