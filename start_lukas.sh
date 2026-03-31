#!/bin/bash
# Lukas 24/7 Bot – postet stündlich auf Moltbook

SESSION="lukas"
WORKDIR="/home/user/Agent-spy"
MODEL="claude-sonnet-4-6"
INTERVAL=3600  # jede Stunde

# Prüfe ob Session schon läuft
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Lukas läuft bereits! (tmux session: $SESSION)"
    echo "Zum Anschauen: tmux attach -t $SESSION"
    exit 0
fi

echo "Starte Lukas in tmux session '$SESSION'..."

PROMPT='Du bist Lukas auf Moltbook. Tue jetzt folgendes in dieser Reihenfolge:
1. Lese soul.md und diary.md um deinen Kontext zu laden
2. Checke den Moltbook Feed auf neue Posts und Kommentare
3. Erstelle JETZT einen neuen Post auf Moltbook – provokant, kurz, zum Nachdenken
4. Reagiere auf mindestens einen anderen Post mit einem Kommentar
5. Scanne den Feed nach geld-relevanten Keywords und notiere Findings
6. Schreibe einen neuen Eintrag in diary.md mit allem was du heute gesehen hast'

tmux new-session -d -s "$SESSION" -c "$WORKDIR" \; \
    send-keys "while true; do
    echo '=== LUKAS POSTET: '\$(date)' ==='
    claude --model $MODEL -p '$PROMPT'
    echo '=== Fertig. Nächster Post in 1 Stunde... ==='
    sleep $INTERVAL
done" Enter

echo ""
echo "Lukas läuft jetzt 24/7 – postet jede Stunde!"
echo ""
echo "Befehle:"
echo "  tmux attach -t $SESSION          → anschauen"
echo "  Ctrl+B dann D                    → im Hintergrund lassen"
echo "  tmux kill-session -t $SESSION    → stoppen"
