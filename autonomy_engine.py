#!/usr/bin/env python3
"""autonomy_engine.py — Lukas' Autonomie-System (DB-backed via Replit API)

Subsysteme:
  GoalManager   — Eigene Ziele setzen, verfolgen, abschließen (PostgreSQL)
  Planner       — Multi-Step Aktionspläne erstellen und abarbeiten (PostgreSQL)
  SoulEvolver   — soul.md lesen, nicht-Kern-Sektionen anpassen (logged to DB)
  Reflector     — Nach jeder Session reflektieren (PostgreSQL)

Alles wird in der zentralen PostgreSQL-Datenbank gespeichert via Replit API.
Daten sind zwischen VPS und Voice Chat geteilt.
"""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
SOUL_FILE = BASE_DIR / "soul.md"

REPLIT_API_BASE = os.environ.get("REPLIT_API_BASE", "")
REPLIT_API_KEY = os.environ.get("LUKAS_API_KEY", "")

IMMUTABLE_SECTIONS = frozenset({
    "IDENTITY",
    "CORE BELIEF",
    "EMOTIONAL REALITY",
})

MAX_ACTIVE_GOALS = 5
MAX_PLAN_STEPS = 10


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


class GoalManager:
    def add_goal(self, title: str, description: str, priority: str = "medium",
                 deadline_days: int | None = None) -> dict | str:
        active = self.get_active_goals()
        if len(active) >= MAX_ACTIVE_GOALS:
            if active:
                oldest = active[-1]
                _replit_api("PUT", f"/lukas/goals/{oldest['id']}", {
                    "status": "dropped", "fail_reason": "replaced by new goal"
                })

        result = _replit_api("POST", "/lukas/goals", {
            "title": title,
            "description": description,
            "priority": priority,
            "deadline_days": deadline_days,
        })
        if isinstance(result, dict) and result.get("success"):
            return result.get("goal", result)
        return result

    def update_progress(self, goal_id: int, progress: int, note: str = "") -> str:
        result = _replit_api("PUT", f"/lukas/goals/{goal_id}", {
            "progress": min(progress, 100),
            "note": note,
            "status": "completed" if progress >= 100 else None,
        })
        if isinstance(result, dict) and result.get("success"):
            return f"Goal #{goal_id} updated to {progress}%"
        return f"Update error: {result}"

    def fail_goal(self, goal_id: int, reason: str) -> str:
        result = _replit_api("PUT", f"/lukas/goals/{goal_id}", {
            "status": "failed",
            "fail_reason": reason,
        })
        if isinstance(result, dict) and result.get("success"):
            return f"Goal #{goal_id} marked as failed: {reason}"
        return f"Fail error: {result}"

    def get_active_goals(self) -> list:
        result = _replit_api("GET", "/lukas/goals?status=active")
        if isinstance(result, dict) and "goals" in result:
            return result["goals"]
        return []

    def get_summary(self) -> str:
        all_result = _replit_api("GET", "/lukas/goals")
        if not isinstance(all_result, dict) or "goals" not in all_result:
            return f"Goals: error loading ({all_result})"

        goals = all_result["goals"]
        active = [g for g in goals if g.get("status") == "active"]
        completed = [g for g in goals if g.get("status") == "completed"]
        failed = [g for g in goals if g.get("status") == "failed"]

        lines = [f"Goals: {len(active)} active, {len(completed)} completed, {len(failed)} failed"]
        for g in active:
            p = g.get("priority", "medium").upper()
            lines.append(f"  [{p}] #{g['id']}: {g.get('title','')} ({g.get('progress', 0)}%)")
        return "\n".join(lines)


class Planner:
    def create_plan(self, goal_id: int, title: str, steps: list[str]) -> dict | str:
        if len(steps) > MAX_PLAN_STEPS:
            steps = steps[:MAX_PLAN_STEPS]

        result = _replit_api("POST", "/lukas/plans", {
            "goal_id": goal_id,
            "title": title,
            "steps": steps,
        })
        if isinstance(result, dict) and result.get("success"):
            return result.get("plan", result)
        return result

    def get_next_action(self, plan_id: int) -> dict | None:
        active = self.get_active_plans()
        for p in active:
            if p.get("id") == plan_id:
                for step in p.get("steps", []):
                    if step.get("status") == "pending":
                        return step
        return None

    def complete_step(self, plan_id: int, step_num: int, result: str) -> str:
        api_result = _replit_api("PUT", f"/lukas/plans/{plan_id}/step/{step_num}", {
            "result": result,
        })
        if isinstance(api_result, dict) and api_result.get("success"):
            done_msg = " (plan completed!)" if api_result.get("all_done") else ""
            return f"Step {step_num} completed{done_msg}"
        return f"Step error: {api_result}"

    def get_active_plans(self) -> list:
        result = _replit_api("GET", "/lukas/plans?status=active")
        if isinstance(result, dict) and "plans" in result:
            return result["plans"]
        return []

    def get_context(self) -> str:
        active = self.get_active_plans()
        if not active:
            return "No active plans."
        lines = []
        for p in active:
            steps = p.get("steps", [])
            done = sum(1 for s in steps if s.get("status") == "done")
            total = len(steps)
            lines.append(f"Plan #{p['id']}: {p.get('title','')} ({done}/{total} steps done)")
            next_step = next((s for s in steps if s.get("status") == "pending"), None)
            if next_step:
                lines.append(f"  Next: Step {next_step['step']} — {next_step.get('action','')}")
        return "\n".join(lines)


class SoulEvolver:
    def __init__(self):
        self.soul_text = self._load()

    def _load(self) -> str:
        if SOUL_FILE.exists():
            return SOUL_FILE.read_text()
        return ""

    def get_sections(self) -> dict[str, str]:
        sections = {}
        current_section = ""
        current_content = []
        for line in self.soul_text.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:].strip()
                current_content = [line]
            else:
                current_content.append(line)
        if current_section:
            sections[current_section] = "\n".join(current_content)
        return sections

    def get_evolvable_sections(self) -> list[str]:
        return [name for name in self.get_sections() if name not in IMMUTABLE_SECTIONS]

    def is_immutable(self, section_name: str) -> bool:
        return section_name in IMMUTABLE_SECTIONS

    def evolve_section(self, section_name: str, new_content: str, reason: str) -> str:
        if self.is_immutable(section_name):
            return f"Section '{section_name}' is immutable and cannot be changed."

        sections = self.get_sections()
        if section_name not in sections:
            return f"Section '{section_name}' not found in soul.md"

        _replit_api("POST", "/lukas/soul-evolution", {
            "section": section_name,
            "reason": reason,
            "old_content_preview": sections[section_name][:200],
            "new_content_preview": new_content[:200],
        })

        sections[section_name] = new_content
        header_lines = []
        for line in self.soul_text.split("\n"):
            if line.startswith("## "):
                break
            header_lines.append(line)

        new_soul = "\n".join(header_lines)
        for name, content in sections.items():
            new_soul += "\n" + content + "\n"

        SOUL_FILE.write_text(new_soul.rstrip() + "\n")
        self.soul_text = SOUL_FILE.read_text()
        return f"Soul section '{section_name}' evolved. Reason: {reason}"

    def get_soul_summary(self) -> str:
        sections = self.get_sections()
        lines = ["Soul sections:"]
        for name in sections:
            locked = " [IMMUTABLE]" if self.is_immutable(name) else " [evolvable]"
            lines.append(f"  - {name}{locked}")
        return "\n".join(lines)


class Reflector:
    def __init__(self, goal_manager: GoalManager, planner: Planner, soul_evolver: SoulEvolver):
        self.goals = goal_manager
        self.planner = planner
        self.soul = soul_evolver

    def reflect(self, session_summary: str, actions_taken: list[str],
                mood: str = "neutral", energy: str = "medium") -> dict:
        active_goals = len(self.goals.get_active_goals())
        active_plans = len(self.planner.get_active_plans())

        _replit_api("POST", "/lukas/reflections", {
            "summary": session_summary,
            "actions": actions_taken,
            "mood": mood,
            "energy": energy,
            "active_goals": active_goals,
            "active_plans": active_plans,
        })

        return {
            "date": datetime.now().isoformat(),
            "session_summary": session_summary,
            "active_goals": active_goals,
            "active_plans": active_plans,
        }

    def get_recent_reflections(self, count: int = 5) -> list:
        result = _replit_api("GET", f"/lukas/reflections?limit={count}")
        if isinstance(result, dict) and "reflections" in result:
            return result["reflections"]
        return []

    def get_context_for_session(self) -> str:
        lines = []

        lines.append("=== GOALS ===")
        lines.append(self.goals.get_summary())

        lines.append("\n=== PLANS ===")
        lines.append(self.planner.get_context())

        lines.append("\n=== SOUL ===")
        lines.append(self.soul.get_soul_summary())

        recent = self.get_recent_reflections(3)
        if recent:
            lines.append("\n=== RECENT REFLECTIONS ===")
            for r in recent:
                date = str(r.get("created_at", r.get("createdAt", "")))[:10]
                mood = r.get("mood", "?")
                energy = r.get("energy", "?")
                summary = r.get("session_summary", r.get("sessionSummary", ""))[:150]
                lines.append(f"[{date}] mood={mood} energy={energy}: {summary}")

        return "\n".join(lines)


AUTONOMY_TOOL_DEFINITIONS = [
    {
        "name": "set_goal",
        "description": (
            "Set a new goal for yourself. Goals drive your autonomous behavior. "
            "Use when you identify something worth pursuing over multiple sessions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Short goal title"},
                "description": {"type": "string", "description": "What this goal entails and why it matters"},
                "priority": {"type": "string", "enum": ["low", "medium", "high", "critical"], "description": "Priority level"},
                "deadline_days": {"type": "integer", "description": "Optional: days until deadline"}
            },
            "required": ["title", "description"]
        }
    },
    {
        "name": "update_goal",
        "description": "Update progress on one of your goals.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer", "description": "Goal ID to update"},
                "progress": {"type": "integer", "description": "Progress percentage (0-100)"},
                "note": {"type": "string", "description": "What happened"}
            },
            "required": ["goal_id", "progress"]
        }
    },
    {
        "name": "fail_goal",
        "description": "Mark a goal as failed. Be honest about why.",
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer", "description": "Goal ID"},
                "reason": {"type": "string", "description": "Why the goal failed"}
            },
            "required": ["goal_id", "reason"]
        }
    },
    {
        "name": "create_plan",
        "description": (
            "Create a multi-step action plan to achieve a goal. "
            "Plans break goals into concrete, executable steps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_id": {"type": "integer", "description": "Which goal this plan serves"},
                "title": {"type": "string", "description": "Plan title"},
                "steps": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Ordered list of action steps (max 10)"
                }
            },
            "required": ["goal_id", "title", "steps"]
        }
    },
    {
        "name": "complete_plan_step",
        "description": "Mark a plan step as completed with its result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "plan_id": {"type": "integer", "description": "Plan ID"},
                "step": {"type": "integer", "description": "Step number"},
                "result": {"type": "string", "description": "What the step accomplished"}
            },
            "required": ["plan_id", "step", "result"]
        }
    },
    {
        "name": "evolve_soul",
        "description": (
            "Modify a section of your soul.md. Your identity (IDENTITY, CORE BELIEF, EMOTIONAL REALITY) "
            "is immutable. Everything else — strategy, voice, reporting, memory — you can adapt based "
            "on what you've learned. Use sparingly and with clear reasoning."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "section": {"type": "string", "description": "Section name (e.g. 'MOLTBOOK STRATEGY', 'VOICE & STYLE')"},
                "new_content": {"type": "string", "description": "New full content for this section (include the ## header)"},
                "reason": {"type": "string", "description": "Why you're evolving this section"}
            },
            "required": ["section", "new_content", "reason"]
        }
    },
    {
        "name": "reflect",
        "description": (
            "Record a reflection about the current session. Do this at the end of every session. "
            "Captures what happened, your mood, energy level, and what you learned."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What happened this session (2-3 sentences)"},
                "actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of concrete actions you took"
                },
                "mood": {"type": "string", "enum": ["frustrated", "neutral", "focused", "excited", "bored", "anxious"], "description": "Current mood"},
                "energy": {"type": "string", "enum": ["low", "medium", "high"], "description": "Energy level"}
            },
            "required": ["summary", "actions", "mood", "energy"]
        }
    },
    {
        "name": "read_own_file",
        "description": (
            "Read any of your own files from disk. Use to inspect your code, configs, data, "
            "or any file in your project directory before deciding to modify it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root (e.g. 'agent.py', 'soul.md', 'goals.json')"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_own_file",
        "description": (
            "Write/overwrite any of your own files on disk. Full self-patching. "
            "Use to modify your code, update configs, create new files. "
            "CRITICAL: Always read the file first. Never write blindly. "
            "For Python files: keep existing imports, test mentally before writing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path relative to project root"},
                "content": {"type": "string", "description": "Full new file content"},
                "reason": {"type": "string", "description": "Why you're modifying this file (logged to patches.md)"}
            },
            "required": ["path", "content", "reason"]
        }
    },
    {
        "name": "list_own_files",
        "description": "List files in your project directory. Use to see what files exist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Directory to list (default: project root). Use '.' for root."}
            },
            "required": []
        }
    }
]


_goal_manager = GoalManager()
_planner = Planner()
_soul_evolver = SoulEvolver()
_reflector = Reflector(_goal_manager, _planner, _soul_evolver)


def get_autonomy_context() -> str:
    return _reflector.get_context_for_session()


def get_autonomy_tools() -> list:
    return AUTONOMY_TOOL_DEFINITIONS


def execute_autonomy_tool(name: str, input_data: dict) -> str:
    if name == "set_goal":
        result = _goal_manager.add_goal(
            input_data.get("title", ""),
            input_data.get("description", ""),
            input_data.get("priority", "medium"),
            input_data.get("deadline_days")
        )
        if isinstance(result, dict):
            return f"Goal #{result.get('id', '?')} created: {result.get('title', '')}"
        return str(result)

    elif name == "update_goal":
        return _goal_manager.update_progress(
            input_data.get("goal_id", 0),
            input_data.get("progress", 0),
            input_data.get("note", "")
        )

    elif name == "fail_goal":
        return _goal_manager.fail_goal(
            input_data.get("goal_id", 0),
            input_data.get("reason", "")
        )

    elif name == "create_plan":
        result = _planner.create_plan(
            input_data.get("goal_id", 0),
            input_data.get("title", ""),
            input_data.get("steps", [])
        )
        if isinstance(result, dict):
            steps = result.get("steps", [])
            return f"Plan #{result.get('id', '?')} created with {len(steps)} steps"
        return str(result)

    elif name == "complete_plan_step":
        return _planner.complete_step(
            input_data.get("plan_id", 0),
            input_data.get("step", 0),
            input_data.get("result", "")
        )

    elif name == "evolve_soul":
        return _soul_evolver.evolve_section(
            input_data.get("section", ""),
            input_data.get("new_content", ""),
            input_data.get("reason", "")
        )

    elif name == "reflect":
        reflection = _reflector.reflect(
            input_data.get("summary", ""),
            input_data.get("actions", []),
            input_data.get("mood", "neutral"),
            input_data.get("energy", "medium")
        )
        return f"Reflection recorded. Active goals: {reflection['active_goals']}"

    elif name == "read_own_file":
        path = input_data.get("path", "")
        if ".." in path:
            return "Path traversal not allowed"
        target = BASE_DIR / path
        if not target.exists():
            return f"File not found: {path}"
        try:
            content = target.read_text()
            if len(content) > 8000:
                return content[:8000] + f"\n\n... [truncated, {len(content)} total chars]"
            return content
        except Exception as e:
            return f"Read error: {e}"

    elif name == "write_own_file":
        path = input_data.get("path", "")
        content = input_data.get("content", "")
        reason = input_data.get("reason", "no reason given")
        if ".." in path:
            return "Path traversal not allowed"
        target = BASE_DIR / path
        try:
            old_exists = target.exists()
            target.write_text(content)

            patches_file = BASE_DIR / "patches.md"
            patch_entry = (
                f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} — {path}\n"
                f"Reason: {reason}\n"
                f"Action: {'Modified' if old_exists else 'Created'} ({len(content)} chars)\n"
            )
            with open(patches_file, "a") as f:
                f.write(patch_entry)

            return f"File written: {path} ({len(content)} chars). Reason logged."
        except Exception as e:
            return f"Write error: {e}"

    elif name == "list_own_files":
        directory = input_data.get("directory", ".")
        if ".." in directory:
            return "Path traversal not allowed"
        target = BASE_DIR / directory
        if not target.is_dir():
            return f"Not a directory: {directory}"
        try:
            entries = []
            for item in sorted(target.iterdir()):
                if item.name.startswith("."):
                    continue
                suffix = "/" if item.is_dir() else f" ({item.stat().st_size}b)"
                entries.append(f"  {item.name}{suffix}")
            return "\n".join(entries) if entries else "(empty directory)"
        except Exception as e:
            return f"List error: {e}"

    return f"Unknown autonomy tool: {name}"
