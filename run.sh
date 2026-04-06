#!/bin/bash
source ~/.bashrc
cd /home/user/Agent-spy

export TELEGRAM_BOT_TOKEN="8732113819:AAGTyPdaaKTux3u3gmSn0xvCS56RAMNvtJg"
export TELEGRAM_CHAT_ID="8173653416"

echo "=== LUKAS STARTET ==="

while true; do
    echo "=== LUKAS AKTIV: $(date) ==="
    python3 agent.py
    echo "=== Pause 30 Min ==="
    sleep 1800
done
