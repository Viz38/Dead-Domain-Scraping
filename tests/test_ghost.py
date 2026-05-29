import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_ghost_orchestrator_resumes_interrupted_rows():
    from ghost import GhostOrchestrator
    
    with patch('ghost.GoogleSheetClient') as mock_client_cls, \
         patch('ghost.HardwareOptimizer') as mock_hw, \
         patch('ghost.ForensicEngine'), \
         patch('ghost.GhostArchiver'):
         
        mock_hw.calculate_concurrency.return_value = (5, {"os": "mock"})
        mock_hw.optimize_system_limits.return_value = (True, 1024)
        
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        
        mock_client.get_all_rows.return_value = [
            ["Domain", "Scan Status"],
            ["completed1.com", "SUCCESS"],
            ["completed2.com", "BLOCK: NO_VALID_TARGET"],
            ["interrupted1.com", "PROBING LIVE (MULTIPLE PAGES)..."],
            ["interrupted2.com", "HIT: Wayback (1)..."],
            ["queued1.com", "QUEUED"],
            ["completed3.com", "SUCCESS"], # A completed one appearing later
            ["queued2.com", ""]
        ]
        
        orchestrator = GhostOrchestrator("dummy_sheet")
        orchestrator._process_domain_protected = AsyncMock()
        orchestrator._status_flusher_loop = AsyncMock()
        
        await orchestrator.run()
        
        # Check what was queued in pending_rows (these will be called in _process_domain_protected)
        calls = orchestrator._process_domain_protected.call_args_list
        queued_domains = [c.args[0] for c in calls]
        
        assert "interrupted1.com" in queued_domains, "Did not resume PROBING LIVE"
        assert "interrupted2.com" in queued_domains, "Did not resume Wayback hit"
        assert "queued1.com" in queued_domains, "Did not process QUEUED"
        assert "queued2.com" in queued_domains, "Did not process empty status"
        assert "completed1.com" not in queued_domains, "Processed a SUCCESS row"
        assert "completed2.com" not in queued_domains, "Processed a BLOCK row"
        assert "completed3.com" not in queued_domains, "Processed a later SUCCESS row"
