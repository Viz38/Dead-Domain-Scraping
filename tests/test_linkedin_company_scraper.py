import pytest
from unittest.mock import patch, MagicMock
from services.linkedin_company_scraper import LinkedInCompanyScraper

@pytest.mark.asyncio
async def test_linkedin_company_scraping_and_website_check():
    enricher = LinkedInCompanyScraper(api_key="mock-proxycurl")
    mock_data = {
        "name": "Acme Electric",
        "description": "Manufacturer of industrial high-performance tools.",
        "website": "https://www.acmeelectric.com",
        "industry": "Electrical Manufacturing"
    }
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_data)
        profile = await enricher.scrape_company("https://www.linkedin.com/company/acme-electric")
        
        assert profile["website"] == "https://www.acmeelectric.com"
