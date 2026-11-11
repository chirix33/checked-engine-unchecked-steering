"""Seccomp filter for the DEVS-Gen *build* sandbox (scripts/wsl_devs_gen_isolated_generate.sh).

The program sandbox's filter (scripts/make_seccomp_filter.py) allows AF_UNIX only. A build needs more: the builder
reaches the model API through a forwarder on 127.0.0.1 inside its own network namespace, so AF_INET (and AF_INET6,
AF_NETLINK, which libraries use for loopback and interface lookups inside that namespace) must work. Everything
else is refused with EPERM, in particular AF_VSOCK: `--unshare-net` does not cover vsock on the WSL2 kernel, and from
inside a sandbox a program reached the Windows host, where a port answered the 9P handshake that serves /mnt/c.

io_uring_setup, io_uring_enter and io_uring_register are refused too: io_uring's IORING_OP_SOCKET creates sockets
without the socket() system call, so a filter on socket() alone can be bypassed while io_uring is enabled
(/proc/sys/kernel/io_uring_disabled is 0 on this WSL kernel).

Classic BPF, x86_64 only; another architecture or the x32 ABI is killed. Run inside WSL:
  python3 make_seccomp_filter_builder.py <out_path>
"""
import struct
import sys

AUDIT_ARCH_X86_64 = 0xC000003E
X32_BIT = 0x40000000
NR_SOCKET, NR_SOCKETPAIR = 41, 53
NR_IO_URING = (425, 426, 427)                    # io_uring_setup, io_uring_enter, io_uring_register
ALLOWED_FAMILIES = (1, 2, 10, 16)                # AF_UNIX, AF_INET, AF_INET6, AF_NETLINK
RET_ALLOW, RET_KILL, RET_EPERM = 0x7FFF0000, 0x80000000, 0x00050000 | 1
LD_W_ABS, JEQ_K, JGE_K, RET_K = 0x20, 0x15, 0x35, 0x06


def ins(code, jt, jf, k):
    return struct.pack("<HBBI", code, jt, jf, k)


def program():
    p = [
        ins(LD_W_ABS, 0, 0, 4),                  # A = arch
        ins(JEQ_K, 1, 0, AUDIT_ARCH_X86_64),     # x86_64 -> skip the kill
        ins(RET_K, 0, 0, RET_KILL),
        ins(LD_W_ABS, 0, 0, 0),                  # A = system call number
        ins(JGE_K, 0, 1, X32_BIT),               # x32 ABI -> kill
        ins(RET_K, 0, 0, RET_KILL),
    ]
    # io_uring: EPERM. Each test jumps to the EPERM return that follows the group.
    n = len(NR_IO_URING)
    for i, nr in enumerate(NR_IO_URING):
        p.append(ins(JEQ_K, n - i, 0, nr))       # -> EPERM below (after the remaining tests and the jump)
    p.append(ins(0x05, 0, 0, 1))                 # JA +1: not io_uring, skip the EPERM
    p.append(ins(RET_K, 0, 0, RET_EPERM))
    # socket/socketpair: family allow-list
    p.append(ins(JEQ_K, 2, 0, NR_SOCKET))        # -> load family
    p.append(ins(JEQ_K, 1, 0, NR_SOCKETPAIR))
    p.append(ins(RET_K, 0, 0, RET_ALLOW))        # any other call
    p.append(ins(LD_W_ABS, 0, 0, 16))            # A = args[0] low 32 bits (address family)
    m = len(ALLOWED_FAMILIES)
    for j, fam in enumerate(ALLOWED_FAMILIES):
        p.append(ins(JEQ_K, m - j, 0, fam))      # -> ALLOW (after the remaining tests and the EPERM)
    p.append(ins(RET_K, 0, 0, RET_EPERM))
    p.append(ins(RET_K, 0, 0, RET_ALLOW))
    return p


if __name__ == "__main__":
    prog = program()
    with open(sys.argv[1], "wb") as f:
        f.write(b"".join(prog))
    print(f"wrote {len(prog)} instructions to {sys.argv[1]}")
