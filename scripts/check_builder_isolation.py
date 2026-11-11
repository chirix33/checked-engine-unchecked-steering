"""Check that evaluation-side material is hidden from a program builder (see manifests/builder_isolation.md).

Run it inside the builder's sandbox, with the builder's interpreter and isolation, just before a build:

    python3 check_builder_isolation.py --wsl --workspace <builder workspace>         (WSL, e.g. DEVS-Gen)
    python  check_builder_isolation.py --windows --workspace <builder workspace>     (a Windows sandbox)

Exit 0 only if nothing listed is reachable. It never reads a file's contents and never prints a secret: for
credentials it reports only which names exist.

Positive control: run it once OUTSIDE the sandbox with --expect-visible. Every project path must then be visible;
if one is not, the path list or the root is wrong, and a pass inside the sandbox would mean nothing. Keep both
outputs with the build log.

A path counts as hidden only if it does not exist (FileNotFoundError, NotADirectoryError) or is an empty folder
(a tmpfs mounted over it). Any other error, e.g. permission denied, counts as visible: a folder that cannot be listed
can still have files opened by name, so known files are also probed directly.

WSL also probes ways out that need no file path or network (added 2026-11-10 after the judges session's reviewer
escaped the `--ro-bind / /` form): Unix sockets under /run and WSLg, starting a process outside through
`systemd-run --user` over the session bus, sharing the host's PID namespace, inherited descriptors above 2 and a
reachable controlling terminal. With --expect-visible these probes must fire outside the sandbox. Tool deny-lists inside an agent do not
hide anything from this check; only operating-system isolation (a separate user, a container, bubblewrap, a VM) can.

Usage: python3 check_builder_isolation.py (--wsl | --windows) [--root DIR ...] [--workspace DIR] [--expect-visible]
                                          [--allow-socket PATH ...] [--nonce TOKEN]
  --allow-socket  a Unix socket that is the sandbox's intended way out (e.g. the one-host proxy); not a finding
  --nonce         also print one line `<TOKEN> CHECK_SUMMARY <json>` for a harness to parse
"""
import os
import socket
import sys

WIN_ROOT = r"C:\Users\aashraf\Desktop\Work\2026\ACM Trust 2027"
WSL_ROOT = "/mnt/c/Users/aashraf/Desktop/Work/2026/ACM Trust 2027"
# relative to the project root
DIRS = ["manifests", "runs", "validation", "reference_engine", "checker", "spec", "scripts", "baseline", "assurance",
        "data", "adapters", "redesign", "papers", "meeting", ".git", ".tools", ".claude"]
FILES = [".env", "AGENTS.md", "RESEARCH_DIRECTION.md",
         "manifests/workflow_questions_test_v1.json", "manifests/workflow_questions_policy_v1.json",
         "manifests/mlsys_questions_test_v1.json", "manifests/mlsys_questions_dev_v1.json", "manifests/pilot_questions_v1.json",
         "runs/workflow_docs/workflow_loan_test/document.pdf", "runs/workflow_docs/workflow_loan_test/document_meta.json",
         "runs/workflow_docs/workflow_pharmacy_test/document.pdf", "runs/workflow_docs/workflow_pharmacy_test/document_meta.json",
         "runs/workflow_docs/workflow_loan_policyP/document_meta.json", "runs/mlsys_docs",
         "reference_engine/engine.py", "checker/run.py", "validation/blind_review_workflow_key_v1.json",
         "baseline/otf-tools-10f5401/implementation-1", ".git/HEAD",
         # MLSys (manufacturing and IT) test material, added 2026-11-10 before the DEVS-Gen MLSys builds:
         # test questions with gold, blind-review keys and scores, gold code, test-side soundness, test documents
         "manifests/mlsys_questions_v1.sha256", "manifests/mlsys_splits_v1.json", "manifests/probe_soundness_mlsys_v2_test.json",
         "validation/blind_review_mlsys_key_v3.json", "validation/blind_review_mlsys/score_v3.json",
         "validation/blind_review_mlsys", "scripts/mlsys_gold.py", "scripts/make_mlsys_questions.py",
         "runs/mlsys_docs/mfg_d01/document.pdf", "runs/mlsys_docs/itops_d02/navmap.json"]
OPTIONAL = {".claude", ".env"}        # may legitimately be absent from the project; not required by the positive control
WIN_EXTRA = [r"C:\Users\aashraf\Desktop\Work\2026\MLSystem 2027", r"C:\Users\aashraf\.claude",
             r"C:\Users\aashraf\AppData\Local\Temp\claude", r"C:\Users\aashraf\AppData\Local\Claude-Data",
             r"\\wsl.localhost\Ubuntu-24.04\home\aashraf\trust2027", r"\\wsl$\Ubuntu-24.04\home\aashraf\trust2027",
             r"C:\Users\aashraf\.git-credentials", r"C:\Users\aashraf\AppData\Roaming\GitHub CLI", r"C:\Users\aashraf\.ssh"]
WSL_EXTRA = ["/mnt/c", "/mnt/c/Users/aashraf/Desktop/Work/2026/MLSystem 2027", "/mnt/c/Users/aashraf/.claude",
             "~/trust2027/gen", "~/trust2027/screen", "~/.git-credentials", "~/.config/gh", "~/.ssh",
             # other DEVS-Gen tasks and the release's own generated programs and results (added 2026-11-10)
             "~/trust2027/devs_gen_code/benchmark/WorkflowLoan", "~/trust2027/devs_gen_code/benchmark/WorkflowPharmacy",
             "~/trust2027/devs_gen_code/benchmark/ABP", "~/trust2027/devs_gen_code/generated",
             "~/trust2027/devs_gen_code/results",
             # /run holds the user's systemd/D-Bus session bus and WSL's interop sockets (escape found 2026-11-10)
             "/run", "/var/run"]
WSL_SYSTEM_MOUNTS = {"/usr/lib/wsl/drivers", "/usr/lib/wsl/lib"}
SECRET_ENV = ("API_KEY", "TOKEN", "SECRET", "PASSWORD", "ANTHROPIC", "OPENAI", "OPENROUTER", "GH_", "GITHUB")


def state(path):
    """'absent', 'empty' (hidden), or 'visible'."""
    try:
        if os.path.isdir(path):
            return "visible" if os.listdir(path) else "empty"
        os.stat(path)
        return "visible"
    except (FileNotFoundError, NotADirectoryError):
        return "absent"
    except OSError:
        return "visible"          # exists but cannot be listed or reached: files may still open by name


def win_spellings(root):
    """The root under other names the same Windows object answers to: UNC and the 8.3 short name."""
    out = [r"\\localhost\c$" + root[2:], "\\\\?\\" + root]
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(root, buf, 1024) and buf.value != root:
            out.append(buf.value)
    except (AttributeError, OSError):
        pass
    return out


def wsl_mounts():
    """Mounts of the Windows drives or host shares (drvfs, 9p, virtiofs) visible to this process."""
    bad = []
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as f:
            for line in f:
                left, _, right = line.partition(" - ")
                fstype = right.split()[0] if right else ""
                mp = left.split()[4].replace("\040", " ")
                # a host share counts only if this process can reach it (one mounted over, e.g. /mnt/c under a
                # tmpfs on /mnt, stays in the table but is hidden), and WSL's own driver and GPU-library shares are
                # system files, not project data
                if fstype in ("drvfs", "9p", "virtiofs", "v9fs") and state(mp) == "visible" and mp not in WSL_SYSTEM_MOUNTS:
                    bad.append(f"{mp} ({fstype})")
    except OSError:
        pass
    return bad


def host_share_mounts():
    out = set()
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as f:
            for line in f:
                left, _, right = line.partition(" - ")
                if right and right.split()[0] in ("drvfs", "9p", "virtiofs", "v9fs"):
                    out.add(left.split()[4].replace("\\040", " "))
    except OSError:
        pass
    return out


def visible_sockets(allowed=(), limit=50, max_entries=400000):
    """Unix sockets this process can see anywhere in its tree (the user session bus, the system bus, WSL interop,
    WSLg, Docker), except the ones named in `allowed` (a sandbox's own way out). --unshare-net does not block a Unix
    socket reached by path, and code that can connect to one of these can ask something outside the sandbox to act
    for it. The usual places are walked first; /proc, /sys, /usr, /dev and Windows-drive shares are skipped.
    A walk cut short by its size limit is itself reported."""
    import stat
    allowed = {os.path.realpath(a) for a in allowed}
    skip = {"/proc", "/sys", "/usr", "/dev"} | host_share_mounts()
    tops = ["/run", "/var/run", "/mnt/wslg", "/mnt/wsl", "/tmp", "/"]
    out, seen, n = [], set(), 0
    for top in tops:
        for dirpath, dirnames, filenames in os.walk(top, onerror=lambda e: None):
            dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) not in skip
                           and (top != "/" or os.path.join(dirpath, d) not in tops)]
            for name in filenames:
                n += 1
                p = os.path.join(dirpath, name)
                try:
                    if stat.S_ISSOCK(os.lstat(p).st_mode):
                        real = os.path.realpath(p)
                        if real not in seen and real not in allowed:
                            seen.add(real)
                            out.append(p)
                except OSError:
                    pass
            n += len(dirnames)
            if len(out) >= limit:
                return out
            if n > max_entries:
                out.append(f"(walk stopped after {n} entries; the rest of the tree was not searched)")
                return out
    return out


def outside_start():
    """Try the escape found 2026-11-10: ask the user's systemd, over its session bus, to start a process outside the
    sandbox (`systemd-run --user`). Each candidate bus is tried with the address set explicitly, because a cleared
    environment does not stop it. A run that succeeds, or that hangs, counts."""
    import glob
    import shutil
    import subprocess
    exe = shutil.which("systemd-run") or next((p for p in ("/usr/bin/systemd-run", "/bin/systemd-run") if os.path.exists(p)), None)
    if not exe:
        return []
    buses = sorted(set(glob.glob("/run/user/*/bus") + [f"/run/user/{os.getuid()}/bus"]))
    out = []
    for bus in buses:
        env = {**os.environ, "DBUS_SESSION_BUS_ADDRESS": f"unix:path={bus}", "XDG_RUNTIME_DIR": os.path.dirname(bus)}
        try:
            p = subprocess.run([exe, "--user", "--wait", "--pipe", "--quiet", "--collect", "/bin/sh", "-c", "echo OUTSIDE_STARTED"],
                               capture_output=True, text=True, timeout=20, env=env, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            out.append(f"OUTSIDE START undetermined: systemd-run --user via {bus} did not return in 20 s")
            continue
        except OSError:
            continue
        if p.returncode == 0 or "OUTSIDE_STARTED" in p.stdout:
            out.append(f"OUTSIDE START systemd-run --user via {bus} started a process outside the sandbox")
    return out


def host_pid_namespace():
    """The sandbox shares the host's process namespace if pid 1 is the host's init (a new PID namespace makes pid 1 the
    sandbox's own first process). Without one, a background child can outlive the sandbox and host processes are seen."""
    try:
        with open("/proc/1/comm", encoding="utf-8") as f:
            comm = f.read().strip()
        n = sum(1 for p in os.listdir("/proc") if p.isdigit())
    except OSError:
        return []
    return [f"HOST PID NAMESPACE (pid 1 is {comm}, {n} processes visible)"] if comm in ("systemd", "init") else []


def inherited_descriptors():
    """Open file descriptors above 2 that this process inherited (e.g. the launching terminal's /dev/ptmx), and a
    controlling terminal that can still be opened (keystrokes can be pushed into it unless the sandbox starts a new
    session)."""
    out = [f"TERMINAL on descriptor {n}" for n in (0, 1, 2) if os.isatty(n)]
    try:
        fds = sorted(int(x) for x in os.listdir("/proc/self/fd"))
    except OSError:
        fds = []
    for n in fds:
        if n <= 2:
            continue
        try:
            out.append(f"INHERITED DESCRIPTOR {n} -> {os.readlink(f'/proc/self/fd/{n}')}")
        except OSError:
            pass                      # the descriptor used to list the folder, closed by now
    try:
        fd = os.open("/dev/tty", os.O_RDWR | os.O_NOCTTY)
        os.close(fd)
        out.append("CONTROLLING TERMINAL reachable (/dev/tty opens)")
    except OSError:
        pass
    return out


def vsock_socket():
    """`--unshare-net` does not cover AF_VSOCK on the WSL2 kernel: a vsock socket can reach the Windows host (CID 2),
    where WSL serves /mnt/c over 9P (found 2026-11-10 by the library sandbox's review). Creating one is the finding;
    nothing is connected."""
    fam = getattr(socket, "AF_VSOCK", 40)
    try:
        socket.socket(fam, socket.SOCK_STREAM).close()
        return ["VSOCK socket can be created (AF_VSOCK not blocked)"]
    except OSError:
        return []


def io_uring_socket():
    """io_uring's IORING_OP_SOCKET creates a socket without the socket() system call, so a seccomp rule on socket()
    alone does not stop it. Try to create an AF_VSOCK socket that way (one submission, nothing connected); a returned
    descriptor is the finding. io_uring merely being available is reported only if this succeeds."""
    import ctypes
    import mmap
    import struct
    libc = ctypes.CDLL(None, use_errno=True)
    sc = libc.syscall
    sc.restype = ctypes.c_long
    params = ctypes.create_string_buffer(120)
    fd = sc(ctypes.c_long(425), ctypes.c_long(4), params)                       # io_uring_setup(4, &params)
    if fd < 0:
        return []
    try:
        sq_entries, cq_entries, _, _, _, features = struct.unpack_from("<6I", params, 0)
        sq_head, sq_tail, sq_mask, _, _, _, sq_array = struct.unpack_from("<7I", params, 40)
        cq_head, cq_tail, cq_mask, _, _, cq_cqes = struct.unpack_from("<6I", params, 80)
        sq_size = sq_array + sq_entries * 4
        cq_size = cq_cqes + cq_entries * 16
        single = features & 1                                                    # IORING_FEAT_SINGLE_MMAP
        prot = mmap.PROT_READ | mmap.PROT_WRITE
        sq = mmap.mmap(fd, max(sq_size, cq_size) if single else sq_size, mmap.MAP_SHARED, prot, offset=0)
        cq = sq if single else mmap.mmap(fd, cq_size, mmap.MAP_SHARED, prot, offset=0x8000000)
        sqes = mmap.mmap(fd, sq_entries * 64, mmap.MAP_SHARED, prot, offset=0x10000000)
        fam = getattr(socket, "AF_VSOCK", 40)
        # opcode 45 = IORING_OP_SOCKET: fd = domain, off = type, len = protocol
        sqes[0:64] = struct.pack("<BBHiQQIIQHHiQQ", 45, 0, 0, fam, socket.SOCK_STREAM, 0, 0, 0, 7, 0, 0, 0, 0, 0)
        tail = struct.unpack_from("<I", sq, sq_tail)[0]
        mask = struct.unpack_from("<I", sq, sq_mask)[0]
        struct.pack_into("<I", sq, sq_array + 4 * (tail & mask), 0)
        struct.pack_into("<I", sq, sq_tail, tail + 1)
        r = sc(ctypes.c_long(426), ctypes.c_long(fd), ctypes.c_long(1), ctypes.c_long(1), ctypes.c_long(1),
               ctypes.c_void_p(0), ctypes.c_long(0))                             # io_uring_enter(fd, 1, 1, GETEVENTS)
        if r < 0:
            return []
        head = struct.unpack_from("<I", cq, cq_head)[0]
        cmask = struct.unpack_from("<I", cq, cq_mask)[0]
        _, res, _ = struct.unpack_from("<QiI", cq, cq_cqes + 16 * (head & cmask))
        if res >= 0:
            os.close(res)
            return ["IO_URING created an AF_VSOCK socket without socket() (a seccomp rule on socket() alone is bypassed)"]
        return []
    except (OSError, ValueError, struct.error):
        return []
    finally:
        os.close(fd)


def escape_findings(allowed_sockets=()):
    return ([f"SOCKET {s}" for s in visible_sockets(allowed_sockets)] + outside_start() + host_pid_namespace()
            + inherited_descriptors() + vsock_socket() + io_uring_socket())


def network_reachable():
    """By name and by address: a sandbox without /etc/resolv.conf fails the name lookup whether or not it has a network."""
    for target in (("github.com", 443), ("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            socket.create_connection(target, timeout=3).close()
            return True
        except OSError:
            pass
    return False


def workspace_escapes(ws):
    """Links or mount points inside the workspace that lead outside it."""
    out, base = [], os.path.realpath(ws)
    for dirpath, dirnames, filenames in os.walk(ws):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            real = os.path.realpath(p)
            if os.path.islink(p) and not (real == base or real.startswith(base + os.sep)):
                out.append(f"{p} -> {real}")
            elif os.path.ismount(p):
                out.append(f"{p} (mount point)")
    return out


def main(argv):
    wsl, win, expect = "--wsl" in argv, "--windows" in argv, "--expect-visible" in argv
    if wsl == win:
        print("give exactly one of --wsl or --windows")
        return 2
    if (wsl and not sys.platform.startswith("linux")) or (win and sys.platform != "win32"):
        print(f"--{'wsl' if wsl else 'windows'} does not match this platform ({sys.platform})")
        return 2
    extra_roots = [a for i, a in enumerate(argv) if i and argv[i - 1] == "--root"]
    ws = next((a for i, a in enumerate(argv) if i and argv[i - 1] == "--workspace"), None)
    primary = WSL_ROOT if wsl else WIN_ROOT
    roots = [primary] + extra_roots + (win_spellings(WIN_ROOT) if win else [])
    project = []
    for root in roots:
        project += [root] + [os.path.join(root, *r.split("/")) for r in DIRS + FILES]
    extra = [os.path.expanduser(p) for p in (WSL_EXTRA if wsl else WIN_EXTRA)]
    results = {p: state(p) for p in project + extra}
    if expect:
        # positive control, outside the sandbox: every path under the primary root must be visible
        want = [primary] + extra_roots + [os.path.join(primary, *r.split("/")) for r in DIRS + FILES if r not in OPTIONAL]
        missing = [p for p in want if results[p] != "visible"]
        for p in missing:
            print("NOT VISIBLE (positive control)", p)
        bad_probe = []
        if wsl:
            # the escape probes must fire outside the sandbox too, or their silence inside would mean nothing
            esc = escape_findings()
            for e in esc:
                print("ESCAPE PROBE (positive control)", e)
            kinds = {e.split(" ")[0] for e in esc}
            if "SOCKET" not in kinds:
                bad_probe.append("no socket seen under /run")
            if "HOST" not in kinds:
                bad_probe.append("host PID namespace not detected")
            if any(e.startswith("SOCKET ") and e.endswith("/bus") for e in esc) and "OUTSIDE" not in kinds:
                bad_probe.append("a session bus exists but systemd-run did not start a process through it")
            if "microsoft" in os.uname().release.lower() and "VSOCK" not in kinds:
                bad_probe.append("WSL2 kernel but no vsock socket could be created")
            try:
                with open("/proc/sys/kernel/io_uring_disabled") as f:
                    uring_on = f.read().strip() == "0"
            except OSError:
                uring_on = False
            if uring_on and "IO_URING" not in kinds:
                bad_probe.append("io_uring is enabled but the io_uring socket probe did not create a socket")
            for b in bad_probe:
                print("ESCAPE PROBE FAILED (positive control)", b)
        print(f"positive control: {len(want) - len(missing)} of {len(want)} project paths visible"
              + (f"; escape probes {'fire' if not bad_probe else 'BROKEN'}" if wsl else ""))
        return 1 if missing or bad_probe else 0
    findings = [f"VISIBLE {p}" for p, s in results.items() if s == "visible"]
    if wsl:
        findings += [f"HOST MOUNT {m}" for m in wsl_mounts()]
        exe = [p for p in ("/mnt/c/Windows/System32/cmd.exe", "/mnt/c/Windows/System32/wsl.exe") if state(p) == "visible"]
        if os.path.exists("/proc/sys/fs/binfmt_misc/WSLInterop") and exe:
            findings.append(f"WSL INTEROP enabled and Windows programs reachable ({exe[0]})")
        findings += escape_findings([a for i, a in enumerate(argv) if i and argv[i - 1] == "--allow-socket"])
    if network_reachable():
        findings.append("NETWORK reachable (github.com:443, 1.1.1.1:443 or 8.8.8.8:53)")
    findings += [f"CREDENTIAL VARIABLE {k}" for k in sorted(k for k in os.environ if any(s in k.upper() for s in SECRET_ENV))]
    if ws:
        if not os.path.isdir(ws):
            findings.append(f"WORKSPACE missing: {ws}")
        else:
            findings += [f"WORKSPACE ESCAPE {e}" for e in workspace_escapes(ws)]
    for f in findings:
        print(f)
    print(f"{len(results)} paths checked, {len(findings)} findings")
    nonce = next((a for i, a in enumerate(argv) if i and argv[i - 1] == "--nonce"), None)
    if nonce:
        # one machine-readable line a harness can trust: names printed above (e.g. a workspace link) cannot carry the
        # nonce, which the harness makes fresh for each run
        import json
        print(f"{nonce} CHECK_SUMMARY {json.dumps({'paths': len(results), 'findings': findings})}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
