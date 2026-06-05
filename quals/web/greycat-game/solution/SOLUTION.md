# GreyCat Game Solution

## Real flag

`grey{th3_trex_rep1ac3d_by_a_gr3y_cat}`

## Intended solve path

1. Start a run and survive long enough to enter the late fast phase.
2. Let the browser send several legitimate `/api/run` updates over time.
3. Open devtools and inspect the late-game `/api/ghost` responses.
4. Notice that the response carries `stamp` and `traceId` values rather than plain flag text.
5. Open the loaded client JavaScript and find the decode logic used to turn those values into visible background fragments.
6. Reproduce that decode step on the captured `stamp` values and recover each fragment in order.
7. Join the decoded fragments to recover the full flag.

The decode logic uses the `traceId` seed and index to derive a small XOR key,
then applies that key across the base64-decoded `stamp` bytes to reconstruct
the original fragment text.

The fragment sequence is:

```text
grey{th3_
trex_
rep1ac3d_
by_a_
gr3y_
cat}
```

Which reconstructs to:

```text
grey{th3_trex_rep1ac3d_by_a_gr3y_cat}
```

## Bait Flags :')

- `index.html` contains flag-like scraps.
- `styles.css` exposes hidden generated content.
- `localStorage` and runtime globals expose checksum and traffic-themed noise.
- Obstacles still carry faint decoy strings.

These are there to nudge players toward inspection without making the real flag a one-grep client-side leak.
