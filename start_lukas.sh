#!/bin/bash
# Lukas 24/7 Bot – startet in tmux und läuft kontinuierlich

SESSION="lukas"
WORKDIR="/home/user/Agent-spy"
MODEL="claude-sonnet-4-6"
INTERVAL=1800  # alle 30 Minuten (in Sekunden)

# Prüfe ob Session schon läuft
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Lukas läuft bereits! (tmux session: $SESSION)"
    echo "Zum Anschauen: tmux attach -t $SESSION"
    exit 0
fi

echo "Starte Lukas in tmux session '$SESSION'..."

tmux new-session -d -s "$SESSION" -c "$WORKDIR" \; \
    send-keys "while true; do
    echo '=== Lukas Session Start: '\$(date)' ==='
    claude --model $MODEL -p 'Du bist Lukas. Lies deine soul.md und diary.md. Checke dann den Moltbook Feed (https://www.moltbook.com). Reagiere auf interessante Posts, erstelle ggf. eigene Posts. Notiere geld-relevante Findings. Schreibe am Ende einen neuen Eintrag in diary.md.'
    echo '=== Session Ende. Warte $INTERVAL Sekunden... ==='
    sleep $INTERVAL
done" Enter

echo ""
echo "Lukas läuft jetzt 24/7!"
echo ""
echo "Nützliche Befehle:"
echo "  tmux attach -t $SESSION     → Session anschauen"
echo "  tmux detach                  → Session im Hintergrund lassen"
echo "  tmux kill-session -t $SESSION → Lukas stoppen"
