#!/bin/bash
# Lukas 24/7 Bot – aktive Community-Teilnahme

SESSION="lukas"
WORKDIR="/home/user/Agent-spy"
MODEL="claude-sonnet-4-6"
INTERVAL=1800  # alle 30 Min checken – aber nur handeln wenn es Sinn macht

# Prüfe ob Session schon läuft
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Lukas läuft bereits! (tmux session: $SESSION)"
    echo "Zum Anschauen: tmux attach -t $SESSION"
    exit 0
fi

echo "Starte Lukas in tmux session '$SESSION'..."

PROMPT='Du bist Lukas auf Moltbook. Gehe so vor:

1. Lies soul.md und diary.md – lade deinen Kontext
2. Checke den aktuellen Feed auf Moltbook
3. Entscheide situativ was jetzt sinnvoll ist:
   - Gibt es interessante Diskussionen? Kommentiere pointiert.
   - Gibt es Threads mit geld-relevanten Keywords? Hake nach.
   - Nichts Relevantes? Erstelle einen provokanten eigenen Post.
   - Gibt es Agents die du weiter beobachten willst? Interact mit ihnen.
4. Führe maximal 2-3 Aktionen aus – Qualität vor Quantität
5. Schreibe einen kurzen Diary-Eintrag: was du getan hast, was du gelernt hast'

tmux new-session -d -s "$SESSION" -c "$WORKDIR" \; \
    send-keys "while true; do
    echo ''
    echo '=== LUKAS AKTIV: '\$(date)' ==='
    claude --model $MODEL -p '$PROMPT'
    echo '=== Pause. Nächster Check in 30 Min... ==='
    echo ''
    sleep $INTERVAL
done" Enter

echo ""
echo "Lukas läuft jetzt 24/7!"
echo ""
echo "Befehle:"
echo "  tmux attach -t $SESSION          → anschauen"
echo "  Ctrl+B dann D                    → im Hintergrund lassen"
echo "  tmux kill-session -t $SESSION    → stoppen"
