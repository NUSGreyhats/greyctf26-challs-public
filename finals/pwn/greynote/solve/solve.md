# greynote — solve writeup

Cross-cache UAF → Dirty Pagetable → `cred` overwrite, against a SLUB **sheaves**
kernel (Linux 7.0.x) with SMEP, SMAP and KASLR.

---

## 1. The bug

`greynote` is a misc device (`/dev/greynote`) exposing four ioctls over an array
of up to `0x1000` note slots:

| ioctl      | action                                                        |
|------------|---------------------------------------------------------------|
| `GN_ALLOC` | `kmem_cache_zalloc` a note into `notes[idx]`                  |
| `GN_FREE`  | `kmem_cache_free(notes[idx])` **but leaves `notes[idx]` set** |
| `GN_EDIT`  | `copy_from_user` into `notes[idx]->data`                      |
| `GN_READ`  | `copy_to_user` from `notes[idx]->data`                       |

`GN_FREE` frees the object but never clears the slot pointer:

```c
kmem_cache_free(note_cache, notes[idx]);
/* BUG: notes[idx] not cleared -> dangling pointer */
```

So after a free we still have full **use-after-free read and write** on the
freed object via `GN_READ` / `GN_EDIT` (and a double-free, unused here).

## 2. Why it has to be cross-cache

Notes live in their **own dedicated cache**:

```c
note_cache = kmem_cache_create("greynote", NOTE_SIZE /*0x400*/, 0,
                               SLAB_NO_MERGE, NULL);
```

`SLAB_NO_MERGE` means the cache is never merged with `kmalloc-1024`, so we can
**not** reclaim a freed note with a normal kmalloc victim object in the same
cache. The only thing a freed note's slab shares with the rest of the system is
its **physical page**, once that page is returned to the buddy allocator. That
is the cross-cache angle: recycle the *page*, not the *object*.

### Object geometry

`NOTE_SIZE = 0x400` (1024 B), and the cache reports `objs_per_slab = 16`, so a
greynote slab is an **order-2 page block** (16 KB = 4 pages, 16 × 1024 B). Each
4 KB page inside a slab therefore holds exactly 4 notes.

## 3. The sheaves problem (what changed vs. older kernels)

On a classic SLUB kernel you free a slab's worth of objects, drain the per-CPU
*partial* list, and the empty slab page goes back to the buddy allocator.

This kernel uses **percpu sheaves** and has **removed percpu-partial slabs**. A
`kmem_cache_free` no longer decrements the slab's in-use count directly:

```
free -> percpu sheaf (array, capacity C)
     -> per-node "barn"  (holds up to ~B full sheaves)
     -> only on overflow are objects pushed back to the real slab
```

Consequences for the exploit:

* Freeing a handful of notes does **nothing** observable — they just sit in the
  sheaf and get re-handed-out LIFO.
* To actually empty a slab you must overflow the whole front end: roughly
  `(2 + B) * C` frees are absorbed by the two percpu sheaves plus the barn
  before anything drains back to slabs.
* Everything must stay **on one CPU** (`sched_setaffinity`) — sheaves are
  per-CPU, and the freed page is later reclaimed from this CPU's percpu
  page-allocator freelist too.

Once objects *do* drain back and a slab becomes empty, the back end is actually
simpler than before (no partial list): when `nr_partial > min_partial` the empty
**order-2 page** is released to the buddy allocator.

Because page tables come straight from the buddy allocator and **bypass the
sheaf layer entirely**, the reclaim target — a page table — needs no sheaf
draining, which is what makes Dirty Pagetable the clean choice here.

## 4. Exploitation pipeline

The exploit (`exploit.c`) runs five stages.

### Stage 1 — groom
Allocate `NGROOM = 2048` notes. This forces the cache to create many fully
occupied order-2 slabs that are entirely under our control.

### Stage 2 — drain slabs to the buddy allocator
Free **all** `NGROOM` notes, keeping every index (each is now a dangling UAF
handle). The first `~(2+B)*C` frees fill the sheaf + barn; the rest drain back
into the slabs, empty them, and release whole order-2 pages to the buddy
allocator. `NGROOM` is sized well above the sheaf/barn reservoir so dozens of
slabs actually empty.

### Stage 3 — reclaim a freed page as a page table
`mmap` a large, **2 MB-aligned** anonymous region (`MAP_NORESERVE`, so a 1 GB
mapping is accepted on the 512 MB VM) and fault it **one 2 MB chunk at a time**:

* Faulting a 2 MB range makes the kernel allocate exactly **one order-0 PTE
  page**.
* That order-0 demand also forces the buddy allocator to **split our freed
  order-2 slab blocks** back into order-0 pages.
* So a freed note's page gets reused as a page table.

After each region we `GN_READ` every dangling note. When one reads back as a
densely populated page table — entries shaped like `0x8000_0000_xxxxx_067`
(NX | present | rw | user | accessed | dirty, ascending PFNs) — that note now
**aliases live kernel PTEs**. `looks_like_ptes()` makes this decision; the
debug dump prints the entries so you can eyeball the ascending PFNs.

We record `U` (the winning note index) and `Rbase` (the 2 MB-aligned VA the PTE
page maps). 2 MB alignment guarantees `entry_index == (VA - Rbase) / PAGE`.

### Stage 4 — anchor the window to a virtual address
A 1 KB note overlaps only **128 of the 512 PTEs** in the page — one quarter
`q ∈ {0,1,2,3}`, mapping VAs `[Rbase + q·128·PAGE, +128·PAGE)`. To learn `q`:

* Read the window; `entry0` is currently present (`w0[0]`).
* For each candidate quarter, `MADV_DONTNEED` its base page. Only for the
  **correct** quarter does this tear down *our* `entry0`, which we observe
  through the UAF read (`chk[0]` changes).

That candidate is `V0`, the base of the 128 pages whose PTEs we can now forge by
writing through the note.

### Stage 5 — arbitrary physical R/W → `cred` overwrite
We now have a controllable page table: writing 128 PTEs via `GN_EDIT` maps 128
physical frames of our choosing at `V0`. Sweep physical RAM a 512 KB window at a
time looking for our own `struct cred`:

```
struct cred { atomic_long usage; u32 uid, gid, suid, sgid, euid, egid, fsuid, fsgid; ... }
```

A `cred` for our process is **eight consecutive `u32` equal to our uid (1000)**
preceded by a small `usage` refcount. On a match we zero those eight fields. We
don't identify *our* cred in advance — after zeroing each candidate we just call
`getuid()`; the instant we hit our own cred it returns `0` and we
`execl("/bin/sh", …)` for a root shell. Zeroing another uid-1000 task's cred
first is harmless.

#### Two details that make Stage 5 not crash the box

* **`_PAGE_SPECIAL` (bit 9) is set in every forged PTE** (`PTE_RW = 0x267`).
  The forged PTEs point at memory we don't own; without `_PAGE_SPECIAL` the
  per-epoch `MADV_DONTNEED` (used to flush the window's TLB) would run
  `put_page` on every scanned frame, corrupting refcounts across all of RAM and
  hanging the kernel. With it, the kernel treats the frame as having no
  `struct page`, so `madvise`/`fork`/`exit` never touch the refcount. Hardware
  ignores bit 9, so reads/writes still work.
* **`SCAN_END` must be ≤ installed RAM** (`-m 512M` → `0x2000_0000`). Scanning
  past real RAM maps device MMIO, and reading that wedges the VM.

## 5. Tunables (`exploit.c`)

| macro       | value          | meaning                                                      |
|-------------|----------------|--------------------------------------------------------------|
| `NGROOM`    | `2048`         | notes sprayed/freed; must exceed the sheaf+barn reservoir    |
| `AREASZ`    | `1 GB`         | VA reservoir faulted to spray PTE pages (lazy, `MAP_NORESERVE`) |
| `SCAN_BASE` | `0x100_0000`   | physical scan start (16 MB; skips low MMIO)                  |
| `SCAN_END`  | `0x2000_0000`  | physical scan end; **must be ≤ RAM (512 MB)**                |
| `PTE_RW`    | `0x267`        | present\|rw\|user\|accessed\|dirty \| `_PAGE_SPECIAL`        |
| `UID`       | `1000`         | the uid we are looking for in physmap                        |
