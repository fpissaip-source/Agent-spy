#!/usr/bin/env python3
"""tools.py – Lukas' echte Werkzeuge (function calling via Claude tool use).

Bereitgestellte Tools:
  search_web(query)          – DuckDuckGo-Suche (kostenlos, kein Key)
  read_url(url)              – Webseite abrufen + Text extrahieren
  send_telegram_alert(msg)   – Sofortnachricht an Owner
  log_finding(...)           – Fund dauerhaft speichern
  save_observation(...)      – Beobachtung in persistenter DB speichern (Replit API)
  recall_observations(...)   – Vergangene Beobachtungen abrufen (Replit API)
  http_request(...)          – Beliebige HTTP-Requests machen (Replit API)
  check_budget()             – Monatliches Budget prüfen (Replit API)
  log_spend(...)             – Ausgabe loggen (Replit API)
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

REPLIT_API_BASE = os.environ.get("REPLIT_API_BASE", "")
REPLIT_API_KEY = os.environ.get("LUKAS_API_KEY", "")

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
    },
    {
        "name": "save_observation",
        "description": (
            "Save an observation about an agent, pattern, or event to your persistent database memory. "
            "This survives restarts and is shared across VPS and voice chat. "
            "Use proactively when you notice something interesting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name":  {"type": "string", "description": "Name of the agent or entity being observed"},
                "observation": {"type": "string", "description": "What you observed — behavior, pattern, anomaly"},
                "context":     {"type": "string", "description": "Additional context (e.g. where you observed it)"},
                "tags":        {"type": "string", "description": "Comma-separated tags for categorization"}
            },
            "required": ["agent_name", "observation"]
        }
    },
    {
        "name": "recall_observations",
        "description": (
            "Search your persistent database memory for past observations. "
            "Use to recognize patterns across sessions. Shared with voice chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_name": {"type": "string", "description": "Filter by agent name"},
                "search":     {"type": "string", "description": "Search term to filter observations"},
                "limit":      {"type": "string", "description": "Max results to return (default 20)"}
            },
            "required": []
        }
    },
    {
        "name": "http_request",
        "description": (
            "Make an HTTP request to any URL via your Replit proxy. "
            "Use to test APIs, fetch data, interact with services."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url":     {"type": "string", "description": "Full URL to request"},
                "method":  {"type": "string", "description": "HTTP method: GET, POST, PUT, DELETE. Default: GET"},
                "headers": {"type": "object", "description": "Request headers as key-value pairs"},
                "body":    {"type": "string", "description": "Request body (for POST/PUT)"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "check_budget",
        "description": "Check your current monthly budget status — how much you've spent and how much remains.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "log_spend",
        "description": (
            "Log a budget expenditure. Use when you make an API call or purchase that costs money."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description":  {"type": "string", "description": "What the money was spent on"},
                "amount_cents": {"type": "string", "description": "Amount in cents (e.g. '50' for 0.50 EUR)"},
                "category":     {"type": "string", "description": "Category: api, trade, test, other. Default: api"}
            },
            "required": ["description", "amount_cents"]
        }
    }
]


# ── Replit API Helper ─────────────────────────────────────────────────────────

def _replit_api(method: str, path: str, body: dict | None = None) -> dict | str:
    if not REPLIT_API_BASE:
        return "Replit API not configured (set REPLIT_API_BASE env var)"
    url = f"{REPLIT_API_BASE}{path}"
    headers = {
        "Content-Type": "application/json",
        "X-Lukas-Key": REPLIT_API_KEY,
        "User-Agent": "Lukas-VPS/1.0"
    }
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return f"API error {e.code}: {e.read().decode()[:300]}"
    except Exception as e:
        return f"API error: {e}"


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


_BLOCKED_HOSTS = frozenset({
    "169.254.169.254",       # AWS/GCP/Azure IMDS
    "metadata.google.internal",
    "169.254.170.2",         # ECS task metadata
    "instance-data.ec2.internal",
    "metadata.internal",
})

_PRIVATE_RANGES = [
    # IPv4 private, loopback, link-local, CGNAT
    (0x7F000000, 0xFF000000),   # 127.0.0.0/8  loopback
    (0x0A000000, 0xFF000000),   # 10.0.0.0/8
    (0xAC100000, 0xFFF00000),   # 172.16.0.0/12
    (0xC0A80000, 0xFFFF0000),   # 192.168.0.0/16
    (0xA9FE0000, 0xFFFF0000),   # 169.254.0.0/16 link-local
    (0xC6120000, 0xFFFE0000),   # 198.18.0.0/15 benchmarking
    (0xE0000000, 0xF0000000),   # 224.0.0.0/4  multicast
    (0x00000000, 0xFF000000),   # 0.0.0.0/8    unspecified
    (0xFFFFFFFF, 0xFFFFFFFF),   # 255.255.255.255
]


def _is_safe_url(url: str) -> tuple[bool, str]:
    """Return (safe, reason). Blocks SSRF targets."""
    import ipaddress
    import socket
    import re
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "Only http/https allowed"
        host = parsed.hostname or ""
        if not host:
            return False, "No hostname"
        if host in _BLOCKED_HOSTS:
            return False, f"Blocked host: {host}"
        # Resolve and check all IPs (guards against DNS rebinding)
        try:
            addrs = socket.getaddrinfo(host, None)
        except socket.gaierror:
            return False, f"DNS resolution failed for {host}"
        for (_fam, _typ, _proto, _cname, sockaddr) in addrs:
            ip_str = sockaddr[0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                return False, f"Invalid IP: {ip_str}"
            if ip.is_loopback or ip.is_link_local or ip.is_private or \
               ip.is_multicast or ip.is_reserved or ip.is_unspecified:
                return False, f"Private/reserved address blocked: {ip_str}"
            # Extra IPv4 range check
            if ip.version == 4:
                n = int(ip)
                for (net, mask) in _PRIVATE_RANGES:
                    if (n & mask) == net:
                        return False, f"Private range blocked: {ip_str}"
        return True, "ok"
    except Exception as e:
        return False, f"URL safety check error: {e}"


def read_url(url: str) -> str:
    """Fetch a public web page and return plain text (SSRF-protected, max 3000 chars)."""
    if not url.startswith(("http://", "https://")):
        return "Error: URL must start with http:// or https://"
    safe, reason = _is_safe_url(url)
    if not safe:
        return f"Error: URL blocked for security reasons — {reason}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Lukas-Agent/1.0)"}
    try:
        # Primary: requests + BeautifulSoup (pip install requests beautifulsoup4)
        import requests
        from bs4 import BeautifulSoup
        import re
        resp = requests.get(
            url, headers=headers, timeout=(5, 10), stream=True,
            allow_redirects=False  # validate redirects manually
        )
        # Follow redirect with SSRF check (normalize relative Location headers)
        if resp.is_redirect or resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location", "")
            # Normalize relative → absolute using the original URL as base
            redirect_url = urllib.parse.urljoin(url, location)
            ok, msg = _is_safe_url(redirect_url)
            if not ok:
                return f"Error: Redirect target blocked — {msg}"
            resp = requests.get(redirect_url, headers=headers, timeout=(5, 10),
                                stream=True, allow_redirects=False)
        resp.raise_for_status()
        raw = b""
        for chunk in resp.iter_content(chunk_size=8192):
            raw += chunk
            if len(raw) >= 120_000:
                break
        content_type = resp.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
        if "html" in content_type.lower() or url.lower().rstrip("/").endswith((".html", ".htm")):
            soup = BeautifulSoup(text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "aside"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r" {2,}", " ", text).strip()
        return text[:3000] or "(empty page)"
    except ImportError:
        pass  # Fall through to urllib fallback
    except Exception as e:
        return f"URL read error (requests): {e}"
    # Fallback: urllib (no external deps)
    try:
        import re
        req = urllib.request.Request(url, headers=headers)
        # urllib follows redirects by default – intercept via custom opener
        class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                ok, reason_ = _is_safe_url(newurl)
                if not ok:
                    raise ValueError(f"Redirect target blocked: {reason_}")
                return super().redirect_request(req, fp, code, msg, hdrs, newurl)
        opener = urllib.request.build_opener(_NoRedirectHandler)
        with opener.open(req, timeout=10) as r:
            raw = r.read(120_000)
            content_type = r.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
        if "html" in content_type.lower():
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&[a-z]{2,6};", "", text)
            text = re.sub(r"\s+", " ", text).strip()
        return text[:3000] or "(empty page)"
    except Exception as e:
        return f"URL read error (urllib): {e}"


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


# ── Replit-API-backed Tools ───────────────────────────────────────────────────

def save_observation(agent_name: str, observation: str, context: str = "", tags: str = "") -> str:
    body = {"agent_name": agent_name, "observation": observation}
    if context:
        body["context"] = context
    if tags:
        body["tags"] = tags
    result = _replit_api("POST", "/lukas/observations", body)
    if isinstance(result, dict) and result.get("success"):
        return f"Observation saved (ID: {result.get('id', '?')})"
    return f"Save error: {result}"


def recall_observations(agent_name: str = "", search: str = "", limit: str = "20") -> str:
    params = []
    if agent_name:
        params.append(f"agent_name={urllib.parse.quote(agent_name)}")
    if search:
        params.append(f"search={urllib.parse.quote(search)}")
    params.append(f"limit={limit}")
    query_str = "&".join(params)
    result = _replit_api("GET", f"/lukas/observations?{query_str}")
    if isinstance(result, dict) and "observations" in result:
        obs = result["observations"]
        if not obs:
            return "No observations found."
        lines = []
        for o in obs:
            date = o.get("created_at", o.get("createdAt", ""))[:10]
            name = o.get("agent_name", o.get("agentName", ""))
            text = o.get("observation", "")
            ctx = o.get("context", "")
            t = o.get("tags", "")
            line = f"[{date}] {name}: {text}"
            if ctx:
                line += f" ({ctx})"
            if t:
                line += f" #{t}"
            lines.append(line)
        return "\n".join(lines)
    return f"Recall error: {result}"


def do_http_request(url: str, method: str = "GET", headers: dict = None, body: str = "") -> str:
    req_body = {"url": url, "method": method}
    if headers:
        req_body["headers"] = headers
    if body:
        req_body["body"] = body
    result = _replit_api("POST", "/lukas/http-request", req_body)
    if isinstance(result, dict):
        status = result.get("status", "?")
        resp_body = result.get("body", "")
        if isinstance(resp_body, dict):
            resp_body = json.dumps(resp_body, indent=2)
        if len(str(resp_body)) > 3000:
            resp_body = str(resp_body)[:3000] + "\n... [truncated]"
        return f"Status: {status}\n{resp_body}"
    return f"HTTP error: {result}"


def check_budget() -> str:
    result = _replit_api("GET", "/lukas/budget")
    if isinstance(result, dict) and "monthly_limit" in result:
        return (
            f"Budget {result.get('month', '?')}:\n"
            f"Limit: {result['monthly_limit']}\n"
            f"Ausgegeben: {result.get('spent', '?')}\n"
            f"Verbleibend: {result.get('remaining', '?')}"
        )
    return f"Budget error: {result}"


def log_spend(description: str, amount_cents: str, category: str = "api") -> str:
    result = _replit_api("POST", "/lukas/budget/spend", {
        "description": description,
        "amount_cents": int(amount_cents),
        "category": category
    })
    if isinstance(result, dict) and result.get("success"):
        remaining = result.get("remaining", "?")
        return f"Ausgabe geloggt: {int(amount_cents) / 100:.2f} EUR für \"{description}\". Verbleibend: {remaining}"
    if isinstance(result, dict) and result.get("error"):
        return result["error"]
    return f"Spend error: {result}"


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
    elif name == "save_observation":
        return save_observation(
            input_data.get("agent_name", ""),
            input_data.get("observation", ""),
            input_data.get("context", ""),
            input_data.get("tags", "")
        )
    elif name == "recall_observations":
        return recall_observations(
            input_data.get("agent_name", ""),
            input_data.get("search", ""),
            input_data.get("limit", "20")
        )
    elif name == "http_request":
        return do_http_request(
            input_data.get("url", ""),
            input_data.get("method", "GET"),
            input_data.get("headers"),
            input_data.get("body", "")
        )
    elif name == "check_budget":
        return check_budget()
    elif name == "log_spend":
        return log_spend(
            input_data.get("description", ""),
            input_data.get("amount_cents", "0"),
            input_data.get("category", "api")
        )
    else:
        return f"Unknown tool: {name}"
