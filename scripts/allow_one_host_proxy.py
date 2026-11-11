"""Network for a sandboxed builder that needs one model API and nothing else (manifests/builder_isolation.md).

Two halves, standard library only:
- `serve <unix_socket> <allowed_host> <log>` runs OUTSIDE the sandbox. It accepts connections on a Unix socket and
  honours only `CONNECT <allowed_host>:443`; every other request gets 403 and is logged. TLS stays end to end (the
  proxy never sees the API key or the traffic).
- `forward <port> <unix_socket>` runs INSIDE the sandbox (`--unshare-net`, so only loopback exists). It listens on
  127.0.0.1:<port> and passes each connection to the Unix socket, which is the only way out. The builder is given
  `HTTPS_PROXY=http://127.0.0.1:<port>`.
"""
import json
import os
import socket
import sys
import threading
import time


def pipe(a, b, count=None):
    try:
        while True:
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
            if count is not None:
                count[0] += len(data)
    except OSError:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def both_ways(a, b):
    """Relay until either side closes; returns the bytes sent a->b and b->a."""
    up, down = [0], [0]
    t = threading.Thread(target=pipe, args=(b, a, down), daemon=True)
    t.start()
    pipe(a, b, up)
    t.join(timeout=5)
    a.close()
    b.close()
    return up[0], down[0]


def die_with_parent():
    """The serving proxy must not outlive the launcher (e.g. when the Windows side times out and kills wsl.exe)."""
    try:
        import ctypes
        import signal
        ctypes.CDLL(None).prctl(1, signal.SIGTERM)            # PR_SET_PDEATHSIG
        if os.getppid() == 1:
            sys.exit(0)
    except (OSError, AttributeError):
        pass


def log_line(path, **kw):
    with open(path, "a") as f:
        f.write(json.dumps({"t": round(time.time(), 1), **kw}) + "\n")


def serve(sock_path, allowed, log):
    if os.path.lexists(sock_path):            # lexists: a dangling link planted there is removed too
        os.unlink(sock_path)
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    os.chmod(sock_path, 0o600)
    srv.listen(64)

    def handle(c):
        buf = b""
        while b"\r\n\r\n" not in buf and len(buf) < 16384:
            chunk = c.recv(4096)
            if not chunk:
                c.close()
                return
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        line = head.split(b"\r\n", 1)[0].decode("latin-1", "replace")
        parts = line.split()
        target = parts[1] if len(parts) >= 2 else ""
        host, _, port = target.rpartition(":")
        if len(parts) >= 2 and parts[0] == "CONNECT" and host == allowed and port == "443":
            try:
                # IPv4 first: from this WSL the IPv6 address of the API host takes about 11 s to fail over
                up = None
                try:
                    v4 = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
                    if v4:
                        up = socket.create_connection(v4[0][4], timeout=15)
                except OSError:
                    up = None
                if up is None:
                    up = socket.create_connection((host, 443), timeout=30)
                up.settimeout(None)
            except OSError as e:
                log_line(log, result="upstream_error", target=target, error=str(e)[:100])
                c.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                c.close()
                return
            log_line(log, result="allowed", target=target)
            c.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            if rest:
                up.sendall(rest)
            sent, got = both_ways(c, up)
            # bytes through the tunnel: a rough meter the builder cannot edit (the token log is in its workspace)
            log_line(log, result="tunnel_closed", target=target, bytes_up=sent + len(rest), bytes_down=got)
        else:
            log_line(log, result="denied", request=line[:120])
            c.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            c.close()

    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


def forward(port, sock_path):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", int(port)))
    srv.listen(64)
    while True:
        c, _ = srv.accept()
        u = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            u.connect(sock_path)
        except OSError:
            c.close()
            continue
        threading.Thread(target=both_ways, args=(c, u), daemon=True).start()


if __name__ == "__main__":
    if sys.argv[1] == "serve":
        die_with_parent()
        serve(sys.argv[2], sys.argv[3], sys.argv[4])
    elif sys.argv[1] == "forward":
        forward(sys.argv[2], sys.argv[3])
    else:
        sys.exit("usage: serve <sock> <host> <log> | forward <port> <sock>")
