# Challenge List

Note: **NO LLM agents / chatbots** in finals.

### pwn

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | cpp-bbq | C++ `shared_ptr` 32-bit refcount overflow → UAF → reclaim chunk, forge vtable → win() | 3 | 31067 |
| yes | artifact-4-revenge | Pivot to transform stack buffer *twice* to form shellcode | 2 | 31167 |
| yes | artifact-11-revenge | Underflow → Overflow → Stack BOF | 1 | 31267 |
| yes | greynote | Cross-cache UAF → Dirty Pagetable → cred overwrite | 4 | 31367 |
| yes | dictionary | CPython dict internals abuse → RCE | 3 | 31467 |

### rev

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | zuma gangster edition | reverse enough to find out you need to complete a fsop payload | 3 | NA |
| yes | greyhats-link | Lua CGI rev; custom block cipher over Z/251 matrix state, reverse firmware signing to recover flag | 3 | 32067 |

### web

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | if n00bcak could dream | parameter pollution | 1 | 33067 |
| yes | shiny-notes | Big5 multibyte SQLi + VSV00019 HTTP/2-to-HTTP/1 request smuggling, XSS to steal the admin bot's browser-side flag secret | 4 | 33167 |
| yes | GreyCTF 2026 Feedback Form | URL parser differential | 2 | 33467 |
| yes | Let's Go Gambling! | Cold cache hit side channel | 2 | 33267 and 33367 |

### forensics

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | Our Drafts Unite | Filesystem analysis, openstego LSB steg, zip manual deflation decryption, XOR of images | 3 | NA |


### misc

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | low cortisol gachapon | Onsite physical gachapon challenge; solve using Proxmark/Flipper interaction with the machine | 2 | NA |

### crapto (?)

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | Efficient DSA Algorithm | LFSR-generated ECDSA nonce; use Berlekamp-Massey to predict `k`, recover the private key, and decrypt the flag. | 2 | NA |
| yes | Half-Bit Wonder | LadderLeak paper; quite old already :P | 4 | NA |
| yes | Long Khipu Braids | Reconstruct omitted Lawrence-Krammer-Bigelow braid matrices and solve linear intertwiner systems to recover the shared key. | 5 | NA |
| yes | Wintertime 2 | POKE but modified; Use weil pairings + number theory to derive secrets and reverse decryption | 4 | NA |
| yes | random_brainrot | Use data analysis / maximum likelihood estimator to recover plaintext | 1 | 34067 |

### ai

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes | n00bcaks Last Gradient | Deep leakage from gradients. | 2 | NA |
| yes | enshittification-detector | LiRA-style membership inference using shadow models, candidate-specific calibration, and balanced no-feedback submissions. | 3 | 35067 |
| pending discussions to implement KOTH | blind-devil | Solve a 2x2x2 Rubik's cube knowing **ONLY** which faces are solved, in the fewest moves possible. | 5 | 35167 |


### hardware

| Done? | Name | Challenge Details | Estimated Difficulty (1-5) | Port Number |
| ----- | ---- | ----------------- | -------------------------- | ----------- |
| yes   | fast secure memory | Hardware TOCTOU + PIO Timing implementation | 3 | NA |
| yes   | watchdog | RISC-V soft-core on FPGA; read flag via MMIO and print over UART while evading the watchdog timer | 3 | NA |
| yes   | watchdog-koth | KOTH variant of watchdog — onstage `.wdog` submission, fewest clock cycles wins | 4 | NA |
| yes   | welcome to hardware | Intro to the ESP32-C6 GreyFlag badge: flash firmware with esptool, connect over USB serial, reverse provided firmware | 1 | NA |
| yes   | hidden in plain sight | Flag stored in ESP32 eFuses; dump with `espefuse` | 2 | NA |
| yes   | music to my ears | Inject a 20kHz square wave into the badge's audio input (TP3) to trigger the flag | 3 | NA |
| yes   | what's this thread connecting us? | OpenThread (802.15.4): join the Thread network, recover the network key, sniff frames (PAN ID 1337) and decrypt | 5 | NA |
