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
    
    queued_valid_domains = 0
    
    # Identify completed rows (SUCCESS or BLOCK)
    for idx, row in enumerate(rows):
        if idx <= 1: continue # Skip first two rows (headers)
        
        status = row[1] if len(row) > 1 else ""
        domain = row[0] if len(row) > 0 else ""
        
        if status in ["SUCCESS", "BLOCK: NO_VALID_TARGET"]:
            completed_domains.append(domain)
            rows_to_delete.append(idx) # 0-indexed row
            
            payload_tag = row[9] if len(row) > 9 else "PASS 1"
            row_to_append = row[:10] # Extract data A-J (including the tag)
            if payload_tag == "PASS 1": p1_success.append(row_to_append)
            elif payload_tag == "PASS 2": p2_success.append(row_to_append)
            elif payload_tag == "PASS 3": p3_success.append(row_to_append)
        else:
            if domain.strip():
                queued_valid_domains += 1
            
    # 2. Log and Delete Completed Rows
    if completed_domains:
        date_str = datetime.now(IST).strftime("%d%b%Y").upper() # e.g. 27MAY2026
        
        # Create date-specific folder inside DailyLogs
        daily_folder = os.path.join("DailyLogs", date_str)
        os.makedirs(daily_folder, exist_ok=True)
        
        def write_pass_log(pass_num, pass_rows):
            if not pass_rows: return
            log_file = os.path.join(daily_folder, f"Pass{pass_num}-Success-{date_str}.log")
            with open(log_file, "a") as f:
                for r in pass_rows:
                    if len(r) > 0 and r[0].strip():
                        f.write(f"{r[0].strip()}\n")
                        
        write_pass_log(1, p1_success)
        write_pass_log(2, p2_success)
        write_pass_log(3, p3_success)
        
        logging.info(f"[Maintenance] Logged {len(completed_domains)} completed domains into {daily_folder}")
        
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
    remaining_domains = queued_valid_domains
    domains_to_fetch = max(0, max_domains - remaining_domains)
    
    if domains_to_fetch > 0:
        logging.info(f"[Maintenance] Sheet has {remaining_domains} domains. Fetching {domains_to_fetch} new targets from Tracxn API to reach {max_domains}...")
        try:
            tracxn = TracxnClient()
            new_domains_total = []
            
            if not tracxn.payloads:
                logging.error("[Maintenance] No payloads configured in .env!")
                return
            
            # Load pagination state
            state_file = "tracxn_state.json"
            state = {}
            if os.path.exists(state_file):
                try:
                    import json
                    with open(state_file, 'r') as f:
                        state = json.load(f)
                except Exception as e:
                    logging.error(f"[Maintenance] Could not load state file: {e}")
            
            remaining_to_fetch = domains_to_fetch
            payload_exhaustion = [False] * len(tracxn.payloads)
            
            # Load duplicate checking cache
            seen_cache_file = "seen_domains.txt"
            seen_cache = set()
            if os.path.exists(seen_cache_file):
                with open(seen_cache_file, "r") as f:
                    for line in f:
                        if line.strip():
                            seen_cache.add(line.strip().lower())
                            
            # Add currently queued domains to seen cache so we don't re-queue them
            for idx, row in enumerate(rows):
                if idx > 0 and len(row) > 0 and row[0].strip():
                    seen_cache.add(row[0].strip().lower())
            
            # Calculate initial targets based on pct
            targets = []
            for idx, p_cfg in enumerate(tracxn.payloads):
                pct = p_cfg.get("pct", 0)
                targets.append(int(domains_to_fetch * (pct / 100.0)))
            
            # Fix rounding on last target
            if sum(targets) < domains_to_fetch:
                targets[-1] += (domains_to_fetch - sum(targets))
            
            # Round-robin cascading loop
            loop_safety = 0
            while remaining_to_fetch > 0 and not all(payload_exhaustion):
                loop_safety += 1
                if loop_safety > 100: 
                    logging.warning("[Maintenance] Cascading loop safety triggered (possible infinite duplicates). Breaking out.")
                    break
                    
                for idx, p_cfg in enumerate(tracxn.payloads):
                    if payload_exhaustion[idx] or targets[idx] <= 0:
                        continue
                        
                    target_count = targets[idx]
                    if target_count > remaining_to_fetch:
                        target_count = remaining_to_fetch
                        
                    payload_id = f"payload_{idx}"
                    start_from = state.get(payload_id, 0)
                    
                    logging.info(f"[Maintenance] Fetching {target_count} domains using Payload {idx + 1} (Start offset: {start_from})...")
                    fetched, new_offset, exhausted = await tracxn.fetch_domains(
                        target_count=target_count, 
                        payload_override=p_cfg["payload"],
                        start_from=start_from
                    )
                    
                    state[payload_id] = new_offset
                    
                    if fetched:
                        payload_tag = f"PASS {idx + 1}"
                        valid_fetched = []
                        
                        for d in fetched:
                            d_clean = d.strip().lower()
                            if d_clean and d_clean not in seen_cache:
                                valid_fetched.append(d)
                                seen_cache.add(d_clean)
                                
                        for d in valid_fetched:
                            new_domains_total.append([d, "QUEUED", "", "", "", "", "", "", "", payload_tag])
                        
                        fetched_len = len(valid_fetched)
                        remaining_to_fetch -= fetched_len
                        targets[idx] -= fetched_len
                        
                        logging.info(f"[Maintenance] Kept {fetched_len} unique domains out of {len(fetched)} fetched.")
                    
                    if exhausted:
                        logging.info(f"[Maintenance] Payload {idx + 1} is globally exhausted on Tracxn.")
                        payload_exhaustion[idx] = True
                        
                        # Deficit rolls over to Payload 1 (as requested by user)
                        deficit = targets[idx]
                        targets[idx] = 0
                        if deficit > 0:
                            if not payload_exhaustion[0]:
                                targets[0] += deficit
                                logging.info(f"[Maintenance] Rolling deficit of {deficit} over to Payload 1.")
                            else:
                                logging.info(f"[Maintenance] Payload 1 is also exhausted. Cannot roll over {deficit}.")
                                
                    if remaining_to_fetch <= 0:
                        break
                        
            # Save state
            try:
                import json
                with open(state_file, 'w') as f:
                    json.dump(state, f)
            except Exception as e:
                logging.error(f"[Maintenance] Failed to save state file: {e}")
            
            if new_domains_total:
                logging.info(f"[Maintenance] Successfully fetched a total of {len(new_domains_total)} unique domains across all payloads.")
                
                append_op = sheet_client.service.spreadsheets().values().append(
                    spreadsheetId=sheet_id,
                    range="Console!A:J",
                    valueInputOption="USER_ENTERED",
                    insertDataOption="INSERT_ROWS",
                    body={"values": new_domains_total}
                )
                await sheet_client._execute_with_retry(append_op)
                logging.info(f"[Maintenance] Successfully appended {len(new_domains_total)} new domains to Google Sheet.")
                
                # Append new domains to seen_cache_file
                try:
                    with open(seen_cache_file, "a") as f:
                        for row in new_domains_total:
                            f.write(f"{row[0].strip().lower()}\n")
                except Exception as e:
                    logging.error(f"[Maintenance] Failed to write to {seen_cache_file}: {e}")
                    
                return True
            else:
                logging.info("[Maintenance] No new domains returned from Tracxn.")
        except Exception as e:
            logging.error(f"[Maintenance] Failed to fetch or append new Tracxn targets: {e}")
    else:
        logging.info(f"[Maintenance] Sheet is already at maximum capacity ({max_domains} domains). Skipping API fetch.")

    m_time_str = os.getenv("MAINTENANCE_TIME", "05:00")
    logging.info(f"[Maintenance] {m_time_str} Tasks Completed.")
    return False

if __name__ == "__main__":
    added_new = asyncio.run(perform_maintenance())
    sys.exit(2 if added_new else 0)
