import pytest
from unittest.mock import AsyncMock, patch, MagicMock, mock_open

@pytest.mark.asyncio
async def test_maintenance_moves_failed_rows():
    from maintenance import perform_maintenance
    
    with patch('maintenance.GoogleSheetClient') as mock_client_cls, \
         patch('maintenance.TracxnClient') as mock_tracxn_cls, \
         patch('maintenance.os.getenv') as mock_getenv, \
         patch('maintenance.os.makedirs'), \
         patch('builtins.open', mock_open()):
        
        # Setup env vars
        def getenv_side_effect(key, default=None):
            env = {
                "GHOST_SHEET_ID": "sheet_123",
                "SUCCESS_SHEET_P1_ID": "p1_sheet",
                "SUCCESS_SHEET_P2_ID": "p2_sheet",
                "SUCCESS_SHEET_P3_ID": "p3_sheet",
                "MAINTENANCE_TIME": "05:00",
                "MAX_DOMAINS_IN_SHEET": "6000"
            }
            return env.get(key, default)
            
        mock_getenv.side_effect = getenv_side_effect
        
        # Setup Sheet Client
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        
        # Setup mock rows
        mock_client.get_all_rows.return_value = [
            ["Domain", "Scan Status", "C", "D", "E", "F", "G", "H", "I", "Payload"],
            ["success.com", "SUCCESS", "", "", "", "", "", "", "", "PASS 1"],
            ["failed.com", "BLOCK: NO_VALID_TARGET", "", "", "", "", "", "", "", "PASS 2"],
            ["queued.com", "QUEUED", "", "", "", "", "", "", "", "PASS 3"],
        ]
        
        mock_service = MagicMock()
        mock_client.service = mock_service
        mock_service.spreadsheets().get.return_value = {"sheets": [{"properties": {"title": "Console", "sheetId": 123}}]}
        mock_client._execute_with_retry = AsyncMock()
        mock_client._execute_with_retry.side_effect = lambda op: op if isinstance(op, dict) else op
        
        mock_append_p1 = MagicMock()
        mock_append_p2 = MagicMock()
        mock_service.spreadsheets().values().append.side_effect = lambda spreadsheetId, **kwargs: mock_append_p1 if spreadsheetId == "p1_sheet" else mock_append_p2
        
        # Setup Tracxn Client (simulate no domains to fetch or simple return)
        mock_tracxn = AsyncMock()
        mock_tracxn_cls.return_value = mock_tracxn
        mock_tracxn.payloads = []
        
        await perform_maintenance()
        
        # Assertions
        # It should append to both P1 (for SUCCESS) and P2 (for BLOCK)
        # Check call args of append
        appends = mock_client.service.spreadsheets().values().append.call_args_list
        p1_calls = [c for c in appends if c.kwargs.get('spreadsheetId') == 'p1_sheet']
        p2_calls = [c for c in appends if c.kwargs.get('spreadsheetId') == 'p2_sheet']
        
        assert len(p1_calls) == 1
        assert p1_calls[0].kwargs['body']['values'][0][0] == 'success.com'
        
        assert len(p2_calls) == 1, "Failed row was not appended to success sheets"
        assert p2_calls[0].kwargs['body']['values'][0][0] == 'failed.com', "Failed row was not appended correctly"
        
        # Check that both SUCCESS and BLOCK rows are queued for deletion
        batch_update_calls = mock_client.service.spreadsheets().batchUpdate.call_args_list
        assert len(batch_update_calls) == 1, "Batch update for deletions was not called"
        
        delete_requests = batch_update_calls[0].kwargs['body']['requests']
        assert len(delete_requests) == 2, "Should delete exactly 2 rows"
        
        # The deletions should be in reverse order (indices 2 and 1)
        assert delete_requests[0]['deleteDimension']['range']['startIndex'] == 2
        assert delete_requests[1]['deleteDimension']['range']['startIndex'] == 1
