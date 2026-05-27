import httpx
import os
import logging
import re
from utils.scraper import get_global_browser, html_to_markdown

class LinkedInCompanyScraper:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("PROXYCURL_API_KEY", "")
        self.url = "https://nubela.co/api/v1/linkedin/company"
        
    async def scrape_company(self, company_url: str) -> dict:
        if self.api_key:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"url": company_url}
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(self.url, headers=headers, params=params)
                    if resp.status_code == 200:
                        return resp.json()
            except Exception as e:
                logging.error(f"[COMPANY_SCRAPER] Proxycurl error: {e}")
                
        return await self._scrape_public_company(company_url)
        
    async def _scrape_public_company(self, company_url: str) -> dict:
        logging.info(f"[COMPANY_SCRAPER] Public Playwright scrape fallback for {company_url}")
        browser = await get_global_browser()
        ctx = await browser.new_context()
        page = await ctx.new_page()
        try:
            await page.goto(company_url, timeout=30000, wait_until="load")
            content = await page.content()
            title = await page.title()
            
            markdown = html_to_markdown(content)
            
            # Simple regex search to extract listed website from page contents
            website_match = re.search(r"website\s*:\s*(https?://[^\s'\"]+)", markdown, re.IGNORECASE)
            website = website_match.group(1) if website_match else ""
            
            return {
                "name": title.replace(" | LinkedIn", ""),
                "description": markdown[:4000],
                "website": website,
                "source": "Playwright Public Fallback"
            }
        except Exception as e:
            logging.error(f"[COMPANY_SCRAPER] Playwright fallback error: {e}")
        finally:
            await ctx.close()
        return {}
