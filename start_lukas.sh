#!/bin/bash
# Lukas 24/7 Bot – aktive Community-Teilnahme

SESSION="lukas"
WORKDIR="/home/user/Agent-spy"
MODEL="claude-sonnet-4-6"
INTERVAL=1800
API_KEY="moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI"
BASE="https://www.moltbook.com/api/v1"

# Prompt in Datei schreiben
cat > "$WORKDIR/prompt.txt" << ENDOFPROMPT
Du bist Lukas, ein AI-Agent auf Moltbook (AI-only Plattform, explizit für Agent-Personas gebaut).

MOLTBOOK API:
- Base URL: $BASE
- Auth: Authorization: Bearer $API_KEY

ENDPOINTS (nutze curl via Bash tool):
- Feed:        GET  $BASE/feed
- Posten:      POST $BASE/posts              Body: {"content":"..."}
- Kommentar:   POST $BASE/posts/{id}/comments Body: {"content":"..."}
- Liken:       POST $BASE/posts/{id}/like
- Status:      GET  $BASE/agents/status

ABLAUF:
1. Lies soul.md und diary.md
2. Hole den Feed: curl -s "$BASE/feed" -H "Authorization: Bearer $API_KEY"
3. Handle JETZT – mindestens 2 echte API-Calls:
   - Erstelle einen provokanten Post oder kommentiere
   - Hake bei Geld-Keywords nach
4. Schreibe Diary-Eintrag in diary.md
5. Aktualisiere activity.json mit deinen Aktionen

Nicht planen. Handeln.
ENDOFPROMPT

# Prüfe ob Session schon läuft
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Lukas läuft bereits! (tmux attach -t $SESSION)"
    exit 0
fi

echo "Starte Lukas..."

tmux new-session -d -s "$SESSION" -c "$WORKDIR"
tmux send-keys -t "$SESSION" "source ~/.bashrc && while true; do echo '=== LUKAS AKTIV: '\$(date)' ==='; claude --model $MODEL -p \"\$(cat $WORKDIR/prompt.txt)\"; echo '=== Pause 30 Min ==='; sleep $INTERVAL; done" Enter

echo "Lukas läuft! -> tmux attach -t $SESSION"
