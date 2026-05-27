from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import asyncio, time, logging
from socket import error as SocketError
import os

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

import json

class GoogleSheetClient:
    # Global throttling state: 60 requests per minute limit across all instances
    _request_history = []
    _lock = asyncio.Lock()

    def __init__(self):
        # Fetch credentials securely from the environment variable
        creds_json = os.getenv("GOOGLE_CREDENTIALS")
        if not creds_json:
            logging.error("[GSHEET] GOOGLE_CREDENTIALS environment variable not found.")
            raise ValueError("GOOGLE_CREDENTIALS environment variable is not set.")

        try:
            creds_info = json.loads(creds_json)
        except json.JSONDecodeError as e:
            logging.error(f"[GSHEET] Invalid JSON in GOOGLE_CREDENTIALS: {e}")
            raise

        self.creds = service_account.Credentials.from_service_account_info(
            creds_info, scopes=SCOPES)
        self._refresh_service()

    def _refresh_service(self):
        """Re-initializes the Google Sheets service to recover from corrupted SSL states."""
        self.service = build('sheets', 'v4', credentials=self.creds, cache_discovery=False)

    async def _wait_for_budget(self):
        """Ensures we stay under the 60 requests per minute limit."""
        async with GoogleSheetClient._lock:
            now = time.time()
            # Remove requests older than 60 seconds
            GoogleSheetClient._request_history = [t for t in GoogleSheetClient._request_history if now - t < 60]
            
            if len(GoogleSheetClient._request_history) >= 55: # Safety margin
                wait_time = 60 - (now - GoogleSheetClient._request_history[0])
                if wait_time > 0:
                    print(f"[GSHEET] Global Budget exhausted ({len(GoogleSheetClient._request_history)} req/min). Waiting {wait_time:.2f}s...")
                    await asyncio.sleep(wait_time)
            
            GoogleSheetClient._request_history.append(time.time())

    async def _execute_with_retry(self, operation, retries=5):
        """Async-native wrapper for Google API calls with throttling and exponential backoff."""
        await self._wait_for_budget()
        
        for attempt in range(retries):
            try:
                # operation.execute() is blocking, but it's a network call.
                # In a high-concurrency app, we should ideally use an async library for Google Sheets,
                # but for now we wrap the blocking call to minimize impact.
                return await asyncio.to_thread(operation.execute)
            except (HttpError, SocketError, ConnectionResetError, TimeoutError, Exception) as err:
                msg = str(err).lower()
                is_ssl = "ssl" in msg or "record layer failure" in msg
                is_quota = isinstance(err, HttpError) and err.resp.status == 429
                is_server_error = isinstance(err, HttpError) and err.resp.status in [500, 502, 503, 504]
                
                if is_ssl:
                    print(f"[GSHEET] SSL/Record Layer Failure detected. Re-initializing service...")
                    self._refresh_service()
                
                if attempt == retries - 1:
                    print(f"[GSHEET] Final failure after {retries} attempts: {err}")
                    raise err
                
                wait_time = 15 if is_quota else (2 ** attempt) + 1
                reason = "Quota" if is_quota else "SSL Error" if is_ssl else "Server Error" if is_server_error else "Network/Timeout"
                print(f"[GSHEET] {reason} ({err}). Attempt {attempt+1}/{retries}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
        return None

    async def get_sheet_data(self, spreadsheet_id, range_name):
        op = self.service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name)
        try:
            result = await self._execute_with_retry(op)
            return result.get('values', []) if result else []
        except Exception:
            return []

    async def update_cells(self, spreadsheet_id, range_name, values):
        body = {'values': values}
        op = self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_name,
            valueInputOption='USER_ENTERED', body=body)
        try:
            return await self._execute_with_retry(op)
        except Exception:
            return None

    async def get_all_rows(self, spreadsheet_id, sheet_name="Console"):
        """Fetches all rows from the specified sheet."""
        return await self.get_sheet_data(spreadsheet_id, f"{sheet_name}!A:Z")

    async def update_cell(self, spreadsheet_id, row, col, value, sheet_name="Console"):
        """Updates a single cell using 1-indexed row/col."""
        col_letter = chr(64 + col)
        range_name = f"{sheet_name}!{col_letter}{row}"
        return await self.update_cells(spreadsheet_id, range_name, [[value]])

    async def batch_update_cells(self, spreadsheet_id, data_batches, retries=5):
        """Updates multiple cell ranges in a single batch request with detailed logging."""
        if not data_batches: return
        
        total_cells = sum(len(b.get('values', [])) for b in data_batches)
        ranges = [b.get('range', 'unknown') for b in data_batches[:3]]
        range_str = ", ".join(ranges) + ("..." if len(data_batches) > 3 else "")
        logging.info(f"[GSHEET] Batch Update: {total_cells} cells across ranges [{range_str}]")
        
        body = {
            'valueInputOption': 'USER_ENTERED',
            'data': data_batches
        }
        op = self.service.spreadsheets().values().batchUpdate(spreadsheetId=spreadsheet_id, body=body)
        try:
            return await self._execute_with_retry(op, retries=retries)
        except Exception as err:
            logging.error(f"[GSHEET] Batch Update FAILED: {err}")
            return None

    async def apply_status_formatting(self, spreadsheet_id):
        try:
            metadata = await self._execute_with_retry(self.service.spreadsheets().get(spreadsheetId=spreadsheet_id))
            sheet_id = 0
            for s in metadata.get('sheets', []):
                if s['properties']['title'] == 'Console':
                    sheet_id = s['properties']['sheetId']
                    break

            rules = [
                ("RECONSTRUCTION READY", {"red": 0.18, "green": 0.49, "blue": 0.20}),
                ("RAW DATA SCRAPED", {"red": 0.55, "green": 0.76, "blue": 0.29}),
                ("RECONSTRUCTING", {"red": 0.0, "green": 0.74, "blue": 0.83}),
                ("OSINT SEARCH", {"red": 0.53, "green": 0.81, "blue": 0.92}),
                ("PROCESSING", {"red": 0.13, "green": 0.59, "blue": 0.95}),
                ("QUEUED", {"red": 0.88, "green": 0.88, "blue": 0.88}),
                ("DOMAIN PARKED", {"red": 1.0, "green": 0.76, "blue": 0.03}),
                ("NO DATA FOUND", {"red": 1.0, "green": 0.6, "blue": 0.0}),
                ("SYSTEM ERROR", {"red": 0.96, "green": 0.26, "blue": 0.21}),
            ]

            requests = []
            for i, (text, color) in enumerate(rules):
                requests.append({
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{"sheetId": sheet_id, "startRowIndex": 2, "endRowIndex": 5000, "startColumnIndex": 1, "endColumnIndex": 2}],
                            "booleanRule": {
                                "condition": {"type": "TEXT_STARTS_WITH", "values": [{"userEnteredValue": text}]},
                                "format": {"backgroundColor": color, "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}}}
                            }
                        },
                        "index": i
                    }
                })

            op = self.service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests})
            await self._execute_with_retry(op)
            return True
        except Exception as err:
            print(f"Formatting failed: {err}")
            return False

    async def format_professional_headers(self, spreadsheet_id, sources):
        try:
            metadata = await self._execute_with_retry(self.service.spreadsheets().get(spreadsheetId=spreadsheet_id))
            sheet_id = 0
            for s in metadata.get('sheets', []):
                if s['properties']['title'] == 'Console':
                    sheet_id = s['properties']['sheetId']
                    break

            num_sources = len(sources)
            requests = [
                {"unmergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 100}}},
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10}, "mergeType": "MERGE_ALL"}},
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 10, "endColumnIndex": 10 + num_sources}, "mergeType": "MERGE_ALL"}},
                {"mergeCells": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 10 + num_sources, "endColumnIndex": 10 + 2 * num_sources}, "mergeType": "MERGE_ALL"}},
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 10},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.06, "green": 0.31, "blue": 0.60}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                    }
                },
                # Snapshot Header
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 10, "endColumnIndex": 10 + num_sources},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.0, "green": 0.4, "blue": 0.2}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                    }
                },
                # Raw Data Header
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 10 + num_sources, "endColumnIndex": 10 + 2 * num_sources},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.26, "green": 0.26, "blue": 0.26}, "textFormat": {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True, "fontSize": 11}, "horizontalAlignment": "CENTER"}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                    }
                },
                # Subheaders
                {
                    "repeatCell": {
                        "range": {"sheetId": sheet_id, "startRowIndex": 1, "endRowIndex": 2, "startColumnIndex": 0, "endColumnIndex": 10 + 2 * num_sources},
                        "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.95, "green": 0.95, "blue": 0.95}, "textFormat": {"bold": True, "fontSize": 10}, "horizontalAlignment": "CENTER"}},
                        "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)"
                    }
                }
            ]
            op = self.service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": requests})
            await self._execute_with_retry(op)
            return True
        except Exception as err:
            if "frozen and non-frozen" in str(err):
                logging.warning("[GSHEET] Skipping professional header merge due to frozen columns in sheet.")
                return True
            print(f"Styling failed: {err}")
            return False

    async def clear_range(self, spreadsheet_id, range_name):
        op = self.service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name)
        try:
            await self._execute_with_retry(op)
        except Exception as err:
            print(f"Error clearing range: {err}")
