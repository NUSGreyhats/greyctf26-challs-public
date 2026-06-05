#include <fcntl.h>
#include <ncurses.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>

// gcc -s -o chal chal.c -lncurses

#define N 15
#define c2i(x) (2*(x)+1)
#define WALL '#'
#define SPACE ' '
#define PLAYER '@'
#define BOOST '.'
#define FLAG 'F'
#define BONUS 67

struct Player {
    unsigned char x;
    unsigned char y;
    unsigned char z;
    unsigned char bonus;
    unsigned int score;
};
struct Player p = { .x = 7, .y = 7, .z = 7, .bonus = 0, .score = 0 };
unsigned char *maze, *pool, *sp, *base, *pc, *data;

#define VM_OFFSET 152
#define DATA_OFFSET 0x100
#define PAGE_SIZE 0x1000
#define REGION_SIZE 0x10000
void setup(void) {
    void *buf = mmap(NULL, PAGE_SIZE + REGION_SIZE + 5*PAGE_SIZE + REGION_SIZE + PAGE_SIZE, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);

    buf += PAGE_SIZE;
    mmap(buf, REGION_SIZE, PROT_READ, MAP_PRIVATE | MAP_FIXED, open("maze.txt", O_RDONLY), 0);
    maze = (char *)buf;
    
    buf += REGION_SIZE + PAGE_SIZE;
    mmap(buf, PAGE_SIZE, PROT_READ, MAP_PRIVATE | MAP_FIXED, open("pool.bin", O_RDONLY), 0);
    pool = (char *)buf;

    buf += PAGE_SIZE + PAGE_SIZE;
    mprotect(buf, PAGE_SIZE, PROT_READ | PROT_WRITE);
    sp = (char *)buf-1;

    buf += PAGE_SIZE + PAGE_SIZE;
    mmap(buf, PAGE_SIZE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_FIXED, open("vm.bin", O_RDONLY), 0);
    base = (char *)buf;
    pc = base + VM_OFFSET;
    data = base + DATA_OFFSET;
}

#define PRINT ' '
#define PUSH 67
#define POP 0x67
#define SWAP 0x35
#define DUP 0x36
#define ROT 0x37
#define LOAD 'L'
#define STORE 'S'
#define MEMSWAP 'X'
#define ADD '+'
#define SUB '-'
#define MUL '*'
#define AND '&'
#define XOR '^'
#define JMP 5
#define JZ 6
#define JNZ 7
#define _push(x) (*++sp = (x))
#define _pop(x) ((x) = *sp--)
void win(void) {
    unsigned char x, y, z, tmp;
    endwin();
    printf("%s\n", "You win!");
    while (1) {
        // if (s) printf("%hhd: %d (%c)\n", (char)(pc-VM_OFFSET), *pc, *pc);
        switch (*pc++) {
        case PRINT:   putchar(*sp--); break;
        case PUSH:    *++sp = *pc++; break;
        case POP:     sp--; break;
        case SWAP:    _pop(y); _pop(x); _push(y); _push(x); break;
        case DUP:     _pop(x); _push(x); _push(x); break;
        case ROT:     _pop(z); _pop(y); _pop(x); _push(y); _push(z); _push(x); break;
        case LOAD:    _pop(x); _pop(y); z = base[(unsigned short)x << 8 | y]; _push(z); break;
        case STORE:   _pop(x); _pop(y); _pop(z); base[(unsigned short)x << 8 | y] = z; break;
        case ADD:     _pop(y); _pop(x); z = x+y; _push(z); break;
        case SUB:     _pop(y); _pop(x); z = x-y; _push(z); break;
        case MUL:     _pop(y); _pop(x); z = x*y; _push(z); break;
        case AND:     _pop(y); _pop(x); z = x&y; _push(z); break;
        case XOR:     _pop(y); _pop(x); z = x^y; _push(z); break;
        case JMP:     tmp = *pc++; *(unsigned char *)&pc += tmp; break;
        case JZ:      tmp = *pc++; _pop(x); if (!x) { *(unsigned char *)&pc += tmp; } break;
        case JNZ:     tmp = *pc++; _pop(x); if (x) { *(unsigned char *)&pc += tmp; } break;
        default:      exit(0);
        }
    }
}

int p2i(void) {
    return c2i((int)(char)p.z)*c2i(N)*c2i(N) + c2i((int)(char)p.y)*c2i(N) + c2i((int)(char)p.x);
}

void commit(void) {
    char cur = maze[p2i()];
    if (cur == FLAG) {
        win();
    } else if (cur == BOOST) {
        p.bonus = BONUS;
    }
}
int move_player(char dx, char dy, char dz) {
    int old = p2i();
    p.x += dx;
    p.y += dy;
    p.z += dz;
    int new = p2i();
    int mid = (old + new) / 2;
    if (maze[mid] != SPACE) {
        p.x -= dx;
        p.y -= dy;
        p.z -= dz;
        return 0;
    }
    unsigned int idx = -1;
    if (dy == -1) idx = 0;
    else if (dy == 1) idx = 1;
    else if (dx == -1) idx = 2;
    else if (dx == 1) idx = 3;
    if (idx <= 3) {
        unsigned char score = p.bonus + pool[idx];
        p.bonus = 0;
        p.score += score;
        *data++ = score;
        pool += 4;
    }
    commit();
    return 1;
}
void reset(void) {
    p.x = 7;
    p.y = 7;
    p.z = 7;
    p.bonus = 67;
    p.score = 0;
}

void draw(void) {
    clear();
    int length = c2i(N);
    int px = c2i(p.x), py = c2i(p.y);
    char *ptr = &maze[c2i((int)(char)p.z)*length*length];
    for (int y = 0; y < length; ++y) {
        for (int x = 0; x < length; ++x) {
            if (x == px && y == py)
                mvaddch(y, x, PLAYER);
            else
                mvaddch(y, x, ptr[y*length + x]);
        }
    }
    int offset = (c2i(N)-N)/2;
    for (int z = 0; z < N; ++z) {
        mvaddch(offset+z, length+3, '_');
        if (z == p.z) {
            mvaddch(offset+z, length+5, '<');
        }
    }
    mvprintw(length+1, 0, "w/a/s/d/o/l");
    mvprintw(length+2, 0, "Current score: %d / %d", p.score, p.bonus);
    refresh();
}
void game(void) {
    char input;
    while (1) {
        draw();
        switch (getch()) {
        case 'w': move_player(0, -1, 0); break;
        case 's': move_player(0, 1, 0); break;
        case 'a': move_player(-1, 0, 0); break;
        case 'd': move_player(1, 0, 0); break;
        case 'o': move_player(0, 0, -1); break;
        case 'l': move_player(0, 0, 1); break;
        case 'q': return;
        }
    }
}

int main(void) {
    initscr();
    noecho();
    cbreak();
    curs_set(0);
    setup();
    while (1) {
        game();
        clear();
        mvprintw(c2i(N)+2, 0, "Final score: %d", p.score);
        mvprintw(c2i(N)+3, 0, "Press enter to exit... ");
        refresh();
        reset();
        if (getch() == '\n') break;
    }
    endwin();
    return 0;
}
