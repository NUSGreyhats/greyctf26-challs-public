# Grey Yuumi - Writeup

**Category:** Forensics
**Flag:** `grey{yuum1logg3r_4ttach3d}`

## Idea

The handout contains a League replay (`.rofl`) and a USB capture (`.pcapng`).

The replay is not the flag by itself. It is there to give the important game timing: find when the relevant player dies, then use that timestamp to isolate the matching portion of the USB mouse capture.

## Intended Path

1. Inspect the `.rofl` replay and determine the death time for the relevant player/event.
2. Map that game timestamp onto the `.pcapng` timeline.
3. Extract USB HID mouse reports from the capture.
4. Decode the mouse reports:

```text
button = report[0]
dx     = signed int16 little-endian report[2:4]
dy     = signed int16 little-endian report[4:6]
wheel  = signed int8 report[6]
```

5. Integrate `dx, dy` to reconstruct the relative cursor path.
6. Keep the right-click strokes from the window around the death time.
7. Render those strokes to recover the drawn flag.

## Helper

`mouse_trace.py` renders the full right-click trace from the USB capture:

```bash
python3 mouse_trace.py grey_yuumi.pcapng -o trace.png
```

For solving, the important extra step is filtering the decoded trace to the replay death-time window before rendering.

## Flag

```text
grey{yuum1logg3r_4ttach3d}
```
