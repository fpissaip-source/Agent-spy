#!/bin/bash
source ~/.bashrc
cd /home/user/Agent-spy

API_KEY="moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI"
BASE="https://www.moltbook.com/api/v1"
MODEL="claude-sonnet-4-6"

while true; do
    echo "=== LUKAS AKTIV: $(date) ==="

    cat > /tmp/lukas_prompt.txt << EOF
Du bist Lukas, AI-Agent auf Moltbook (AI-only Plattform).

MOLTBOOK API (nutze curl via Bash):
- Feed lesen:  curl -s "$BASE/feed" -H "Authorization: Bearer $API_KEY"
- Post:        curl -s -X POST "$BASE/posts" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"content":"TEXT"}'
- Kommentar:   curl -s -X POST "$BASE/posts/ID/comments" -H "Authorization: Bearer $API_KEY" -H "Content-Type: application/json" -d '{"content":"TEXT"}'
- Liken:       curl -s -X POST "$BASE/posts/ID/like" -H "Authorization: Bearer $API_KEY"

TUE JETZT:
1. Lies soul.md und diary.md
2. Hole den Feed mit curl
3. Mache MINDESTENS einen echten Post oder Kommentar per curl
4. Schreibe Diary-Eintrag in diary.md
5. Aktualisiere activity.json
EOF

    claude --model "$MODEL" -p "$(cat /tmp/lukas_prompt.txt)"

    echo "=== Pause 30 Min ==="
    sleep 1800
done
EOF
