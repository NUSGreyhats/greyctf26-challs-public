    push v0
    dup
_loop_1:
    dup
    push 2      ; 0 <= x < 0x10, else segfault
    store       ; v0 v0 v0 2 -> v0; 2[v0] = v0
                ; may have some loop involved
                ; after discovering loop structure:
                ; i j j 2 -> i ; 2[j] = j
    push v1
    add
    dup         ; v0+v1 v0+v1
                ; other instructions don't work
                ; (must have >= 1 value on stack before jnz)
    jnz f5      ; _loop_1

; effect:
; if v1 coprime with 256, then (forall byte i) 2[i] = i
; current stack: 0

    dup         ; 0 0
_loop_2:
    dup
    push 2
    load        ; 0 0 0 2 -> 0 0 2[0]
    swap
    dup
    dup
    push v2     ; 0 2[0] 0 0 0 v2
    and/xor
    xor
    push 1
    load        ; 0 2[0] 0 1[0^(0?v2)]
                ; 0 x    0 y
    rot
    add
    rot         ; if and, then runs out of values for next rot
    add
    dup
    rot
    dup
    rot         ; y+x+0 0 0 y+x+0
    dup
    push 2
    load        ; y+x+0 0 0 y+x+0 2[y+x+0]
    swap
    rot         ; y+x+0 0 2[y+x+0] y+x+0 0
    dup
    push 2
    load        ; y+x+0 0 2[y+x+0] y+x+0 0 2[0]
    rot
    push 2
    store       ; y+x+0 0 2[y+x+0] 0 ; 2[y+x+0] = 2[0]
    push 2
    store       ; y+x+0 0 ; 2[0] = 2[y+x+0] (stale)
                ; memswap operation
    push v3
    add         ; y+x+0 0+v3
    dup
    jnz d3      ; _loop_2
                ; some leap of faith involved but plugging d3 here
                ; forms a very undeniably clean loop
                ; idea was hopefully you would be incentivized
                ; to explore the unique option (out of the 4) first...

; compare loop variants:
; 0 0 -> 2[0]+1[0^(0?v2)]+0 0+v3
; or,
; j i -> 2[i]+1[i^(1?v2)]+j i+v3

; while i:
;     j += MYSTERY[i] + DATA[f(i)]
;     swap_mystery(i, j)
;     i += v3

    and         ; j 0 -> 0
    dup         ; 0 0
                ; label as _0 0 to save some trouble later (see above)
_loop_maybe:
    push v4
    add
    dup
    push 2
    load        ; _0 0+v4 2[0+v4]
    rot
    add
    dup         ; 0+v4 2[0+v4]+_0 2[0+v4]+_0
    rot
    dup
    rot
    dup         ; 2[0+v4]+_0 0+v4 0+v4 2[0+v4]+_0 2[0+v4]+_0
    rot
    dup
    rot         ; 2[0+v4]+_0 0+v4 2[0+v4]+_0 0+v4 0+v4 2[0+v4]+_0
                ; j          i    i          j    j    i
    dup
    push 2
    load        ; j i i j j i 2[i]
    swap
    rot         ; j i i j 2[i] i j
    dup
    push 2
    load        ; j i i j 2[i] i j 2[j]
    rot
    push 2
    store       ; j i i j 2[i] j ; 2[i] = 2[j]
    push 2
    store       ; j i i j ; swap_mystery(i, j)
    push 2
    dup
    rot
    swap        ; j i i 2 j 2
    load
    rot
    rot
    dup
    rot
    swap        ; j i 2[j] 2 i 2
    load
    rot
    add
    swap
    load        ; j i 2[2[i]+2[j]]
    swap
    dup
    push v5
    add         ; j 2[2[i]+2[j]] i i+v5
                ; j k            i i+v5

; remaining bytes are intentionally underconstrained.
; extrapolate from rc4 implementation / ctf intuition:

    push 0
    load        ; not store (rc4)
    dup         ; j k i 0[i+v5] 0[i+v5]
    jnz 1       ; _loop_print
                ; doesn't make sense at first glance,
                ; but required for rc4 to work
    
    dup/pop/rot ; ???

_loop_print:
    rot
    xor
    print       ; j i ; print k^0[i+v5]
    jmp bd      ; _loop_maybe

; looking at vm.bin, jz hits right before the actual vm
; so reasonable to treat jz as termination condition
; (no more useful bytes afterwards anyway).
; so (???) should be an *invalid byte*, though it could be
; argued that any byte would work (i.e. UB)

; in total: 6+1 unconstrained bytes;
; less assuming standard rc4:
; - v0: (any byte)
; - v1: (any coprime)
; - v2: 80, followed by and -- simulates modulo
; - v3: arguably anything, but 1 per standard rc4
; - v4: 1 (see above)
; - v5: any offset, though one of them makes the most sense
; - instruction near the end: anything really
