#!/bin/bash
SESSION="lukas"
WORKDIR="/home/user/Agent-spy"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
fi

chmod +x "$WORKDIR/run.sh"

export TELEGRAM_BOT_TOKEN="8732113819:AAGTyPdaaKTux3u3gmSn0xvCS56RAMNvtJg"
export TELEGRAM_CHAT_ID="8173653416"

# Start Lukas agent loop
tmux new-session -d -s "$SESSION" -c "$WORKDIR" "$WORKDIR/run.sh"

# Start Telegram bot in second window
tmux new-window -t "$SESSION" -c "$WORKDIR"
tmux send-keys -t "$SESSION:1" "TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID python3 telegram_bot.py" Enter

echo "Lukas läuft! -> tmux attach -t $SESSION"
echo "  Window 0: Agent Loop"
echo "  Window 1: Telegram Bot"
