#!/usr/bin/env python3
"""
3D Maze Generator with Embedded Character Encoder
Author: Antigravity

Generates a 3D maze of size (2N+1)x(2N+1)x(2N+1) where N is odd and >= 15.
Features:
- Randomized DFS for high-quality standard maze layers.
- Swiss cheese grate transition layers for vertical traversability.
- Embedded character encoder that guarantees mathematical traversability
  of any 5x5 2D character trace.
- Sparse boost placement (at most 5% of valid path cells) excluding the center core.
- Built-in verification engine to trace 2D character sequences in 3D.
"""

import sys
import random
import argparse

# Standard lowercase letter direction sequences (from center)
LETTER_TRACES = {
    'c': 'awssd',
    'g': 'asdwssa',
    'j': 'dsssa',
    'l': 'ssss',
    'o': 'awssddaaw',
    'u': 'ssdaaw'
}

def generate_2d_maze(N):
    """
    Generates a standard 2D maze of path size N x N using randomized DFS.
    The resulting grid has dimensions (2N+1) x (2N+1).
    """
    grid_2d = [['#' for _ in range(2*N+1)] for _ in range(2*N+1)]
    visited = [[False for _ in range(N)] for _ in range(N)]
    
    def dfs(r, c):
        visited[r][c] = True
        grid_2d[2*r+1][2*c+1] = ' '
        
        # Directions: up, down, left, right in terms of path cells
        dirs = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        random.shuffle(dirs)
        
        for dr, dc in dirs:
            nr, nc = r + dr, c + dc
            if 0 <= nr < N and 0 <= nc < N and not visited[nr][nc]:
                # Open the wall between (r, c) and (nr, nc)
                grid_2d[2*r+1 + dr][2*c+1 + dc] = ' '
                dfs(nr, nc)
                
    dfs(0, 0)
    return grid_2d

def generate_3d_maze(N, seed=67):
    """
    Generates a 3D maze of size (2N+1)x(2N+1)x(2N+1) satisfying all requirements.
    """
    random.seed(seed)
    
    # 1. Initialize the 3D grid with all walls
    grid = [[['#' for _ in range(2*N+1)] for _ in range(2*N+1)] for _ in range(2*N+1)]
    
    # 2. Generate standard 2D mazes for each odd layer (the playable maze layers)
    for z_idx in range(N):
        z = 2 * z_idx + 1
        grid_2d = generate_2d_maze(N)
        for y in range(2*N+1):
            for x in range(2*N+1):
                grid[z][y][x] = grid_2d[y][x]
                
    # 3. Create transition layers (even z) as swiss cheese / grates
    # All odd (y, x) coordinates in transition layers (except boundaries z=0, 2N) are paths.
    for z in range(2, 2*N, 2):
        for y in range(1, 2*N, 2):
            for x in range(1, 2*N, 2):
                grid[z][y][x] = ' '
                
    # 4. Punch holes in the center 5x5 grid just enough to satisfy the character encoder.
    # Center physical coordinate is N (since start is at (N, N, N)).
    # The 5x5 path cells are centered at N, with physical coordinates N + 2*i.
    connections = []
    # Horizontal adjacent connections in the 5x5 path grid
    for i in [-2, -1, 0, 1, 2]:
        for j in [-2, -1, 0, 1]:
            y = N + 2 * i
            x = N + 2 * j + 1
            connections.append((y, x))
    # Vertical adjacent connections in the 5x5 path grid
    for i in [-2, -1, 0, 1]:
        for j in [-2, -1, 0, 1, 2]:
            y = N + 2 * i + 1
            x = N + 2 * j
            connections.append((y, x))
            
    # Check which connections are already open on at least one layer
    open_connections = set()
    for (cy, cx) in connections:
        for z in range(1, 2*N, 2):
            if grid[z][cy][cx] == ' ':
                open_connections.add((cy, cx))
                break
                
    # Filter closed connections
    closed_connections = [c for c in connections if c not in open_connections]
    
    # Shuffle closed connections and distribute them to layers
    random.shuffle(closed_connections)
    maze_layers = list(range(1, 2*N, 2))
    for idx, (cy, cx) in enumerate(closed_connections):
        z = maze_layers[idx % len(maze_layers)]
        grid[z][cy][cx] = ' '
        
    # 5. Place start and end
    # Center layer is N, center cell is (N, N, N)
    # End is at bottom right corner of the center layer (N, 2N-1, 2N-1)
    grid[N][N][N] = ' '  # Player start is a path cell
    grid[N][2*N-1][2*N-1] = 'F'
    
    # 6. Randomly scatter boosts sparsely
    # Valid cells are path cells on odd layers, excluding start, end, and the center core taxicab distance
    valid_cells = []
    min_dist_threshold = 1.5 * (N - 1)
    
    for z in range(1, 2*N, 2):
        for y in range(1, 2*N, 2):
            for x in range(1, 2*N, 2):
                if grid[z][y][x] == ' ':
                    # Exclude start and end
                    if (z, y, x) == (N, N, N) or (z, y, x) == (N, 2*N-1, 2*N-1):
                        continue
                    # Compute taxicab distance from center (N, N, N)
                    dist = abs(z - N) + abs(y - N) + abs(x - N)
                    if dist >= min_dist_threshold:
                        valid_cells.append((z, y, x))
                        
    # Scatter boosts sparsely: at most 5% of valid cells
    num_boosts = int(0.05 * len(valid_cells))
    boost_cells = random.sample(valid_cells, num_boosts)
    for (bz, by, bx) in boost_cells:
        grid[bz][by][bx] = '.'
        
    return grid

def find_3d_path_for_moves(grid, N, moves):
    """
    Finds a 3D path starting at (N, N, N) that matches the 2D sequence of moves (w, a, s, d),
    allowing arbitrary vertical up/down transitions.
    """
    import collections
    start = (N, N, N, 0)
    queue = collections.deque([(start, [(N, N, N)])])
    visited = set([start])
    
    dir_map = {
        'w': (-2, 0), # (dy, dx)
        's': (2, 0),
        'a': (0, -2),
        'd': (0, 2)
    }
    
    while queue:
        (z, y, x, step_idx), path = queue.popleft()
        
        if step_idx == len(moves):
            return path
            
        # 1. Horizontal moves matching the current character trace
        move = moves[step_idx]
        if move in dir_map:
            dy, dx = dir_map[move]
            ny, nx = y + dy, x + dx
            if 0 < ny < 2*N and 0 < nx < 2*N:
                # Check if path is open on this layer
                wall_y, wall_x = y + dy//2, x + dx//2
                if grid[z][wall_y][wall_x] != '#' and grid[z][ny][nx] != '#':
                    state = (z, ny, nx, step_idx + 1)
                    if state not in visited:
                        visited.add(state)
                        queue.append((state, path + [(z, ny, nx)]))
                        
        # 2. Vertical moves (up/down) to any other odd layer
        for nz in [z - 2, z + 2]:
            if 0 < nz < 2*N:
                mid_z = (z + nz) // 2
                # Check if vertical shaft is clear
                if grid[mid_z][y][x] != '#' and grid[nz][y][x] != '#':
                    state = (nz, y, x, step_idx)
                    if state not in visited:
                        visited.add(state)
                        queue.append((state, path + [(nz, y, x)]))
                        
    return None

def main():
    parser = argparse.ArgumentParser(description="Generate a beautiful 3D maze with embedded character encoder.")
    parser.add_argument("size", type=int,
                        help="Maze size N (must be odd and >= 15). Grid size will be 2N+1.")
    parser.add_argument("--test-char", "-c", type=str, default="g",
                        help="Character to trace (e.g. 'c', 'g', 'j', 'l', 'o', 'u') or custom move string of w,a,s,d.")
    parser.add_argument("--raw", action="store_true",
                        help="Output only the raw character grid without titles or headers.")
    parser.add_argument("--seed", type=int, default=67,
                        help="Random seed for generation.")
                        
    args = parser.parse_args()
    
    N = args.size
    if N < 15 or N % 2 == 0:
        print("Error: Size N must be odd and at least 15.", file=sys.stderr)
        sys.exit(1)
        
    # Generate the 3D maze
    grid = generate_3d_maze(N, seed=args.seed)
    
    # Standard stdout printing
    if args.raw:
        for z in range(2*N+1):
            for y in range(2*N+1):
                sys.stdout.write("".join(grid[z][y]))
    else:
        print("========================================")
        print(f"       3D MAZE GENERATOR (Size N={N})")
        print(f"       Grid dimensions: {2*N+1}x{2*N+1}x{2*N+1}")
        print(f"       Total character cells: {(2*N+1)**3}")
        print("========================================\n")
        
        # Count boosts
        boost_count = sum(row.count('.') for layer in grid for row in layer)
        print(f"Start cell (Center): ({N}, {N}, {N})")
        print(f"End cell 'F': ({N}, {2*N-1}, {2*N-1})")
        print(f"Sparse boosts ('.') placed: {boost_count}")
        print()
        
        # Print the grid layer by layer
        for z in range(2*N+1):
            print(f"--- Layer {z} ---")
            for y in range(2*N+1):
                print("".join(grid[z][y]))
            print()
            
        # Perform character trace verification
        test_val = args.test_char.lower()
        moves = LETTER_TRACES.get(test_val, test_val)
        
        # Ensure moves only contain valid characters
        if not all(m in 'wasd' for m in moves):
            print(f"Skipping verification: Custom sequence '{moves}' contains invalid directions. Only 'w', 'a', 's', 'd' allowed.")
        else:
            print("========================================")
            print(f"    SECRET ENCODER TRACE VERIFICATION")
            print(f"    Tracing sequence: '{moves}' (mapped from '{args.test_char}')")
            print("========================================")
            path = find_3d_path_for_moves(grid, N, moves)
            if path:
                print("✓ Character trace successfully encoded and verified!")
                print("\n3D Path Steps:")
                current_idx = 0
                for i, pos in enumerate(path):
                    if i == 0:
                        print(f"  Start at Center: {pos}")
                    else:
                        prev_pos = path[i-1]
                        if pos[0] != prev_pos[0]:
                            direction = "Up" if pos[0] < prev_pos[0] else "Down"
                            print(f"  Step {i:2d}: Move {direction:<4} to Layer {pos[0]} at {pos[1:3]}")
                        else:
                            move_char = moves[current_idx]
                            current_idx += 1
                            dir_word = {"w": "North (w)", "s": "South (s)", "a": "West (a)", "d": "East (d)"}[move_char]
                            print(f"  Step {i:2d}: Move {dir_word:<9} on Layer {pos[0]} to {pos[1:3]}")
            else:
                print("✗ Verification failed: No 3D path found matching the 2D direction sequence.")
                print("This should not happen. Please verify your maze generation algorithms.")

if __name__ == "__main__":
    main()
