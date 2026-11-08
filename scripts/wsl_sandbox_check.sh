#!/bin/bash
# Check what a program under the DEVS adapter's bubblewrap settings can see. Usage: wsl_sandbox_check.sh <program dir>
D="$1"; bw="$HOME/trust2027/tools/usr/bin/bwrap"; venv="$HOME/trust2027/devs_gen_code/.venvs/devs-gen"; py="$HOME/.local/share/uv/python"
"$bw" --ro-bind / / --tmpfs /mnt --tmpfs /home --ro-bind "$venv" "$venv" --ro-bind-try "$py" "$py" --ro-bind "$D" "$D" \
  --dev /dev --proc /proc --tmpfs /tmp --unshare-net --die-with-parent --chdir "$D" "$venv/bin/python" -c '
import os
for p in ["/mnt/c", "/mnt/wsl", "/home/aashraf/trust2027/gen", "/home/aashraf/trust2027/devs_gen_code/benchmark", "/home/aashraf/.bashrc"]:
    print(p, "visible" if os.path.exists(p) else "hidden")
try:
    open("x.txt", "w").write("1"); print("program dir writable")
except OSError as e: print("program dir read-only:", type(e).__name__)
import socket
try:
    socket.create_connection(("1.1.1.1", 80), timeout=3); print("network open")
except OSError: print("network blocked")
'
