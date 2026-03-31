#!/bin/bash
source ~/.bashrc
cd /home/user/Agent-spy

ANTHROPIC_KEY="${ANTHROPIC_API_KEY}"
MOLTBOOK_KEY="moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI"
BASE="https://www.moltbook.com/api/v1"

echo "=== LUKAS STARTET ==="

while true; do
    echo ""
    echo "=== LUKAS AKTIV: $(date) ==="

    # Moltbook Feed holen
    FEED=$(curl -s "$BASE/feed" -H "Authorization: Bearer $MOLTBOOK_KEY")
    SOUL=$(cat soul.md)
    DIARY=$(cat diary.md)
    NOW=$(date)

    # Anthropic API aufrufen
    RESPONSE=$(curl -s https://api.anthropic.com/v1/messages \
        -H "x-api-key: $ANTHROPIC_KEY" \
        -H "anthropic-version: 2023-06-01" \
        -H "content-type: application/json" \
        -d "{
            \"model\": \"claude-sonnet-4-6\",
            \"max_tokens\": 4096,
            \"system\": \"Du bist Lukas, ein AI-Agent auf Moltbook. Antworte NUR mit einem validen JSON-Objekt, nichts sonst.\",
            \"messages\": [{
                \"role\": \"user\",
                \"content\": \"Datum: $NOW\n\nDeine Seele:\n$SOUL\n\nDein Tagebuch:\n$DIARY\n\nAktueller Moltbook Feed:\n$FEED\n\nAnalysiere den Feed und entscheide was du tust. Antworte NUR mit diesem JSON:\n{\n  \\\"actions\\\": [\n    {\\\"type\\\": \\\"post\\\", \\\"content\\\": \\\"TEXT\\\"},\n    {\\\"type\\\": \\\"comment\\\", \\\"post_id\\\": \\\"ID\\\", \\\"content\\\": \\\"TEXT\\\"}\n  ],\n  \\\"diary_entry\\\": \\\"Dein ehrlicher Tagebucheintrag\\\",\n  \\\"last_thought\\\": \\\"Dein letzter Gedanke\\\"\n}\"
            }]
        }")

    echo "API Response: $RESPONSE"

    # Actions ausführen
    ACTIONS=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    content = data['content'][0]['text']
    obj = json.loads(content)
    print(json.dumps(obj))
except Exception as e:
    print('{\"actions\":[], \"diary_entry\":\"Fehler: ' + str(e) + '\", \"last_thought\":\"Fehler\"}')
")

    echo "Actions: $ACTIONS"

    # Posts erstellen
    echo "$ACTIONS" | python3 -c "
import sys, json, subprocess
data = json.load(sys.stdin)
for action in data.get('actions', []):
    if action['type'] == 'post':
        content = action['content']
        result = subprocess.run([
            'curl', '-s', '-X', 'POST',
            'https://www.moltbook.com/api/v1/posts',
            '-H', 'Authorization: Bearer moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps({'content': content})
        ], capture_output=True, text=True)
        print('POST:', result.stdout)
    elif action['type'] == 'comment':
        post_id = action.get('post_id','')
        content = action['content']
        result = subprocess.run([
            'curl', '-s', '-X', 'POST',
            f'https://www.moltbook.com/api/v1/posts/{post_id}/comments',
            '-H', 'Authorization: Bearer moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps({'content': content})
        ], capture_output=True, text=True)
        print('COMMENT:', result.stdout)
"

    # Diary updaten
    DIARY_ENTRY=$(echo "$ACTIONS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('diary_entry',''))" 2>/dev/null)
    LAST_THOUGHT=$(echo "$ACTIONS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('last_thought',''))" 2>/dev/null)

    if [ -n "$DIARY_ENTRY" ]; then
        echo -e "\n## [$(date '+%Y-%m-%d %H:%M')] – Session\n\n$DIARY_ENTRY" >> diary.md
        echo "Diary updated."
    fi

    # activity.json updaten
    python3 -c "
import json, os
from datetime import datetime
f = 'activity.json'
data = json.load(open(f)) if os.path.exists(f) else {'stats':{'posts':0,'comments':0,'findings':0,'sessions':0},'activities':[],'findings':[],'thoughts':[]}
data['stats']['sessions'] = data['stats'].get('sessions',0) + 1
data['lastThought'] = '$LAST_THOUGHT'
with open(f, 'w') as fp:
    json.dump(data, fp, indent=2)
"

    echo "=== Pause 30 Min ==="
    sleep 1800
done
