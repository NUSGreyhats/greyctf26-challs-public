; 0 mov
; 1 ld
; 2 st
; 3 push
; 4 pop
; 5 bne
; 6 gets
; 7 exit
; 8 call

start:
  call main
  exit rax

scramble:
  push rbp
  mov  rbp, rsp
scramble_loop:
  ld   rax, [rdi]
  bne  rax, zer, scramble_cont
  bne  rsi, zer, scramble_exit
scramble_cont:
  mov  rax, rax-0x20
  st   rax, [rdi]
  mov  rdi, rdi+1
  mov  rsi, rsi-1
  bne  rsi, zer, scramble_loop
scramble_exit:
  mov  rsp, rbp
  pop  rbp
  ret

main:
  push rbp
  mov  rbp, rsp
  mov  rsp, rsp-0x20
  mov  rdi, rbp-0x20
  gets rdi

  mov  rsi, 0x20
  call scramble

  mov  rdi, rbp-0x20
  mov  rsi, FLAG
main_loop:
  ld   rax, [rdi]
  ld   rcx, [rsi]
  bne  rax, rcx, main_bad
  mov  rdi, rdi+1
  mov  rsi, rsi+1
  bne  rdi, rbp, main_loop

  mov  rax, 1
  bne  rax, zer, main_exit
main_bad:
  mov  rax, 0
main_exit:
  mov  rsp, rbp
  pop  rbp
  ret
