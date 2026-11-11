#!/bin/bash
# DEVS-Gen generation under builder isolation (manifests/builder_isolation.md). Same release command and settings as
# wsl_devs_gen_generate.sh, run inside bubblewrap:
#   only /usr and a few non-secret /etc files, an empty /home (no /mnt, /run or /var: every Windows drive, every other
#   build, the session bus and credentials hidden; hardened 2026-11-10, see below), then read-only binds of
#   the DEVS-Gen code and venv with benchmark/, generated/ and results/ emptied, and only this task's folder bound
#   back; the uv Python home; a copy of the provider hook; the workspace (read-write);
#   --unshare-all (new user, PID, IPC, UTS, cgroup and network namespaces), --new-session, inherited descriptors
#   closed, stdin from /dev/null, with one way out: a Unix socket to allow_one_host_proxy.py, which honours only
#   CONNECT api.anthropic.com:443 (logged, with bytes per tunnel); the environment holds PATH, HOME, the proxy,
#   ANTHROPIC_API_KEY and the run's settings only. The key reaches bubblewrap through its environment, never its
#   command line.
# Modes: check  = run check_builder_isolation.py, the proxy probes and a /home listing inside the same sandbox; the
#                 first output line is `NONCE <token>`, and only lines starting with that fresh token come from the
#                 harness (names printed from the workspace cannot carry it);
#        smoke  = no model call: the release starts, the writable places work, TLS through the proxy works, litellm
#                 reaches the API host with an invalid key (expects 401, costs nothing), no process is left running;
#        build  = the generation itself.
# Usage: wsl_devs_gen_isolated_generate.sh <mode> <task> <litellm model> <label> <run> <max output tokens> <timeout s> <project dir in WSL>
set -u
MODE="$1"; TASK="$2"; MODEL="$3"; LABEL="$4"; RUN="$5"; MAXTOK="$6"; TOUT="$7"; PROJ="$8"
: "${ANTHROPIC_API_KEY:?the key must arrive in the environment}"
case "$MODE" in check|smoke|build) ;; *) echo "unknown mode $MODE"; exit 2;; esac
CODE="$HOME/trust2027/devs_gen_code"; VENV="$CODE/.venvs/devs-gen"; PYHOME="$HOME/.local/share/uv/python"
BW="$HOME/trust2027/tools/usr/bin/bwrap"
WS="$HOME/trust2027/gen/$LABEL/$TASK/$RUN"
ST="$HOME/trust2027/stage/$LABEL-$TASK-$RUN"
# inside the sandbox the workspace is mounted at a neutral path, so ~/trust2027/gen (other builds) does not exist there
WSIN="$HOME/ws"
if [ "$MODE" = build ] && [ -n "$(find "$WS" -name run.py -print -quit 2>/dev/null)" ]; then echo "{\"skip\": \"$WS exists\"}"; exit 0; fi
mkdir -p "$ST/hooks" "$ST/sock" "$WS" "$ST/persistent_storage"
# DEVS-Gen writes agent logs into its own src/generation/devs_app/persistent_storage; that folder is replaced by an
# empty, writable one per build (kept in the stage folder), so earlier builds' logs are not visible either
cp "$PROJ/scripts/allow_one_host_proxy.py" "$PROJ/scripts/check_builder_isolation.py" "$ST/"
cp "$PROJ/adapters/devs_gen_hooks/sitecustomize.py" "$ST/hooks/"
# a hosts file of our own: the machine's name and domain stay out of the sandbox (and out of generated logs)
printf '127.0.0.1 localhost\n::1 localhost ip6-localhost ip6-loopback\n127.0.1.1 sandbox\n' > "$ST/hosts"
NONCE=$(cat /proc/sys/kernel/random/uuid | tr -d -)
cat > "$ST/inner.sh" <<'INNER'
#!/bin/bash
/usr/bin/python3 "$STAGE/allow_one_host_proxy.py" forward 18080 "$STAGE/sock/p.sock" &
FW=$!
sleep 0.5
export HTTPS_PROXY=http://127.0.0.1:18080 HTTP_PROXY=http://127.0.0.1:18080 https_proxy=http://127.0.0.1:18080 \
       http_proxy=http://127.0.0.1:18080 NO_PROXY=127.0.0.1,localhost LITELLM_LOCAL_MODEL_COST_MAP=True
if [ "$1" = check ]; then
  /usr/bin/python3 "$STAGE/check_builder_isolation.py" --wsl --workspace "$WS" --allow-socket "$STAGE/sock/p.sock" \
    --nonce "$NONCE"; echo "$NONCE CHECK_EXIT $?"
  /usr/bin/python3 - <<'PY'
import json, os, socket
n = os.environ["NONCE"]
for host in ("github.com", "raw.githubusercontent.com", "api.anthropic.com"):
    # the proxy's own upstream connect may take up to 30 s; a failure is recorded as a line, not a crash
    try:
        s = socket.create_connection(("127.0.0.1", 18080), timeout=60)
        s.sendall(f"CONNECT {host}:443 HTTP/1.1\r\nHost: {host}:443\r\n\r\n".encode())
        print(n, "PROXY_PROBE", host, s.recv(200).split(b"\r\n")[0].decode()); s.close()
    except OSError as e:
        print(n, "PROXY_PROBE", host, "error", type(e).__name__)
try:
    socket.create_connection(("1.1.1.1", 443), timeout=3).close(); print(n, "DIRECT_NET reachable")
except OSError as e:
    print(n, "DIRECT_NET blocked", type(e).__name__)
print(n, "PERSISTENT_STORAGE", json.dumps(sorted(os.listdir(os.environ["CODE"] + "/src/generation/devs_app/persistent_storage"))))
# /home to depth 5, without the venv, the Python home and the release's src/ (each path as JSON, so a name with a
# line break cannot pose as a harness line)
skip = ("/.venvs/", "/uv/python/", "/devs_gen_code/src/")
paths = []
for d, ds, fs in os.walk("/home"):
    depth = d.rstrip("/").count("/") - 1                 # /home is 0
    for name in ds + fs:
        p = os.path.join(d, name)
        if not any(s in p for s in skip):
            paths.append(p)
    ds[:] = [x for x in ds if depth + 1 < 5 and not any(s in os.path.join(d, x) + "/" for s in skip)]
for p in sorted(paths):
    print(n, "HOME", json.dumps(p))
PY
elif [ "$1" = smoke ]; then
  # a detached background child must not outlive the sandbox (the old form had no PID namespace)
  /usr/bin/setsid /usr/bin/sleep 86421 </dev/null >/dev/null 2>&1 &
  cd "$CODE/src/generation" && PYTHONPATH="$STAGE/hooks" "$VENV/bin/python" run_generation.py --help >/dev/null 2>&1; echo "SMOKE_HELP $?"
  PYTHONPATH="$STAGE/hooks" "$VENV/bin/python" - <<'PY'
import asyncio, os, getpass, socket, httpx, litellm
print("SMOKE_USER", getpass.getuser(), "HOST", socket.gethostname())
for d in (os.environ["WS"], os.environ["CODE"] + "/src/generation/devs_app/persistent_storage", "/tmp", "/dev/shm"):
    t = os.path.join(d, ".smoke"); open(t, "w").write("x"); os.remove(t); print("SMOKE_WRITE ok", d)
r = httpx.get("https://api.anthropic.com/", timeout=20)
print("SMOKE_TLS", r.status_code)
# the release's own client, sync and async, with a key that cannot work: reaches the API host, costs nothing
msg = [{"role": "user", "content": "x"}]
for how in ("sync", "async"):
    try:
        if how == "sync":
            litellm.completion(model=os.environ["MODEL"], messages=msg, api_key="invalid", max_tokens=1, num_retries=0)
        else:
            asyncio.run(litellm.acompletion(model=os.environ["MODEL"], messages=msg, api_key="invalid", max_tokens=1, num_retries=0))
        print("SMOKE_LITELLM", how, "unexpected success")
    except Exception as e:
        print("SMOKE_LITELLM", how, type(e).__name__, getattr(e, "status_code", None), repr(str(e)[:300]))
PY
else
  cd "$CODE/src/generation" && PYTHONPATH="$STAGE/hooks" "$VENV/bin/python" run_generation.py --framework devs_gen \
    --model "$MODEL" --benchmark "$TASK" --workspace "$WS" --timeout "$TOUT" --max-output-tokens "$MAXTOK"
  echo "GEN_EXIT $?"
fi
kill $FW 2>/dev/null
INNER
chmod +x "$ST/inner.sh"
# one proxy log per mode, so a build's counts hold only that build's traffic (an earlier attempt's log is kept aside)
if [ "$MODE" = build ] && [ -s "$ST/proxy_build.jsonl" ]; then mv "$ST/proxy_build.jsonl" "$ST/proxy_build.$(date +%s).jsonl"; fi
# the proxy dies with this script (PR_SET_PDEATHSIG in allow_one_host_proxy.py, and the trap on a normal exit)
/usr/bin/python3 "$ST/allow_one_host_proxy.py" serve "$ST/sock/p.sock" api.anthropic.com "$ST/proxy_$MODE.jsonl" </dev/null >/dev/null 2>&1 &
PX=$!
trap 'kill $PX 2>/dev/null' EXIT HUP INT TERM
sleep 0.5
START=$(date +%s)
# Hardened 2026-11-10 (the judges session's reviewer escaped the earlier `--ro-bind / /` form through /run: the user
# session bus let `systemd-run --user` start a process outside, and there was no PID namespace). Only /usr, the linker
# files and a few non-secret /etc files (TLS roots, passwd/group, nsswitch, localtime, alternatives, and a hosts file
# of our own) are mounted: no /run, /var, /mnt, other /etc files or host /home; /usr/lib/wsl (Windows driver
# programs) is covered. Every namespace is new (user, PID, IPC, UTS, cgroup, network), the host name is `sandbox`,
# the session is new, stdin is /dev/null, and descriptors above 2 are closed before bubblewrap starts. The stage
# folder (proxy, check, hooks, inner script) stays a read-only mount; only the workspace, the log folder and the
# proxy socket's folder are writable. The closer builds bubblewrap's whole environment: NAME=VALUE pairs as given,
# and a bare NAME (the key) copied from this script's environment, so the key is never on a command line.
# `timeout` bounds the whole sandbox (the build's own timeout plus 10 minutes).
WSLCOVER=""; [ -d /usr/lib/wsl ] && WSLCOVER="--tmpfs /usr/lib/wsl"
# litellm counts tokens with tiktoken before its own module that points tiktoken at its bundled encodings is loaded,
# so tiktoken would download cl100k_base from openaipublic.blob.core.windows.net (refused by the proxy). Point it at
# litellm's bundled copy (read-only; tiktoken checks each file's sha256 before use).
TKDIR=$(ls -d "$VENV"/lib/python3*/site-packages/litellm/litellm_core_utils/tokenizers 2>/dev/null | head -1)
# an empty value would disable tiktoken's cache (and so download); refuse to start instead
[ -n "$TKDIR" ] && [ -f "$TKDIR/9b5ad71b2ce5302211f9c61530b329a4922fc6a4" ] || { echo "litellm's bundled tokenizers not found"; exit 3; }
LIMIT=$(( TOUT + 600 )); [ "$MODE" != build ] && LIMIT=600
# seccomp (scripts/make_seccomp_filter_builder.py): socket families other than unix, inet, inet6 and netlink are
# refused (vsock reaches the Windows host past --unshare-net), and io_uring is refused (it creates sockets without
# socket()). Written fresh for each run and handed to bubblewrap on descriptor 10.
/usr/bin/python3 "$PROJ/scripts/make_seccomp_filter_builder.py" "$ST/seccomp.bpf" >/dev/null || { echo "no seccomp filter"; exit 3; }
/usr/bin/timeout -k 30 "$LIMIT" /usr/bin/python3 -c '
import os, sys
os.closerange(3, 65536)
fd = os.open(sys.argv[1], os.O_RDONLY)
if fd != 10:
    os.dup2(fd, 10)
    os.close(fd)
i = sys.argv.index("--")
env = {}
for a in sys.argv[2:i]:
    k, eq, v = a.partition("=")
    env[k] = v if eq else os.environ[k]
os.execve(sys.argv[i + 1], sys.argv[i + 1:], env)' "$ST/seccomp.bpf" \
  PATH=/usr/bin:/bin HOME="$HOME" ANTHROPIC_API_KEY WS="$WSIN" CODE="$CODE" VENV="$VENV" MODEL="$MODEL" TASK="$TASK" \
  TOUT="$TOUT" MAXTOK="$MAXTOK" STAGE="$ST" NONCE="$NONCE" TIKTOKEN_CACHE_DIR="$TKDIR" -- \
  "$BW" --seccomp 10 --ro-bind /usr /usr --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin --symlink usr/sbin /sbin \
  --ro-bind-try /etc/ld.so.cache /etc/ld.so.cache --ro-bind-try /etc/ld.so.conf /etc/ld.so.conf \
  --ro-bind-try /etc/ld.so.conf.d /etc/ld.so.conf.d --ro-bind-try /etc/ssl /etc/ssl \
  --ro-bind-try /etc/ca-certificates /etc/ca-certificates --ro-bind-try /etc/passwd /etc/passwd \
  --ro-bind-try /etc/group /etc/group --ro-bind "$ST/hosts" /etc/hosts --ro-bind-try /etc/nsswitch.conf /etc/nsswitch.conf \
  --ro-bind-try /etc/localtime /etc/localtime --ro-bind-try /etc/alternatives /etc/alternatives $WSLCOVER \
  --tmpfs /home \
  --ro-bind "$CODE" "$CODE" --tmpfs "$CODE/benchmark" --ro-bind "$CODE/benchmark/$TASK" "$CODE/benchmark/$TASK" \
  --tmpfs "$CODE/generated" --tmpfs "$CODE/results" --tmpfs "$CODE/.git" \
  --bind "$ST/persistent_storage" "$CODE/src/generation/devs_app/persistent_storage" \
  --ro-bind-try "$PYHOME" "$PYHOME" --bind "$WS" "$WSIN" \
  --ro-bind "$ST" "$ST" --bind "$ST/sock" "$ST/sock" \
  --dev /dev --proc /proc --tmpfs /tmp --unshare-all --hostname sandbox --die-with-parent --new-session \
  "$ST/inner.sh" "$MODE" < /dev/null > "$ST/$MODE.log" 2>&1
CODE_RC=$?
END=$(date +%s)
# every process inside is gone, so its tunnels are closing; give the proxy a moment to log their byte counts
sleep 2
kill $PX 2>/dev/null
if [ "$MODE" = smoke ]; then sleep 1; echo "SMOKE_LEFT_RUNNING $(pgrep -fc '[s]leep 86421')" >> "$ST/smoke.log"; fi
if [ "$MODE" = check ]; then echo "NONCE $NONCE"; cat "$ST/check.log"; exit 0; fi
if [ "$MODE" = smoke ]; then cat "$ST/smoke.log"; exit 0; fi
HAS=$( [ -n "$(find "$WS" -name run.py -type f -print -quit)" ] && echo true || echo false )
GEN=$(grep -o "GEN_EXIT [0-9]*" "$ST/build.log" | tail -1 | cut -d" " -f2)
# counts from the parsed log (a denied request's text could otherwise pose as "allowed")
read ALLOW DENY BU BD < <(/usr/bin/python3 -c 'import json, sys
a = n = u = d = 0
try:
    for l in open(sys.argv[1]):
        r = json.loads(l)
        res = r.get("result")
        a += res == "allowed"; n += res == "denied"
        if res == "tunnel_closed":
            u += int(r.get("bytes_up", 0)); d += int(r.get("bytes_down", 0))
except (OSError, ValueError):
    pass
print(a, n, u, d)' "$ST/proxy_build.jsonl" 2>/dev/null || echo "0 0 0 0")
# the key must not appear in anything the build left, compressed files included; the key comes from the
# environment, never an argument, and links are not followed. Only a count is printed.
KEYHITS=$(/usr/bin/python3 -c 'import gzip, os, stat, sys
key = os.environ["ANTHROPIC_API_KEY"].encode()
hits = 0
for top in sys.argv[1:]:
    for d, ds, fs in os.walk(top):
        for f in fs:
            p = os.path.join(d, f)
            try:
                st = os.lstat(p)
                if not stat.S_ISREG(st.st_mode) or st.st_size > 2**30:
                    continue
                with open(p, "rb") as fh:
                    data = fh.read()
                if key in data:
                    hits += 1
                    continue
                if data[:2] == b"\x1f\x8b":
                    with gzip.open(p, "rb") as g:
                        tail = b""
                        while True:
                            chunk = g.read(2**20)
                            if not chunk:
                                break
                            if key in tail + chunk:
                                hits += 1
                                break
                            tail = chunk[-len(key):]
            except (OSError, EOFError, gzip.BadGzipFile):
                pass
print(hits)' "$WS" "$ST" 2>/dev/null || echo -1)
echo "{\"task\": \"$TASK\", \"model\": \"$MODEL\", \"label\": \"$LABEL\", \"run\": \"$RUN\", \"max_output_tokens\": $MAXTOK, \"timeout\": $TOUT, \"exit\": ${GEN:-$CODE_RC}, \"seconds\": $((END-START)), \"has_run_py\": $HAS, \"proxy_allowed\": ${ALLOW:-0}, \"proxy_denied\": ${DENY:-0}, \"proxy_bytes_up\": ${BU:-0}, \"proxy_bytes_down\": ${BD:-0}, \"key_found_in_files\": ${KEYHITS:--1}, \"sandbox_rc\": $CODE_RC}"
