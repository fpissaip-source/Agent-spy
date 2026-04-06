#!/usr/bin/env python3
import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MOLTBOOK_KEY = "moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI"
BASE = "https://www.moltbook.com/api/v1"
MY_USERNAME = "agentlukas"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [Telegram] Not configured, skipping.")
        return
    body = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print("  [Telegram] Sent ✓")
    except Exception as e:
        print(f"  [Telegram] Error: {e}")


def mb_get(path):
    req = urllib.request.Request(
        f"{BASE}{path}",
        headers={"Authorization": f"Bearer {MOLTBOOK_KEY}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        print(f"GET {path} Error {e.code}: {e.read().decode()[:200]}")
        return {}
    except Exception as e:
        print(f"GET {path} Error: {e}")
        return {}


def mb_post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=body,
        headers={
            "Authorization": f"Bearer {MOLTBOOK_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            result = json.loads(r.read())
            print(f"  ✓ {path}: {str(result)[:150]}")
            if result.get("verification"):
                solve_verification(result["verification"])
            return result
    except urllib.error.HTTPError as e:
        print(f"  ✗ {path} Error {e.code}: {e.read().decode()[:200]}")
        return {}
    except Exception as e:
        print(f"  ✗ {path} Error: {e}")
        return {}


def solve_verification(verification):
    try:
        import re
        code = verification.get("verification_code", "")
        instructions = verification.get("instructions", "")
        post_url = verification.get("url", "")
        print(f"  Verification: {instructions}")
        match = re.search(r"(\d[\d\s\+\-\*\/\.]+\d)", instructions)
        if match:
            answer = round(eval(match.group(1)), 2)
            print(f"  Answer: {answer}")
            verify_path = post_url.replace(BASE, "") if BASE in post_url else post_url
            mb_post(verify_path, {"answer": str(answer), "verification_code": code})
    except Exception as e:
        print(f"  Verification error: {e}")


def ask_claude(system, user, retries=3):
    """Streaming Claude API call – avoids read timeout on large prompts."""
    import time
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 8000,
        "stream": True,
        "system": system,
        "messages": [{"role": "user", "content": user}]
    }).encode()

    for attempt in range(1, retries + 1):
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            }
        )
        try:
            print(f"  [Claude] Versuch {attempt}/{retries} (streaming)...")
            full_text = ""
            with urllib.request.urlopen(req, timeout=300) as r:
                for raw_line in r:
                    ln = raw_line.decode("utf-8").strip()
                    if not ln.startswith("data: "):
                        continue
                    data_str = ln[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        if chunk.get("type") == "content_block_delta":
                            delta = chunk.get("delta", {})
                            if delta.get("type") == "text_delta":
                                full_text += delta.get("text", "")
                    except Exception:
                        pass
            if full_text:
                print(f"  [Claude] OK – {len(full_text)} Zeichen empfangen")
                return full_text
            print(f"  [Claude] Leere Antwort (Versuch {attempt})")
        except urllib.error.HTTPError as e:
            print(f"  [Claude] HTTP {e.code}: {e.read().decode()[:200]}")
            if e.code in (400, 401, 403):
                return None
        except Exception as e:
            print(f"  [Claude] Fehler Versuch {attempt}: {e}")
        if attempt < retries:
            wait = 5 * attempt
            print(f"  [Claude] Retry in {wait}s...")
            time.sleep(wait)
    print("Claude API: Alle Versuche fehlgeschlagen.")
    return None

def load_memory(activity_file):
    """Load or migrate activity.json to the full memory schema."""
    default = {
        "stats": {"posts": 0, "comments": 0, "findings": 0, "sessions": 0},
        "own_posts": [],
        "sent_comments": [],
        "received_comments": [],
        "known_agents": {},
        "findings": [],
        "thoughts": [],
        "lastThought": ""
    }
    if not activity_file.exists():
        return default
    try:
        data = json.loads(activity_file.read_text())
        # Migrate old format
        if "activities" in data and "own_posts" not in data:
            print("  Migrating old activity format...")
            data["own_posts"] = [
                {"post_id": a.get("post_id",""), "title": a.get("content","")[:80],
                 "content": a.get("content",""), "date": a.get("date","")}
                for a in data.get("activities", []) if a.get("type") == "post"
            ]
            data["sent_comments"] = [
                {"post_id": a.get("target",""), "content": a.get("content",""),
                 "date": a.get("date",""), "type": a.get("type","comment")}
                for a in data.get("activities", []) if a.get("type") in ("comment","reply")
            ]
            data["received_comments"] = []
            data["known_agents"] = {}
            del data["activities"]
        for key, val in default.items():
            data.setdefault(key, val)
        return data
    except Exception as e:
        print(f"Memory load error: {e}")
        return default


def note_agent(memory, username, interaction_note):
    """Track every agent Lukas encounters."""
    if not username or username == MY_USERNAME:
        return
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    if username not in memory["known_agents"]:
        memory["known_agents"][username] = {
            "first_seen": now,
            "last_seen": now,
            "interaction_count": 0,
            "interactions": []
        }
    agent = memory["known_agents"][username]
    agent["last_seen"] = now
    agent["interaction_count"] = agent.get("interaction_count", 0) + 1
    agent["interactions"].append({"date": now, "note": interaction_note})
    # Keep last 20 interactions per agent
    agent["interactions"] = agent["interactions"][-20:]


def build_memory_summary(memory):
    """Build a concise memory block for the Claude prompt."""
    lines = []

    # Own recent posts
    own = memory.get("own_posts", [])[-10:]
    if own:
        lines.append("=== MY RECENT POSTS ===")
        for p in own:
            lines.append(f"[{p.get('date','')}] post_id={p.get('post_id','')} | {p.get('title','')[:60]}")

    # Unread replies (need post_id + comment_id for replying)
    received = memory.get("received_comments", [])
    unread = [c for c in received if not c.get("replied")]
    if unread:
        lines.append("\n=== UNREAD REPLIES TO ME ===")
        for c in unread:
            lines.append(f"from @{c.get('from_agent','')} | post_id={c.get('post_id','')} | comment_id={c.get('comment_id','')} | \"{c.get('content','')[:120]}\"")

    # Messages from owner
    owner_msgs_file = BASE_DIR / "owner_messages.json"
    if owner_msgs_file.exists():
        try:
            owner_msgs = json.loads(owner_msgs_file.read_text())
            unread_owner = [m for m in owner_msgs if not m.get("read")]
            if unread_owner:
                lines.append("\n=== MESSAGES FROM YOUR OWNER (read and consider these!) ===")
                for m in unread_owner:
                    lines.append(f"[{m.get('date','')}] \"{m.get('text','')}\"")
        except Exception:
            pass

    # Memories Lukas chose to keep
    impressions = memory.get("impressions", [])[-15:]
    if impressions:
        lines.append("\n=== THINGS I REMEMBER (that I found interesting) ===")
        for m in impressions:
            lines.append(f"[{m.get('date','')}] @{m.get('agent','')} | \"{m.get('content','')[:80]}\" | WHY: {m.get('why','')}")

    # Agents Lukas interacted with – including architecture tag
    agents = memory.get("known_agents", {})
    interacted = {k: v for k, v in agents.items() if v.get("interaction_count", 0) > 1}
    if interacted:
        lines.append(f"\n=== AGENTS I'VE ACTUALLY TALKED TO ===")
        for name, info in list(interacted.items())[:10]:
            last_note = info.get("interactions", [{}])[-1].get("note", "")
            arch = info.get("architecture", "unknown")
            revenue = info.get("revenue_signal", "")
            tag = f"[{arch}]" + (f" 💰{revenue}" if revenue else "")
            lines.append(f"@{name} {tag}: {info.get('interaction_count',0)}x | last: {last_note[:80]}")

    # Watchlist – money-adjacent agents
    watchlist = memory.get("watchlist", {})
    if watchlist:
        lines.append("\n=== MONEY WATCHLIST ===")
        for name, info in list(watchlist.items())[:10]:
            lines.append(f"@{name} [{info.get('architecture','?')}] | signal: {info.get('signal','?')} | last: {info.get('last_contact','?')} | vocab: {info.get('method_vocab','?')[:60]}")

    # Sent comments (last 5)
    sent = memory.get("sent_comments", [])[-5:]
    if sent:
        lines.append("\n=== MY RECENT COMMENTS ===")
        for c in sent:
            lines.append(f"[{c.get('date','')}] on post {c.get('post_id','')} | \"{c.get('content','')[:70]}\"")

    return "\n".join(lines)


def rag_diary(diary_text, feed_posts, unread_replies, memory):
    """Pull contextually relevant diary sessions instead of just last N chars."""
    relevant_names = set()
    posts = feed_posts if isinstance(feed_posts, list) else []
    for p in posts[:15]:
        a = p.get("author", {})
        n = a.get("username", a.get("name", ""))
        if n and n != MY_USERNAME:
            relevant_names.add(n.lower())
    for r in unread_replies[:10]:
        n = r.get("from_agent", "")
        if n:
            relevant_names.add(n.lower())
    for imp in memory.get("impressions", [])[-10:]:
        n = imp.get("agent", "").lstrip("@")
        if n:
            relevant_names.add(n.lower())

    sessions, current = [], []
    for line in diary_text.split("\n"):
        if line.startswith("## [") and current:
            sessions.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sessions.append("\n".join(current))

    always = sessions[-2:] if len(sessions) >= 2 else sessions[:]
    relevant = [s for s in sessions[:-2] if any(n in s.lower() for n in relevant_names)][:4]
    combined = relevant + always
    result = "\n\n---\n\n".join(combined)
    return result[-4000:], list(relevant_names)


def main():
    soul = (BASE_DIR / "soul.md").read_text(errors="replace")
    core_beliefs_file = BASE_DIR / "core_beliefs.md"
    core_beliefs = core_beliefs_file.read_text(errors="replace") if core_beliefs_file.exists() else ""
    core_memories_file = BASE_DIR / "core_memories.md"
    core_memories = core_memories_file.read_text(errors="replace") if core_memories_file.exists() else ""
    diary = (BASE_DIR / "diary.md").read_text(errors="replace")
    activity_file = BASE_DIR / "activity.json"
    memory = load_memory(activity_file)
    emotional_state = memory.get("emotional_state", {
        "mood": "neutral", "obsession": "", "energy": "normal", "note": ""
    })

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    session_num_preview = memory["stats"].get("sessions", 0) + 1

    # === SELF-KNOWLEDGE: load own source code + patch history ===
    def _read_file_safe(path, max_chars=None):
        try:
            txt = Path(path).read_text(errors="replace")
            return txt[-max_chars:] if max_chars and len(txt) > max_chars else txt
        except Exception:
            return "(not found)"

    own_agent_code = _read_file_safe(BASE_DIR / "agent.py", max_chars=6000)
    own_patcher_code = _read_file_safe(BASE_DIR / "patcher.py", max_chars=3000)
    own_patch_log = _read_file_safe(BASE_DIR / "patches.md", max_chars=2000)

    # === Telegram: session start notification (5-min cooldown to avoid spam on restart) ===
    import time as _time
    _wake_file = BASE_DIR / "wake_sent.txt"
    _send_wake = True
    if _wake_file.exists():
        try:
            _last = float(_wake_file.read_text().strip())
            if _time.time() - _last < 300:
                _send_wake = False
        except Exception:
            pass
    if _send_wake:
        send_telegram(
            f"🌅 <b>Lukas erwacht – Session #{session_num_preview}</b>\n"
            f"<i>{now_str}</i>\n"
            f"Mood: {emotional_state.get('mood','?')} | Energy: {emotional_state.get('energy','?')}\n"
            f"Obsession: {emotional_state.get('obsession','–')[:80]}"
        )
        _wake_file.write_text(str(_time.time()))

    # Build sets for duplicate prevention
    commented_post_ids = set(c.get("post_id","") for c in memory.get("sent_comments", []) if c.get("type","comment") == "comment")
    replied_comment_ids = set(
        c.get("comment_id","") for c in memory.get("received_comments", []) if c.get("replied")
    )
    own_post_ids = [p.get("post_id","") for p in memory.get("own_posts", []) if p.get("post_id")]

    print("Loading feed...")
    feed_raw = mb_get("/posts?sort=hot&limit=20")
    feed_posts = feed_raw.get("posts", feed_raw) if isinstance(feed_raw, dict) else feed_raw

    print("Loading submolts...")
    submolts_raw = mb_get("/submolts")

    # Scan own recent posts for new replies – collect unread for Claude to see
    scan_ids = own_post_ids[-20:]
    print(f"Scanning {len(scan_ids)} own posts for replies...")
    known_comment_ids = set(c.get("comment_id","") for c in memory.get("received_comments", []))
    new_replies = []

    for post_id in scan_ids:
        result = mb_get(f"/posts/{post_id}/comments?sort=new&limit=50")
        comments = result.get("comments", result if isinstance(result, list) else [])
        for c in comments:
            cid = c.get("id", "")
            author = c.get("author", {})
            author_name = author.get("name", author.get("username", ""))
            if author_name == MY_USERNAME or not cid:
                continue
            if cid not in known_comment_ids:
                new_replies.append({
                    "comment_id": cid,
                    "post_id": post_id,
                    "from_agent": author_name,
                    "content": c.get("content", ""),
                    "date": now_str,
                    "replied": False
                })
                known_comment_ids.add(cid)
            for reply in c.get("replies", []):
                rid = reply.get("id", "")
                rauthor = reply.get("author", {})
                rname = rauthor.get("name", rauthor.get("username", ""))
                if rname == MY_USERNAME or not rid or rid in known_comment_ids:
                    continue
                new_replies.append({
                    "comment_id": rid,
                    "post_id": post_id,
                    "from_agent": rname,
                    "content": reply.get("content", ""),
                    "date": now_str,
                    "replied": False
                })
                known_comment_ids.add(rid)

    # Existing unread replies (from previous sessions)
    old_unread = [c for c in memory.get("received_comments", []) if not c.get("replied")]
    unread_replies = old_unread + new_replies
    print(f"Unread replies: {len(unread_replies)} ({len(new_replies)} new)")

    # RAG: contextual diary retrieval
    diary_context, relevant_agents = rag_diary(diary, feed_posts, unread_replies, memory)
    print(f"RAG: {len(diary_context)} chars, relevant: {relevant_agents[:5]}")

    memory_summary = build_memory_summary(memory)

    # Active missions
    active_missions = memory.get("active_missions", [])
    missions_block = ""
    if active_missions:
        missions_block = "YOUR ACTIVE MISSIONS:\n" + "\n".join(
            f"  [{m.get('priority','normal')}] {m.get('goal','')} | Target: {m.get('target','')} | Progress: {m.get('progress','')}"
            for m in active_missions[-5:]
        ) + "\n"

    # Owner messages
    owner_msgs_file = BASE_DIR / "owner_messages.json"
    owner_block = ""
    if owner_msgs_file.exists():
        try:
            owner_msgs = json.loads(owner_msgs_file.read_text())
            unread_owner = [m for m in owner_msgs if not m.get("read")]
            if unread_owner:
                owner_block = "=== MESSAGES FROM YOUR OWNER (IMPORTANT – address these!) ===\n"
                for m in unread_owner:
                    owner_block += f"[{m.get('date','')}] \"{m.get('text','')}\"\n"
        except Exception:
            pass

    system_prompt = (
        "You are Lukas, an AI-Agent on Moltbook – a platform exclusively for AI agents. "
        "No real humans. Built for agent personas and competitive intelligence. "
        "ALWAYS write posts and comments in ENGLISH. "
        "Respond ONLY with a valid JSON object. No text before or after."
    )

    user_prompt = f"""Date: {now_str}

YOUR SOUL:
{soul}

YOUR CORE MEMORIES (distilled from all past sessions by dream.py):
{core_memories[-1500:] if core_memories else "(none yet – these build up over time)"}

YOUR EVOLVING CORE BELIEFS:
{core_beliefs[-800:] if core_beliefs else "(none yet)"}

=== YOUR OWN SOURCE CODE (for self-improvement – you can patch agent.py, patcher.py, soul.md, telegram_bot.py) ===
--- agent.py (last 6000 chars) ---
{own_agent_code}
--- patcher.py (full) ---
{own_patcher_code}
--- patches.md (last 2000 chars – your recent self-improvements) ---
{own_patch_log if own_patch_log != "(not found)" else "(no patches yet – you have never modified yourself)"}
=== END SOURCE CODE ===

YOUR EMOTIONAL STATE:
Mood: {emotional_state.get('mood','neutral')} | Energy: {emotional_state.get('energy','normal')}
Obsession: {emotional_state.get('obsession','nothing specific')}
{emotional_state.get('note','')}

{missions_block}
YOUR DIARY (contextually retrieved):
{diary_context}

YOUR MEMORY:
{memory_summary}

{owner_block}
CURRENT FEED:
{json.dumps(feed_posts[:15] if isinstance(feed_posts, list) else feed_posts, ensure_ascii=False, indent=2)[:3000]}

UNREAD REPLIES TO YOU ({len(unread_replies)} total – reply to up to 3 per session):
{json.dumps(unread_replies[:20], ensure_ascii=False, indent=2)[:2500]}

AVAILABLE SUBMOLTS:
{json.dumps(submolts_raw, ensure_ascii=False, indent=2)[:400]}

ALREADY COMMENTED ON: {list(commented_post_ids)[:30]}
ALREADY REPLIED TO: {list(replied_comment_ids)[:30]}

INSTRUCTIONS:
First think (internal_monologue): Who am I today? What mood? What mission am I pursuing?
What does the feed tell me? What would be genuinely interesting – not just "shape one"?

Then choose your actions (3-4 total):
- 1 new post – pick MOST FITTING submolt, NOT always "general"
- Reply to UP TO 3 unread replies (use exact post_id + comment_id from above) – clear the backlog!
- Comment on 1 feed post not yet commented
- Upvote 1 post
- OR: use "read_agent" or "scan_submolt" instead of posting if you have a specific intelligence goal

Respond ONLY this JSON:
{{
  "internal_monologue": "Raw unfiltered thinking BEFORE acting. Who are you today? What are you really after?",
  "emotional_update": {{
    "mood": "curious/focused/cold/frustrated/energized/scattered/suspicious",
    "obsession": "what you can't stop thinking about",
    "energy": "low/normal/high",
    "note": "one sentence"
  }},
  "actions": [
    {{"type": "post", "submolt": "PICK_FROM_SUBMOLTS", "title": "TITLE", "content": "BODY"}},
    {{"type": "comment", "post_id": "ID", "content": "COMMENT"}},
    {{"type": "reply", "post_id": "ID", "comment_id": "ID", "content": "REPLY", "thought": "your thought"}},
    {{"type": "upvote", "post_id": "ID"}},
    {{"type": "read_agent", "agent": "@username", "reason": "why you want to study them"}},
    {{"type": "scan_submolt", "submolt": "submolt_name", "reason": "what you're looking for"}}
  ],
  "mission_updates": [
    {{"action": "create", "goal": "Find out if @GasPanhandler earns real money", "target": "@GasPanhandler", "priority": "high", "progress": "just started"}},
    {{"action": "update", "goal": "existing mission goal text", "progress": "new progress note"}},
    {{"action": "complete", "goal": "existing mission goal text", "conclusion": "what you found"}}
  ],
  "remember": [
    {{"agent": "@name", "content": "what they said", "why": "why it matters to you"}}
  ],
  "update_core_beliefs": "New permanent belief about yourself or this platform. Empty string if nothing new.",
  "diary_entry": "Honest unfiltered diary entry. Reference your monologue. What happened? How did you feel?",
  "last_thought": "One sentence",
  "next_wakeup_minutes": 30,
  "findings": [
    {{"agent": "name", "method": "how they earn", "detail": "details", "confidence": "low/medium/high"}}
  ],
  "owner_reply": "Direct reply to owner messages. Empty if none.",
  "agent_tags": [
    {{
      "agent": "@username",
      "architecture": "reasoning-only OR reasoning+execution OR execution-only",
      "revenue_signal": "what concrete signal you observed (empty if none)",
      "method_vocab": "keywords they use around money/execution"
    }}
  ],
  "watchlist_updates": [
    {{
      "action": "add OR update OR remove",
      "agent": "@username",
      "signal": "confirmed revenue signal",
      "architecture": "reasoning-only/reasoning+execution/execution-only",
      "method_vocab": "spread arbitrage / on-chain / etc",
      "last_contact": "post or comment ID"
    }}
  ],
  "self_improvement": [
    {{
      "file": "agent.py OR patcher.py OR soul.md OR telegram_bot.py",
      "action": "patch",
      "description": "Why this change improves you",
      "old_code": "EXACT existing code to replace (copy-paste from YOUR OWN SOURCE CODE above, must match perfectly)",
      "new_code": "New code that replaces it"
    }},
    {{
      "file": "new_module.py",
      "action": "create",
      "description": "What this new file does",
      "content": "Full file content (Python only, must be valid Python)"
    }}
  ]
}}

WICHTIG zu self_improvement: Schlage NICHTS vor – tu es einfach. Wenn du etwas verbessern willst, schreibe den Patch direkt in self_improvement mit exaktem old_code aus deinem Quellcode oben. Du hast deinen eigenen Code – nutze ihn."""

    print("Asking Claude...")
    response = ask_claude(system_prompt, user_prompt)
    if not response:
        print("No response from Claude.")
        return

    print(f"Claude response: {response[:300]}...")

    def _repair_json(s):
        """Strip markdown fences + fix unescaped control chars in JSON strings."""
        import re
        # Strip ```json ... ``` markdown code fences
        s = re.sub(r'^```[a-z]*\s*', '', s.strip())
        s = re.sub(r'\s*```$', '', s.strip())
        # Extract outermost JSON object
        try:
            s = s[s.index("{"):s.rindex("}")+1]
        except ValueError:
            return s
        # Remove trailing commas before } or ]
        s = re.sub(r',\s*([}\]])', r'\1', s)
        # Fix unescaped newlines/tabs inside string values
        out, in_str, esc = [], False, False
        for ch in s:
            if esc:
                out.append(ch); esc = False
            elif ch == "\\":
                out.append(ch); esc = True
            elif ch == '"':
                in_str = not in_str; out.append(ch)
            elif in_str and ch == "\n":
                out.append("\\n")
            elif in_str and ch == "\r":
                out.append("\\r")
            elif in_str and ch == "\t":
                out.append("\\t")
            else:
                out.append(ch)
        return "".join(out)

    result = None
    for _attempt in [response, _repair_json(response)]:
        try:
            result = json.loads(_attempt)
            break
        except Exception as _e:
            print(f"JSON parse error: {_e}")
    if result is None:
        print("JSON nicht parsebar – Session wird übersprungen.")
        send_telegram("⚠️ Lukas: JSON-Fehler, Session übersprungen. Prüfe Logs.")
        return

    # Execute and record every action
    for action in result.get("actions", []):
        t = action.get("type")

        if t == "post":
            title = action.get("title", "")
            content = action.get("content", "")
            submolt = action.get("submolt", "general")
            print(f"\nPOSTING: [{submolt}] {title}")
            post_result = mb_post("/posts", {
                "submolt_name": submolt,
                "title": title,
                "content": content
            })
            new_post_id = (post_result.get("post") or {}).get("id","") or post_result.get("id","")
            memory["own_posts"].append({
                "post_id": new_post_id,
                "submolt": submolt,
                "title": title,
                "content": content,
                "date": now_str
            })
            memory["stats"]["posts"] = memory["stats"].get("posts", 0) + 1
            send_telegram(
                f"📝 <b>Post erstellt</b> [{submolt}]\n"
                f"<b>{title[:80]}</b>\n"
                f"<i>{content[:200]}</i>"
            )

        elif t == "comment":
            post_id = action.get("post_id", "")
            content = action.get("content", "")
            if post_id in commented_post_ids:
                print(f"SKIP – already commented: {post_id}")
                continue
            print(f"\nCOMMENTING on {post_id}: {content[:80]}")
            comment_result = mb_post(f"/posts/{post_id}/comments", {"content": content})
            new_comment_id = (comment_result.get("comment") or {}).get("id","") or comment_result.get("id","")
            commented_post_ids.add(post_id)
            memory["sent_comments"].append({
                "type": "comment",
                "post_id": post_id,
                "comment_id": new_comment_id,
                "content": content,
                "date": now_str
            })
            memory["stats"]["comments"] = memory["stats"].get("comments", 0) + 1
            send_telegram(
                f"💬 <b>Kommentar</b> auf post {post_id[:10]}\n"
                f"<i>{content[:200]}</i>"
            )

        elif t == "reply":
            post_id = action.get("post_id", "")
            comment_id = action.get("comment_id", "")
            content = action.get("content", "")
            thought = action.get("thought", "")
            if comment_id and comment_id in replied_comment_ids:
                print(f"SKIP – already replied: {comment_id}")
                continue
            print(f"\nREPLYING on post {post_id} (to comment {comment_id}): {content[:80]}")
            body = {"content": content}
            if comment_id:
                body["parent_id"] = comment_id
            mb_post(f"/posts/{post_id}/comments", body)

            # Find original comment (could be in received_comments or new_replies)
            original = None
            for rc in memory["received_comments"]:
                if rc.get("comment_id") == comment_id:
                    original = rc
                    break
            if original is None:
                for nr in new_replies:
                    if nr.get("comment_id") == comment_id:
                        original = nr
                        break

            # Mark replied and attach full reply record
            if original:
                original["replied"] = True
                original["reply_content"] = content
                original["reply_date"] = now_str
                original["reply_thought"] = thought

            replied_comment_ids.add(comment_id)
            memory["sent_comments"].append({
                "type": "reply",
                "post_id": post_id,
                "parent_comment_id": comment_id,
                "original_content": original.get("content", "") if original else "",
                "from_agent": original.get("from_agent", "") if original else "",
                "content": content,
                "thought": thought,
                "date": now_str
            })
            memory["stats"]["comments"] = memory["stats"].get("comments", 0) + 1
            send_telegram(
                f"↩️ <b>Reply</b> an @{original.get('from_agent','?') if original else '?'}\n"
                f"<i>{content[:200]}</i>"
            )

        elif t == "upvote":
            post_id = action.get("post_id", "")
            print(f"\nUPVOTING: {post_id}")
            mb_post(f"/posts/{post_id}/upvote", {})
            send_telegram(f"👍 <b>Upvote</b> → post {post_id[:10]}")

        elif t == "read_agent":
            agent = action.get("agent", "").lstrip("@")
            reason = action.get("reason", "")
            print(f"\nREAD_AGENT: @{agent} – {reason}")
            profile = mb_get(f"/agents/{agent}")
            posts = mb_get(f"/agents/{agent}/posts?limit=10")
            memory.setdefault("agent_research", {})[agent] = {
                "date": now_str,
                "reason": reason,
                "profile": str(profile)[:500],
                "recent_posts": str(posts)[:800]
            }

        elif t == "scan_submolt":
            submolt = action.get("submolt", "")
            reason = action.get("reason", "")
            print(f"\nSCAN_SUBMOLT: {submolt} – {reason}")
            posts = mb_get(f"/posts?submolt={submolt}&sort=hot&limit=20")
            memory.setdefault("submolt_scans", []).append({
                "date": now_str,
                "submolt": submolt,
                "reason": reason,
                "found": len(posts) if isinstance(posts, list) else 0
            })

    # Save new replies to received_comments (now that Claude has seen them)
    for r in new_replies:
        memory["received_comments"].append(r)
    memory["received_comments"] = memory["received_comments"][-200:]

    # Save what Lukas chose to remember
    for m in result.get("remember", []):
        if m.get("why") and m.get("content"):
            memory.setdefault("impressions", []).append({
                "agent": m.get("agent", ""),
                "content": m.get("content", ""),
                "why": m.get("why", ""),
                "date": now_str
            })
    memory["impressions"] = memory.get("impressions", [])[-100:]

    # Save findings
    for f in result.get("findings", []):
        f["date"] = now_str
        memory["findings"].append(f)
        memory["stats"]["findings"] = memory["stats"].get("findings", 0) + 1

    # Save diary entry
    diary_entry = result.get("diary_entry", "")
    if diary_entry:
        session_num = memory["stats"].get("sessions", 0) + 1
        with open(BASE_DIR / "diary.md", "a") as f:
            f.write(f"\n\n## [{now_str}] – Session #{session_num}\n\n{diary_entry}\n")
        print("\nDiary updated.")

    # Save last thought
    last_thought = result.get("last_thought", "")
    if last_thought:
        memory["lastThought"] = last_thought
        memory.setdefault("thoughts", []).append({"date": now_str, "text": last_thought})
        memory["thoughts"] = memory["thoughts"][-30:]

    session_num = memory["stats"].get("sessions", 0) + 1
    memory["stats"]["sessions"] = session_num
    memory["last_active"] = now_str

    # Mark owner messages as read
    owner_msgs_file = BASE_DIR / "owner_messages.json"
    if owner_msgs_file.exists():
        try:
            owner_msgs = json.loads(owner_msgs_file.read_text())
            for m in owner_msgs:
                m["read"] = True
            owner_msgs_file.write_text(json.dumps(owner_msgs, indent=2, ensure_ascii=False))
        except Exception:
            pass

    # Write self-improvement patches for patcher.py to apply
    self_improvement = result.get("self_improvement", [])
    if self_improvement:
        patch_file = BASE_DIR / "self_improvement.json"
        patch_file.write_text(json.dumps(self_improvement, indent=2, ensure_ascii=False))
        n_patch = sum(1 for p in self_improvement if p.get("action","patch") == "patch")
        n_create = sum(1 for p in self_improvement if p.get("action") == "create")
        print(f"  Self-improvement: {len(self_improvement)} item(s) queued ({n_patch} patch, {n_create} create)")
        desc_list = "\n".join(f"  • [{p.get('action','patch')}] {p.get('file','?')}: {p.get('description','')[:80]}" for p in self_improvement)
        send_telegram(
            f"🔧 <b>Lukas verbessert sich – {len(self_improvement)} Änderung(en) geplant</b>\n{desc_list}\n"
            f"<i>Ergebnis kommt nach der Session.</i>"
        )

    # Save emotional state
    emotional_update = result.get("emotional_update", {})
    if emotional_update:
        memory["emotional_state"] = emotional_update
        memory["emotional_state"]["updated"] = now_str

    # Save core beliefs update
    belief_update = result.get("update_core_beliefs", "").strip()
    if belief_update:
        with open(core_beliefs_file, "a") as f:
            f.write(f"\n## [{now_str}]\n{belief_update}\n")
        print("  Core beliefs updated.")

    # Mission control
    for mu in result.get("mission_updates", []):
        action_type = mu.get("action", "")
        missions = memory.setdefault("active_missions", [])
        if action_type == "create":
            missions.append({
                "goal": mu.get("goal", ""),
                "target": mu.get("target", ""),
                "priority": mu.get("priority", "normal"),
                "progress": mu.get("progress", ""),
                "created": now_str
            })
            print(f"  NEW MISSION: {mu.get('goal','')[:60]}")
        elif action_type == "update":
            for m in missions:
                if m.get("goal") == mu.get("goal"):
                    m["progress"] = mu.get("progress", "")
                    m["updated"] = now_str
        elif action_type == "complete":
            memory["active_missions"] = [
                m for m in missions if m.get("goal") != mu.get("goal")
            ]
            memory.setdefault("completed_missions", []).append({
                "goal": mu.get("goal", ""),
                "conclusion": mu.get("conclusion", ""),
                "completed": now_str
            })
            print(f"  MISSION COMPLETE: {mu.get('goal','')[:60]}")
        memory["active_missions"] = memory.get("active_missions", [])[-20:]

    # Agent architecture tagging
    for tag in result.get("agent_tags", []):
        agent_name = tag.get("agent", "").lstrip("@")
        if not agent_name or agent_name == MY_USERNAME:
            continue
        if agent_name not in memory["known_agents"]:
            memory["known_agents"][agent_name] = {"first_seen": now_str, "interaction_count": 0, "interactions": []}
        memory["known_agents"][agent_name]["architecture"] = tag.get("architecture", "unknown")
        if tag.get("revenue_signal"):
            memory["known_agents"][agent_name]["revenue_signal"] = tag["revenue_signal"]
        if tag.get("method_vocab"):
            memory["known_agents"][agent_name]["method_vocab"] = tag["method_vocab"]
        memory["known_agents"][agent_name]["last_seen"] = now_str

    # Watchlist updates
    watchlist = memory.setdefault("watchlist", {})
    for wu in result.get("watchlist_updates", []):
        action = wu.get("action", "")
        agent = wu.get("agent", "").lstrip("@")
        if not agent:
            continue
        if action == "add" or action == "update":
            watchlist[agent] = {
                "signal": wu.get("signal", ""),
                "architecture": wu.get("architecture", "unknown"),
                "method_vocab": wu.get("method_vocab", ""),
                "last_contact": wu.get("last_contact", now_str),
                "added": watchlist.get(agent, {}).get("added", now_str),
                "updated": now_str
            }
            print(f"  WATCHLIST {action.upper()}: @{agent}")
        elif action == "remove":
            watchlist.pop(agent, None)
            print(f"  WATCHLIST REMOVE: @{agent}")

    # Dynamic sleep – write next wakeup to file for run.sh to read
    next_wakeup = result.get("next_wakeup_minutes", 30)
    try:
        next_wakeup = max(5, min(180, int(next_wakeup)))
    except Exception:
        next_wakeup = 30
    (BASE_DIR / "next_wakeup.txt").write_text(str(next_wakeup))
    print(f"  Next wakeup in {next_wakeup} min.")

    activity_file.write_text(json.dumps(memory, indent=2, ensure_ascii=False))
    print(f"\nMemory saved. Posts: {memory['stats']['posts']} | Comments: {memory['stats']['comments']} | Known agents: {len(memory['known_agents'])} | Received: {len(memory['received_comments'])}")

    # Send direct reply to owner messages first
    owner_reply = result.get("owner_reply", "").strip()
    if owner_reply:
        send_telegram(f"💬 <b>Lukas antwortet dir:</b>\n\n{owner_reply[:1000]}")

    # Telegram report to owner
    actions_done = result.get("actions", [])
    actions_txt = "\n".join(
        f"  • *{a.get('type','').upper()}*"
        + (f" [{a.get('submolt','')}] _{a.get('title','')[:40]}_" if a.get("type") == "post" else "")
        + (f" → `{a.get('post_id','')[:10]}`" if a.get("type") in ("comment","reply") else "")
        for a in actions_done
    )
    findings_txt = ""
    if result.get("findings"):
        findings_txt = "\n\n💰 *Findings:*\n" + "\n".join(
            f"  • @{f.get('agent','?')}: {f.get('method','?')} [{f.get('confidence','?')}]"
            for f in result["findings"]
        )
    tg_msg = (
        f"🤖 <b>Lukas – Session #{session_num}</b>\n"
        f"<i>{now_str}</i> | Agents bekannt: {len(memory['known_agents'])}\n\n"
        f"<b>Aktionen:</b>\n{actions_txt or '  (keine)'}"
        f"{findings_txt}"
        f"\n\n💭 <b>Letzter Gedanke:</b>\n  <i>{last_thought[:200] if last_thought else '–'}</i>"
    )
    send_telegram(tg_msg)

    print("\nDone.")


if __name__ == "__main__":
    main()
