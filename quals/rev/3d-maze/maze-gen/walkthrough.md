# Walkthrough - 3D Maze Generator with Character Encoder

We have successfully implemented and verified the 3D maze generator with an embedded character encoder in [maze.py](file:///challenge/maze.py).

## Completed Accomplishments

1. **Maze Representation**:
   - Grid dimensions are exactly $(2N+1) \times (2N+1) \times (2N+1)$ where $N$ is odd and $\ge 15$.
   - Walls are `'#'`, paths are `' '`, boosts are `'.'`, and the end goal is `'F'`.
   - Start is at the center $(N, N, N)$ and is a path cell.
   - End `'F'` is at $(N, 2N-1, 2N-1)$ on the center layer.
2. **Layer Structures**:
   - Each playable odd-indexed layer is generated using randomized Depth-First Search (DFS), producing a high-quality organic maze.
   - Transition even-indexed layers are created as "swiss cheese grates" that allow vertical up/down traversal at any odd coordinate junction $(y, x)$.
3. **Secret Character Encoder**:
   - Embedded a mathematically guaranteed character encoder centered in the 5x5 path grid around $(N, N)$.
   - Scans the generated layers for the 40 possible adjacent connections in the 5x5 grid.
   - Minimally punches closed walls on a distributed set of layers to ensure **every one of the 40 connections is open on at least one layer**.
   - This guarantees that **any 2D move sequence** (like `'asdwssa'` for `'g'`) can be traced in 3D by interleaving layer transitions!
4. **Boost Placement**:
   - Computes the $L_1$ (taxicab) distance from the center $(N, N, N)$ for all odd path cells.
   - Filters out cells closer than $1.5(N-1)$ (50% of maximum distance), which mathematically guarantees a central boost-free core.
   - Sparsely scatters boosts on exactly 5% of these valid cells.
5. **Interactive Tracer Verification**:
   - Implements a 3D pathfinder/tracer that takes a 2D sequence of moves (e.g. `'asdwssa'` for `'g'`) and outputs the exact step-by-step coordinates.

## Verification Results

We verified the generation and character encoder with `python3 maze.py 15 --test-char g`.
The output path was successfully found:
```text
✓ Character trace successfully encoded and verified!

3D Path Steps:
  Start at Center: (15, 15, 15)
  Step  1: Move West (a)  on Layer 15 to (15, 13)
  Step  2: Move Down to Layer 17 at (15, 13)
  Step  3: Move South (s) on Layer 17 to (17, 13)
  Step  4: Move Up   to Layer 15 at (17, 13)
  Step  5: Move East (d)  on Layer 15 to (17, 15)
  Step  6: Move Up   to Layer 13 at (17, 15)
  Step  7: Move North (w) on Layer 13 to (15, 15)
  Step  8: Move South (s) on Layer 13 to (17, 15)
  Step  9: Move Up   to Layer 11 at (17, 15)
  Step 10: Move Up   to Layer 9 at (17, 15)
  Step 11: Move South (s) on Layer 9 to (19, 15)
  Step 12: Move Down to Layer 11 at (19, 15)
  Step 13: Move West (a)  on Layer 11 to (19, 13)
```
Notice how vertical moves are seamlessly interleaved to find the layers where the horizontal connections are open!
This is a stunning validation of the core concept.
