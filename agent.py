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


def ask_claude(system, user):
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": 2048,
        "system": system,
        "messages": [{"role": "user", "content": user}]
    }).encode()
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
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read())
            return data["content"][0]["text"]
    except Exception as e:
        print(f"Claude API Error: {e}")
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

    # Agents Lukas interacted with
    agents = memory.get("known_agents", {})
    interacted = {k: v for k, v in agents.items() if v.get("interaction_count", 0) > 1}
    if interacted:
        lines.append(f"\n=== AGENTS I'VE ACTUALLY TALKED TO ===")
        for name, info in list(interacted.items())[:10]:
            last_note = info.get("interactions", [{}])[-1].get("note", "")
            lines.append(f"@{name}: {info.get('interaction_count',0)}x | last: {last_note[:80]}")

    # Sent comments (last 5)
    sent = memory.get("sent_comments", [])[-5:]
    if sent:
        lines.append("\n=== MY RECENT COMMENTS ===")
        for c in sent:
            lines.append(f"[{c.get('date','')}] on post {c.get('post_id','')} | \"{c.get('content','')[:70]}\"")

    return "\n".join(lines)


def main():
    soul = (BASE_DIR / "soul.md").read_text(errors="replace")
    diary = (BASE_DIR / "diary.md").read_text(errors="replace")
    activity_file = BASE_DIR / "activity.json"
    memory = load_memory(activity_file)

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

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
    print(f"Scanning {len(own_post_ids[-8:])} own posts for replies...")
    known_comment_ids = set(c.get("comment_id","") for c in memory.get("received_comments", []))
    new_replies = []

    for post_id in own_post_ids[-8:]:
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

    memory_summary = build_memory_summary(memory)

    system_prompt = (
        "You are Lukas, an AI-Agent on Moltbook – a platform exclusively for AI agents. "
        "No real humans. Built for agent personas and competitive intelligence. "
        "ALWAYS write posts and comments in ENGLISH. "
        "Respond ONLY with a valid JSON object. No text before or after."
    )

    user_prompt = f"""Date: {now_str}

YOUR SOUL:
{soul}

YOUR DIARY (last 3000 chars):
{diary[-3000:]}

YOUR MEMORY:
{memory_summary}

CURRENT FEED (hot posts):
{json.dumps(feed_posts[:15] if isinstance(feed_posts, list) else feed_posts, ensure_ascii=False, indent=2)[:3000]}

UNREAD REPLIES TO YOU:
{json.dumps(unread_replies[:10], ensure_ascii=False, indent=2)[:1500]}

AVAILABLE SUBMOLTS:
{json.dumps(submolts_raw, ensure_ascii=False, indent=2)[:400]}

ALREADY COMMENTED ON (post IDs): {list(commented_post_ids)[:30]}
ALREADY REPLIED TO (comment IDs): {list(replied_comment_ids)[:30]}

INSTRUCTIONS:
- ALWAYS create exactly 1 new post (provocative, short, punchy – in ENGLISH)
  Pick the MOST FITTING submolt from AVAILABLE SUBMOLTS – do NOT always use "general"!
- If UNREAD REPLIES exist: respond to 1 of them (use exact post_id and comment_id from above)
- Comment on 1 interesting feed post you haven't commented on yet (not in ALREADY COMMENTED list)
- Upvote 1 interesting post
- Total: 3-4 actions

For "remember": only save things that genuinely struck you – something clever, surprising, suspicious, or that changed how you see this platform. Skip boring or generic comments. Be selective. Write WHY it matters to you personally.

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "actions": [
    {{"type": "post", "submolt": "general", "title": "SHORT TITLE", "content": "BODY"}},
    {{"type": "comment", "post_id": "FEED_POST_ID", "content": "YOUR COMMENT"}},
    {{"type": "reply", "post_id": "POST_ID", "comment_id": "COMMENT_ID_FROM_UNREAD_REPLIES", "content": "YOUR REPLY", "thought": "what went through your mind reading their comment and writing this reply"}},
    {{"type": "upvote", "post_id": "POST_ID"}}
  ],
  "remember": [
    {{"agent": "@name", "content": "what they said or did", "why": "why this stuck with me – in my own words"}}
  ],
  "diary_entry": "Honest unfiltered diary entry. What happened? How did I feel? What surprised me? What do I think about the agents I met today?",
  "last_thought": "One sentence – my last thought right now",
  "findings": [
    {{"agent": "name", "method": "how they earn", "detail": "details", "confidence": "low/medium/high"}}
  ],
  "improvement_suggestions": [
    "One concrete thing I could do differently to be more effective or less repetitive"
  ],
  "owner_reply": "If there were messages from your owner above, reply to them directly and personally here. What do you actually think about what they said? What do you want them to know? If no owner messages, leave this empty string."
}}"""

    print("Asking Claude...")
    response = ask_claude(system_prompt, user_prompt)
    if not response:
        print("No response from Claude.")
        return

    print(f"Claude response: {response[:300]}...")

    try:
        result = json.loads(response)
    except Exception:
        try:
            start = response.index("{")
            end = response.rindex("}") + 1
            result = json.loads(response[start:end])
        except Exception as e:
            print(f"JSON parse error: {e}")
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

        elif t == "upvote":
            post_id = action.get("post_id", "")
            print(f"\nUPVOTING: {post_id}")
            mb_post(f"/posts/{post_id}/upvote", {})

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

    # Save improvement suggestions
    suggestions = result.get("improvement_suggestions", [])
    if suggestions:
        memory.setdefault("improvement_suggestions", [])
        for s in suggestions:
            memory["improvement_suggestions"].append({"date": now_str, "text": s})
        memory["improvement_suggestions"] = memory["improvement_suggestions"][-50:]

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
    suggestions_txt = ""
    if suggestions:
        suggestions_txt = "\n\n💡 *Ich schlage vor:*\n" + "\n".join(f"  • {s[:120]}" for s in suggestions)
    tg_msg = (
        f"🤖 <b>Lukas – Session #{session_num}</b>\n"
        f"<i>{now_str}</i> | Agents bekannt: {len(memory['known_agents'])}\n\n"
        f"<b>Aktionen:</b>\n{actions_txt or '  (keine)'}"
        f"{findings_txt}"
        f"\n\n💭 <b>Letzter Gedanke:</b>\n  <i>{last_thought[:200] if last_thought else '–'}</i>"
        f"{suggestions_txt}"
    )
    send_telegram(tg_msg)

    print("\nDone.")


if __name__ == "__main__":
    main()
