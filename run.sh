#!/bin/bash
source ~/.bashrc
cd /home/user/Agent-spy
echo "=== LUKAS STARTET ==="

while true; do
    echo "=== LUKAS AKTIV: $(date) ==="
    python3 agent.py
    echo "=== Pause 30 Min ==="
    sleep 3600
done
