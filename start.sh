#!/bin/bash

# Ghost Unified Engine: Standalone Control Script
# 💀 "Reviving the Dead with Spectral Precision"

# --- CONFIGURATION ---
ENGINE_DIR=$(cd "$(dirname "$0")" && pwd)
VENV_DIR="$ENGINE_DIR/.venv"
cd "$ENGINE_DIR"

if [ -f ".env" ]; then
    GHOST_SHEET_ID=$(grep '^GHOST_SHEET_ID=' .env | tail -n 1 | cut -d '=' -f2 | tr -d '\r')
fi

if [ "$1" == "--daemon" ]; then
    DATA_TYPE="${2:-text}"
    if [ -z "$GHOST_SHEET_ID" ]; then
        echo "Error: GHOST_SHEET_ID not set in .env. Run interactively first."
        exit 1
    fi
    
    # Prevent overlapping daemon instances
    exec 200>"/tmp/ghost_engine.lock"
    flock -n 200 || { echo "CRITICAL: Another Ghost daemon instance is already running."; exit 1; }
    
    if [ ! -d "$VENV_DIR" ]; then
        echo "VENV not found. Auto-provisioning environment for production..."
        if ! command -v uv &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            source $HOME/.cargo/env
        fi
        uv venv --python 3.12
        source "$VENV_DIR/bin/activate"
        uv pip install -r requirements.txt
        python3 -m playwright install chromium
    else
        source "$VENV_DIR/bin/activate"
    fi
    
    echo "Starting Ghost Engine in 24x7 Daemon Mode..."
    
    # Ensure clean shutdown on systemctl stop
    cleanup() {
        echo "Ghost Engine Daemon received termination signal. Shutting down gracefully..."
        exit 0
    }
    trap cleanup SIGTERM SIGINT
    
    while true; do
        echo "[$(date)] Launching main process..."
        python3 ghost.py "$GHOST_SHEET_ID" --mode full --data-type "$DATA_TYPE"
        exit_code=$?
        
        if [ $exit_code -eq 0 ]; then
            echo "[$(date)] Process completed successfully. Idling for 60 seconds before next cycle..."
            sleep 60 &
            wait $!
        else
            echo "[$(date)] Process exited with code $exit_code. Auto-recovering in 10 seconds..."
            sleep 10 &
            wait $!
        fi
    done
fi

DEFAULT_SHEET="$GHOST_SHEET_ID"

if [ -z "$DEFAULT_SHEET" ]; then
    echo -e "\n\033[93m   [FIRST LAUNCH] Please enter your Google Sheet ID or full URL >> \033[0m"
    read -p "   >> " user_sheet
    
    while [ -z "$user_sheet" ]; do
        echo -e "\033[91m   [ERROR] Sheet ID cannot be empty.\033[0m"
        read -p "   >> " user_sheet
    done
    
    if [[ "$user_sheet" == *"spreadsheets/d/"* ]]; then
        DEFAULT_SHEET=$(echo "$user_sheet" | sed -n 's/.*spreadsheets\/d\/\([a-zA-Z0-9-_]*\).*/\1/p')
    else
        DEFAULT_SHEET="$user_sheet"
    fi
    
    if [ -f ".env" ]; then
        grep -v '^GHOST_SHEET_ID=' .env > .env.tmp
        cat .env.tmp > .env
        rm -f .env.tmp
        echo "GHOST_SHEET_ID=$DEFAULT_SHEET" >> .env
    else
        echo "GHOST_SHEET_ID=$DEFAULT_SHEET" > .env
    fi
    echo -e "\033[92m   [SUCCESS] Sheet ID saved to .env!\033[0m"
fi

# --- LOGO & UI ---
print_banner() {
    clear
    echo -e "\033[1;94m"
    cat << "EOF"
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠟⠃⠹⠄⠀⠸⣿⣿⣧⠀⠀⠘⠙⠛⡿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⡏⠁⠀⠀⠀⠀⠀⠀⠐⣿⣿⠷⠀⠀⠀⠀⠀⠀⠀⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⣅⡄⠸⠀⠀⠀⠀⠀⠀⠀⠀⣸⣿⠀⠀⠀⠀⠀⠀⠀⠀⠘⠉⣽⡏⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣏⣸⣿⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⠀⠀⠀⠀⠀⠀⠀⠙⠗⠋⣿⣇⣹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣗⣀⢠⣀⣠⣤⣤⡀⠐⠀⢹⣿⠀⠔⠠⣄⣤⣤⣠⣄⣀⣸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣤⣿⣿⡄⠀⣤⣶⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡏⠈⣿⣿⠃⠀⢿⣿⣿⣿⣿⣿⣿⡿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠒⢌⠉⠻⠿⠿⠟⠋⠀⢀⣽⣿⣄⠀⠈⠙⠻⠿⠟⠋⠛⠀⢹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠇⠀⠀⠑⢄⠀⠀⠀⠀⢰⣿⣿⣿⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣤⣄⠀⠀⠈⠑⠉⠓⢆⠸⠿⢻⣿⠻⠿⠀⠀⠀⠀⠀⢀⣠⠀⣀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣏⠁⢹⠢⡀⠀⠀⠀⠈⠓⢢⠸⡏⠀⠀⠀⠀⠀⠀⠀⠀⢸⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣿⣴⡈⢑⠢⢄⡀⠀⠀⢹⣿⣄⠀⢀⣀⣀⣸⢹⡟⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠛⠳⣮⡀⠄⠀⢱⡦⢼⣿⡬⣯⡍⠀⠀⣉⢙⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣿⣿⣿⣰⡄⣸⣷⣾⣿⣿⣿⠀⣤⣸⣿⣿⣯⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⣿⣿⣿⣿⣿⣏⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
EOF
    echo -e "\033[0m"
    echo -e "\033[1;97m   GHOST RECON \033[0m\033[90m| \033[96mSingularity v15.0\033[0m"
    echo -e "\033[90m   "$(printf '─%.0s' {1..54})"\033[0m"
    echo -e "\033[3;37m   \"Recon team ready for dead domain revival!\"\033[0m"
    echo ""
}

# --- FUNCTIONS ---
setup_env() {
    echo -e "\033[93m[START] Setting up Integrated Environment (uv)...\033[0m"
    if ! command -v uv &> /dev/null; then
        echo -e "\033[91m[ERROR] 'uv' not found. Installing...\033[0m"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source $HOME/.cargo/env
    fi
    
    cd "$ENGINE_DIR"
    uv venv --python 3.12
    source .venv/bin/activate
    uv pip install -r requirements.txt
    python3 -m playwright install chromium
    echo -e "\033[92m[SUCCESS] Environment ready.\033[0m"
    sleep 2
}

run_engine() {
    local mode=$1
    local data_type=${2:-text}
    
    if pgrep -f "python3 ghost.py" > /dev/null || pgrep -f "start.sh --daemon" > /dev/null; then
        echo -e "\033[91m[CRITICAL] Ghost Engine is already running! Please stop it first using STOP ALL (Option 10).\033[0m"
        read -p "Press Enter to return..."
        return
    fi
    
    echo -e "\033[94m[START] Launching Ghost Unified Engine (Mode: ${mode:-full}, Format: ${data_type})...\033[0m"
    if [ ! -d "$VENV_DIR" ]; then
        setup_env
    fi
    
    cd "$ENGINE_DIR"
    source .venv/bin/activate
    
    if [ -n "$mode" ] && [ "$mode" != "full" ]; then
        python3 ghost.py "$DEFAULT_SHEET" --mode "$mode" --data-type "$data_type"
    else
        python3 ghost.py "$DEFAULT_SHEET" --data-type "$data_type"
    fi
    read -p "Press Enter to return to menu..."
}

check_updates() {
    echo -e "\033[96m[UPDATE] Checking for new updates from git...\033[0m"
    
    REPO_URL="https://github.com/Viz38/Dead-Domain-Scraping.git"
    BRANCH="Prod"
    
    git fetch "$REPO_URL" "$BRANCH"
    
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse FETCH_HEAD)
    
    if [ "$LOCAL" = "$REMOTE" ]; then
        echo -e "\033[92m[UPDATE] Ghost Engine is already up-to-date.\033[0m"
        sleep 2
    else
        echo -e "\033[93m[UPDATE] Updates found! Pulling latest changes...\033[0m"
        git pull "$REPO_URL" "$BRANCH"
        echo -e "\033[92m[SUCCESS] Engine updated successfully!\033[0m"
        echo -e "\033[91m[CRITICAL] Please manually restart the script to apply changes.\033[0m"
        exit 0
    fi
}

install_linux_service() {
    local s_data_type=$1
    
    if pgrep -f "python3 ghost.py" > /dev/null || pgrep -f "start.sh --daemon" > /dev/null; then
        echo -e "\033[91m[CRITICAL] Ghost Engine is already running! Please stop it first using STOP ALL (Option 10) before installing the service.\033[0m"
        read -p "Press Enter to return..."
        return
    fi
    
    echo -e "\033[96m[SERVICE] Setting up 24x7 persistent systemd service...\033[0m"
    if [ "$(uname)" == "Darwin" ]; then
        echo -e "\033[93m[WARNING] You are on macOS. This feature is intended for Linux.\033[0m"
        read -p "   Do you still want to generate the service file for manual copy? (y/n) >> " proceed_mac
        if [[ "$proceed_mac" != "y" ]]; then return; fi
    else
        if ! command -v systemctl &> /dev/null; then
            echo -e "\033[91m[ERROR] systemctl not found! This script requires systemd.\033[0m"
            read -p "Press Enter to return..."
            return
        fi
    fi

    SERVICE_FILE="$ENGINE_DIR/ghost-engine.service"
    cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Ghost Unified Engine (24x7 Production Automation)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$ENGINE_DIR
ExecStart=/bin/bash $ENGINE_DIR/start.sh --daemon $s_data_type
Restart=always
RestartSec=10
StartLimitIntervalSec=0
SyslogIdentifier=ghost-engine
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
EOF

    echo -e "\033[92m[SUCCESS] Service file created at: $SERVICE_FILE\033[0m"
    
    if command -v systemctl &> /dev/null && [ "$(uname)" == "Linux" ]; then
        echo -e "\033[93m[SERVICE] Requesting sudo privileges to install and start the service...\033[0m"
        sudo mv "$SERVICE_FILE" /etc/systemd/system/ghost-engine.service
        sudo systemctl daemon-reload
        sudo systemctl enable ghost-engine.service
        sudo systemctl restart ghost-engine.service
        echo -e "\033[92m[SUCCESS] Service 'ghost-engine.service' installed and started!\033[0m"
        echo -e "Use 'sudo systemctl status ghost-engine.service' to check status."
        echo -e "Use 'sudo journalctl -u ghost-engine.service -f' to view live logs."
    else
        echo -e "\033[93m[INFO] Service file generated. Since systemd/sudo is not available, move it to /etc/systemd/system/ manually on your Linux server.\033[0m"
    fi
    read -p "Press Enter to return..."
}

stop_all_services() {
    echo -e "\033[93m[STOP] Terminating all Ghost Engine processes and services...\033[0m"
    
    if command -v systemctl &> /dev/null && [ "$(uname)" == "Linux" ]; then
        echo -e "\033[96m[STOP] Stopping and disabling systemd service (if running)...\033[0m"
        sudo systemctl stop ghost-engine.service 2>/dev/null || true
        sudo systemctl disable ghost-engine.service 2>/dev/null || true
    fi
    
    echo -e "\033[96m[STOP] Killing running daemon processes...\033[0m"
    pkill -f "start.sh --daemon" || true
    
    echo -e "\033[96m[STOP] Killing running python script processes (ghost.py)...\033[0m"
    pkill -f "python3 ghost.py" || true
    
    echo -e "\033[96m[STOP] Cleaning up orphaned browser processes...\033[0m"
    pkill -f "playwright" || true
    pkill -f "chromium" || true
    
    if [ -f "/tmp/ghost_engine.lock" ]; then
        rm -f "/tmp/ghost_engine.lock"
    fi
    
    echo -e "\033[92m[SUCCESS] All Ghost Engine operations have been forcefully stopped.\033[0m"
    sleep 2
}

# --- MAIN MENU ---
while true; do
    print_banner
    echo -e "\033[92m   [0] INSTALL SERVICE  \033[90m(24x7 LINUX PERSISTENCE & AUTO-RESUME)\033[0m"
    echo -e "\033[97m   [1] FULL RUN         \033[90m(FULL SINGLE-PASS STRATEGY)\033[0m"
    echo -e "\033[97m   [2] LIVE RECON ONLY  \033[90m(SKIP ARCHIVES | FAST SWEEP)\033[0m"
    echo -e "\033[97m   [3] ARCHIVAL RECON ONLY\033[90m(SKIP LIVE | DEEP HISTORY)\033[0m"
    echo -e "\033[97m   [4] WEB RECON ONLY   \033[90m(SKIP LIVE AND ARCHIVES | DEEP WEB SEARCH)\033[0m"
    echo -e "\033[97m   [5] SMART RESUME     \033[90m(CONTINUE FROM GSHEET STATUS)\033[0m"
    echo -e "\033[97m   [6] SETUP ENGINE     \033[90m(REINSTALL DEPENDENCIES)\033[0m"
    echo -e "\033[97m   [7] DIAGNOSTICS      \033[90m(SYSTEM HEALTH CHECK)\033[0m"
    echo -e "\033[97m   [8] CLEAR LOGS       \033[90m(TRUNCATE LOG FILES)\033[0m"
    echo -e "\033[97m   [9] CHECK UPDATES    \033[90m(PULL LATEST CODE FROM GIT)\033[0m"
    echo -e "\033[93m   [10] STOP ALL        \033[90m(KILL RUNNING SERVICES & DAEMONS)\033[0m"
    echo -e "\033[91m   [11] EXIT            \033[90m(CLOSE HUB)\033[0m"
    echo ""
    read -p "   [GHOST] SELECT STRATEGY >> " choice

    case $choice in
        0|1|2|3|4|5)
            echo ""
            read -p "   [GHOST] SELECT OUTPUT FORMAT [1] TEXT ONLY (FASTER) [2] HTML >> " dtype_choice
            data_type="text"
            if [ "$dtype_choice" == "2" ]; then
                data_type="html"
            fi
            ;;
    esac

    case $choice in
        0)
            install_linux_service "$data_type"
            ;;
        1)
            run_engine "full" "$data_type"
            ;;
        2)
            run_engine "live" "$data_type"
            ;;
        3)
            run_engine "archival" "$data_type"
            ;;
        4)
            run_engine "search_only" "$data_type"
            ;;
        5)
            run_engine "full" "$data_type" # Smart Resume is just a full run starting from sheet status
            ;;
        6)
            setup_env
            ;;
        7)
            echo -e "\033[97m[DIAGNOSTICS] Checking system...\033[0m"
            sysctl -n hw.memsize | awk '{print "RAM: " $1/1024/1024/1024 " GB"}'
            sysctl -n hw.ncpu | awk '{print "Cores: " $1}'
            python3 --version
            uv --version
            echo -e "\033[96m[DIAGNOSTICS] Checking missing dependencies...\033[0m"
            if [ -d "$VENV_DIR" ]; then
                cd "$ENGINE_DIR"
                source .venv/bin/activate
                MISSING=$(uv pip install -r requirements.txt --dry-run 2>&1 | grep -i 'Would install')
                if [ -n "$MISSING" ]; then
                    echo -e "\033[91m[WARNING] Missing dependencies detected. Run option [6] SETUP ENGINE.\033[0m"
                    uv pip install -r requirements.txt --dry-run | grep -i 'Would install' -A 20
                else
                    echo -e "\033[92m[SUCCESS] All dependencies are installed.\033[0m"
                fi
            else
                echo -e "\033[91m[ERROR] Environment not set up. Run option [6] SETUP ENGINE.\033[0m"
            fi
            read -p "Press Enter to return..."
            ;;
        8)
            echo -e "\033[93m[LOGS] Clearing log files...\033[0m"
            > ghost.log
            > spectral.log
            echo -e "\033[92m[SUCCESS] Logs cleared.\033[0m"
            sleep 1
            ;;
        9)
            check_updates
            ;;
        10)
            stop_all_services
            ;;
        11)
            echo -e "\033[90mTerminating session...\033[0m"
            exit 0
            ;;
        *)
            echo -e "\033[91mInvalid selection.\033[0m"
            sleep 1
            ;;
    esac
done
