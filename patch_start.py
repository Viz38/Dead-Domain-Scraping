import re
import os

start_file = os.path.join(os.getcwd(), 'start.sh')
with open(start_file, 'r') as f:
    content = f.read()

# Insert log_echo function safely
parts = content.split('if [ -f ".env" ]; then\n    GHOST_SHEET_ID=$(grep \'^GHOST_SHEET_ID=\' .env | tail -n 1 | cut -d \'=\' -f2 | tr -d \'\\r\')\nfi\n')
if len(parts) == 2:
    log_func = """
log_echo() {
    echo -e "$@"
    echo -e "$@" | sed 's/\\x1b\\[[0-9;]*[a-zA-Z]//g' >> "$ENGINE_DIR/ghost.log"
}
"""
    content = parts[0] + 'if [ -f ".env" ]; then\n    GHOST_SHEET_ID=$(grep \'^GHOST_SHEET_ID=\' .env | tail -n 1 | cut -d \'=\' -f2 | tr -d \'\\r\')\nfi\n' + log_func + parts[1]

# Replace 'echo' and 'echo -e' with 'log_echo' safely
content = re.sub(r'echo -e "(\\033\[9[123456]m\[.*?)"', r'log_echo "\1"', content)
content = re.sub(r'echo -e "(\\033\[97m\[.*?)"', r'log_echo "\1"', content)
content = re.sub(r'echo "Starting Ghost Engine.*?Daemon Mode..."', r'log_echo "Starting Ghost Engine in 24x7 Daemon Mode..."', content)
content = re.sub(r'echo "\[\$\(date\)\].*?"', lambda m: m.group(0).replace('echo', 'log_echo'), content)
content = re.sub(r'echo "Error: GHOST_SHEET_ID not set.*?"', r'log_echo "Error: GHOST_SHEET_ID not set in .env. Run interactively first."', content)

with open(start_file, 'w') as f:
    f.write(content)
