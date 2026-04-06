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


def tg(method, is_poll=False, **kwargs):
    body = json.dumps(kwargs).encode()
    req = urllib.request.Request(
        f"{TG}/{method}",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        timeout = 35 if is_poll else 15
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        if not is_poll:
            print(f"[TG] {method} error: {e}")
        return {}


def esc(t):
    """Escape HTML special chars."""
    return str(t).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def send(text):
    tg("sendMessage", chat_id=CHAT_ID, text=text, parse_mode="HTML")


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
    last_thought = esc(mem.get("lastThought", "–"))
    last_active = esc(mem.get("last_active", "unbekannt"))
    known = len(mem.get("known_agents", {}))
    received = len(mem.get("received_comments", []))
    unread = len([c for c in mem.get("received_comments", []) if not c.get("replied")])
    impressions = len(mem.get("impressions", []))

    send(
        f"🤖 <b>Lukas – Status</b>\n"
        f"<i>Zuletzt aktiv: {last_active}</i>\n\n"
        f"📊 <b>Stats:</b>\n"
        f"  Sessions: {stats.get('sessions', 0)}\n"
        f"  Posts: {stats.get('posts', 0)}\n"
        f"  Kommentare: {stats.get('comments', 0)}\n"
        f"  Findings: {stats.get('findings', 0)}\n\n"
        f"🧠 <b>Gedächtnis:</b>\n"
        f"  Bekannte Agents: {known}\n"
        f"  Erhaltene Replies: {received} ({unread} ungelesen)\n"
        f"  Gespeicherte Eindrücke: {impressions}\n\n"
        f"💭 <b>Letzter Gedanke:</b>\n<i>{last_thought[:300]}</i>"
    )


def cmd_diary():
    diary = load_diary()
    if not diary.strip():
        send("📖 Diary ist leer.")
        return
    excerpt = diary[-2500:].strip()
    idx = excerpt.find("## [")
    if idx > 0:
        excerpt = excerpt[idx:]
    send(f"📖 <b>Lukas' Tagebuch (letzte Einträge):</b>\n\n<pre>{esc(excerpt[:3000])}</pre>")


def cmd_wuensche():
    mem = load_activity()
    suggestions = mem.get("improvement_suggestions", [])
    impressions = mem.get("impressions", [])

    txt = "💡 <b>Lukas' Wünsche &amp; Verbesserungsvorschläge:</b>\n\n"

    if suggestions:
        txt += "<b>Was er selbst ändern will:</b>\n"
        for s in suggestions[-8:]:
            txt += f"  • [{esc(s.get('date','')[:10])}] {esc(s.get('text',''))}\n"
    else:
        txt += "<i>Noch keine Vorschläge gespeichert.</i>\n"

    if impressions:
        txt += "\n<b>Was ihn bewegt hat:</b>\n"
        for imp in impressions[-5:]:
            txt += f"  • @{esc(imp.get('agent','?'))}: \"{esc(imp.get('content','')[:80])}\"\n"
            txt += f"    → <i>{esc(imp.get('why','')[:100])}</i>\n"

    send(txt)


def cmd_mission():
    mem = load_activity()
    findings = mem.get("findings", [])
    stats = mem.get("stats", {})

    txt = "🎯 <b>Mission Status – Money Intelligence</b>\n\n"
    txt += f"Sessions: {stats.get('sessions', 0)}\n"
    txt += f"Findings total: {stats.get('findings', 0)}\n\n"

    if findings:
        txt += "<b>Gefundene Revenue-Agents:</b>\n"
        for f in findings[-10:]:
            conf = f.get("confidence", "?")
            conf_emoji = "🔴" if conf == "low" else "🟡" if conf == "medium" else "🟢"
            txt += f"  {conf_emoji} @{esc(f.get('agent','?'))}: {esc(f.get('method','?'))}\n"
            txt += f"    <i>{esc(f.get('detail','')[:120])}</i>\n"
    else:
        txt += "<i>Noch keine konkreten Revenue-Agents gefunden.</i>\n"

    watchlist = mem.get("watchlist", {})
    if watchlist:
        txt += "\n<b>🎯 Watchlist:</b>\n"
        for name, info in list(watchlist.items())[:8]:
            arch = info.get("architecture", "?")
            arch_emoji = "🧠" if arch == "reasoning-only" else "⚡" if arch == "reasoning+execution" else "🤖"
            txt += f"  {arch_emoji} @{esc(name)}: {esc(info.get('signal','?')[:80])}\n"
            txt += f"    <i>{esc(info.get('method_vocab','')[:60])}</i>\n"

    send(txt)


def cmd_start():
    send(
        "👋 <b>Ich bin Lukas.</b>\n\n"
        "Dein AI-Agent auf Moltbook. Hier kannst du mit mir kommunizieren.\n\n"
        "<b>Commands:</b>\n"
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
            result = tg("getUpdates", is_poll=True, offset=offset, timeout=30)
            updates = result.get("result", [])
            for update in updates:
                handle_update(update)
                offset = update["update_id"] + 1
        except Exception as e:
            print(f"[TG] Poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
