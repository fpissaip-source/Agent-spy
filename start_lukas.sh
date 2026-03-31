#!/bin/bash
SESSION="lukas"
WORKDIR="/home/user/Agent-spy"

if tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux kill-session -t "$SESSION"
fi

chmod +x "$WORKDIR/run.sh"
tmux new-session -d -s "$SESSION" -c "$WORKDIR" "$WORKDIR/run.sh"
echo "Lukas läuft! -> tmux attach -t $SESSION"
