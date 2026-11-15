#!/usr/bin/env bash
# Copy the DEVS-Gen programs from this artifact to where the scripts look for them inside WSL:
#   $HOME/trust2027/gen/<label>/<task>/<run>/          (scripts/main_runner.py, scripts/pilot_runner.py)
# The scripts name the home folder /home/user/trust2027 (the real account name was replaced for anonymity);
# if your WSL account is not called `user`, either create it or link: sudo ln -s "$HOME" /home/user
# Usage (from the artifact root, inside WSL):  bash scripts/wsl_install_programs.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
dest="${HOME}/trust2027/gen"
mkdir -p "${dest}"
cp -r "${here}/programs/devs_gen/." "${dest}/"
echo "installed $(find "${dest}" -name run.py | wc -l) DEVS-Gen programs under ${dest}"
