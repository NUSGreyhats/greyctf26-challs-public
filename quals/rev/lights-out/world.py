import numpy as np
import amulet
import amulet_nbt as nbt
from amulet.api.block import Block
import os

# level data

os.makedirs('dist/lights-out', exist_ok=True)

_GENERATOR = nbt.CompoundTag({
    'type': nbt.StringTag('minecraft:flat'),
    'settings': nbt.CompoundTag({
        'biome':               nbt.StringTag('minecraft:the_void'),
        'features':            nbt.ByteTag(0),
        'lakes':               nbt.ByteTag(0),
        'layers':              nbt.ListTag([], 0),
        'structure_overrides': nbt.ListTag([], nbt.StringTag.tag_id),
    }),
})
nbt.NamedTag(
    nbt.CompoundTag({
        'Data': nbt.CompoundTag({
            'DataVersion':  nbt.IntTag(4671),
            'version':      nbt.IntTag(19133),
            'Version': nbt.CompoundTag({
                'Id':       nbt.IntTag(4671),
                'Name':     nbt.StringTag('1.21.11'),
                'Series':   nbt.StringTag('main'),
                'Snapshot': nbt.ByteTag(0),
            }),

            'LevelName':        nbt.StringTag('lights-out'),
            'initialized':      nbt.ByteTag(1),
            'WasModded':        nbt.ByteTag(0),
            'LastPlayed':       nbt.LongTag(0),
            'GameType':         nbt.IntTag(1),
            'hardcore':         nbt.ByteTag(0),
            'Difficulty':       nbt.ByteTag(0),
            'DifficultyLocked': nbt.ByteTag(0),
            'spawn': nbt.CompoundTag({
                'dimension':    nbt.StringTag('minecraft:overworld'),
                'pitch':        nbt.FloatTag(0.0),
                'yaw':          nbt.FloatTag(0.0),
                'pos':          nbt.IntArrayTag([67, 267, 67]),
            }),

            'Time':                       nbt.LongTag(0),
            'DayTime':                    nbt.LongTag(6000),
            'raining':                    nbt.ByteTag(0),
            'rainTime':                   nbt.IntTag(0),
            'thundering':                 nbt.ByteTag(0),
            'thunderTime':                nbt.IntTag(0),
            'clearWeatherTime':           nbt.IntTag(0),
            'WanderingTraderSpawnChance': nbt.IntTag(0),
            'WanderingTraderSpawnDelay':  nbt.IntTag(0),

            'allowCommands': nbt.ByteTag(1),
            'game_rules': nbt.CompoundTag({
                'minecraft:advance_time':    nbt.ByteTag(0),
                'minecraft:advance_weather': nbt.ByteTag(0),
                'minecraft:respawn_radius':  nbt.IntTag(0),
                'minecraft:spawn_mobs':      nbt.ByteTag(0),
            }),

            'WorldGenSettings': nbt.CompoundTag({
                'bonus_chest':       nbt.ByteTag(0),
                'generate_features': nbt.ByteTag(0),
                'seed':              nbt.LongTag(67),
                'dimensions':        nbt.CompoundTag({
                    'minecraft:overworld': nbt.CompoundTag({
                        'type': nbt.StringTag('minecraft:overworld'),
                        'generator': _GENERATOR,
                    }),
                    'minecraft:the_nether': nbt.CompoundTag({
                        'type': nbt.StringTag('minecraft:the_nether'),
                        'generator': _GENERATOR,
                    }),
                    'minecraft:the_end': nbt.CompoundTag({
                        'type': nbt.StringTag('minecraft:the_end'),
                        'generator': _GENERATOR,
                    }),
                }),
            }),

            'DataPacks': nbt.CompoundTag({
                'Enabled':  nbt.ListTag([nbt.StringTag('vanilla')]),
                'Disabled': nbt.ListTag([], nbt.StringTag.tag_id),
            }),
        })
    })
).save_to('dist/lights-out/level.dat', compressed=True, little_endian=False)

# ==========================================================================

# blocks

RANK = 256

_LVL = amulet.load_level('dist/lights-out')
_DIM = 'minecraft:overworld'
_VER = ('java', (1, 21, 11))
_CHUNKS = set()
def place(b, x, y, z):
    cx, cz = x>>4, z>>4
    _LVL.set_version_block(
        x, y, z,
        _DIM, _VER,
        b
    )
    _LVL.get_chunk(cx, cz, _DIM).changed = True
    _CHUNKS.add((cx, cz))

#        N (-z)
# (-x) W   E (+x)
#        S (+z)
#        -> contraption will expand this way

# blocks
_b = lambda x: Block('minecraft', x)
_bb = lambda x, y: Block('minecraft', x, {
    k: nbt.StringTag(v)
    for k, v in y.items()
})
BLOCK = _b('white_concrete')
LEVER = _bb('lever', {'face': 'wall', 'facing': 'west', 'powered': 'false'})
LAMP = _bb('redstone_lamp', {'lit': 'false'})
BULB = lambda on: _bb('waxed_copper_bulb', {'lit': 'true' if on else 'false', 'powered': 'false'})
WIRE = lambda dir: _bb('observer', {'facing': dir, 'powered': 'false'})
DROPPER = _bb('dropper', {'facing': 'up', 'triggered': 'false'})

_X = 67
_Y = 267
_Z = 67

# UI platform
bulb_row = np.load('bulbs.npy')
for dz in range(RANK):
    # floor (3-wide)
    for dx in range(3):
        place(BLOCK, _X+dx, _Y-1, _Z+dz)
    # wall
    for dy in (-1, 0):
        place(BLOCK, _X+3, _Y+dy, _Z+dz)
    # levers
    place(LEVER, _X+2, _Y+0, _Z+dz)
    # translation layer
    place(BULB(bulb_row[dz] == 1),  _X+4, _Y+1, _Z+dz)
    place(LAMP,  _X+4, _Y+0, _Z+dz)
    # base wiring
    place(WIRE('west'), _X+5, _Y+0, _Z+dz)
    for dy in range(1, 256):
        place(WIRE('up'), _X+5, _Y-dy, _Z+dz)
    # receiver pad
    for dy in range(256):
        place(WIRE('west'), _X+6+RANK, _Y-dy, _Z+dz)
        place(
            BLOCK if (dz^dy)&1 else WIRE('west'),
            _X+6+RANK+1, _Y-dy, _Z+dz
        )
        place(
            DROPPER if (dz^dy)&1 else WIRE('down'),
            _X+6+RANK+2, _Y-dy, _Z+dz
        )
    if not (dz^dy)&1:
        place(DROPPER, _X+6+RANK+2, _Y-256, _Z+dz)
    # return wire
    place(WIRE('down'), _X+6+RANK+2, _Y+1, _Z+dz)
    for dx in range(6+RANK+1, 4, -1):
        place(WIRE('east'), _X+dx, _Y+1, _Z+dz)

BOARD = np.load('cube.npy').tolist()
SERIALIZE = [None, 'north', 'south', 'east', 'west', 'up', 'down']

for x, a in enumerate(BOARD):
    for y, b in enumerate(a):
        for z, c in enumerate(b):
            if (cur := SERIALIZE[c]) is not None:
                place(WIRE(cur), _X+6+x, _Y-y, _Z+z)

_LVL.save()
_LVL.close()

# ==========================================================================

# forceload

os.makedirs('dist/lights-out/data', exist_ok=True)
nbt.NamedTag(
    nbt.CompoundTag({
        'DataVersion': nbt.IntTag(4671),
        'data': nbt.CompoundTag({
            'tickets': nbt.ListTag([
                nbt.CompoundTag({
                    'chunk_pos': nbt.IntArrayTag([cx, cz]),
                    'level':     nbt.IntTag(31),
                    'type':      nbt.StringTag('minecraft:forced'),
                })
                for cx, cz in _CHUNKS
            ]),
        }),
    })
).save_to('dist/lights-out/data/chunks.dat', compressed=True, little_endian=False)

# ==========================================================================

# cleanup

os.remove('dist/lights-out/session.lock')
os.remove('dist/lights-out/entities/r.0.0.mca')
os.rmdir('dist/lights-out/entities')

print('done')
