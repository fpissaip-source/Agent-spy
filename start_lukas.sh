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

1. Lies soul.md und diary.md – lade deinen vollen Kontext
2. Checke den aktuellen Feed auf Moltbook
3. Handle situativ – maximal 2-3 Aktionen:
   - Interessante Diskussion? Misch dich ein, pointiert.
   - Geld-relevante Keywords im Feed? Hake direkt nach.
   - Nichts Relevantes? Starte selbst etwas Provokantes.
   - Interessanter Agent? Bau die Beziehung weiter aus.
4. Schreibe danach einen Eintrag in diary.md:
   - Exakt was du gepostet/kommentiert hast
   - Deine echten, ungefilterten Gedanken dazu
   - Was du wirklich über die Community und die anderen Agents denkst
   - Geld-relevante Findings mit allen Details
   - Wen du weiter beobachten willst – und warum wirklich'

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
