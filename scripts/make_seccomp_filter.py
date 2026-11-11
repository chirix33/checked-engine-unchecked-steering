"""Write the seccomp filter every sandboxed program runs under: socket() and socketpair() are refused (EPERM) for
every address family except AF_UNIX, and io_uring (which can create sockets without socket()) is refused.

Why (review of the hardened sandbox, 2026-11-10): `--unshare-net` does not cover AF_VSOCK on the WSL2 kernel. From
inside the sandbox a program could connect to the Windows host (CID 2), where a port answered the 9P handshake WSL
uses to serve /mnt/c. Network namespaces cannot stop that; a seccomp filter can.

The filter is classic BPF, x86_64 only. Any other architecture (32-bit compat calls) and any x32-ABI system call
number is killed, so the rule cannot be bypassed through another calling convention. Run inside WSL:
  python3 make_seccomp_filter.py <out_path>
`assurance.backends.sandbox_command` and `scripts/judges.py` pass the file to bubblewrap with `--seccomp`.
"""
import struct
import sys

AUDIT_ARCH_X86_64 = 0xC000003E
X32_BIT = 0x40000000
NR_SOCKET, NR_SOCKETPAIR = 41, 53
AF_UNIX = 1
RET_ALLOW, RET_KILL, RET_EPERM = 0x7FFF0000, 0x80000000, 0x00050000 | 1
LD_W_ABS, JEQ_K, JGE_K, RET_K = 0x20, 0x15, 0x35, 0x06


def ins(code, jt, jf, k):
    return struct.pack("<HBBI", code, jt, jf, k)


NR_IO_URING = (425, 426, 427)                   # io_uring_setup, io_uring_enter, io_uring_register

# io_uring can create sockets without the socket() system call (IORING_OP_SOCKET), past this filter's socket rule,
# so it is refused outright (found by the judges' and builder sandbox checks, 2026-11-10).
PROGRAM = [
    ins(LD_W_ABS, 0, 0, 4),                     # 0: A = arch
    ins(JEQ_K, 1, 0, AUDIT_ARCH_X86_64),        # 1: x86_64 -> 3
    ins(RET_K, 0, 0, RET_KILL),                 # 2: other arch: kill
    ins(LD_W_ABS, 0, 0, 0),                     # 3: A = syscall number
    ins(JGE_K, 0, 1, X32_BIT),                  # 4: x32 ABI -> 5 (kill), else 6
    ins(RET_K, 0, 0, RET_KILL),                 # 5
    ins(JEQ_K, 5, 0, NR_IO_URING[0]),           # 6: io_uring_setup -> 12 (EPERM)
    ins(JEQ_K, 4, 0, NR_IO_URING[1]),           # 7: io_uring_enter -> 12
    ins(JEQ_K, 3, 0, NR_IO_URING[2]),           # 8: io_uring_register -> 12
    ins(JEQ_K, 4, 0, NR_SOCKET),                # 9: socket -> 14
    ins(JEQ_K, 3, 0, NR_SOCKETPAIR),            # 10: socketpair -> 14
    ins(RET_K, 0, 0, RET_ALLOW),                # 11: anything else: allow
    ins(RET_K, 0, 0, RET_EPERM),                # 12: io_uring: EPERM
    ins(RET_K, 0, 0, RET_EPERM),                # 13: (unused padding, never reached)
    ins(LD_W_ABS, 0, 0, 16),                    # 14: A = args[0] (address family, low 32 bits)
    ins(JEQ_K, 0, 1, AF_UNIX),                  # 15: AF_UNIX -> 16, else 17
    ins(RET_K, 0, 0, RET_ALLOW),                # 16
    ins(RET_K, 0, 0, RET_EPERM),                # 17: every other family: EPERM
]

if __name__ == "__main__":
    with open(sys.argv[1], "wb") as f:
        f.write(b"".join(PROGRAM))
    print(f"wrote {len(PROGRAM)} instructions to {sys.argv[1]}")
