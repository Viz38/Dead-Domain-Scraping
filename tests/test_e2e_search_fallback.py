import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from ghost import GhostOrchestrator

@pytest.mark.asyncio
async def test_ghost_fallback_trigger_on_scraping_failure():
    # Configure orchestrator in archival-only mode to skip live probe
    orchestrator = GhostOrchestrator(sheet_url="mock-sheet-id", mode="archival")
    
    # Mock dashboard and sheet clients
    orchestrator.dashboard = MagicMock()
    orchestrator._update_row_status = AsyncMock()
    orchestrator.sheet_client = MagicMock()
    orchestrator.sheet_client.write_classification = AsyncMock()
    
    # Mock finalization
    orchestrator._finalize_hit = AsyncMock()
    
    # Simulates zero snapshots returned (archival scanning fail)
    orchestrator.forensics = MagicMock()
    orchestrator.forensics.search_all_archives = AsyncMock(return_value=([], [], 0, 0))
    
    # Mock Serper Search results
    mock_search_results = [
        {"title": "Acme Electric: Overview | LinkedIn", "link": "https://www.linkedin.com/company/acme-electric", "snippet": "Acme Electric (acmeelectric.com) makes tools."}
    ]
    
    # Mock LinkedIn Company Page details
    mock_company_data = {
        "name": "Acme Electric",
        "description": "Premium industrial manufacturer.",
        "website": "https://www.acmeelectric.com",
        "industry": "Electrical Manufacturing"
    }
    
    with patch("services.search_client.SearchClient.search", new_callable=AsyncMock) as mock_search, \
         patch("services.linkedin_company_scraper.LinkedInCompanyScraper.scrape_company", new_callable=AsyncMock) as mock_scrape:
         
        mock_search.return_value = mock_search_results
        mock_scrape.return_value = mock_company_data
        
        # Execute processing on mock domain
        success = await orchestrator._process_domain("acmeelectric.com", row_idx=5, worker_id=1)
        
        # Assertions: fallback succeeded, search/scrape were called, and _finalize_hit recorded success
        assert success is True
        mock_search.assert_called()
        mock_scrape.assert_called_with("https://www.linkedin.com/company/acme-electric")
        
        # Verify finalized payload structure contains assembled headers
        call_args = orchestrator._finalize_hit.call_args[0]
        content_payload = call_args[2]
        
        assert "### [FALLBACK METADATA FOR: acmeelectric.com]" in content_payload
        assert "Premium industrial manufacturer." in content_payload

@pytest.mark.asyncio
async def test_ghost_search_only_mode():
    orchestrator = GhostOrchestrator(sheet_url="mock-sheet-id", mode="search_only")
    orchestrator.dashboard = MagicMock()
    orchestrator._update_row_status = AsyncMock()
    orchestrator._finalize_hit = AsyncMock()
    
    orchestrator.forensics = MagicMock()
    orchestrator.forensics.search_all_archives = AsyncMock(return_value=([], [], 0, 0))
    
    mock_search_results = [
        {"title": "Acme Electric: Overview | LinkedIn", "link": "https://www.linkedin.com/company/acme-electric", "snippet": "Acme Electric (acmeelectric.com) makes tools."}
    ]
    mock_company_data = {
        "name": "Acme Electric",
        "description": "Premium industrial manufacturer.",
        "website": "https://www.acmeelectric.com",
        "industry": "Electrical Manufacturing"
    }
    
    with patch("services.search_client.SearchClient.search", new_callable=AsyncMock) as mock_search, \
         patch("services.linkedin_company_scraper.LinkedInCompanyScraper.scrape_company", new_callable=AsyncMock) as mock_scrape, \
         patch("ghost.stealth_probe", new_callable=AsyncMock) as mock_probe:
         
        mock_search.return_value = mock_search_results
        mock_scrape.return_value = mock_company_data
        
        success = await orchestrator._process_domain("acmeelectric.com", row_idx=5, worker_id=1)
        
        assert success is True
        mock_probe.assert_not_called()
        orchestrator.forensics.search_all_archives.assert_not_called()
        mock_search.assert_called()

@pytest.mark.asyncio
async def test_ghost_live_probe_workflow():
    orchestrator = GhostOrchestrator(sheet_url="mock-sheet-id", mode="full")
    orchestrator.dashboard = MagicMock()
    orchestrator._update_row_status = AsyncMock()
    orchestrator._finalize_hit = AsyncMock()
    
    # Mock stealth_probe to return a high-fidelity dictionary (>1800 characters of text)
    mock_live_text = "Acme Electric " * 200 # Over 1800 characters
    mock_live_content = {"html": "<p>Acme Electric</p>" * 200, "text": mock_live_text}
    
    with patch("ghost.stealth_probe", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = mock_live_content
        
        # This will execute _process_domain with mode="full", hitting the live probe branch
        success = await orchestrator._process_domain("acmeelectric.com", row_idx=5, worker_id=1)
        
        assert success is True
        assert mock_probe.call_count == 5
        expected_html = "\n\n---\n\n".join([mock_live_content["html"]] * 5)
        expected_text = "\n\n---\n\n".join([mock_live_text] * 5)
        orchestrator._finalize_hit.assert_called_once_with(5, "acmeelectric.com", expected_html, "LIVE_PROBE", ["acmeelectric.com"], text_data=expected_text)


