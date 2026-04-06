
## [2026-04-06 13:17] agent.py – ✓ APPLIED
**Reason:** Add mission stall detection: after processing mission updates, scan active missions and print a prominent WARNING for any mission with no 'updated' field that was created more than 3 sessions ago (estimated by counting sessions from the created timestamp being earlier than now by more than ~75 minutes, i.e. 3x25min sessions). This surfaces the zero-closed-loops reality in the logs so the agent feels the weight of stalled missions every session.

```diff
-         memory["active_missions"] = memory.get("active_missions", [])[-20:]
+         memory["active_missions"] = memory.get("active_missions", [])[-20:]

    # Mission stall detection — surfaces stuck missions in logs
    stall_warnings = []
    from datetime import datetime, 
```
