import pytest
import asyncio
from unittest.mock import patch, MagicMock
from engine.forensics import RegionalSource

@pytest.mark.asyncio
async def test_arquivo_source_api():
    """Test that RegionalSource correctly parses hits from the official Arquivo.pt API."""
    domain = "example.com"
    source = RegionalSource("Arquivo.pt", "https://arquivo.pt/textsearch", "https://arquivo.pt/wayback/{ts}/{url}", None)
    
    # Mock response from Arquivo.pt Search API (CDX JSON array format)
    mock_response = [
        ["timestamp", "original", "digest", "length"],
        ["20100101000000", "http://example.com", "digest123", "1000"]
    ]
    
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value = MagicMock(status_code=200, json=lambda: mock_response)
        
        results = await source.fetch(domain)
        
        assert len(results) == 1
        assert results[0]["timestamp"] == "20100101000000"
        assert "arquivo.pt" in results[0]["url"]
        assert results[0]["source"] == "Arquivo.pt"
