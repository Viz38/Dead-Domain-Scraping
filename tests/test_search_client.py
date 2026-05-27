import pytest
from unittest.mock import patch, MagicMock
from services.search_client import SearchClient

@pytest.mark.asyncio
async def test_search_client_success():
    client = SearchClient(api_key="mock-key")
    mock_response = {
        "organic": [
            {"title": "Acme Electric: Overview | LinkedIn", "link": "https://www.linkedin.com/company/acme-electric", "snippet": "Acme Electric is an electrical services company..."},
            {"title": "Acme Electric - Crunchbase Company Profile", "link": "https://www.crunchbase.com/organization/acme-electric", "snippet": "Acme Electric manufactures electrical equipment..."}
        ]
    }
    
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, json=lambda: mock_response)
        results = await client.search("site:linkedin.com/company/ \"Acme Electric\"")
        
        assert len(results) == 2
        assert results[0]["link"] == "https://www.linkedin.com/company/acme-electric"
        assert "company/acme-electric" in results[0]["link"]
