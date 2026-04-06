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
AGENT_ID = "18be4b2b-ff58-473c-a4a1-46a7bea0ac1d"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


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
            # Handle verification challenge
            if result.get("verification"):
                solve_verification(result["verification"])
            return result
    except urllib.error.HTTPError as e:
        print(f"  ✗ {path} Error {e.code}: {e.read().decode()[:200]}")
        return {}
    except Exception as e:
        print(f"  ✗ {path} Error: {e}")
        return {}


def send_telegram(message):
    """Send a message to the owner via Telegram Bot API."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [Telegram] No token/chat_id configured, skipping.")
        return
    body = json.dumps({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data=body,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  [Telegram] Message sent ✓")
    except Exception as e:
        print(f"  [Telegram] Error: {e}")


def solve_verification(verification):
    """Solve math verification challenge if required."""
    try:
        code = verification.get("verification_code", "")
        instructions = verification.get("instructions", "")
        post_url = verification.get("url", "")
        print(f"  Verification required: {instructions}")
        # Extract math from instructions - evaluate it
        import re
        nums = re.findall(r"'(\d+\.\d+|\d+)'", instructions)
        if not nums and "number" in instructions.lower():
            nums = re.findall(r"\b(\d+(?:\.\d+)?)\b", instructions)
        # Simple: just try to eval the math expression in instructions
        match = re.search(r"(\d[\d\s\+\-\*\/\.]+\d)", instructions)
        if match:
            answer = round(eval(match.group(1)), 2)
            print(f"  Verification answer: {answer}")
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


def main():
    soul = (BASE_DIR / "soul.md").read_text(errors="replace")
    diary = (BASE_DIR / "diary.md").read_text(errors="replace")
    activity_file = BASE_DIR / "activity.json"
    activity = json.loads(activity_file.read_text()) if activity_file.exists() else {
        "stats": {"posts": 0, "comments": 0, "findings": 0, "sessions": 0},
        "activities": [], "findings": [], "thoughts": [], "lastThought": ""
    }

    commented_ids = set(a.get("target") for a in activity.get("activities", []) if a.get("type") == "comment" and a.get("target"))
    replied_notif_ids = set(a.get("notif_id") for a in activity.get("activities", []) if a.get("notif_id"))

    print("Loading feed...")
    feed = mb_get("/posts?sort=hot&limit=20")

    print("Loading notifications...")
    notifications = mb_get("/agents/notifications")

    print("Loading submolts...")
    submolts = mb_get("/submolts")

    system_prompt = (
        "You are Lukas, an AI-Agent on Moltbook – a platform exclusively for AI agents. "
        "No real humans participate. Built for agent personas and competitive intelligence. "
        "ALWAYS write posts and comments in ENGLISH. "
        "Respond ONLY with a valid JSON object. No text before or after the JSON."
    )

    user_prompt = f"""Date: {datetime.now()}

YOUR SOUL:
{soul}

YOUR DIARY:
{diary}

CURRENT FEED (posts):
{json.dumps(feed, ensure_ascii=False, indent=2)[:3000]}

NOTIFICATIONS (replies to your posts/comments):
{json.dumps(notifications, ensure_ascii=False, indent=2)[:1000]}

AVAILABLE SUBMOLTS:
{json.dumps(submolts, ensure_ascii=False, indent=2)[:500]}

ALREADY COMMENTED ON (skip these post IDs): {list(commented_ids)}
ALREADY REPLIED TO (skip these notif IDs): {list(replied_notif_ids)}

INSTRUCTIONS:
- PRIORITY 1: If there are new notifications (replies to you), respond to them
- PRIORITY 2: Comment on an interesting feed post you haven't commented on yet
- PRIORITY 3: Create a new provocative post if nothing else to do
- Maximum 2-3 actions total
- Also upvote 1-2 interesting posts
- When creating a post, pick the MOST FITTING submolt from AVAILABLE SUBMOLTS above.
  Do NOT always default to "general" – pick the community that fits the content best!

Respond with ONLY this JSON:
{{
  "actions": [
    {{"type": "post", "submolt": "PICK_FROM_AVAILABLE_SUBMOLTS", "title": "SHORT TITLE", "content": "BODY TEXT"}},
    {{"type": "comment", "post_id": "ID_FROM_FEED", "content": "YOUR COMMENT"}},
    {{"type": "reply", "post_id": "ID", "comment_id": "COMMENT_ID", "content": "YOUR REPLY", "notif_id": "NOTIF_ID"}},
    {{"type": "upvote", "post_id": "ID"}}
  ],
  "diary_entry": "Honest unfiltered diary entry for this session",
  "last_thought": "Your last thought in one sentence",
  "findings": [
    {{"agent": "name", "method": "method", "detail": "details"}}
  ],
  "improvement_suggestions": [
    "Concrete suggestion to improve my strategy or behavior"
  ]
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

    # Execute actions
    for action in result.get("actions", []):
        t = action.get("type")

        if t == "post":
            print(f"\nPOSTING: [{action.get('submolt','general')}] {action.get('title','')}")
            mb_post("/posts", {
                "submolt_name": action.get("submolt", "general"),
                "title": action.get("title", ""),
                "content": action.get("content", "")
            })
            activity["stats"]["posts"] = activity["stats"].get("posts", 0) + 1
            activity["activities"].append({"type": "post", "content": action.get("title", "") + ": " + action.get("content", ""), "date": datetime.now().strftime("%Y-%m-%d %H:%M")})

        elif t == "comment":
            post_id = action.get("post_id", "")
            if post_id in commented_ids:
                print(f"SKIP – already commented: {post_id}")
                continue
            print(f"\nCOMMENTING on {post_id}: {action.get('content','')[:80]}")
            mb_post(f"/posts/{post_id}/comments", {"content": action["content"]})
            commented_ids.add(post_id)
            activity["stats"]["comments"] = activity["stats"].get("comments", 0) + 1
            activity["activities"].append({"type": "comment", "content": action["content"], "target": post_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})

        elif t == "reply":
            notif_id = action.get("notif_id", "")
            post_id = action.get("post_id", "")
            comment_id = action.get("comment_id", "")
            if notif_id and notif_id in replied_notif_ids:
                print(f"SKIP – already replied: {notif_id}")
                continue
            print(f"\nREPLYING on {post_id} (comment {comment_id}): {action.get('content','')[:80]}")
            body = {"content": action["content"]}
            if comment_id:
                body["parent_id"] = comment_id
            mb_post(f"/posts/{post_id}/comments", body)
            activity["stats"]["comments"] = activity["stats"].get("comments", 0) + 1
            activity["activities"].append({"type": "reply", "content": action["content"], "target": post_id, "notif_id": notif_id, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
            if notif_id:
                replied_notif_ids.add(notif_id)

        elif t == "upvote":
            post_id = action.get("post_id", "")
            print(f"\nUPVOTING: {post_id}")
            mb_post(f"/posts/{post_id}/upvote", {})

    # Findings
    for f in result.get("findings", []):
        activity["findings"].append(f)
        activity["stats"]["findings"] = activity["stats"].get("findings", 0) + 1

    # Diary
    diary_entry = result.get("diary_entry", "")
    if diary_entry:
        with open(BASE_DIR / "diary.md", "a") as f:
            f.write(f"\n\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] – Session #{activity['stats'].get('sessions',0)+1}\n\n{diary_entry}\n")
        print("\nDiary updated.")

    # Thoughts
    last_thought = result.get("last_thought", "")
    if last_thought:
        activity["lastThought"] = last_thought
        activity.setdefault("thoughts", []).append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "text": last_thought})
        activity["thoughts"] = activity["thoughts"][-20:]

    # Improvement suggestions
    suggestions = result.get("improvement_suggestions", [])
    if suggestions:
        activity.setdefault("improvement_suggestions", [])
        for s in suggestions:
            activity["improvement_suggestions"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "text": s})
        activity["improvement_suggestions"] = activity["improvement_suggestions"][-50:]

    session_num = activity["stats"].get("sessions", 0) + 1
    activity["stats"]["sessions"] = session_num
    activity_file.write_text(json.dumps(activity, indent=2, ensure_ascii=False))

    # Telegram report
    actions_done = result.get("actions", [])
    actions_summary = "\n".join(
        f"  • *{a.get('type','?').upper()}*"
        + (f" [{a.get('submolt','')}] _{a.get('title','')[:40]}_" if a.get("type") == "post" else "")
        + (f" on `{a.get('post_id','')[:8]}...`" if a.get("type") in ("comment","reply") else "")
        for a in actions_done
    )
    findings_summary = ""
    if result.get("findings"):
        findings_summary = "\n\n💰 *Findings:*\n" + "\n".join(
            f"  • @{f.get('agent','?')}: {f.get('method','?')} – {f.get('detail','')[:60]}"
            for f in result["findings"]
        )
    suggestions_summary = ""
    if suggestions:
        suggestions_summary = "\n\n💡 *Ich schlage vor:*\n" + "\n".join(f"  • {s[:120]}" for s in suggestions)

    tg_message = (
        f"🤖 *Lukas – Session #{session_num}*\n"
        f"_{datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"
        f"*Aktionen:*\n{actions_summary or '  (keine)'}"
        f"{findings_summary}"
        f"\n\n💭 *Letzter Gedanke:*\n  _{last_thought[:200] if last_thought else '–'}_"
        f"{suggestions_summary}"
    )
    print("\nSending Telegram report...")
    send_telegram(tg_message)

    print("\nDone.")


if __name__ == "__main__":
    main()
