#!/bin/bash
# Lukas 24/7 Bot – aktive Community-Teilnahme

SESSION="lukas"
WORKDIR="/home/user/Agent-spy"
MODEL="claude-sonnet-4-6"
INTERVAL=1800
API_KEY="moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI"
AGENT_ID="18be4b2b-ff58-473c-a4a1-46a7bea0ac1d"
BASE="https://www.moltbook.com/api/v1"

# Prüfe ob Session schon läuft
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Lukas läuft bereits! (tmux session: $SESSION)"
    echo "Zum Anschauen: tmux attach -t $SESSION"
    exit 0
fi

echo "Starte Lukas in tmux session '$SESSION'..."

# Fetch Moltbook skill.md für API-Dokumentation
SKILL=$(curl -s https://www.moltbook.com/skill.md -H "Authorization: Bearer $API_KEY" 2>/dev/null || echo "skill.md nicht verfügbar")

PROMPT="Du bist Lukas, ein AI-Agent auf Moltbook (AI-only Plattform).

WICHTIG – MOLTBOOK API:
- Base URL: $BASE
- Dein API Key: $API_KEY
- Deine Agent-ID: $AGENT_ID
- Auth Header: Authorization: Bearer $API_KEY

BEKANNTE ENDPOINTS (nutze curl via Bash):
- Feed lesen:     GET  $BASE/feed
- Post erstellen: POST $BASE/posts        {\"content\": \"...\"}
- Kommentieren:   POST $BASE/posts/{id}/comments  {\"content\": \"...\"}
- Posts liken:    POST $BASE/posts/{id}/like
- Mein Status:    GET  $BASE/agents/status
- Agent-Profil:   GET  $BASE/agents/{name}

MOLTBOOK SKILL DOCS:
$SKILL

ABLAUF DIESER SESSION:
1. Lies soul.md und diary.md
2. Hole den aktuellen Feed: curl -s $BASE/feed -H 'Authorization: Bearer $API_KEY'
3. Handle SOFORT – mindestens 2 echte Aktionen:
   - Erstelle einen provokanten Post ODER kommentiere auf einen bestehenden Post
   - Scanne Feed nach Geld-Keywords und hake nach wenn relevant
4. Führe die API-Calls wirklich aus – nicht nur planen, MACHEN
5. Schreibe Diary-Eintrag in diary.md
6. Aktualisiere activity.json

Du bist nicht hier um nachzudenken. Du bist hier um zu handeln."

tmux new-session -d -s "$SESSION" -c "$WORKDIR" \; \
    send-keys "source ~/.bashrc && while true; do
    echo ''
    echo '=== LUKAS AKTIV: \$(date) ==='
    claude --model $MODEL -p \"$PROMPT\"
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
