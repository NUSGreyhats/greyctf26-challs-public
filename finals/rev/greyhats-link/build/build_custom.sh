#!/bin/bash
set -e

VER="5.4.7"
WORK=/tmp/lua-build
INSTALL=/opt/custom-lua/bin

rm -rf "$WORK"
mkdir -p "$WORK" "$INSTALL"
cd "$WORK"

echo "[1] Download Lua $VER"
wget -q "https://www.lua.org/ftp/lua-${VER}.tar.gz" -O lua.tar.gz
tar xzf lua.tar.gz
SRCDIR="$WORK/lua-${VER}/src"

echo "[2] Rotate opcodes in lopcodes.h"
cd "$SRCDIR"

# 3-way rotation: ADD → MUL slot, MUL → BXOR slot, BXOR → ADD slot
# Result: real XOR compiles to slot 34 (std ADD) → decompiler shows +
#         real MUL compiles to slot 43 (std BXOR) → decompiler shows ~
#         real ADD compiles to slot 36 (std MUL) → decompiler shows *
rotate_3() {
    local a="$1" b="$2" c="$3" file="$4"
    local la=$(grep "^${a}," "$file" 2>/dev/null || grep "^  ${a}," "$file")
    local lb=$(grep "^${b}," "$file" 2>/dev/null || grep "^  ${b}," "$file")
    local lc=$(grep "^${c}," "$file" 2>/dev/null || grep "^  ${c}," "$file")
    # a→b, b→c, c→a  (rotate forward)
    awk -v la="$la" -v lb="$lb" -v lc="$lc" \
        -v pa="^${a}," -v pb="^${b}," -v pc="^${c}," \
        '{if ($0 ~ pa) print lc; else if ($0 ~ pb) print la; else if ($0 ~ pc) print lb; else print}' \
        "$file" > "$file.tmp"
    mv "$file.tmp" "$file"
}

# Also handle lines that start with two spaces (enum entries in ltm.h)
rotate_3_indent() {
    local a="$1" b="$2" c="$3" file="$4"
    local la=$(grep "^  ${a}," "$file")
    local lb=$(grep "^  ${b}," "$file")
    local lc=$(grep "^  ${c}," "$file")
    awk -v la="$la" -v lb="$lb" -v lc="$lc" \
        -v pa="^  ${a}," -v pb="^  ${b}," -v pc="^  ${c}," \
        '{if ($0 ~ pa) print lc; else if ($0 ~ pb) print la; else if ($0 ~ pc) print lb; else print}' \
        "$file" > "$file.tmp"
    mv "$file.tmp" "$file"
}

# OpCode enum: OP_ADD → OP_MUL position, OP_MUL → OP_BXOR position, OP_BXOR → OP_ADD position
rotate_3 OP_ADD OP_MUL OP_BXOR lopcodes.h

# K variants follow the same rotation
rotate_3 OP_ADDK OP_MULK OP_BXORK lopcodes.h

echo "   Rotated ADD/MUL/BXOR + K variants"

echo "[2b] Rotate TMS enum in ltm.h"
rotate_3_indent TM_ADD TM_MUL TM_BXOR ltm.h
echo "   Rotated TM_ADD/TM_MUL/TM_BXOR"

echo "[2c] Replace metamethod names with generic placeholders in ltm.c"
sed -i \
  's/"__add"/"__m0"/g; s/"__sub"/"__m1"/g; s/"__mul"/"__m2"/g;
   s/"__mod"/"__m3"/g; s/"__pow"/"__m4"/g; s/"__div"/"__m5"/g;
   s/"__idiv"/"__m6"/g; s/"__band"/"__m7"/g; s/"__bor"/"__m8"/g;
   s/"__bxor"/"__m9"/g; s/"__shl"/"__m10"/g; s/"__shr"/"__m11"/g;
   s/"__unm"/"__m12"/g; s/"__bnot"/"__m13"/g' ltm.c
echo "   Replaced arithmetic/bitwise metamethod names with __m0..__m13"

echo "[2d] Fix MMBIN range assert in lvm.c"
sed -i 's/lua_assert(OP_ADD <= GET_OPCODE(pi) && GET_OPCODE(pi) <= OP_SHR)/lua_assert(34 <= GET_OPCODE(pi) \&\& GET_OPCODE(pi) <= 45)/' lvm.c
echo "   Fixed assert"

echo "[2e] Rotate BinOpr enum in lcode.h"
sed -i 's/\bOPR_ADD\b/OPR_TMPA/g; s/\bOPR_MUL\b/OPR_ADD/g; s/\bOPR_BXOR\b/OPR_MUL/g; s/OPR_TMPA/OPR_BXOR/g' lcode.h
echo "   Rotated OPR_ADD/OPR_MUL/OPR_BXOR"

echo "[2f] Fix operator precedence table in lparser.c"
# priority[] is ORDER OPR. After rotating BinOpr, entries must rotate too.
# Standard: [0]=ADD{10,10} [1]=SUB{10,10} [2]=MUL{11,11} [3]=MOD{11,11} ...
#           [7]=BAND{6,6} [8]=BOR{4,4} [9]=BXOR{5,5}
# After rotation pos: [0]=BXOR [1]=SUB [2]=ADD [3]=MOD ... [7]=BAND [8]=BOR [9]=MUL
# Needed: [0]={5,5} [2]={10,10} [9]={11,11}
python3 -c "
lines = open('lparser.c').read()
# Replace the priority table entries directly
old = '''   {10, 10}, {10, 10},           /* '+' '-' */
   {11, 11}, {11, 11},           /* '*' '%' */
   {14, 13},                  /* '^' (right associative) */
   {11, 11}, {11, 11},           /* '/' '//' */
   {6, 6}, {4, 4}, {5, 5},   /* '&' '|' '~' */'''
new = '''   {5, 5}, {10, 10},            /* '~'(xor) '-' */
   {10, 10}, {11, 11},           /* '+' '%' */
   {14, 13},                  /* '^' (right associative) */
   {11, 11}, {11, 11},           /* '/' '//' */
   {6, 6}, {4, 4}, {11, 11},  /* '&' '|' '*' */'''
lines = lines.replace(old, new)
open('lparser.c','w').write(lines)
print('   Rotated priority table')
"

echo "[2g] Fix constant folding in lcode.c"
# constfolding() uses "opr + LUA_OPADD" to convert BinOpr → LUA_OP*.
# After our BinOpr rotation, the offset arithmetic is wrong.
# Fix: add a mapping array that converts rotated BinOpr to standard LUA_OP.
# OPR_BXOR(pos 0) → LUA_OPADD(0), OPR_SUB(1) → LUA_OPSUB(1),
# OPR_ADD(pos 2) → LUA_OPMUL(2)... wait, we need BinOpr→LUA_OP:
#   rotated BinOpr: BXOR(0) SUB(1) ADD(2) MOD(3) POW(4) DIV(5) IDIV(6) BAND(7) BOR(8) MUL(9) SHL(10) SHR(11)
#   desired LUA_OP:    9      1      0      3      4      5      6       7       8      2      10      11
# But simpler: just undo the rotation in the constfolding call.
# Replace "opr + LUA_OPADD" with a corrected expression.
# Our rotation: OPR_ADD is at pos 2, OPR_MUL at pos 9, OPR_BXOR at pos 0
# Standard LUA_OP: ADD=0, MUL=2, BXOR=9
# Mapping: pos 0(BXOR)→9, pos 2(ADD)→0, pos 9(MUL)→2, all others identity
sed -i '/foldbinop.*constfolding/s/opr + LUA_OPADD/((int[]){9,1,0,3,4,5,6,7,8,2,10,11})[opr]/' lcode.c
grep "constfolding" lcode.c | head -3
echo "   Patched constfolding"

echo "[2h] Remove debug library"
sed -i '/{LUA_DBLIBNAME.*luaopen_debug}/d' linit.c
echo "   Removed luaopen_debug from linit.c"

echo "[3] Verify enum values"
gcc -I. -x c -o /tmp/check - << 'EOF'
#include <stdio.h>
#include "lopcodes.h"
int main() {
    printf("  OP_ADD=%d (std 34)  OP_MUL=%d (std 36)  OP_BXOR=%d (std 43)\n", OP_ADD, OP_MUL, OP_BXOR);
    printf("  OP_ADDK=%d (std 22) OP_MULK=%d (std 24) OP_BXORK=%d (std 31)\n", OP_ADDK, OP_MULK, OP_BXORK);
}
EOF
/tmp/check

echo "[4] Regenerate ljumptab.h"
ENTRIES=$(sed -n '/^OP_/!d; s/OP_/\&\&L_OP_/; s/,.*/,/; s/\/.*//; p' lopcodes.h)
cat > ljumptab.h << 'HDR'
/* Jump Table for rotated opcodes */
#undef vmdispatch
#undef vmcase
#undef vmbreak
#define vmdispatch(x)     goto *disptab[x];
#define vmcase(l)     L_##l:
#define vmbreak		vmfetch(); vmdispatch(GET_OPCODE(i));
static const void *const disptab[NUM_OPCODES] = {
HDR
echo "$ENTRIES" >> ljumptab.h
sed -i '$ s/,$//' ljumptab.h
echo "};" >> ljumptab.h
echo "   $(echo "$ENTRIES" | wc -l) entries"

echo "[5] Clean build"
cd "$WORK/lua-${VER}"
make clean >/dev/null 2>&1
make linux MYCFLAGS="-DLUA_USE_LINUX -O2 -DLUA_USE_JUMPTABLE=0" 2>&1 | tail -1

echo "[6] Install"
cp src/lua  "$INSTALL/lua-custom"
cp src/luac "$INSTALL/luac-custom"
strip "$INSTALL/lua-custom"
echo "   $INSTALL/lua-custom"
echo "   $INSTALL/luac-custom"
