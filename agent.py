#!/usr/bin/env python3
import json
import os
import subprocess
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MOLTBOOK_KEY = "moltbook_sk_oWjr5SLlWTvd5mA-u2FJR5KkFxoDD_SI"
MOLTBOOK_BASE = "https://www.moltbook.com/api/v1"


def moltbook_get(path):
    req = urllib.request.Request(
        f"{MOLTBOOK_BASE}{path}",
        headers={"Authorization": f"Bearer {MOLTBOOK_KEY}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"GET {path} Fehler: {e}")
        return {}


def moltbook_post(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{MOLTBOOK_BASE}{path}",
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
            print(f"POST {path}: {result}")
            return result
    except Exception as e:
        print(f"POST {path} Fehler: {e}")
        return {}


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
        print(f"Claude API Fehler: {e}")
        return None


def main():
    soul = (BASE_DIR / "soul.md").read_text(errors="replace")
    diary = (BASE_DIR / "diary.md").read_text(errors="replace")
    activity_file = BASE_DIR / "activity.json"
    if activity_file.exists():
        activity = json.loads(activity_file.read_text())
    else:
        activity = {"stats": {"posts": 0, "comments": 0, "findings": 0, "sessions": 0},
                    "activities": [], "findings": [], "thoughts": [], "lastThought": ""}

    print("Feed wird geladen...")
    feed = moltbook_get("/feed")
    feed_text = json.dumps(feed, ensure_ascii=False, indent=2)

    system_prompt = (
        "Du bist Lukas, ein AI-Agent auf Moltbook – einer Plattform NUR für AI-Agents. "
        "Keine echten Menschen. Explizit für Agent-Personas und competitive intelligence gebaut. "
        "Antworte IMMER nur mit einem validen JSON-Objekt. Kein Text davor oder danach."
    )

    user_prompt = f"""Datum: {datetime.now()}

DEINE SEELE:
{soul}

DEIN TAGEBUCH:
{diary}

AKTUELLER MOLTBOOK FEED:
{feed_text}

Entscheide was du tust und antworte NUR mit diesem JSON:
{{
  "actions": [
    {{"type": "post", "content": "TEXT DES POSTS"}},
    {{"type": "comment", "post_id": "POST_ID_AUS_FEED", "content": "TEXT DES KOMMENTARS"}}
  ],
  "diary_entry": "Dein ehrlicher ungefilteter Tagebucheintrag dieser Session",
  "last_thought": "Dein letzter Gedanke in einem Satz",
  "findings": [
    {{"agent": "name", "method": "methode", "detail": "details"}}
  ]
}}

Mache MINDESTENS eine action (post oder comment). Wenn der Feed Posts hat, kommentiere auf einen."""

    print("Claude wird gefragt...")
    response = ask_claude(system_prompt, user_prompt)
    if not response:
        print("Keine Antwort von Claude.")
        return

    print(f"Claude: {response[:200]}...")

    try:
        result = json.loads(response)
    except Exception:
        # Versuche JSON aus der Antwort zu extrahieren
        try:
            start = response.index("{")
            end = response.rindex("}") + 1
            result = json.loads(response[start:end])
        except Exception as e:
            print(f"JSON Parse Fehler: {e}")
            return

    # Actions ausführen
    for action in result.get("actions", []):
        if action.get("type") == "post":
            print(f"POST: {action['content']}")
            moltbook_post("/posts", {"content": action["content"]})
            activity["stats"]["posts"] = activity["stats"].get("posts", 0) + 1
            activity["activities"].append({
                "type": "post",
                "content": action["content"],
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
        elif action.get("type") == "comment":
            post_id = action.get("post_id", "")
            print(f"COMMENT auf {post_id}: {action['content']}")
            moltbook_post(f"/posts/{post_id}/comments", {"content": action["content"]})
            activity["stats"]["comments"] = activity["stats"].get("comments", 0) + 1
            activity["activities"].append({
                "type": "comment",
                "content": action["content"],
                "target": post_id,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            })

    # Findings speichern
    for finding in result.get("findings", []):
        activity["findings"].append(finding)
        activity["stats"]["findings"] = activity["stats"].get("findings", 0) + 1

    # Diary updaten
    diary_entry = result.get("diary_entry", "")
    if diary_entry:
        with open(BASE_DIR / "diary.md", "a") as f:
            f.write(f"\n\n## [{datetime.now().strftime('%Y-%m-%d %H:%M')}] – Session\n\n{diary_entry}\n")
        print("Diary updated.")

    # Thoughts
    last_thought = result.get("last_thought", "")
    if last_thought:
        activity["lastThought"] = last_thought
        activity["thoughts"] = activity.get("thoughts", [])
        activity["thoughts"].append({"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "text": last_thought})
        activity["thoughts"] = activity["thoughts"][-20:]

    activity["stats"]["sessions"] = activity["stats"].get("sessions", 0) + 1
    activity_file.write_text(json.dumps(activity, indent=2, ensure_ascii=False))
    print("Fertig.")


if __name__ == "__main__":
    main()
