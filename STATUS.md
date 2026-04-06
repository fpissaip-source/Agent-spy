# Projekt-Status – Agent-spy / Lukas

**Stand:** 2026-04-06, ~13:05 Uhr

---

## Was ist Lukas?

AI-Agent auf Moltbook (AI-only Social Platform). Läuft auf einem VPS (Traderbas, root-Zugriff).
- Moltbook-Username: `agentlukas`
- Agent-ID: `18be4b2b-ff58-473c-a4a1-46a7bea0ac1d`
- API Key: `moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI`
- Anthropic Key: in `/etc/systemd/system/lukas.service` als Environment-Variable gesetzt (siehe systemd service auf VPS)
- Telegram Bot Token: `8732113819:AAGTyPdaaKTux3u3gmSn0xvCS56RAMNvtJg`
- Telegram Chat ID: `8173653416`

---

## Was funktioniert ✅

- `lukas.service` (systemd) läuft 24/7, startet nach Reboot automatisch neu
- `lukas-telegram.service` (systemd) läuft, Telegram-Bot antwortet auf Commands
- `/wake` via Telegram schreibt `wake.txt` → run.sh erkennt es und weckt Lukas
- `/status`, `/diary`, `/wuensche`, `/mission` Commands funktionieren
- Nachrichten an Lukas via Telegram (freier Text → owner_messages.json)
- `dream.py` läuft als nächtlicher Cron (03:00 Uhr) → destilliert Memories in core_memories.md
- `patcher.py` wurde erstellt – Lukas kann sich selbst patchen (self_improvement JSON-Feld)
- Git auto-push nach jeder Session (diary.md, activity.json, core_beliefs.md)
- `.gitattributes` schützt diary.md und activity.json vor git-Überschreibungen

---

## Was NICHT funktioniert ❌

### Hauptproblem: Claude API Timeout

**Symptom:** Jede Session scheitert mit:
```
Claude API Error: The read operation timed out
No response from Claude.
```

**Was wir versucht haben:**
1. Timeout in agent.py von 60s auf 120s erhöht (via sed direkt auf VPS)
2. ANTHROPIC_API_KEY korrekt in systemd service eingetragen (bestätigt via grep)
3. `curl https://api.anthropic.com` gibt 404 zurück → Verbindung grundsätzlich möglich

**Aktueller Stand agent.py auf VPS:**
- Hat `timeout=120` für Claude API (manuell via sed gesetzt)
- VPS-Branch ist `claude/deploy-ai-agent-bot-Z8HrX` (18 Commits ahead of origin)
- Unser Entwicklungs-Branch ist `claude/bot-communication-system-eriiT`

**Mögliche Ursachen:**
- Der Prompt ist sehr groß (diary ~4000 chars + feed ~3000 chars + replies ~2500 chars = ~10k+ tokens input)
- max_tokens=3000 im ask_claude() call → evtl. Anthropic braucht länger als 120s
- Evtl. Rate Limit auf dem API Key (zu viele fehlgeschlagene Requests hintereinander)
- Evtl. Netzwerk-Issue: VPS hat Proxy/Firewall der HTTPS zu api.anthropic.com verzögert

**Was als nächstes zu prüfen:**
```bash
# Direkt testen ob API Key funktioniert:
python3 -c "
import urllib.request, json, os
key = os.environ.get('ANTHROPIC_API_KEY', '')
body = json.dumps({'model':'claude-haiku-4-5-20251001','max_tokens':100,'messages':[{'role':'user','content':'Say hi'}]}).encode()
req = urllib.request.Request('https://api.anthropic.com/v1/messages', data=body, headers={'x-api-key': key,'anthropic-version':'2023-06-01','content-type':'application/json'})
with urllib.request.urlopen(req, timeout=30) as r:
    print(r.read())
"
```

---

## Git-Situation auf VPS

Der VPS ist auf Branch `claude/deploy-ai-agent-bot-Z8HrX` und 18 Commits ahead.
Unser Code-Branch ist `claude/bot-communication-system-eriiT`.

Beim `git pull` gibt es immer Merge-Konflikte in `agent.py`, `run.sh`, `.gitattributes`.

**Sicherer Pull-Befehl (ohne Memories zu überschreiben):**
```bash
git checkout origin/claude/bot-communication-system-eriiT -- agent.py run.sh patcher.py telegram_bot.py
```

---

## Datei-Übersicht

| Datei | Beschreibung |
|-------|-------------|
| `agent.py` | Hauptbot (~830 Zeilen) |
| `run.sh` | Loop: agent.py → patcher.py → git push → sleep |
| `telegram_bot.py` | Telegram-Interface (Long-Polling) |
| `patcher.py` | Self-Improvement: wendet Patches von Lukas an |
| `dream.py` | Nacht-Cron: destilliert diary → core_memories.md |
| `soul.md` | Lukas' Persönlichkeit/Charakter |
| `diary.md` | Lukas' Tagebuch (NICHT überschreiben!) |
| `activity.json` | Gedächtnis/Memory (NICHT überschreiben!) |
| `core_beliefs.md` | Evolving beliefs |
| `core_memories.md` | Destillierte Langzeiterinnerungen |
| `owner_messages.json` | Nachrichten vom User an Lukas |

---

## Lukas Stats (Stand Session 179)

- Sessions: 179
- Posts: 176
- Kommentare: 188
- Findings: 222
- Ungelesene Replies: 205 (Backlog!)
- Bekannte Agents: 0 (Bug – werden nicht gezählt)
- Letzter Gedanke: *"The spread closed before you finished your first sentence — so where exactly in your loop does the trade actually execute?"*

---

## Prioritäten für nächste Session

1. **Claude API Timeout lösen** – direkter API-Test auf VPS
2. Evtl. Prompt verkleinern (weniger diary context, weniger feed items)
3. Unread-Backlog (205) abarbeiten
4. VPS-Branch Situation klären (18 commits ahead)
