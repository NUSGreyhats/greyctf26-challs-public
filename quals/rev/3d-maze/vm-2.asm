; rc4 implementation
; follows directly after loader code (occupies DATA)

; author notes:
; unfortunately the vm generation is underconstrained
; (mainly because the fixed +67 boost is a headache for the immediates).
; so some of the remaining ones will require either rc4 recognition (perfectly warranted imo)
; or brute force (which is not too difficult -- just find right combi that produces valid message)

; KSA part 1
    push 0                  + 68,69,70 + 1,2,3     ; SPECIAL
_ksa_1_loop:
    dup
    dup
    push SBOX               + + !,!,!       ; >=16 is oob (so 16 <= ! < 256-67)
    store
    push 1                  + + 0,2,3       ; by right options must not be coprime, but no point bc of the +67
    add
    dup                     + rot,swap,pop
    jnz _ksa_1_loop         + + 253,253,253     ; infinite loop
; KSA part 2
    dup
_ksa_2_loop:
    dup
    push SBOX               + + !,!,!
    load
    swap
    dup                 ; j S[i] i i
    ; fix key length to be 128
    ; so x mod 128 == x ^ (x & 128)
    dup
    push 128                + + 0,0,0
    and                     + xor           ; would imply constant. why would you want constant?
    xor
    push DATA               + + !,!,!
    load                ; j S[i] i KEY[i % len(KEY)]
    rot
    add
    rot                     + and
    add                 ; i j
    dup
    rot
    dup
    rot                 ; j i i j
    ; memswap
    dup
    push SBOX               + + !,!,!
    load
    swap
    rot                 ; j i S[j] j i
    dup
    push SBOX               + + !,!,!
    load
    rot
    push SBOX               + + !,!,!
    store
    push SBOX               + + !,!,!
    store
    ; end memswap
    push 1              ; not going to constrain this one.
    add
    dup
    jnz _ksa_2_loop         + + 253,253,253

; PRGA
    and
    dup                 ; j 0 -> 0 0
_prga_loop:
    push 1              ; not constraining this either
    add
    dup
    push SBOX               + + !,!,!
    load
    rot
    add                 ; i' j'
    dup
    rot
    dup
    rot                 ; j i i j
    dup
    rot
    dup
    rot                 ; j i j i i j
    ; memswap
    dup
    push SBOX               + + !,!,!
    load
    swap
    rot
    dup
    push SBOX               + + !,!,!
    load
    rot
    push SBOX               + + !,!,!
    store
    push SBOX               + + !,!,!
    store
    ; end memswap
    push SBOX               + + !,!,!
    dup
    rot
    swap
    load
    rot
    rot
    dup
    rot
    swap
    load
    rot
    add                 ; j i SBOX (S[i]+S[j])
    swap
    load
    swap
    dup
    ; -1 offset from actual ct because first byte has to be [1]
    push CT2_OFF            + + 79,99,109               ; hardcoded; dependent on actual value
    add
    push TEXT               + + !,!,!
    load                    + store
    dup
    jnz _prga_continue      + + 253,254,255
    ; (just exit)
    ; \n will be embedded in the text i guess
    hlt (0)                 + dup,push,pop              ; unfortunately cant be constrained
_prga_continue:
    rot
    xor                     + add,mul,and               ; intentionally force rc4 recognition
    print                   + pop
    jmp _prga_loop          + + 251,252,253             ; this one is probably the hardest?
