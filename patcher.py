#!/usr/bin/env python3
"""
patcher.py – Lukas verbessert sich selbst.
Wird von run.sh nach jeder Session aufgerufen.
Liest self_improvement aus dem letzten agent output und patcht den Code.
Nur agent.py und soul.md sind erlaubt.
"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
ALLOWED_FILES = {"agent.py", "soul.md"}
PATCH_LOG = BASE_DIR / "patches.md"


def apply_patch(patch):
    filename = patch.get("file", "").strip()
    description = patch.get("description", "")
    old_code = patch.get("old_code", "")
    new_code = patch.get("new_code", "")

    if filename not in ALLOWED_FILES:
        print(f"  [Patcher] BLOCKED: {filename} not in allowed files")
        return False

    if not old_code or not new_code:
        print(f"  [Patcher] SKIP: empty old_code or new_code")
        return False

    filepath = BASE_DIR / filename
    if not filepath.exists():
        print(f"  [Patcher] SKIP: {filename} not found")
        return False

    content = filepath.read_text(errors="replace")

    if old_code not in content:
        print(f"  [Patcher] SKIP: old_code not found in {filename}")
        print(f"    Looking for: {old_code[:80]}...")
        return False

    # Backup before patching
    backup = filepath.with_suffix(filepath.suffix + ".prepatch")
    backup.write_text(content)

    # Apply patch
    new_content = content.replace(old_code, new_code, 1)
    filepath.write_text(new_content)

    # Validate syntax if Python
    if filename.endswith(".py"):
        result = subprocess.run(
            ["python3", "-c", f"import py_compile; py_compile.compile('{filepath}', doraise=True)"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  [Patcher] SYNTAX ERROR – reverting: {result.stderr[:200]}")
            filepath.write_text(content)
            backup.unlink(missing_ok=True)
            return False
        backup.unlink(missing_ok=True)

    # Log the patch
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(PATCH_LOG, "a") as f:
        f.write(f"\n## [{now}] {filename}\n")
        f.write(f"**Reason:** {description}\n\n")
        f.write(f"```diff\n- {old_code[:200]}\n+ {new_code[:200]}\n```\n")

    print(f"  [Patcher] ✓ Patched {filename}: {description[:80]}")
    return True


def main():
    # Read pending patches from self_improvement.json (written by agent.py)
    patch_file = BASE_DIR / "self_improvement.json"
    if not patch_file.exists():
        return

    try:
        patches = json.loads(patch_file.read_text())
    except Exception as e:
        print(f"  [Patcher] Read error: {e}")
        return

    if not patches:
        return

    print(f"  [Patcher] Applying {len(patches)} patch(es)...")
    applied = 0
    for patch in patches:
        if apply_patch(patch):
            applied += 1

    # Clear the queue
    patch_file.unlink(missing_ok=True)

    if applied > 0:
        # Commit self-improvements to git
        subprocess.run(["git", "add", "agent.py", "soul.md", "patches.md"],
                      capture_output=True, cwd=BASE_DIR)
        msg = f"self-improvement: {applied} patch(es) by Lukas"
        subprocess.run(["git", "commit", "-m", msg],
                      capture_output=True, cwd=BASE_DIR)
        subprocess.run(["git", "push", "origin",
                       "HEAD:claude/bot-communication-system-eriiT", "--force"],
                      capture_output=True, cwd=BASE_DIR)
        print(f"  [Patcher] Committed and pushed {applied} self-improvement(s).")


if __name__ == "__main__":
    main()
