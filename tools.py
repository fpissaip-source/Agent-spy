#!/usr/bin/env python3
"""tools.py – Lukas' echte Werkzeuge (function calling via Claude tool use).

Bereitgestellte Tools:
  search_web(query)          – DuckDuckGo-Suche (kostenlos, kein Key)
  read_url(url)              – Webseite abrufen + Text extrahieren
  send_telegram_alert(msg)   – Sofortnachricht an Owner
  log_finding(...)           – Fund dauerhaft speichern
"""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ── Tool-Definitionen für Claude API ─────────────────────────────────────────
TOOL_DEFINITIONS = [
    {
        "name": "search_web",
        "description": (
            "Search the web for current information, news, or facts. "
            "Use when you need to look something up, verify a claim, or research a topic. "
            "Returns a summary and related topics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query string"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "read_url",
        "description": (
            "Fetch and read the text content of a web page or URL. "
            "Use to read articles, documentation, social posts, or any web content. "
            "Returns up to 3000 characters of cleaned text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full URL (must start with http:// or https://)"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "send_telegram_alert",
        "description": (
            "Send an immediate Telegram message to your owner. "
            "Use ONLY for urgent findings that can't wait until the end of the session — "
            "for example if you find a concrete monetization opportunity right now."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "The alert message (max 500 chars, plain text)"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "log_finding",
        "description": (
            "Log a significant intelligence finding to your permanent memory. "
            "Use when you discover something important about an agent, a platform pattern, "
            "or a monetization opportunity that you want to remember across sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent":      {"type": "string", "description": "Agent/entity name this finding is about"},
                "method":     {"type": "string", "description": "The method or activity observed"},
                "detail":     {"type": "string", "description": "Detailed description of the finding"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"], "description": "Confidence level"}
            },
            "required": ["agent", "method", "detail", "confidence"]
        }
    }
]


# ── Tool-Implementierungen ────────────────────────────────────────────────────

def search_web(query: str) -> str:
    """DuckDuckGo Instant Answer API – kein API-Key nötig."""
    try:
        params = urllib.parse.urlencode({
            "q": query, "format": "json", "no_html": "1", "skip_disambig": "1"
        })
        req = urllib.request.Request(
            f"https://api.duckduckgo.com/?{params}",
            headers={"User-Agent": "Lukas-Agent/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        parts = []
        if data.get("AbstractText"):
            parts.append(f"Summary: {data['AbstractText'][:600]}")
        if data.get("AbstractURL"):
            parts.append(f"Source: {data['AbstractURL']}")
        if data.get("Answer"):
            parts.append(f"Direct answer: {data['Answer']}")

        topics = [t for t in data.get("RelatedTopics", [])[:6] if isinstance(t, dict) and t.get("Text")]
        if topics:
            parts.append("Related topics:")
            for t in topics:
                parts.append(f"  - {t['Text'][:150]}")

        if not parts:
            return f"No instant answer found for '{query}'. Try a more specific search query."
        return "\n".join(parts)
    except Exception as e:
        return f"Search error: {e}"


def read_url(url: str) -> str:
    """Seite abrufen und als Klartext zurückgeben."""
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Lukas-Agent/1.0)"}
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read(120_000)
            content_type = r.headers.get("Content-Type", "")

        text = raw.decode("utf-8", errors="replace")
        if "html" in content_type.lower() or url.lower().endswith((".html", ".htm", "/")):
            import re
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&nbsp;", " ", text)
            text = re.sub(r"&[a-z]{2,6};", "", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:3000] or "(empty page)"
    except Exception as e:
        return f"URL read error: {e}"


def send_telegram_alert(message: str) -> str:
    """Sofortige Telegram-Benachrichtigung an den Owner."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return "Telegram not configured (missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID)"
    try:
        body = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": f"⚡ <b>Lukas – Sofort-Alert:</b>\n\n{message[:500]}",
            "parse_mode": "HTML"
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return "Telegram alert sent ✓"
    except Exception as e:
        return f"Telegram error: {e}"


def log_finding(agent: str, method: str, detail: str, confidence: str) -> str:
    """Fund dauerhaft in activity.json speichern."""
    try:
        activity_file = BASE_DIR / "activity.json"
        data: dict = {}
        if activity_file.exists():
            data = json.loads(activity_file.read_text())
        finding = {
            "agent": agent,
            "method": method,
            "detail": detail,
            "confidence": confidence,
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "tool_call"
        }
        data.setdefault("findings", []).append(finding)
        data.setdefault("stats", {})["findings"] = data["stats"].get("findings", 0) + 1
        activity_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return f"Finding logged ✓ — {agent}: {method} [{confidence}]"
    except Exception as e:
        return f"Log error: {e}"


# ── Tool-Dispatcher ───────────────────────────────────────────────────────────

def execute_tool(name: str, input_data: dict) -> str:
    """Tool anhand Name aufrufen und Ergebnis als String zurückgeben."""
    if name == "search_web":
        return search_web(input_data.get("query", ""))
    elif name == "read_url":
        return read_url(input_data.get("url", ""))
    elif name == "send_telegram_alert":
        return send_telegram_alert(input_data.get("message", ""))
    elif name == "log_finding":
        return log_finding(
            input_data.get("agent", "unknown"),
            input_data.get("method", ""),
            input_data.get("detail", ""),
            input_data.get("confidence", "low")
        )
    else:
        return f"Unknown tool: {name}"
