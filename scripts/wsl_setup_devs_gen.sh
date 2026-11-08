#!/bin/bash
# Set up the pinned DEVS-Gen release inside WSL, without sudo or system changes. Everything lives in ~/trust2027.
# Adaptation Category 1: the evaluator's hardcoded bubblewrap path points at an unpacked official Ubuntu package.
set -u
COMMIT=f7461b9f9d23e5c590975d7ecb3a58092c34204a
HOME_DIR="$HOME/trust2027"
mkdir -p "$HOME_DIR" && cd "$HOME_DIR" || exit 1

if [ ! -d devs_gen_code ]; then
  git clone --quiet https://github.com/czyarl/devs_gen_code.git devs_gen_code || exit 1
fi
git -C devs_gen_code checkout --quiet "$COMMIT" || exit 1
echo "commit $(git -C devs_gen_code rev-parse HEAD)"

if [ ! -x tools/usr/bin/bwrap ]; then
  mkdir -p tools/deb && cd tools/deb || exit 1
  apt-get download bubblewrap >/dev/null 2>&1 || { echo "apt-get download failed"; exit 1; }
  dpkg -x bubblewrap_*.deb "$HOME_DIR/tools" || exit 1
  cd "$HOME_DIR" || exit 1
fi
"$HOME_DIR/tools/usr/bin/bwrap" --version

BW="$HOME_DIR/tools/usr/bin/bwrap"
sed -i "s#bwrap = Path(\"/usr/bin/bwrap\")#bwrap = Path(\"$BW\")#" devs_gen_code/src/devs_eval/pipeline.py
git -C devs_gen_code diff --stat
git -C devs_gen_code diff > "$HOME_DIR/category1.diff"

if [ ! -x tools/uv ]; then
  curl -sSL https://github.com/astral-sh/uv/releases/download/0.9.5/uv-x86_64-unknown-linux-gnu.tar.gz -o tools/uv.tgz || exit 1
  tar -xzf tools/uv.tgz -C tools --strip-components=1 || exit 1
fi
UV="$HOME_DIR/tools/uv"
"$UV" --version

cd devs_gen_code || exit 1
if [ ! -x .venvs/devs-gen/bin/python ]; then
  "$UV" venv --python 3.10 .venvs/devs-gen || exit 1
  "$UV" pip install --python .venvs/devs-gen/bin/python -r envs/devs_gen.txt 2>&1 | tail -1
  "$UV" pip install --python .venvs/devs-gen/bin/python . src/third_party/xdevspy simpy==4.1.1 2>&1 | tail -1
fi
.venvs/devs-gen/bin/python --version
"$UV" pip freeze --python .venvs/devs-gen/bin/python > "$HOME_DIR/requirements.lock"
wc -l "$HOME_DIR/requirements.lock"

echo "--- smoke: reproduce bundled programs against reported scores"
.venvs/devs-gen/bin/python src/recheck_results.py --method devs_gen --model gpt --scenario ABP --limit 1 --output "$HOME_DIR/abp_recheck.csv" 2>&1 | tail -6
cat "$HOME_DIR/abp_recheck.csv" | cut -c1-400 | head -4
echo "--- generated"
find generated/devs_gen -name run.py | wc -l
ls benchmark
