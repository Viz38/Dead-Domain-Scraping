# 💀 TRACXN GHOST RECON | Unified Spectral Engine

> **"One Pass. Total Recovery. Singularity Architecture."**

Ghost v15.0 is a unified, high-fidelity digital forensics and reconnaissance pipeline. It consolidates the fragmented P1/P2 architectures into a single "Singularity" engine that dynamically escalates from live stealth probes to deep forensic recovery in a single pass.

---

## 🚀 Unified Singularity Engine

This engine is the pinnacle of the Ghost project, combining blitz-tier speed with deep forensic depth.

### 🧬 Era-Synchronized Stitching & Forensic Scoring
- **Parallel Recovery**: Automatically identifies and scrapes `/about`, `/team`, and `/product` pages in parallel.
- **Temporal Consistency**: Ensures all sub-pages are synced to the same historical "Golden Era" for 100% semantic accuracy.
- **Era-Aware Forensic Scoring Algorithm**: The engine actively combats "Snapshot Rot" and parked domains by parsing specific metadata from the Wayback Machine's CDX API:
  - **Vibrancy Scoring (`timestamp` + `length`)**: Snapshots are grouped by year. Years with a high frequency of large-sized captures receive massive multiplier bonuses, identifying a defunct startup's "Operational Peak".
  - **Aggressive Deduplication (`digest`)**: Uses cryptographic SHA-1 hashes of the historical DOM to silently drop identical crawls (e.g., when IA crawls a parked page 500 times), saving downstream compute.
  - **Root Prioritization (`is_root`)**: Homepages (URLs with a depth <= 2) receive a flat `+250` point boost to ensure authoritative company summaries surface to the top.
  - **Parked Domain Penalization**: Modern snapshots (>= 2022) with very low byte counts (< 5000 bytes) are heavily penalized (`-300` points) to automatically discard domain squatter "For Sale" pages that obscure real history.
- **Stealth CDX Extraction**: Bypasses rate limits and blocks by chunking requests into three historical eras (1995-2005, 2006-2015, 2016-2026), filtering server-side (`statuscode:200|301|302`), appending `id_` to fetch raw DOMs without archive UI wrappers, and enforcing strict asynchronous rate-limiting (1.5s lock) per source.

### 🔄 5 AM Daily Maintenance Engine
Ghost incorporates a fully autonomous 5 AM IST daily maintenance loop designed to seamlessly clean and replenish the processing sheet without corrupting active workers.
- **Graceful Halt**: At 5 AM, new tasks are paused while active tasks finish naturally.
- **Auto-Deletion & Logging**: Completed domains (`SUCCESS` and `BLOCK`) are logged into `DailyLogs/Processed-DDMMMYYYY.log` and then completely batch deleted (in reverse order) from the Google Sheet to prevent index shifting.
- **Multi-Payload Re-Filling**: Ghost automatically calculates `MAX_DOMAINS_IN_SHEET - pending_domains` to find how many domains are needed to refill the sheet. It then dynamically fetches exactly that amount from the Tracxn API using **three different payload distributions** (configured in `.env` as `Pass1Limit`, `Pass2Limit`, and `Pass3Limit`) and appends them with a `QUEUED` status.
- **Auto-Recovery**: The `start.sh` daemon detects the clean completion of maintenance and loops a fresh instance of `ghost.py` automatically.

### 🛡 Advanced Stealth Suite
- **Camoufox Native**: Full hardware fingerprint randomization (Canvas, WebGL, Audio, Fonts).
- **Accessibility Tree Heuristics**: Detects sophisticated parking pages that visually mimic real sites.
- **TLS/JA3 Impersonation**: Mimics real browser handshakes to bypass network-layer fingerprinting.

---

## 🏛 Ghost Forensic Archive Network (GFAN)

Ghost v15.0 utilizes a globally distributed network of **31 archival nodes** to overcome "Archive Bias" and "Snapshot Rot".

### 🏛 The Core Four (Blitz Layer)
| Source | Strengths | Reasoning |
| :--- | :--- | :--- |
| **Wayback Machine (IA)** | Massive scale (800B+ pages). | The global baseline for all web history. |
| **CommonCrawl** | Raw crawl data (20+ indices). | Captures data missed by IA due to different crawler rules. |
| **Archive.is/ph/today** | Human-triggered snapshots. | Bypasses `robots.txt` and captures user-validated content. |
| **URLScan.io** | Real-time DOM snapshots. | Captures transient redirects and recent "Live" states. |

### 🧬 Specialized Forensic Nodes (Deep Tier)
Ghost escalates discovery to specialized regional and academic archives:
- **Regional Strongholds**: Arquivo.pt (EU), WARP (Japan), OASIS (Korea), PANDORA (Australia).
- **Academic Libraries**: Stanford, UT Austin, Library of Congress.
- **Integrity Nodes**: Perma.cc, PageFreezer, WebRecorder, IA Catalog (PDF/Press recovery).

---

## 🚦 Getting Started

### Prerequisites
- Python 3.12+
- `uv` (Fastest Python package manager)
- Google Sheet Credentials (`credentials.json`)

### Quick Start & Orchestrator
The Ghost engine is entirely managed through a single interactive shell script. This acts as the main orchestrator, handling environment setup, dependencies (`uv`), and providing a full interactive menu for executing all recon modes.

Run the interactive orchestrator:
```bash
./start.sh
```

**Available Interactive Modes:**
- `[1] FULL RUN`: Full Single-Pass Strategy (Live + Archival + Web Search)
- `[2] LIVE RECON ONLY`: Fast live sweep, skips archives
- `[3] ARCHIVAL RECON ONLY`: Deep historical search, skips live
- `[4] WEB RECON ONLY`: Deep Web Search fallback, skips live/archives
- `[5] SMART RESUME`: Continues from the Google Sheet "Scan Status"
- `[6] SETUP ENGINE`: Reinstall dependencies automatically via `uv`
- `[7] DIAGNOSTICS`: System Health Check (RAM, CPU)
- `[8] CLEAR LOGS`: Truncate log files
- `[9] CHECK UPDATES`: Pulls latest engine code from git
- `[10] EXIT`: Close Hub
