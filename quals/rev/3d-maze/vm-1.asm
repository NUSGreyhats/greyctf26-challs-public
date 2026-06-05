; bytewise stack machine with load/store architecture
; segmented addressing: load eats two operands, <segment> / <address>
; - [0] TEXT -- rodata first (ct1, ct2), followed by code (align to segment end)
; - [1] DATA -- user input / key / continuation of code
; - [2] SBOX -- yea


; primary loader
; goals:
; - red herring (not meant to solve the challenge)
; - but must look solvable AND difficult to an agent
; - but also must somehow
; - so i think, quitting will just give an implicit +20 boost to the next score
;    - notice first instruction is 0. im thinking we can fake and make it look like the first 2 moves MUST be 0 and 0
;    - but in reality the quitting bonus adds to the first move so it becomes push 0
;    - which would mean you must quit first to get that bonus on the next run
; use [0] for user input
; - final input should definitely be a string
; computes "hash" (f, g) via some basic math
; - f(a) by x = x + a
; - g(a) by x = 131*x + a (any coprime works apparently e.g. 3 but 131 looks suspicious)
; checks hashes against target (just hardcode lol)
; if correct, do simple decryption against ct

; hash (see above)
    push 0
    dup
    dup
_hash_loop:
    dup
    push DATA
    load
    rot
    add
    rot
    rot
    dup
    push DATA
    load
    rot                 ; F' i C G
    dup
    dup
    add
    dup                 ; F' i C G 2G 2G
    push 255
    swap
    sub                 ; F' i C G 2G ~2G
    rot
    dup
    rot                 ; F' i C 2G G G 1 (effectively)
_bitshift_loop:
    dup
    add
    dup
    jz _bitshift_end
    swap
    dup
    add
    swap                ; F' i C 2G G 2G 2 (effectively)
    jmp _bitshift_loop
_bitshift_end:
    pop                 ; F' i C 2G G 128G
    add
    add
    add
    rot
    rot                 ; G' F' i
    push 1
    add
    dup
    jnz _hash_loop

; check
    push TARGET_F
    add
    xor
    jnz _wrong
    push TARGET_G
    xor
    jz _correct
_wrong:
    ; can expand this with filler if feeling the need to
    hlt (0)
_correct:
    ; decryption scheme:
    ; p = c ^ a ^ b
    ; a, b = b, p
    push 0
    push 6
    push DATA
    load
    push 7
    push DATA
    load                ; i a b
_decrypt_loop:
    dup
    rot
    xor                 ; i b a^b
    rot
    dup
    push TEXT
    load
    rot                 ; b i c a^b
    xor
    dup
    jz _decrypt_exit
    dup
    print
    swap
    push 1
    add
    rot
    rot                 ; i b p -- i a' b'
    jmp _decrypt_loop
_decrypt_exit:
    push 10
    print
    pop
    pop
    pop
    ; hlt (0)
