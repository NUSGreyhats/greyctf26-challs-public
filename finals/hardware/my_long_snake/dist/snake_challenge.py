import time

import displayio
import terminalio
from adafruit_display_text import label


MOVE_FILE = "/moves.txt"
SEED = 0x5A17C0DE
TARGET_APPLES = 40
MAX_MOVES = 4096
FLAG = "grey{yay_placeholder_flag}"

BOARD_W = 18
BOARD_H = 18
PLAY_MIN = 1
PLAY_MAX_X = BOARD_W - 2
PLAY_MAX_Y = BOARD_H - 2
CELL_SCALE = 8

COLOR_BG = 0
COLOR_GRID = 1
COLOR_BODY = 2
COLOR_HEAD = 3
COLOR_FOOD = 4
COLOR_WALL = 5

DIRS = {
    "U": (0, -1),
    "D": (0, 1),
    "L": (-1, 0),
    "R": (1, 0),
}


class XorShift32:
    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFF
        if self.state == 0:
            self.state = 0xA5A5A5A5

    def next(self):
        x = self.state
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= (x >> 17) & 0xFFFFFFFF
        x ^= (x << 5) & 0xFFFFFFFF
        self.state = x & 0xFFFFFFFF
        return self.state

    def below(self, limit):
        return self.next() % limit


def make_text_grid(width, x, y, color):
    palette = displayio.Palette(2)
    palette[0] = 0x000000
    palette[1] = color
    w, h = terminalio.FONT.get_bounding_box()
    grid = displayio.TileGrid(
        terminalio.FONT.bitmap,
        tile_width=w,
        tile_height=h,
        pixel_shader=palette,
        width=width,
        height=1,
    )
    grid.x = x
    grid.y = y
    return grid, terminalio.Terminal(grid, terminalio.FONT)


def write_line(term, text, width):
    line = text[:width]
    while len(line) < width:
        line += " "
    term.write("\r" + line)


def write_label(text_area, text, width):
    text_area.text = text[:width]


def wait_for_b_exit(hw_state):
    button_b = hw_state["btn_action"][1]
    while button_b.value is False:
        time.sleep(0.05)
    while button_b.value is True:
        time.sleep(0.05)
    while button_b.value is False:
        time.sleep(0.05)


def clear_board(board):
    for y in range(BOARD_H):
        for x in range(BOARD_W):
            if x == 0 or y == 0 or x == BOARD_W - 1 or y == BOARD_H - 1:
                board[x, y] = COLOR_WALL
            elif (x + y) & 1:
                board[x, y] = COLOR_GRID
            else:
                board[x, y] = COLOR_BG


def erase_cell(board, x, y):
    board[x, y] = COLOR_GRID if ((x + y) & 1) else COLOR_BG


def spawn_food(prng, snake):
    occupied = set(snake)
    for _ in range(2048):
        x = PLAY_MIN + prng.below(PLAY_MAX_X)
        y = PLAY_MIN + prng.below(PLAY_MAX_Y)
        if (x, y) not in occupied:
            return x, y
    raise RuntimeError("no free apple cell")


def draw_snake(board, snake):
    for i, cell in enumerate(snake):
        x, y = cell
        board[x, y] = COLOR_HEAD if i == 0 else COLOR_BODY


def initial_state(board):
    prng = XorShift32(SEED)
    snake = [(9, 9), (8, 9), (7, 9)]
    direction = (1, 0)
    food = spawn_food(prng, snake)
    clear_board(board)
    draw_snake(board, snake)
    board[food[0], food[1]] = COLOR_FOOD
    return prng, snake, direction, food


def parse_moves(path):
    try:
        with open(path, "r") as f:
            data = f.read()
    except OSError:
        return None, "missing %s" % path

    moves = []
    comment = False
    for c in data:
        if comment:
            if c == "\n":
                comment = False
            continue
        if c == "#":
            comment = True
            continue
        c = c.upper()
        if c in DIRS:
            moves.append(c)
            if len(moves) > MAX_MOVES:
                return None, "too many moves"
        elif c in " \r\n\t,.;:":
            continue
        else:
            return None, "bad char %r" % c
    return moves, None


def is_reverse(a, b):
    return a[0] + b[0] == 0 and a[1] + b[1] == 0


def replay_moves(board, moves, status, score_text):
    prng, snake, direction, food = initial_state(board)
    score = 0

    for step, move in enumerate(moves, 1):
        next_dir = DIRS[move]
        if is_reverse(direction, next_dir):
            return False, score, "reverse at %d" % step
        direction = next_dir

        hx, hy = snake[0]
        next_head = (hx + direction[0], hy + direction[1])
        nx, ny = next_head
        grow = next_head == food

        if nx <= 0 or ny <= 0 or nx >= BOARD_W - 1 or ny >= BOARD_H - 1:
            return False, score, "wall at %d" % step

        body = snake if grow else snake[:-1]
        if next_head in body:
            return False, score, "self at %d" % step

        snake.insert(0, next_head)
        if grow:
            score += 1
            write_line(score_text, "EAT %02d/40" % score, 9)
            print("SNAKE_CHALLENGE: apple %02d step=%d pos=%d,%d" % (score, step, nx, ny))
            if score >= TARGET_APPLES:
                draw_snake(board, snake)
                return True, score, "solved in %d moves" % step
            food = spawn_food(prng, snake)
            board[food[0], food[1]] = COLOR_FOOD
        else:
            tail = snake.pop()
            erase_cell(board, tail[0], tail[1])

        draw_snake(board, snake)
        if step % 10 == 0:
            write_line(status, "STEP %04d" % step, 9)
        time.sleep(0.012)

    return False, score, "ended after %d moves" % len(moves)


def snake_challenge(hw_state):
    display = hw_state["display"]

    palette = displayio.Palette(6)
    palette[COLOR_BG] = 0x04140A
    palette[COLOR_GRID] = 0x062010
    palette[COLOR_BODY] = 0x22CC55
    palette[COLOR_HEAD] = 0xD8FF55
    palette[COLOR_FOOD] = 0xFF3355
    palette[COLOR_WALL] = 0x3E7050

    board = displayio.Bitmap(BOARD_W, BOARD_H, 6)
    board_grid = displayio.TileGrid(board, pixel_shader=palette)
    board_group = displayio.Group(scale=CELL_SCALE)
    board_group.x = (240 - (BOARD_W * CELL_SCALE)) // 2
    board_group.y = 50
    board_group.append(board_grid)

    title_grid, title = make_text_grid(12, 84, 16, 0xD8FF55)
    status_grid, status = make_text_grid(9, 93, 31, 0x9CFF70)
    hint = label.Label(terminalio.FONT, text="", color=0x79B8FF)
    hint.x = 42
    hint.y = 198

    root = displayio.Group()
    root.append(board_group)
    root.append(title_grid)
    root.append(status_grid)
    root.append(hint)
    display.root_group = root

    write_line(title, "SNAKE CHAL", 12)
    write_line(status, "LOAD", 9)
    write_label(hint, "reading moves.txt", 26)

    print("SNAKE_CHALLENGE: seed=0x%08x target=%d file=%s" % (SEED, TARGET_APPLES, MOVE_FILE))
    moves, error = parse_moves(MOVE_FILE)
    if error:
        write_line(title, "NO MOVES", 12)
        write_line(status, "FAIL", 9)
        write_label(hint, "copy moves.txt", 26)
        print("SNAKE_CHALLENGE: FAIL %s" % error)
        wait_for_b_exit(hw_state)
        return

    print("SNAKE_CHALLENGE: loaded %d moves" % len(moves))
    write_line(status, "RUN", 9)
    ok, score, message = replay_moves(board, moves, status, status)
    if ok:
        write_line(title, "SOLVED", 12)
        write_line(status, "EAT 40/40", 9)
        write_label(hint, FLAG, 26)
        print("SNAKE_CHALLENGE: PASS %s" % message)
        print("SNAKE_CHALLENGE: FLAG %s" % FLAG)
        wait_for_b_exit(hw_state)
    else:
        write_line(title, "FAILED", 12)
        write_line(status, "EAT %02d/40" % score, 9)
        write_label(hint, message, 26)
        print("SNAKE_CHALLENGE: FAIL score=%d reason=%s" % (score, message))
        wait_for_b_exit(hw_state)
