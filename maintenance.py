import os
import sys
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from services.google_sheet import GoogleSheetClient
from services.tracxn_client import TracxnClient

# Load env variables
load_dotenv()

# Ensure logging appends to ghost.log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("ghost.log"),
        logging.StreamHandler()
    ]
)
IST = timezone(timedelta(hours=5, minutes=30))

async def perform_maintenance():
    m_time_str = os.getenv("MAINTENANCE_TIME", "05:00")
    logging.info(f"[Maintenance] Starting {m_time_str} IST Daily Maintenance Tasks...")
    
    sheet_id = os.getenv("GHOST_SHEET_ID")
    if not sheet_id:
        logging.error("[Maintenance] GHOST_SHEET_ID not found in environment.")
        return

    sheet_client = GoogleSheetClient()
    
    # 1. Fetch current rows
    rows = await sheet_client.get_all_rows(sheet_id)
    if not rows:
        logging.error("[Maintenance] Could not fetch rows from Google Sheet.")
        return
        
    rows_to_delete = [] # list of 0-indexed row numbers (for deletion API)
    completed_domains = []
    
    p1_success = []
    p2_success = []
    p3_success = []
    
    # Identify completed rows (SUCCESS or BLOCK)
    for idx, row in enumerate(rows):
        if idx == 0: continue # Skip Header
        
        status = row[1] if len(row) > 1 else ""
        domain = row[0] if len(row) > 0 else ""
        
        if status in ["SUCCESS", "BLOCK: NO_VALID_TARGET"]:
            completed_domains.append(domain)
            rows_to_delete.append(idx) # 0-indexed row
            
            if status == "SUCCESS":
                payload_tag = row[9] if len(row) > 9 else "PASS 1"
                row_to_append = row[:9] # Extract pure data A-I, dropping the tag
                if payload_tag == "PASS 1": p1_success.append(row_to_append)
                elif payload_tag == "PASS 2": p2_success.append(row_to_append)
                elif payload_tag == "PASS 3": p3_success.append(row_to_append)
            
    # 2. Log and Delete Completed Rows
    if completed_domains:
        # Create DailyLogs directory
        os.makedirs("DailyLogs", exist_ok=True)
        date_str = datetime.now(IST).strftime("%d%b%Y").upper() # e.g. 27MAY2026
        log_file = f"DailyLogs/Processed-{date_str}.log"
        
        with open(log_file, "a") as f:
            for d in completed_domains:
                if d.strip():
                    f.write(f"{d}\n")
        logging.info(f"[Maintenance] Logged {len(completed_domains)} completed domains to {log_file}")
        
        # Fetch the internal sheetId for the "Console" sheet
        try:
            metadata = await sheet_client._execute_with_retry(sheet_client.service.spreadsheets().get(spreadsheetId=sheet_id))
            console_sheet_id = None
            for s in metadata.get('sheets', []):
                if s['properties']['title'] == 'Console':
                    console_sheet_id = s['properties']['sheetId']
                    break
            
            if console_sheet_id is not None:
                # Distribute Success Cases to designated Payload Sheets
                async def append_success(rows_to_add, env_key):
                    if not rows_to_add: return
                    target_id = os.getenv(env_key)
                    if not target_id: return
                    try:
                        op = sheet_client.service.spreadsheets().values().append(
                            spreadsheetId=target_id,
                            range="A3",
                            valueInputOption="USER_ENTERED",
                            insertDataOption="INSERT_ROWS",
                            body={"values": rows_to_add}
                        )
                        await sheet_client._execute_with_retry(op)
                        logging.info(f"[Maintenance] Appended {len(rows_to_add)} SUCCESS rows to {env_key}.")
                    except Exception as e:
                        logging.error(f"[Maintenance] Failed to append to {env_key}: {e}")

                await append_success(p1_success, "SUCCESS_SHEET_P1_ID")
                await append_success(p2_success, "SUCCESS_SHEET_P2_ID")
                await append_success(p3_success, "SUCCESS_SHEET_P3_ID")

                requests = []
                # Sort in reverse to avoid shifting issues during deletion
                for row_idx in sorted(rows_to_delete, reverse=True):
                    requests.append({
                        "deleteDimension": {
                            "range": {
                                "sheetId": console_sheet_id,
                                "dimension": "ROWS",
                                "startIndex": row_idx,
                                "endIndex": row_idx + 1
                            }
                        }
                    })
                
                if requests:
                    op = sheet_client.service.spreadsheets().batchUpdate(
                        spreadsheetId=sheet_id, 
                        body={"requests": requests}
                    )
                    await sheet_client._execute_with_retry(op)
                    logging.info(f"[Maintenance] Successfully deleted {len(requests)} completed rows from Google Sheet.")
        except Exception as e:
            logging.error(f"[Maintenance] Error deleting rows from sheet: {e}")
    else:
        logging.info("[Maintenance] No completed domains found. Skipping deletion.")

    # 3. Fetch New Domains from Tracxn and Append
    max_domains = int(os.getenv("MAX_DOMAINS_IN_SHEET", 6000))
    remaining_domains = len(rows) - 1 - len(rows_to_delete)
    domains_to_fetch = max(0, max_domains - remaining_domains)
    
    if domains_to_fetch > 0:
        logging.info(f"[Maintenance] Sheet has {remaining_domains} domains. Fetching {domains_to_fetch} new targets from Tracxn API to reach {max_domains}...")
        try:
            tracxn = TracxnClient()
            new_domains_total = []
            
            if tracxn.payloads:
                for idx, p_cfg in enumerate(tracxn.payloads):
                    pct = p_cfg.get("pct", 0)
                    target_count = int(domains_to_fetch * (pct / 100.0))
                    
                    # On the last payload, if there are rounding errors, ensure we hit the exact target
                    if idx == len(tracxn.payloads) - 1:
                        target_count = domains_to_fetch - len(new_domains_total)
                        
                    if target_count <= 0:
                        continue
                        
                    logging.info(f"[Maintenance] Fetching {target_count} domains using Payload {idx + 1} ({pct}%)...")
                    fetched = await tracxn.fetch_domains(limit=target_count, payload_override=p_cfg["payload"])
                    if fetched:
                        payload_tag = f"PASS {idx + 1}"
                        for d in fetched:
                            new_domains_total.append([d, "QUEUED", "", "", "", "", "", "", "", payload_tag])
            else:
                logging.error("[Maintenance] No payloads configured in .env!")
            
            if new_domains_total:
                logging.info(f"[Maintenance] Successfully fetched a total of {len(new_domains_total)} domains across all payloads.")
                
                append_op = sheet_client.service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range="Console!A:J",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": new_domains_total}
                )
                await sheet_client._execute_with_retry(append_op)
                logging.info(f"[Maintenance] Successfully appended {len(new_domains_total)} new domains to Google Sheet.")
            else:
                logging.info("[Maintenance] No new domains returned from Tracxn.")
        except Exception as e:
            logging.error(f"[Maintenance] Failed to fetch or append new Tracxn targets: {e}")
    else:
        logging.info(f"[Maintenance] Sheet is already at maximum capacity ({max_domains} domains). Skipping API fetch.")

    m_time_str = os.getenv("MAINTENANCE_TIME", "05:00")
    logging.info(f"[Maintenance] {m_time_str} Tasks Completed.")

if __name__ == "__main__":
    asyncio.run(perform_maintenance())
