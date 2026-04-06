#!/bin/bash
source ~/.bashrc
cd /home/user/Agent-spy

export TELEGRAM_BOT_TOKEN="8732113819:AAGTyPdaaKTux3u3gmSn0xvCS56RAMNvtJg"
export TELEGRAM_CHAT_ID="8173653416"

# Protect diary and memory from git overwrites
git config merge.ours.driver true 2>/dev/null || true

echo "=== LUKAS STARTET ==="

while true; do
    echo "=== LUKAS AKTIV: $(date) ==="
    python3 agent.py

    # Auto-sync memories to git
    git add diary.md activity.json
    git commit -m "sync: session $(date +%Y-%m-%d-%H%M)" 2>/dev/null || true
    git push origin HEAD:claude/enhance-hero-ai-animation-fqlEe 2>/dev/null || true

    echo "=== Pause 30 Min ==="
    sleep 1800
done
