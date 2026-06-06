# Challenge List

Difficulty estimates assume quals players may use frontier coding agents.

Ports use the format `3<category_id><chall_id>67` (range 30000–39999). `category_id` follows the section order below; `chall_id` is the row order within each section (extra folders not in a table are appended alphabetically).

Remote host: `challs.nusgreyhats.org`

### ezpz

_a collection of BEGINNER-FRIENDLY challenges_

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | AE-no-S | Removing SubBytes from AES makes it an affine system over GF(2). | 1 | NA |
| yes | BabyRSA | Coppersmith RSA solved with sage small_roots | 1 | NA |
| yes | Fort Knockies | Local password manager forensics | 2 | NA |
| yes | babyheap | free libc pointer, overwrite function ptr and profit | 1 | 31367 |
| yes | pollution | Prototype pollution in JS leading to RCE | 1 | 31467 |
| yes | Codex Computer Use | Agent trace of Codex using computer use leaks the flag through the screenshots taken by codex | 1 | NA |
| yes | say_my_name | Identify the alien mascot from GreyCTF 2026 artwork | 1 | NA |
| yes | My Greycat | Static analysis, write python script to accelerate decryption | 1 | NA |

### pwn

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | dbench_jumbf | Heap corruption in a C2PA/JUMBF JPEG metadata parser service. | 4 | 32167 |
| yes | elite ball knowledge | ROP with io_uring syscalls | 2 | 32267 |
| yes | baby-bof | Stack BOF exploited using exception handler | 2 | 32367 |

### rev

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | lights-out | Minecraft block extraction + solve GF(2) linear system | 2 | NA |
| yes | 3d-maze | Build valid RC4 bytecode on stack VM using maze moves | 4.5 | NA |
| yes | spidr | Control Flow Obfuscation, requires IDA scripting | 3 | NA |
| yes | ghidra-ganster-edition | Windows-only Ghidra decompiler challenge | 3 | NA |
| yes | gopher-adventure | go wasm game created with ebitengine | 32 | 33167 |

### web

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | Go Going Goen | LinkedOut ladder web challenge with staged progression and shared-platform protections. | 3 | 34167 |
| yes | Greyhats Gallery | Photo gallery ZIP upload challenge leading to a procfs/libuv signal-pipe RCE chain. | 4 | 34267 |
| yes | Red Flag | CRM path traversal to report export command execution in an obfuscated Go service. | 3 | 34367 |
| yes | GreyCat Game | Browser game with an off-by-one twist | 2 | 34467 |
| yes | SeeTeeEffedIn | Postgres REFINT cascade SQL injection web challenge | 4 | 34567 |

### forensics

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | Chiaroscuro | FFT an audio file, phase shift using a binary phase shift key to encode flag, solve the chunk size and message len, finally decode the flag from the first chunk of audio. | 3 | NA |
| yes | Crimewatch | Android emulator image forensics | 2 | NA |
| yes | Grey Yuumi | League replay + USB mouse capture forensics | 2 | NA |

### misc

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | An old soviet terminal | Bypass information flow control through declassification abuse. Difficulty comes from obscure programming language. | 3 | 36167 |
| yes | Wait a minute | Exploit an evil regex to achieve ReDoS (CPU-limited via redpwn.jail) | 2 | 36267 |
| yes | Training Shooting Flags | ECP5 bitstream rev | 3 | NA |

### crapto (?)

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | filter_flag | PCBC decryption oracle, but flag is filtered | 1 | 37167 |
| yes | caexor | LLL CVP with error vector deriving into the xor  | 3 | 37267 |

### ai

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | Duality In All Things | Dual-formulated linear SVM | 3 | NA |
| yes | SABLE | SDPA graph-attention Sybil injection. | 3 | 38267 |
| yes | Jurgen's Revenge | ML Interpretability Challenge. | 4 | NA |
| yes | If Models Could Dream | Extract the flag from a World Model's dreams. | 5 | NA |
