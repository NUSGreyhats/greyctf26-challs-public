# Grey Yuumi - Writeup

**Category:** Forensics
**Flag:** `grey{yuum1logg3r_4ttach3d}`

## Idea

The handout contains a League replay (`.rofl`) and a USB capture (`.pcapng`).

The replay gives the important game timings: note the death timers, then use those timestamps to isolate matching portions of the USB mouse capture.

## Intended Path

1. Run the solve script from this directory:

```bash
python3 solve.py
```

The script extracts `../dist/grey_yuumi.tar.gz`, uses the known death timers from the replay, and renders one PNG for each candidate right-click window into the current working directory.

The PCAP timeline is not assumed to be exactly the same length as the game timeline, so the script maps game time onto PCAP time by duration ratio using the replay duration and renders `±20` seconds around each death timer.

2. The solve uses these death timers:

```text
5:36, 7:02, 9:40, 12:40, 18:14, 21:21, 23:09, 24:17, 26:09
```

3. Map each timer onto the PCAP timeline.

4. Extract USB HID mouse reports from the capture. The report format used here is:

```text
button = report[0]
dx     = signed int16 little-endian report[2:4]
dy     = signed int16 little-endian report[4:6]
wheel  = signed int8 report[6]
```

5. Integrate `dx, dy` to reconstruct the relative cursor path.
6. Keep the right-click strokes from the window around each death timer.
7. Render those strokes to recover the drawn flag.

## Flag

```text
grey{yuum1logg3r_4ttach3d}
```
