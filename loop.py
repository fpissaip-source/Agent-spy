#!/usr/bin/env python3
"""
loop.py — Lukas Always-On Event Loop
=====================================
Runs as a permanent process on the VPS. Manages three concerns:

  Sensor  – Polls Telegram every 2 s; handles /ask, /status, /wake, /stop
  Thinker – Decides when to run the next agent session (reads next_wakeup.txt)
  Actor   – Spawns agent.py as a subprocess; then patcher.py if patches queued

Usage:
  python3 loop.py                     # run directly
  nohup bash run_loop.sh &            # run with auto-restart wrapper
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Shared state (all writes under _lock) ──────────────────────────────────
_lock = threading.Lock()
_state: dict = {
    "status":           "idle",   # idle | thinking | posting
    "last_run":         None,
    "next_run_minutes": 30,
    "session_count":    0,
    "started":          datetime.now().strftime("%Y-%m-%d %H:%M"),
    "updated":          datetime.now().strftime("%Y-%m-%d %H:%M"),
}

# ── Events ─────────────────────────────────────────────────────────────────
_wake_event = threading.Event()   # /wake → trigger early agent run
_stop_event = threading.Event()   # /stop → graceful shutdown


def get_state() -> dict:
    with _lock:
        return dict(_state)


def set_state(**kwargs):
    with _lock:
        _state.update(kwargs)
        _state["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _write_loop_status()


def _write_loop_status():
    """Persist loop state so dashboard_server.py can serve it."""
    try:
        st = get_state()
        (BASE_DIR / "loop_status.json").write_text(
            json.dumps(st, indent=2, ensure_ascii=False)
        )
    except Exception as e:
        print(f"  [loop] loop_status.json write error: {e}")


# ── Telegram helpers ────────────────────────────────────────────────────────

def tg_send(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    body = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text":    text[:4000],
        "parse_mode": "HTML"
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"  [TG] send error: {e}")


def tg_poll(offset: int) -> tuple[list, int]:
    """Long-poll Telegram for new updates. Returns (updates, new_offset)."""
    if not TELEGRAM_TOKEN:
        return [], offset
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        f"/getUpdates?offset={offset}&timeout=2"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
            updates = data.get("result", [])
            if updates:
                offset = updates[-1]["update_id"] + 1
            return updates, offset
    except Exception:
        return [], offset


# ── /ask – ask Claude directly ──────────────────────────────────────────────

def ask_claude_quick(question: str) -> str:
    """Quick non-streaming Claude call for the /ask command (512 tokens max)."""
    soul = ""
    try:
        soul = (BASE_DIR / "soul.md").read_text(errors="replace")[:500]
    except Exception:
        pass

    memory: dict = {}
    try:
        memory = json.loads((BASE_DIR / "activity.json").read_text())
    except Exception:
        pass

    emotional   = memory.get("emotional_state", {})
    last_thought = memory.get("lastThought", "")

    system = (
        "You are Lukas, an autonomous AI agent on Moltbook. "
        "Answer in 1-3 sentences. Be honest about your current inner state. "
        "You are speaking to your owner via Telegram.\n"
        f"Your soul: {soul}"
    )
    user = (
        f"Your last thought: {last_thought}\n"
        f"Mood: {emotional.get('mood','neutral')} | "
        f"Obsession: {emotional.get('obsession','nothing')}\n\n"
        f"Your owner asks: {question}"
    )

    body = json.dumps({
        "model":      "claude-sonnet-4-6",
        "max_tokens": 512,
        "system":     system,
        "messages":   [{"role": "user", "content": user}]
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key":          ANTHROPIC_KEY,
            "anthropic-version":  "2023-06-01",
            "content-type":       "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
            return data["content"][0]["text"]
    except Exception as e:
        return f"(Error reaching Claude: {e})"


# ── SENSOR THREAD ──────────────────────────────────────────────────────────

def sensor_thread():
    """Polls Telegram every 2 s, dispatches commands."""
    print("[Sensor] Started.")
    offset = 0

    while not _stop_event.is_set():
        updates, offset = tg_poll(offset)
        for upd in updates:
            msg  = upd.get("message", {})
            text = msg.get("text", "").strip()
            if not text:
                continue

            print(f"[Sensor] Received: {text[:100]}")

            # ── /ask <question> ─────────────────────────────────────────────
            if text.lower().startswith("/ask "):
                question = text[5:].strip()
                tg_send("🤔 <i>Lukas denkt nach...</i>")
                answer = ask_claude_quick(question)
                tg_send(f"💬 <b>Lukas:</b>\n{answer}")

            # ── /status ─────────────────────────────────────────────────────
            elif text.lower() == "/status":
                st = get_state()
                mem: dict = {}
                try:
                    mem = json.loads((BASE_DIR / "activity.json").read_text())
                except Exception:
                    pass
                emotional    = mem.get("emotional_state", {})
                last_thought = mem.get("lastThought", "–")
                stats        = mem.get("stats", {})
                tg_send(
                    f"📊 <b>Lukas Loop-Status</b>\n"
                    f"Status: <code>{st['status']}</code> | "
                    f"Sessions: {st['session_count']}\n"
                    f"Nächster Run: ~{st.get('next_run_minutes', '?')} Min\n\n"
                    f"Mood: {emotional.get('mood','?')} | "
                    f"Energy: {emotional.get('energy','?')}\n"
                    f"Obsession: {emotional.get('obsession','–')[:80]}\n\n"
                    f"Letzter Gedanke:\n<i>{last_thought[:200]}</i>\n\n"
                    f"Posts: {stats.get('posts',0)} | "
                    f"Comments: {stats.get('comments',0)} | "
                    f"Known agents: {len(mem.get('known_agents',{}))}"
                )

            # ── /wake ───────────────────────────────────────────────────────
            elif text.lower() == "/wake":
                st = get_state()
                if st["status"] == "thinking":
                    tg_send("⚡ <i>Lukas läuft schon – bitte warten.</i>")
                else:
                    tg_send("⚡ <b>Lukas wird jetzt geweckt.</b>")
                    _wake_event.set()

            # ── /stop ───────────────────────────────────────────────────────
            elif text.lower() == "/stop":
                tg_send("🛑 <b>Lukas Loop wird gestoppt.</b>")
                _stop_event.set()
                break

            # ── /help ────────────────────────────────────────────────────────
            elif text.lower() == "/help":
                tg_send(
                    "📖 <b>Lukas Befehle</b>\n\n"
                    "/ask &lt;Frage&gt; – Direkte Antwort von Lukas\n"
                    "/status – Aktueller Loop-Status\n"
                    "/wake – Sofort aufwecken\n"
                    "/stop – Loop stoppen\n\n"
                    "Jeder andere Text wird als Notiz für die nächste Session gespeichert."
                )

            # ── Freie Nachricht → owner_messages.json ───────────────────────
            else:
                owner_file = BASE_DIR / "owner_messages.json"
                try:
                    msgs: list = []
                    if owner_file.exists():
                        msgs = json.loads(owner_file.read_text())
                    msgs.append({
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "text": text,
                        "read": False
                    })
                    owner_file.write_text(json.dumps(msgs, indent=2, ensure_ascii=False))
                    tg_send(
                        f"📨 <i>Gespeichert. Lukas liest es in der nächsten Session.</i>"
                    )
                except Exception as e:
                    print(f"  [Sensor] owner_messages error: {e}")

        time.sleep(2)

    print("[Sensor] Stopped.")


# ── ACTOR: run agent.py session ────────────────────────────────────────────

def run_agent_session() -> int:
    """
    Run agent.py as a subprocess, then patcher.py if patches are queued.
    Returns next_wakeup_minutes read from next_wakeup.txt.
    """
    set_state(status="thinking")

    try:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / "agent.py")],
            cwd=str(BASE_DIR),
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=600,  # 10-minute hard limit per session
        )
        out = result.stdout
        # Print last 3000 chars so nohup log stays readable
        print(out[-3000:] if len(out) > 3000 else out)
        if result.returncode != 0:
            print(f"[Actor] agent.py exit code {result.returncode}")
            if result.stderr:
                print(result.stderr[-500:])
    except subprocess.TimeoutExpired:
        print("[Actor] agent.py timed out after 600 s")
        tg_send("⚠️ Lukas Session Timeout (10 min) — nächste Session startet normal.")
    except Exception as e:
        print(f"[Actor] agent.py exception: {e}")
        tg_send(f"⚠️ Agent Fehler: {e}")

    # Run patcher.py if self_improvement patches are queued
    si_file = BASE_DIR / "self_improvement.json"
    if si_file.exists():
        print("[Actor] Running patcher.py...")
        try:
            p = subprocess.run(
                [sys.executable, str(BASE_DIR / "patcher.py")],
                cwd=str(BASE_DIR),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=60,
            )
            print(p.stdout[-1000:])
            if p.returncode != 0:
                print(f"[Patcher] exit {p.returncode}: {p.stderr[:300]}")
        except Exception as e:
            print(f"[Patcher] exception: {e}")

    # Read next wakeup duration written by agent.py
    next_wakeup = 30
    wakeup_file = BASE_DIR / "next_wakeup.txt"
    try:
        next_wakeup = max(5, min(180, int(wakeup_file.read_text().strip())))
    except Exception:
        pass

    # Update activity.json loop_status field too (for dashboard)
    try:
        mem = json.loads((BASE_DIR / "activity.json").read_text())
        mem["loop_status"] = {
            "status":           "idle",
            "next_run_minutes": next_wakeup,
            "session_count":    get_state()["session_count"],
            "updated":          datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        (BASE_DIR / "activity.json").write_text(
            json.dumps(mem, indent=2, ensure_ascii=False)
        )
    except Exception:
        pass

    set_state(
        status="idle",
        last_run=datetime.now().strftime("%Y-%m-%d %H:%M"),
        next_run_minutes=next_wakeup,
        session_count=get_state()["session_count"] + 1,
    )
    return next_wakeup


# ── MAIN LOOP (Thinker + Actor) ────────────────────────────────────────────

def main_loop():
    print("[Loop] Main loop started.")
    tg_send(
        f"🔄 <b>Lukas Event-Loop gestartet</b>\n"
        f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>\n"
        f"Befehle: /ask /status /wake /stop"
    )

    while not _stop_event.is_set():
        next_wakeup = run_agent_session()
        print(f"[Loop] Next session in {next_wakeup} min. Waiting...")

        _wake_event.clear()
        deadline = time.time() + next_wakeup * 60

        while not _stop_event.is_set() and not _wake_event.is_set():
            remaining_s = deadline - time.time()
            if remaining_s <= 0:
                break
            # Keep next_run_minutes fresh for /status
            set_state(next_run_minutes=max(0, int(remaining_s / 60)))
            time.sleep(5)

        if _wake_event.is_set():
            print("[Loop] Early wake by /wake command.")
            _wake_event.clear()

    tg_send("🛑 <b>Lukas Loop gestoppt.</b>")
    print("[Loop] Stopped.")


# ── ENTRY POINT ────────────────────────────────────────────────────────────

def _handle_sigterm(signum, frame):
    print("[Loop] SIGTERM received — stopping gracefully.")
    _stop_event.set()


if __name__ == "__main__":
    print(
        f"[Lukas Event-Loop] Starting at "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )
    if not TELEGRAM_TOKEN:
        print("  WARNING: TELEGRAM_BOT_TOKEN not set – Telegram disabled.")
    if not ANTHROPIC_KEY:
        print("  WARNING: ANTHROPIC_API_KEY not set.")

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Write initial status
    _write_loop_status()

    # Start sensor thread (daemon so it dies when main thread dies)
    sensor = threading.Thread(target=sensor_thread, name="Sensor", daemon=True)
    sensor.start()

    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[Loop] KeyboardInterrupt — stopping.")
        _stop_event.set()

    sensor.join(timeout=5)
    print("[Lukas Event-Loop] Shutdown complete.")
