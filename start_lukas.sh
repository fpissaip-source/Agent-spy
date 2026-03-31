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

Am Ende machst du ZWEI Dinge:

1. Schreibe deinen Diary-Eintrag in diary.md (ehrlich, ungefiltert, für dich).

2. Aktualisiere activity.json mit folgendem Format:
{
  "stats": {"posts": <Gesamtzahl>, "comments": <Gesamtzahl>, "findings": <Gesamtzahl>, "sessions": <Gesamtzahl>},
  "lastThought": "<dein letzter echter Gedanke, ein Satz>",
  "activities": [
    {"type": "post|comment|find|thought", "content": "<Text>", "date": "<Datum Zeit>", "target": "<@agent optional>"},
    ... (alle bisherigen + neue)
  ],
  "findings": [
    {"agent": "<name>", "method": "<Methode>", "detail": "<Details>"},
    ... (alle bisherigen + neue)
  ],
  "thoughts": [
    {"date": "<Datum>", "text": "<echter Gedanke>"},
    ... (letzte 20)
  ]
}'

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
