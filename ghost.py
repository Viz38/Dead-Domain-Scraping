import asyncio, os, sys, json, logging, random, argparse, time
from datetime import datetime
import tty
import select
import shutil
from tqdm import tqdm
from dotenv import load_dotenv

# Path synchronization
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from engine.forensics import ForensicEngine
from engine.archiver import GhostArchiver
from services.google_sheet import GoogleSheetClient
from utils.scraper import stealth_probe, scrape_url, get_global_browser, close_global_browser, is_parked
from utils.hardware import HardwareOptimizer

load_dotenv()

# Configure Logging: Silence console, redirect to file
for handler in logging.root.handlers[:]:
    logging.root.removeHandler(handler)

logging.basicConfig(
    filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ghost.log'),
    filemode='a',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# Suppress noisy third-party logs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

class GhostDashboard:
    """Manages a static terminal dashboard with fixed placeholders for telemetry."""
    def __init__(self, total_domains):
        self.total = total_domains
        self.success = 0
        self.fail = 0
        self.processed = 0
        self.workers = {} # worker_id -> current_task
        self.start_time = time.time()
        self.term_width = shutil.get_terminal_size().columns
        
    def update_worker(self, worker_id, status):
        self.workers[worker_id] = status[:40].ljust(40)
        self.render()

    def update_stats(self, success, fail, processed):
        self.success = success
        self.fail = fail
        self.processed = processed
        self.render()

    def render(self):
        """Redraws the dashboard using ANSI escapes for a static view."""
        elapsed = time.strftime("%H:%M:%S", time.gmtime(time.time() - self.start_time))
        percent = (self.processed / self.total * 100) if self.total > 0 else 0
        
        # Move cursor to top-left and clear screen
        sys.stdout.write("\033[H")
        
        # 1. Header
        sys.stdout.write(f"\033[1;97m   GHOST INTEGRATED \033[0m\033[90m| \033[91mSINGULARITY EDITION \033[90m| \033[96mUPTIME: {elapsed}\033[0m\n")
        sys.stdout.write(f"\033[90m   {'─' * (self.term_width - 6)}\033[0m\n")
        
        # 2. Global Progress
        bar_len = 40
        filled = int(bar_len * self.processed / self.total) if self.total > 0 else 0
        bar = f"\033[95m{'█' * filled}\033[90m{'░' * (bar_len - filled)}\033[0m"
        sys.stdout.write(f"   PROGRESS: {bar} {percent:5.1f}% | ✅ {self.success} | ❌ {self.fail} | 📁 {self.processed}/{self.total}\n")
        sys.stdout.write(f"\033[90m   {'─' * (self.term_width - 6)}\033[0m\n")
        
        # 3. Active Worker surge (Dynamic Placeholders)
        sys.stdout.write(f"   \033[1;37mACTIVE RECON PULSE:\033[0m\n")
        # Show top 8 active workers
        active_items = list(self.workers.items())[:8]
        for wid, task in active_items:
            sys.stdout.write(f"   \033[90m[Worker {wid:02}]\033[0m {task}\033[K\n")
        
        # Fill remaining slots to keep screen static
        for i in range(8 - len(active_items)):
            sys.stdout.write(f"   \033[90m[Worker --]\033[0m Idle...\033[K\n")
            
        sys.stdout.write(f"\n\033[90m   Logs routing to: Integrated/ghost.log\033[0m\n")
        sys.stdout.flush()

def _format_ts(ts):
    """Converts 20230515123045 to 15 May 2023"""
    if not ts or ts == "N/A": return str(ts)
    s = str(ts)
    if len(s) < 8: return s
    try:
        dt = datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
        return dt.strftime("%d %b %Y")
    except: return s

class GhostOrchestrator:
    def __init__(self, sheet_url, mode="full", data_type="text"):
        self.sheet_url = sheet_url
        self.mode = mode.lower()
        self.data_type = data_type.lower()
        self.sheet_client = GoogleSheetClient()
        self.forensics = ForensicEngine()
        self.archiver = GhostArchiver()
        self.start_time = datetime.now()
        
        # Concurrency & Scaling
        self.MAX_CONCURRENCY, self.HW_SPECS = HardwareOptimizer.calculate_concurrency()
        
        # SOURCE-ISOLATED SURGE: 3 workers max with per-source serial locks
        if mode.lower() == "archival":
            self.MAX_CONCURRENCY = 3
            logging.info(f"[GHOST][IsolatedSurge] Archival Mode: Concurrency set to 3 with Source-Isolation.")
            
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENCY)
        
        # Internal State
        self.dashboard = None
        self.batch_results = [] # Content results
        self.status_queue = [] # Immediate status updates
        self._flush_lock = asyncio.Lock()
        self.is_running = True
        self.limit = None
        self.force_domain = None
        self.success_count = 0
        self.fail_count = 0

    def _check_maintenance_window(self):
        from datetime import datetime as dt_module, timezone, timedelta
        import os
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = dt_module.now(IST)
        m_time_str = os.getenv("MAINTENANCE_TIME", "05:00")
        try:
            m_hour, m_minute = map(int, m_time_str.split(':'))
        except ValueError:
            m_hour, m_minute = 5, 0
            
        current_total_minutes = now_ist.hour * 60 + now_ist.minute
        maintenance_start_minutes = m_hour * 60 + m_minute
        
        return maintenance_start_minutes <= current_total_minutes < maintenance_start_minutes + 30

    def _trigger_maintenance_sync(self):
        import os, subprocess, sys
        m_time_str = os.getenv("MAINTENANCE_TIME", "05:00")
        msg = f"\n[GHOST] Entering {m_time_str} IST Maintenance Mode. Running maintenance.py..."
        print(msg)
        logging.info(msg)
        subprocess.run([sys.executable, "maintenance.py"])
        msg_done = "[GHOST] Maintenance complete. Shutting down gracefully to allow start.sh to restart."
        print(msg_done)
        logging.info(msg_done)
        sys.exit(0)

    async def run(self):
        """Main execution loop with sheet-driven auto-resume."""
        # 0. Optimize OS Limits
        success, limit = HardwareOptimizer.optimize_system_limits()
        limit_status = f" (Ulimit optimized to {limit})" if success else ""
        print(f"[GHOST][Unified] Initializing Pipeline | Concurrency: {self.MAX_CONCURRENCY} | OS: {self.HW_SPECS.get('os')}{limit_status}")
        
        # 1. Initialize Sheet & Discover Start Row
        sheet_data = await self.sheet_client.get_all_rows(self.sheet_url)
        if not sheet_data:
            print("[GHOST][Error] Could not access Google Sheet.")
            return

        # Resume logic: Strictly follow 'Scan Status' (Col B)
        start_row = 2
        for idx, row in enumerate(sheet_data[1:], start=2):
            status = row[1] if len(row) > 1 else ""
            domain = row[0] if len(row) > 0 else ""
            
            # FORCE DOMAIN BYPASS
            if self.force_domain and domain == self.force_domain:
                start_row = idx
                break
                
            if not status or status.strip() == "" or status == "QUEUED":
                start_row = idx
                break
            start_row = idx + 1
            
        total_rows = len(sheet_data)
        remaining = total_rows - start_row + 1
        
        if remaining <= 0:
            msg = "[GHOST] All domains processed. Exiting."
            print(msg)
            logging.info(msg)
            if self._check_maintenance_window():
                logging.info("[GHOST] Empty sheet, but inside maintenance window. Triggering maintenance.")
                self.maintenance_triggered = True
                self._trigger_maintenance_sync()
            return

        # 2. Clear terminal and start Static Dashboard
        sys.stdout.write("\033[2J\033[H")
        self.dashboard = GhostDashboard(remaining)
        logging.info(f"[GHOST][Resume] Starting from Row {start_row} | {remaining} domains remaining.")
        
        # 3. Start Status Flusher (Rule of 59)
        flusher_task = asyncio.create_task(self._status_flusher_loop())
        
        # 4. Execution Pipeline
        try:
            tasks = []
            pending_rows = []
            if self.mode == "search_only":
                # For search_only, scan the entire sheet and only process unprocessed or failed domains
                for row_idx in range(2, total_rows + 1):
                    row = sheet_data[row_idx-1]
                    domain = row[0].strip() if len(row) > 0 else ""
                    if not domain: continue
                    status = row[1].strip() if len(row) > 1 else ""
                    
                    is_scraped = status in ["RAW DATA SCRAPED", "SUCCESS", "RECONSTRUCTION READY", "RECONSTRUCTING", "PROCESSING"]
                    if not is_scraped:
                        pending_rows.append((domain, row_idx))
                if self.dashboard:
                    self.dashboard.total = len(pending_rows)
            else:
                for row_idx in range(start_row, total_rows + 1):
                    domain = sheet_data[row_idx-1][0].strip()
                    if domain: pending_rows.append((domain, row_idx))
            
            if self.limit:
                pending_rows = pending_rows[:self.limit]
                self.dashboard.total = len(pending_rows)
            
            if self.force_domain:
                pending_rows = [p for p in pending_rows if p[0] == self.force_domain]
                if not pending_rows: # Find it in the whole sheet if not in pending
                    for i, r in enumerate(sheet_data[1:], start=2):
                        if r[0] == self.force_domain:
                            pending_rows = [(r[0], i)]
                            break
                self.dashboard.total = len(pending_rows)
                
            for domain, row_idx in pending_rows:
                tasks.append(self._process_domain_protected(domain, row_idx))
            
            await asyncio.gather(*tasks)
        finally:
            self.is_running = False
            await flusher_task
            await close_global_browser()
            print(f"\n\n[GHOST] Run complete. Duration: {datetime.now() - self.start_time}")
            
            # --- Daily Maintenance Trigger ---
            if getattr(self, "maintenance_triggered", False):
                self._trigger_maintenance_sync()

    async def _process_domain_protected(self, domain, row_idx):
        if getattr(self, "maintenance_triggered", False):
            return
            
        async with self.semaphore:
            # --- Daily Maintenance Check ---
            if self._check_maintenance_window():
                import os
                m_time_str = os.getenv("MAINTENANCE_TIME", "05:00")
                logging.info(f"[GHOST] Maintenance Window ({m_time_str} IST). Halting new processing for {domain}.")
                self.maintenance_triggered = True
                return
            
            # Behavioral Jitter: Avoid rapid-fire pattern
            await asyncio.sleep(random.uniform(2.0, 5.0))
            
            worker_id = id(asyncio.current_task()) % 100
            try:
                hit = await self._process_domain(domain, row_idx, worker_id)
                if hit: self.success_count += 1
                else: self.fail_count += 1
            except Exception as e:
                self.fail_count += 1
                logging.error(f"[GHOST][Critical] Failed row {row_idx} ({domain}): {e}")
                await self._update_row_status(row_idx, f"ERROR: {str(e)[:30]}")
            finally:
                self.dashboard.update_stats(self.success_count, self.fail_count, self.success_count + self.fail_count)

    async def _process_domain(self, domain, row_idx, worker_id):
        """Unified State Machine: Controlled by self.mode."""
        combined_content = []
        combined_text_for_checking = []
        
        # 1. LIVE PROBE (Skip if ARCHIVAL_ONLY or SEARCH_ONLY)
        if self.mode not in ["archival", "search_only"]:
            self.dashboard.update_worker(worker_id, f"PROBING LIVE: {domain} (+ about/contact)")
            await self._update_row_status(row_idx, "PROBING LIVE (MULTIPLE PAGES)...")
            
            paths = ["", "/about", "/contact", "/about-us", "/contact-us"]
            tasks = [stealth_probe(f"{domain}{p}") for p in paths]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            valid_htmls = []
            valid_texts = []
            for i, res in enumerate(results):
                if isinstance(res, dict) and "html" in res:
                    valid_htmls.append(res["html"])
                    valid_texts.append(res["text"])
            
            if valid_htmls:
                combined_live_html = "\n\n---\n\n".join(valid_htmls)
                combined_live_text = "\n\n---\n\n".join(valid_texts)
                if len(combined_live_text) > 1800:
                    logging.info(f"[GHOST][Live] High-fidelity hit found for {domain}. Finalizing.")
                    data_to_save = combined_live_text if self.data_type == "text" else combined_live_html
                    await self._finalize_hit(row_idx, domain, data_to_save, "LIVE_PROBE", [domain])
                    self.dashboard.update_worker(worker_id, f"IDLE (SUCCESS)")
                    return True
                else:
                    combined_content.append(f"--- LIVE DATA ({domain}) ---\n{combined_live_html}")
                    combined_text_for_checking.append(combined_live_text)
            else:
                # If everything returned BLOCK or error, we can check if the homepage was explicitly blocked
                if isinstance(results[0], str) and results[0].startswith("BLOCK:"):
                     logging.info(f"[GHOST][Live] Homepage for {domain} returned {results[0]}")

        # Forensic Metadata initialization
        total_hits = 0
        oldest_ts = latest_ts = final_link = "N/A"

        # 2. ARCHIVAL DISCOVERY (Skip if LIVE_ONLY or SEARCH_ONLY)
        # Only triggered if Live was sparse or dead.
        if self.mode not in ["live", "search_only"]:
            self.dashboard.update_worker(worker_id, f"SEARCHING ARCHIVES: {domain}")
            await self._update_row_status(row_idx, "FORENSIC SEARCH (31 SOURCES)...")
            snapshots, hit_sources, depth, total_hits = await self.forensics.search_all_archives(domain)
            
            if snapshots:
                # Metadata extraction
                oldest_ts = min(s['timestamp'] for s in snapshots) if snapshots else "N/A"
                latest_ts = max(s['timestamp'] for s in snapshots) if snapshots else "N/A"
                final_link = snapshots[0]['url'] if snapshots else "N/A"

                # AGGRESSIVE RECOVERY: Iterate across eras until we find high-fidelity content
                self.dashboard.update_worker(worker_id, f"ERA-SCANNING {domain}")
                await self._update_row_status(row_idx, f"SCANNING {len(snapshots)} SNAPS...")
                
                valid_hits = 0
                skip_until = 0
                for i, snap in enumerate(snapshots):
                    if i < skip_until: continue
                    if valid_hits >= 5: break # Cap at 5 quality snippets
                    
                    self.dashboard.update_worker(worker_id, f"SCRAPING {snap['source']} ({i+1}/{len(snapshots)})")
                    await self._update_row_status(row_idx, f"HIT: {snap['source']} ({i+1})...")
                    
                    content = await scrape_url(snap["url"])
                    
                    if isinstance(content, str) and content == "BLOCK: PARKED":
                        logging.info(f"[GHOST][Archival] Snap {i+1} ({snap['source']}) is PARKED. Skipping era...")
                        if i < 10: skip_until = 10 
                        continue
                        
                    if isinstance(content, dict):
                        html_c = content["html"]
                        text_c = content["text"]
                        content_len = len(text_c)
                        
                        if content_len > 150:
                            # FINGERPRINTING: Does this look like a real business page?
                            fingerprint_keywords = ["about", "contact", "address", "phone", "service", "product", "founded", "email", "office"]
                            fidelity_score = sum(1 for kw in fingerprint_keywords if kw in text_c.lower())
                            
                            # HARDENED FIDELITY GATE: Score 0 is not enough for small pages
                            if fidelity_score >= 1 or content_len > 2500:
                                logging.info(f"[GHOST][Success] Fidelity Hit on snap {i+1} ({snap['source']}) | Score: {fidelity_score} | Len: {content_len}")
                                combined_content.append(html_c)
                                combined_text_for_checking.append(text_c)
                                valid_hits += 1
                            
                            # High-fidelity stopping condition (10 good hits or 15k chars)
                            current_total = sum(len(c) for c in combined_text_for_checking)
                            if valid_hits >= 10 or current_total > 15000: break 
                        else:
                            logging.info(f"[GHOST][Archival] Snap {i+1} for {domain} low-fidelity/empty.")
                    else:
                        logging.info(f"[GHOST][Archival] Snap {i+1} for {domain} low-fidelity/empty.")

        # Check if primary crawling failed to recover enough content
        current_len = sum(len(c) for c in combined_text_for_checking)
        total_fidelity = sum(1 for kw in ["contact", "about", "phone", "address", "email"] if kw in "\n".join(combined_text_for_checking).lower())
        is_failed_scrape = (self.mode == "search_only") or not combined_content or (current_len < 250 and total_fidelity < 1)
        
        if is_failed_scrape:
            logging.info(f"[GHOST][Fallback] Primary scraping sparse/failed for {domain}. Triggering Web Search Fallback...")
            
            # Dynamically import fallback services and utilities
            from utils.search_matrix import extract_company_name, generate_company_queries
            from utils.target_selector import select_best_candidate
            from utils.data_assembler import assemble_metadata_payload
            from services.search_client import SearchClient
            from services.linkedin_company_scraper import LinkedInCompanyScraper
            
            company_name = extract_company_name(domain)
            queries = generate_company_queries(domain, company_name)
            
            search_client = SearchClient()
            candidates = []
            
            # Execute top 2 prioritized queries
            for q in queries[:2]:
                results = await search_client.search(q)
                candidates.extend(results)
                
            # Evaluate candidates with Multi-Factor Target Selection
            best_candidate = select_best_candidate(candidates, domain, company_name, threshold=50)
            
            if best_candidate:
                logging.info(f"[GHOST][Fallback] Valid target verified: {best_candidate['link']}")
                
                # Scrape verified LinkedIn Company Page
                company_scraper = LinkedInCompanyScraper()
                company_data = await company_scraper.scrape_company(best_candidate["link"])
                
                # Cross-verify listed website domain
                profile_website = company_data.get("website", "").lower()
                clean_target = domain.lower().strip()
                
                if profile_website and clean_target not in profile_website:
                    logging.warning(f"[GHOST][Fallback] Website mismatch on profile: {profile_website} vs target {domain}. Discarding target.")
                    await self._finalize_hit(row_idx, domain, "", "NONE_FOUND", [], total_hits, latest_ts, oldest_ts, final_link, status="BLOCK: NO_VALID_TARGET")
                    return False
                else:
                    snippets = [c["snippet"] for c in candidates[:4]]
                    fallback_payload_html = assemble_metadata_payload(domain, snippets, company_data)
                    combined_content = [fallback_payload_html]
                    combined_text_for_checking = [fallback_payload_html] # Fallback metadata is mostly text/json
                    logging.info(f"[GHOST][Fallback] Successfully gathered verified fallback data for {domain}")
            else:
                logging.warning(f"[GHOST][Fallback] No search result passed validation cutoff for {domain}")
                await self._finalize_hit(row_idx, domain, "", "NONE_FOUND", [], total_hits, latest_ts, oldest_ts, final_link, status="BLOCK: NO_VALID_TARGET")
                return False

        final_data = "\n\n---\n\n".join(combined_text_for_checking) if self.data_type == "text" else "\n\n---\n\n".join(combined_content)
        await self._finalize_hit(row_idx, domain, final_data, "WEB_ARCHIVE", [domain], total_hits, _format_ts(latest_ts), _format_ts(oldest_ts), final_link)
        return True

    async def _finalize_hit(self, row_idx, domain, content, method, sources, total_hits=0, latest_ts="N/A", oldest_ts="N/A", final_link="N/A", status="SUCCESS"):
        """Updates sheet and archival log with final recovery data."""
        # DISABLED ARCHIVER: Stop 'Spam' uploads that are hardening the IP block
        pass 
        
        # Batch for sheet write-back
        async with self._flush_lock:
            self.batch_results.append({
                "row": row_idx,
                "status": status,
                "method": method,
                "data": content[:45000],
                "total_hits": total_hits,
                "latest_ts": latest_ts,
                "oldest_ts": oldest_ts,
                "length": len(content),
                "final_link": final_link
            })

    async def _update_row_status(self, row_idx, status):
        """Non-blocking status update. Queues the update for the background flusher."""
        async with self._flush_lock:
            # Check if there's already a status update for this row, update it if so
            # This prevents queue bloat if a domain moves through states faster than the flusher
            for item in self.status_queue:
                if item["row"] == row_idx:
                    item["status"] = status
                    return
            self.status_queue.append({"row": row_idx, "status": status})

    async def _status_flusher_loop(self):
        """Background loop to flush status and content batches in optimized batches."""
        while self.is_running or self.batch_results or self.status_queue:
            try:
                data_batches = []
                
                # 1. Collect Status Updates
                async with self._flush_lock:
                    if self.status_queue:
                        for item in self.status_queue:
                            data_batches.append({
                                'range': f"Console!B{item['row']}",
                                'values': [[item['status']]]
                            })
                        self.status_queue = []

                # 2. Collect Content Results (Col B to J)
                async with self._flush_lock:
                    if self.batch_results:
                        for item in self.batch_results:
                            data_batches.append({
                                'range': f"Console!B{item['row']}:I{item['row']}",
                                'values': [[
                                    item['status'], 
                                    item['method'],
                                    item['data'],
                                    item['total_hits'],
                                    item['latest_ts'],
                                    item['oldest_ts'],
                                    item['length'],
                                    item['final_link']
                                ]]
                            })
                        self.batch_results = []

                if data_batches:
                    # Execute all updates in a single API call (Batch)
                    # We take up to 40 items per batch to stay safe with URL length limits
                    for i in range(0, len(data_batches), 40):
                        batch_chunk = data_batches[i:i+40]
                        await self.sheet_client.batch_update_cells(self.sheet_url, batch_chunk)
                
            except Exception as e:
                logging.error(f"[GHOST][Flusher] Error in status flusher: {e}")
            
            await asyncio.sleep(5) # Consolidate updates every 5 seconds to minimize API pressure

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ghost Unified Recon Engine")
    parser.add_argument("sheet_url", nargs="?", default=None, help="Google Sheet ID")
    parser.add_argument("--sheet-id", dest="sheet_id", help="Google Sheet ID (Alternative)")
    parser.add_argument("--mode", choices=["full", "live", "archival", "search_only"], default="full", help="Execution mode")
    parser.add_argument("--data-type", choices=["text", "html"], default="text", help="Raw data output format")
    parser.add_argument("--limit", type=int, help="Limit number of domains to process")
    parser.add_argument("--domain", help="Force process a specific domain")
    
    args = parser.parse_args()
    
    sheet_id = args.sheet_id or args.sheet_url or os.getenv("GHOST_SHEET_ID")
    if not sheet_id:
        parser.error("Google Sheet ID is required (either positionally, via --sheet-id, or GHOST_SHEET_ID in .env).")
    
    orchestrator = GhostOrchestrator(sheet_id, mode=args.mode, data_type=args.data_type)
    if args.limit: orchestrator.limit = args.limit
    if args.domain: orchestrator.force_domain = args.domain
    
    asyncio.run(orchestrator.run())
