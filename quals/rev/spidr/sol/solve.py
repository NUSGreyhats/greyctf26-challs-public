import idaapi
import idc
import idautils

def get_call_target(ea, insn):
    op_type = insn.ops[0].type
    if op_type == idaapi.o_near or op_type == idaapi.o_far:
        return insn.ops[0].addr
    elif op_type == idaapi.o_imm:
        return insn.ops[0].value
    for xref in idautils.CodeRefsFrom(ea, 0):
        return xref
    return None

def get_cmp_value(insn):
    for i in range(2):
        if insn.ops[i].type == idaapi.o_imm:
            return insn.ops[i].value & 0xffffffff
    return idc.generate_disasm_line(insn.ea, 0)

def fmt(v):
    return hex(v) if isinstance(v, int) else repr(v)

def get_dictionary(start_ea):
    d = {}                  
    current_cmp_key = None  
    first_mov_val = None  
    cmp_ea = None
    call_addr = -1
    call_cmp = -1
    ea = start_ea

    while ea != idaapi.BADADDR and len(d.keys()) < 100:
        insn = idaapi.insn_t()
        idaapi.decode_insn(insn, ea)

        mnem = insn.get_canon_mnem().lower()

        if mnem == "cmp":
            current_cmp_key = get_cmp_value(insn)
            cmp_ea = ea
            first_mov_val   = None

        elif current_cmp_key is not None:

            if mnem == "mov" and first_mov_val is None:
                if insn.ops[1].type == idaapi.o_imm:
                    first_mov_val = insn.ops[1].value & 0xffffffff

            elif mnem == "imul":
                y = None
                # walk back to find the nearest mov imm before imul
                cur = idc.prev_head(ea)
                for _ in range(10):
                    if cur == idaapi.BADADDR:
                        break
                    tmp = idaapi.insn_t()
                    if idaapi.decode_insn(tmp, cur) <= 0:
                        break
                    if tmp.get_canon_mnem().lower() == "mov" and tmp.ops[1].type == idaapi.o_imm:
                        y = tmp.ops[1].value
                        break
                    cur = idc.prev_head(cur)
                d[current_cmp_key] = (cmp_ea, first_mov_val, y, 1)
                
            elif mnem == "add":
                y = None
                cur = idc.prev_head(ea)
                for _ in range(10):
                    if cur == idaapi.BADADDR:
                        break
                    tmp = idaapi.insn_t()
                    if idaapi.decode_insn(tmp, cur) <= 0:
                        break
                    if tmp.get_canon_mnem().lower() == "mov" and tmp.ops[1].type == idaapi.o_imm:
                        y = tmp.ops[1].value
                        break
                    cur = idc.prev_head(cur)
                d[current_cmp_key] = (cmp_ea, first_mov_val, y, 2)

            elif mnem == "xor":
                y = None
                cur = idc.prev_head(ea)
                for _ in range(10):
                    if cur == idaapi.BADADDR:
                        break
                    tmp = idaapi.insn_t()
                    if idaapi.decode_insn(tmp, cur) <= 0:
                        break
                    if tmp.get_canon_mnem().lower() == "mov" and tmp.ops[1].type == idaapi.o_imm:
                        y = tmp.ops[1].value
                        break
                    cur = idc.prev_head(cur)
                d[current_cmp_key] = (cmp_ea, first_mov_val, y, 3)

            elif mnem == "call":
                y = get_call_target(ea, insn)
                d[current_cmp_key] = (cmp_ea, first_mov_val, y, 4)
                call_addr = y
                call_cmp = current_cmp_key

        ea = idc.next_head(ea)
    d[0] = (call_cmp, 0, 0, 0)

    return d, call_addr

def reverse_dictionary(d, last_cmp_val, image):
    rd = {}
    preimage = image
    for cmp_val, (_, next_val, op_val, op_type) in d.items():
        if cmp_val == 0:
            continue
        rd[next_val] = (cmp_val, op_val, op_type)
    
    for _ in range(100):
        try:
            last_cmp_val, op_val, op_type = rd[last_cmp_val]
        except KeyError:
            break
        if op_type == 1:
            preimage = preimage * pow(op_val, -1, 2**64) % 2**64
        elif op_type == 2:
            preimage = (preimage - op_val) % 2**64
        elif op_type == 3:
            preimage = preimage ^ op_val
        else:
            print("You shouldn't be here.")
    return preimage

DS = []
ea = 0x75C10
for _ in range(100):
    d, next_addr = get_dictionary(ea)
    DS.append(d)
    ea = next_addr
    if next_addr == -1:
        break

result = 0x67696D65666C6167
last_cmp_val = 0x2568AC9

ptr = -1
for _ in range(100):
    result = reverse_dictionary(DS[ptr], last_cmp_val, result)
    ptr -= 1
    if _ == 99:
        break
    last_cmp_val = DS[ptr][0][0]
    # print(f'next = {fmt(last_cmp_val)}')
print('grey{' + str(result) + '}')
# grey{4022823573008984730}

# copy paste this into the idapython terminal