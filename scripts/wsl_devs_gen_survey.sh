#!/bin/bash
# Run the DEVS-Gen survey inside WSL. Reads the release only.
cd "$HOME/trust2027/devs_gen_code" || exit 1
.venvs/devs-gen/bin/python "$1" "$PWD"
