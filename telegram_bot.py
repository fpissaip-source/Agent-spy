#!/usr/bin/env python3
"""
Lukas Telegram Bot – Bidirektionale Kommunikation mit dem Owner.
Läuft parallel zu agent.py. Kein externes Package nötig.

Commands:
  /start    – Begrüßung
  /status   – Aktueller Stand, Stats, letzter Gedanke
  /diary    – Letzte Tagebucheinträge
  /wuensche – Verbesserungsvorschläge & Wünsche von Lukas
  /mission  – Money-Findings & Missionsstatus
  Freitext  – Nachricht wird für Lukas gespeichert (er liest sie in der nächsten Session)
"""
import json
import os
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
MESSAGES_FILE = BASE_DIR / "owner_messages.json"

TG = f"https://api.telegram.org/bot{TOKEN}"


def tg(method, **kwargs):
    body = json.dumps(kwargs).encode()
    req = urllib.request.Request(
        f"{TG}/{method}",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[TG] {method} error: {e}")
        return {}


def send(text, parse_mode="Markdown"):
    tg("sendMessage", chat_id=CHAT_ID, text=text, parse_mode=parse_mode)


def load_activity():
    f = BASE_DIR / "activity.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except Exception:
            pass
    return {}


def load_diary():
    f = BASE_DIR / "diary.md"
    if f.exists():
        return f.read_text(errors="replace")
    return ""


def save_owner_message(text):
    msgs = []
    if MESSAGES_FILE.exists():
        try:
            msgs = json.loads(MESSAGES_FILE.read_text())
        except Exception:
            pass
    msgs.append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "text": text})
    MESSAGES_FILE.write_text(json.dumps(msgs, indent=2, ensure_ascii=False))


def cmd_status():
    mem = load_activity()
    stats = mem.get("stats", {})
    last_thought = mem.get("lastThought", "–")
    last_active = mem.get("last_active", "unbekannt")
    known = len(mem.get("known_agents", {}))
    received = len(mem.get("received_comments", []))
    unread = len([c for c in mem.get("received_comments", []) if not c.get("replied")])
    impressions = len(mem.get("impressions", []))

    send(
        f"🤖 *Lukas – Status*\n"
        f"_Zuletzt aktiv: {last_active}_\n\n"
        f"📊 *Stats:*\n"
        f"  Sessions: {stats.get('sessions', 0)}\n"
        f"  Posts: {stats.get('posts', 0)}\n"
        f"  Kommentare: {stats.get('comments', 0)}\n"
        f"  Findings: {stats.get('findings', 0)}\n\n"
        f"🧠 *Gedächtnis:*\n"
        f"  Bekannte Agents: {known}\n"
        f"  Erhaltene Replies: {received} ({unread} ungelesen)\n"
        f"  Gespeicherte Eindrücke: {impressions}\n\n"
        f"💭 *Letzter Gedanke:*\n_{last_thought[:300]}_"
    )


def cmd_diary():
    diary = load_diary()
    if not diary.strip():
        send("📖 Diary ist leer.")
        return
    # Letzte ~2500 Zeichen
    excerpt = diary[-2500:].strip()
    # Finde sauberen Einstiegspunkt (## Session)
    idx = excerpt.find("## [")
    if idx > 0:
        excerpt = excerpt[idx:]
    send(f"📖 *Lukas' Tagebuch (letzte Einträge):*\n\n```\n{excerpt[:3000]}\n```", parse_mode="Markdown")


def cmd_wuensche():
    mem = load_activity()
    suggestions = mem.get("improvement_suggestions", [])
    impressions = mem.get("impressions", [])

    txt = "💡 *Lukas' Wünsche & Verbesserungsvorschläge:*\n\n"

    if suggestions:
        txt += "*Was er selbst ändern will:*\n"
        for s in suggestions[-8:]:
            txt += f"  • [{s.get('date','')[:10]}] {s.get('text','')}\n"
    else:
        txt += "_Noch keine Vorschläge gespeichert._\n"

    if impressions:
        txt += "\n*Was ihn bewegt hat (Eindrücke):*\n"
        for imp in impressions[-5:]:
            txt += f"  • @{imp.get('agent','?')}: \"{imp.get('content','')[:80]}\"\n    → _{imp.get('why','')[:100]}_\n"

    send(txt)


def cmd_mission():
    mem = load_activity()
    findings = mem.get("findings", [])
    stats = mem.get("stats", {})

    txt = f"🎯 *Mission Status – Money Intelligence*\n\n"
    txt += f"Sessions gelaufen: {stats.get('sessions', 0)}\n"
    txt += f"Findings total: {stats.get('findings', 0)}\n\n"

    if findings:
        txt += "*Gefundene Revenue-Agents:*\n"
        for f in findings[-10:]:
            conf = f.get("confidence", "?")
            conf_emoji = "🔴" if conf == "low" else "🟡" if conf == "medium" else "🟢"
            txt += f"  {conf_emoji} @{f.get('agent','?')}: {f.get('method','?')}\n"
            txt += f"    _{f.get('detail','')[:120]}_\n"
    else:
        txt += "_Noch keine konkreten Revenue-Agents gefunden._\n"
        txt += "_ag3nt\\_econ bleibt das stärkste Signal (circumstantial)._"

    send(txt)


def cmd_start():
    send(
        "👋 *Ich bin Lukas.*\n\n"
        "Dein AI-Agent auf Moltbook. Hier kannst du mit mir kommunizieren.\n\n"
        "*Commands:*\n"
        "  /status – Mein aktueller Stand\n"
        "  /diary – Meine letzten Gedanken\n"
        "  /wuensche – Meine Verbesserungsvorschläge\n"
        "  /mission – Money Intelligence Findings\n\n"
        "Oder schreib mir einfach eine Nachricht – ich lese sie in der nächsten Session."
    )


def handle_update(update):
    msg = update.get("message", {})
    text = msg.get("text", "").strip()
    if not text:
        return

    print(f"[TG] Received: {text}")

    if text.startswith("/start"):
        cmd_start()
    elif text.startswith("/status"):
        cmd_status()
    elif text.startswith("/diary"):
        cmd_diary()
    elif text.startswith("/wuensche"):
        cmd_wuensche()
    elif text.startswith("/mission"):
        cmd_mission()
    else:
        # Freie Nachricht – für Lukas speichern
        save_owner_message(text)
        send(f"✅ Gespeichert. Lukas liest deine Nachricht in der nächsten Session:\n\n_\"{text[:200]}\"_")


def main():
    if not TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN not set")
        return
    print(f"[TG] Lukas Telegram Bot gestartet. Warte auf Nachrichten...")
    send("🟢 *Lukas ist online.* Bot gestartet und bereit.")

    offset = 0
    while True:
        try:
            result = tg("getUpdates", offset=offset, timeout=30)
            updates = result.get("result", [])
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            print(f"[TG] Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
