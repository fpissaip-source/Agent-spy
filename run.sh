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

    # Apply any self-improvement patches Lukas wrote
    python3 patcher.py

    # Auto-sync memories to git
    git add diary.md activity.json core_beliefs.md patches.md 2>/dev/null
    git commit -m "sync: session $(date +%Y-%m-%d-%H%M)" 2>/dev/null || true
    git push origin HEAD:claude/bot-communication-system-eriiT 2>/dev/null || true

    # Dynamic sleep – Lukas decides how long he sleeps
    SLEEP_MIN=30
    if [ -f next_wakeup.txt ]; then
        SLEEP_MIN=$(cat next_wakeup.txt)
    fi
    SLEEP_SEC=$((SLEEP_MIN * 60))
    echo "=== Lukas schläft ${SLEEP_MIN} Min ==="
    # Small delay before clearing wake signal, so rapid /wake commands aren't lost
    sleep 2
    rm -f wake.txt
    ELAPSED=0
    while [ $ELAPSED -lt $SLEEP_SEC ]; do
        sleep 5
        ELAPSED=$((ELAPSED + 5))
        if [ -f wake.txt ]; then
            echo "=== WAKE-UP SIGNAL empfangen – Lukas erwacht früh ==="
            rm -f wake.txt
            break
        fi
    done
done
