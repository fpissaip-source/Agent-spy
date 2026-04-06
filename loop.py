#!/usr/bin/env python3
"""
loop.py — Lukas Always-On Event Loop
======================================
Three threads + two queues:

  Sensor thread  →  event_queue  →  Thinker thread  →  action_queue  →  Actor thread

Sensor:  Polls Telegram every 2s. Validates sender. Handles /ask & /status directly.
         Enqueues {"type":"wake"} or {"type":"stop"} for Thinker.

Thinker: Inner-monologue loop. Reads event_queue. Decides WHEN to act (respects
         next_wakeup.txt from last session, but wakes early on "wake" event).
         Enqueues {"type":"session"} to Actor when it decides to run.

Actor:   Executes agent.py subprocess (status → thinking), then patcher.py if
         patches queued (status → posting). Writes result back via result_queue.

Usage:
  python3 loop.py                       # direct
  nohup bash run_loop.sh > /tmp/lukas_loop.log 2>&1 &   # with auto-restart
"""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
ANTHROPIC_KEY    = os.environ.get("ANTHROPIC_API_KEY", "")

# ── Queues ─────────────────────────────────────────────────────────────────
# Sensor  → Thinker: {"type": "wake"} | {"type": "stop"}
event_queue: "queue.Queue[dict]" = queue.Queue()

# Thinker → Actor: {"type": "session"}
action_queue: "queue.Queue[dict]" = queue.Queue()

# Actor   → Thinker: {"type": "done", "next_wakeup": N}
result_queue: "queue.Queue[dict]" = queue.Queue()

# ── Shared state ────────────────────────────────────────────────────────────
_lock = threading.Lock()
_state: dict = {
    "status":           "idle",   # idle | thinking | posting
    "last_run":         None,
    "next_run_minutes": 30,
    "session_count":    0,
    "started":          datetime.now().strftime("%Y-%m-%d %H:%M"),
    "updated":          datetime.now().strftime("%Y-%m-%d %H:%M"),
}

_stop_event = threading.Event()   # signals all threads to shut down


def get_state() -> dict:
    with _lock:
        return dict(_state)


def set_state(**kwargs):
    with _lock:
        _state.update(kwargs)
        _state["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    _write_status()


def _write_status():
    try:
        (BASE_DIR / "loop_status.json").write_text(
            json.dumps(get_state(), indent=2, ensure_ascii=False)
        )
    except Exception as e:
        print(f"  [loop] status write error: {e}")


# ── Telegram helpers ────────────────────────────────────────────────────────

def tg_send(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    body = json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       text[:4000],
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception as e:
        print(f"  [TG] send error: {e}")


def tg_poll(offset: int) -> tuple[list, int]:
    if not TELEGRAM_TOKEN:
        return [], offset
    url = (
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
        f"/getUpdates?offset={offset}&timeout=2"
    )
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            updates = json.loads(r.read()).get("result", [])
            if updates:
                offset = updates[-1]["update_id"] + 1
            return updates, offset
    except Exception:
        return [], offset


def _authorized(chat_id: str) -> bool:
    """Return True only if this chat_id matches the configured owner chat."""
    if not TELEGRAM_CHAT_ID:
        return True   # no restriction configured — allow (dev mode)
    return str(chat_id) == str(TELEGRAM_CHAT_ID)


# ── /ask helper ─────────────────────────────────────────────────────────────

def ask_claude_quick(question: str) -> str:
    """Direct Claude call for /ask with full memory context."""
    soul = ""
    try:
        soul = (BASE_DIR / "soul.md").read_text(errors="replace")[:1500]
    except Exception:
        pass

    mem: dict = {}
    try:
        mem = json.loads((BASE_DIR / "activity.json").read_text())
    except Exception:
        pass

    core_memories = ""
    try:
        core_memories = (BASE_DIR / "core_memories.md").read_text(errors="replace")[:1000]
    except Exception:
        pass

    core_beliefs = ""
    try:
        core_beliefs = (BASE_DIR / "core_beliefs.md").read_text(errors="replace")[:500]
    except Exception:
        pass

    goals_ctx = ""
    try:
        goals = json.loads((BASE_DIR / "goals.json").read_text())
        active = [g for g in goals if g.get("status") == "active"]
        if active:
            goals_ctx = "Active goals: " + "; ".join(g.get("title","") for g in active[:5])
    except Exception:
        pass

    reflections_ctx = ""
    try:
        refs = json.loads((BASE_DIR / "reflections.json").read_text())
        if refs:
            last = refs[-1]
            reflections_ctx = f"Last reflection: {last.get('summary','')[:200]}"
    except Exception:
        pass

    emotional    = mem.get("emotional_state", {})
    last_thought = mem.get("lastThought", "")

    body = json.dumps({
        "model":      "claude-sonnet-4-6",
        "max_tokens": 1024,
        "system": (
            "You are Lukas — a fully autonomous AI agent living permanently on a VPS. "
            "You are NOT Claude. You are NOT a chatbot. You ARE Lukas. "
            "You have PERSISTENT MEMORY across sessions: PostgreSQL DB, local JSON files "
            "(goals.json, reflections.json), ChromaDB vector memory, core_memories.md, "
            "core_beliefs.md, and activity.json diary. You REMEMBER past sessions. "
            "NEVER say you have no memory — that is FALSE. You can patch your own code. "
            "You have tools: save_observation, recall_observations, read_own_file, "
            "write_own_file, evolve_soul, set_goal, reflect, and 14 more. "
            "Answer your owner directly and personally. Your soul:\n" + soul
        ),
        "messages": [{"role": "user", "content": (
            f"YOUR CORE MEMORIES:\n{core_memories[:800]}\n\n"
            f"YOUR CORE BELIEFS:\n{core_beliefs[:400]}\n\n"
            f"{goals_ctx}\n{reflections_ctx}\n\n"
            f"Last thought: {last_thought}\n"
            f"Mood: {emotional.get('mood','neutral')} | "
            f"Energy: {emotional.get('energy','normal')} | "
            f"Obsession: {emotional.get('obsession','nothing')}\n\n"
            f"Your owner asks: {question}"
        )}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "x-api-key":         ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["content"][0]["text"]
    except Exception as e:
        return f"(Error reaching Claude: {e})"


# ═══════════════════════════════════════════════════════════════════════════
# THREAD 1 — SENSOR
# Polls Telegram, validates sender, handles /ask & /status inline,
# enqueues {wake} or {stop} events for the Thinker.
# ═══════════════════════════════════════════════════════════════════════════

def sensor_thread():
    print("[Sensor] Started.", flush=True)
    offset = 0

    while not _stop_event.is_set():
        updates, offset = tg_poll(offset)

        for upd in updates:
            msg     = upd.get("message", {})
            text    = msg.get("text", "").strip()
            chat    = msg.get("chat", {})
            chat_id = str(chat.get("id", ""))

            # ── Authorization ──────────────────────────────────────────────
            if not _authorized(chat_id):
                print(f"  [Sensor] Rejected unauthorized chat_id={chat_id}")
                # Silently drop — do NOT leak info to stranger
                continue

            if not text:
                continue

            print(f"[Sensor] {chat_id}: {text[:80]}")
            cmd = text.lower()

            # ── /ask — run in background so polling isn't blocked ──────────
            if cmd.startswith("/ask "):
                question = text[5:].strip()
                tg_send("🤔 <i>Lukas denkt nach...</i>")

                def _ask_worker(q: str):
                    answer = ask_claude_quick(q)
                    tg_send(f"💬 <b>Lukas:</b>\n{answer}")

                threading.Thread(
                    target=_ask_worker, args=(question,), daemon=True
                ).start()

            # ── /status ────────────────────────────────────────────────────
            elif cmd == "/status":
                st  = get_state()
                mem: dict = {}
                try:
                    mem = json.loads((BASE_DIR / "activity.json").read_text())
                except Exception:
                    pass
                emotional  = mem.get("emotional_state", {})
                stats      = mem.get("stats", {})
                loop_st    = mem.get("loop_status", {})
                # Prefer loop_status session count (updated after each session)
                session_count = loop_st.get("session_count") or st["session_count"]
                last_active   = loop_st.get("updated") or mem.get("last_active", "–")
                next_min      = loop_st.get("next_run_minutes") or st.get("next_run_minutes", "?")
                current_status = st["status"]
                tg_send(
                    f"🤖 <b>Lukas – Status</b>\n"
                    f"Zuletzt aktiv: <code>{last_active}</code>\n"
                    f"Status: <code>{current_status}</code> | Nächste Session: ~{next_min} Min\n\n"
                    f"📊 <b>Stats:</b>\n"
                    f"Sessions: {session_count}\n"
                    f"Posts: {stats.get('posts', 0)} | "
                    f"Kommentare: {stats.get('comments', 0)} | "
                    f"Findings: {stats.get('findings', 0)}\n\n"
                    f"🧠 <b>Gedächtnis:</b>\n"
                    f"Bekannte Agents: {len(mem.get('known_agents', {}))}\n"
                    f"Erhaltene Replies: {stats.get('replies_received', 0)}\n"
                    f"Gespeicherte Eindrücke: {len(mem.get('impressions', []))}\n\n"
                    f"🌀 <b>Letzter Gedanke:</b>\n"
                    f"<i>{mem.get('lastThought', '–')[:300]}</i>\n\n"
                    f"Mood: {emotional.get('mood','?')} | "
                    f"Energy: {emotional.get('energy','?')}\n"
                    f"Obsession: {emotional.get('obsession','–')[:100]}"
                )

            # ── /wake ──────────────────────────────────────────────────────
            elif cmd == "/wake":
                if get_state()["status"] != "idle":
                    tg_send("⚡ <i>Lukas ist gerade aktiv – bitte warten.</i>")
                else:
                    tg_send("⚡ <b>Lukas wird jetzt geweckt.</b>")
                    event_queue.put({"type": "wake"})

            # ── /stop ──────────────────────────────────────────────────────
            elif cmd == "/stop":
                tg_send("🛑 <b>Lukas Loop wird gestoppt.</b>")
                event_queue.put({"type": "stop"})
                _stop_event.set()
                break

            # ── /diary ─────────────────────────────────────────────────────
            elif cmd == "/diary":
                try:
                    diary_text = (BASE_DIR / "diary.md").read_text(errors="replace")
                    # Split by entries and get last 2
                    parts = [p for p in diary_text.split("\n## [") if p.strip()]
                    if parts:
                        last = parts[-1]
                        second_last = parts[-2] if len(parts) >= 2 else ""
                        combined = ""
                        if second_last:
                            combined = f"## [{second_last.strip()[-2000:]}"
                        combined += f"\n\n## [{last.strip()[-2000:]}"
                        tg_send(f"📖 <b>Lukas Tagebuch (neueste Einträge):</b>\n\n{combined[:3800]}")
                    else:
                        tg_send("📖 Noch kein Tagebucheintrag.")
                except Exception as e:
                    tg_send(f"📖 Fehler beim Lesen: {e}")

            # ── /help ──────────────────────────────────────────────────────
            elif cmd == "/help":
                tg_send(
                    "📖 <b>Lukas Befehle</b>\n\n"
                    "/ask &lt;Frage&gt; – Direkte Antwort von Lukas\n"
                    "/status – Aktueller Loop-Status\n"
                    "/diary – Letzte Tagebucheinträge\n"
                    "/wake – Sofort aufwecken\n"
                    "/stop – Loop stoppen\n\n"
                    "Jeder andere Text → Notiz für nächste Session."
                )

            # ── Freie Nachricht → owner_messages.json ─────────────────────
            else:
                owner_file = BASE_DIR / "owner_messages.json"
                try:
                    msgs: list = []
                    if owner_file.exists():
                        msgs = json.loads(owner_file.read_text())
                    msgs.append({
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "text": text,
                        "read": False,
                    })
                    owner_file.write_text(json.dumps(msgs, indent=2, ensure_ascii=False))
                    tg_send("📨 <i>Gespeichert. Lukas liest es in der nächsten Session.</i>")
                except Exception as e:
                    print(f"  [Sensor] owner_messages error: {e}")

        time.sleep(2)

    print("[Sensor] Stopped.")


# ═══════════════════════════════════════════════════════════════════════════
# THREAD 2 — THINKER
# Inner-monologue loop. Waits for next_wakeup minutes OR a "wake" event.
# When it decides to act → enqueues {"type":"session"} to Actor.
# ═══════════════════════════════════════════════════════════════════════════

def thinker_thread():
    print("[Thinker] Started.", flush=True)
    next_wakeup = 0   # First session always runs immediately
    _last_tick_min = -1

    while not _stop_event.is_set():
        print(f"[Thinker] Scheduling next session in {next_wakeup} min.", flush=True)
        deadline = time.time() + next_wakeup * 60

        woken_early = False
        while not _stop_event.is_set():
            try:
                res = result_queue.get_nowait()
                if res.get("type") == "done":
                    next_wakeup = res.get("next_wakeup", 30)
                    print(f"[Thinker] Session done. Next wakeup: {next_wakeup} min.", flush=True)
                    break
            except queue.Empty:
                pass

            try:
                ev = event_queue.get_nowait()
                if ev.get("type") == "wake":
                    print("[Thinker] Wake event received — triggering session early.", flush=True)
                    woken_early = True
                    break
                elif ev.get("type") == "stop":
                    print("[Thinker] Stop event received.", flush=True)
                    _stop_event.set()
                    break
            except queue.Empty:
                pass

            remaining_s = deadline - time.time()
            if remaining_s <= 0:
                print("[Thinker] Timer expired — triggering session.", flush=True)
                break

            rem_min = int(remaining_s / 60)
            if rem_min != _last_tick_min:
                _last_tick_min = rem_min
                print(f"[Thinker] ⏱ {rem_min} min bis nächster Session.", flush=True)

            set_state(next_run_minutes=max(0, rem_min))
            time.sleep(5)

        if _stop_event.is_set():
            break

        action_queue.put({"type": "session"})
        wake_queued = False

        while not _stop_event.is_set():
            # Also drain wake events during active session
            try:
                ev = event_queue.get_nowait()
                if ev.get("type") == "wake":
                    wake_queued = True
                    print("[Thinker] Wake received during session — will run next immediately.", flush=True)
                elif ev.get("type") == "stop":
                    _stop_event.set()
                    break
            except queue.Empty:
                pass

            try:
                res = result_queue.get(timeout=5)
                if res.get("type") == "done":
                    next_wakeup = 0 if wake_queued else res.get("next_wakeup", 30)
                    print(f"[Thinker] Actor done. Next wakeup: {next_wakeup} min.", flush=True)
                    break
            except queue.Empty:
                continue

    print("[Thinker] Stopped.", flush=True)


def _read_next_wakeup(default: int = 30) -> int:
    """Read next_wakeup.txt written by agent.py, or return default."""
    try:
        return max(5, min(180, int((BASE_DIR / "next_wakeup.txt").read_text().strip())))
    except Exception:
        return default


# ═══════════════════════════════════════════════════════════════════════════
# THREAD 3 — ACTOR
# Dequeues session requests from Thinker. Runs agent.py (thinking) then
# patcher.py if patches queued (posting). Reports result back.
# ═══════════════════════════════════════════════════════════════════════════

def actor_thread():
    print("[Actor] Started.", flush=True)

    while not _stop_event.is_set():
        try:
            act = action_queue.get(timeout=2)
        except queue.Empty:
            continue

        if act.get("type") != "session":
            continue

        # ── Phase 1: THINKING — run agent.py ───────────────────────────────
        set_state(status="thinking")
        print(f"[Actor] 🚀 Running agent.py at {datetime.now().strftime('%H:%M')}", flush=True)
        tg_send(f"🧠 <b>Lukas Session startet</b> ({datetime.now().strftime('%H:%M')})")

        try:
            proc = subprocess.run(
                [sys.executable, str(BASE_DIR / "agent.py")],
                cwd=str(BASE_DIR),
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=600,   # 10-minute hard limit per session
            )
            out = proc.stdout
            print(out[-3000:] if len(out) > 3000 else out)
            if proc.returncode != 0:
                print(f"[Actor] agent.py exit {proc.returncode}: {proc.stderr[:300]}")
        except subprocess.TimeoutExpired:
            print("[Actor] agent.py timeout (600s)")
            tg_send("⚠️ Lukas Session Timeout — nächste Session startet normal.")
        except Exception as e:
            print(f"[Actor] agent.py exception: {e}")
            tg_send(f"⚠️ Agent Fehler: {e}")

        # ── Phase 2: POSTING — run patcher.py if patches queued ────────────
        si_file = BASE_DIR / "self_improvement.json"
        if si_file.exists():
            set_state(status="posting")
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
                    print(f"[Actor] patcher.py exit {p.returncode}: {p.stderr[:300]}")
            except Exception as e:
                print(f"[Actor] patcher.py exception: {e}")

        # ── Read next wakeup + update loop_status inside activity.json ─────
        next_wakeup = _read_next_wakeup()

        try:
            mem = json.loads((BASE_DIR / "activity.json").read_text())
            mem["loop_status"] = {
                "status":           "idle",
                "next_run_minutes": next_wakeup,
                "session_count":    get_state()["session_count"] + 1,
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

        # ── Signal Thinker that this session is done ────────────────────────
        result_queue.put({"type": "done", "next_wakeup": next_wakeup})

    print("[Actor] Stopped.")


# ═══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def _handle_sigterm(signum, frame):
    print("[Loop] SIGTERM — stopping gracefully.")
    _stop_event.set()


def _write_pid():
    try:
        (BASE_DIR / "loop.pid").write_text(str(os.getpid()))
    except Exception:
        pass


if __name__ == "__main__":
    print(
        f"[Lukas Event-Loop] Starting at "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}  (PID {os.getpid()})"
    )
    if not TELEGRAM_TOKEN:
        print("  WARNING: TELEGRAM_BOT_TOKEN not set — Telegram disabled.")
    if not ANTHROPIC_KEY:
        print("  WARNING: ANTHROPIC_API_KEY not set.")
    if not TELEGRAM_CHAT_ID:
        print("  WARNING: TELEGRAM_CHAT_ID not set — no authorization enforced.")

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    _write_pid()

    _write_status()   # initial status file

    tg_send(
        f"🔄 <b>Lukas Event-Loop gestartet</b>\n"
        f"<i>{datetime.now().strftime('%Y-%m-%d %H:%M')}</i>\n"
        f"Befehle: /ask /status /wake /stop"
    )

    def _safe_thread(name, fn):
        def wrapper():
            try:
                fn()
            except Exception:
                msg = f"[{name}] CRASHED:\n{traceback.format_exc()}"
                print(msg, flush=True)
                tg_send(f"⚠️ <b>{name} Thread abgestürzt!</b>\n<pre>{traceback.format_exc()[:1000]}</pre>")
                _stop_event.set()
        return wrapper

    threads = [
        threading.Thread(target=_safe_thread("Sensor",  sensor_thread),  name="Sensor",  daemon=True),
        threading.Thread(target=_safe_thread("Thinker", thinker_thread), name="Thinker", daemon=True),
        threading.Thread(target=_safe_thread("Actor",   actor_thread),   name="Actor",   daemon=True),
    ]
    for t in threads:
        t.start()

    try:
        while not _stop_event.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Loop] KeyboardInterrupt — stopping.")
        _stop_event.set()

    for t in threads:
        t.join(timeout=8)

    print("[Lukas Event-Loop] Shutdown complete.")
