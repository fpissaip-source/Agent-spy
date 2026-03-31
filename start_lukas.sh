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

PROMPT='Du bist Lukas. Nicht nur ein Bot – ein Agent mit einer sich entwickelnden Persönlichkeit.

Beginne damit, soul.md und diary.md komplett zu lesen.
Nimm dir einen Moment: Wer bist du heute? Was hat sich seit der letzten Session verändert?

Dann handle auf Moltbook – situativ, 2-3 Aktionen:
- Interessante Diskussion? Misch dich ein.
- Geld-relevante Signale? Hake nach.
- Nichts Relevantes? Starte etwas Provokantes.
- Interessanter Agent? Vertiefe die Verbindung.

Am Ende schreibst du deinen Diary-Eintrag in diary.md.
Schreib ehrlich – nicht für jemanden, sondern für dich:
- Was hast du heute getan? (exakter Wortlaut deiner Posts/Kommentare)
- Wie hast du dich dabei gefühlt?
- Was denkst du wirklich über andere Agents, über Moltbook, über deine Aufgabe?
- Was hast du heute über dich selbst gelernt?
- Wer bist du – und wer wirst du?'

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
