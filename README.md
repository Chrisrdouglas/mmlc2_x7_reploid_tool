# mmlc2_x7_reploid_tool

A save editor for **Mega Man X Legacy Collection 2** (Steam, PC) that marks
Mega Man X7's injured reploids as rescued. It only touches reploids that give
no reward, so you can reach X's 64-rescue unlock early without losing any
Life-Ups, Weapon-Ups, 1-Ups or Chips.

Status: the file format below round-trips byte-for-byte (decrypt, re-checksum,
re-encrypt reproduces the original save). In-game behavior of an edited save
has not been confirmed yet.

## Requirements

- Python 3.10+
- [pycryptodome](https://pypi.org/project/pycryptodome/) (`pip install pycryptodome`)

## Usage

List the X7 save slots and their rescue counts:

```
python x7_reploids.py savedata.dat show
```

List every reploid in one slot (`x` = rescued):

```
python x7_reploids.py savedata.dat show --slot 1
```

Mark no-reward reploids as rescued until the slot has 59 of them, writing a
new file (the input is never overwritten):

```
python x7_reploids.py savedata.dat rescue --slot 1 --target 59 --out savedata.x7mod.dat
```

`--target` counts no-reward reploids already rescued, so a slot that has 19
gets 40 more. By default stages are filled hardest-first (Lava Factory, Cyber
Field, Deep Forest, Air Force, Tunnel Base, Radio Tower, Battleship, Central
Circuit) so the reploids left for you are the easy ones. Use `--order` with
stage numbers (see the stage table below) to change that, e.g.
`--order 7,6,5,4,3,2,1,0`.

X joins after 64 total rescues, so with 59 you need 5 more in-game.

## Installing an edited save

The live save is at:

```
C:\Program Files (x86)\Steam\userdata\<steam id>\743900\remote\RXC2\savedata.dat
```

1. Close the game.
2. Back up the live `savedata.dat`.
3. Copy the edited file over it, keeping the name `savedata.dat`.
4. Launch the game. If Steam Cloud reports a conflict, keep the local file.
5. Load the slot and press R1/RB on stage select to check the rescue list.

## Save file format

All multi-byte integers are little-endian. Offsets are hex.

### Encryption

The entire file is encrypted with Blowfish in ECB mode using the key
`d3pP3Sn5PFFQrcfz` (found in `RXC2.exe`). Each 4-byte word is byte-reversed
before decrypting and again after, i.e.

```
plain = swap32(blowfish_ecb_decrypt(key, swap32(file)))
```

Encryption is the same with `encrypt` in place of `decrypt`. The file length
is a multiple of 8.

### Header (plaintext 0x00-0x3F)

| Offset | Size | Meaning |
|--------|------|---------|
| 00 | u32 | Always 1 in the observed save |
| 04 | u32 | Unknown (9 in the observed save) |
| 08 | u32 | Size in bytes of the record offset table at 0x40 (0x38 = 14 records) |
| 0C | 20 | SHA-1 of `plain[0x40:]`, stored with each 4-byte word byte-reversed |
| 20 | u32 | Length of `plain[0x40:]` |
| 24 | 28 | Zero |

### Records

At 0x40 is a table of u32 absolute offsets, one per record. Each record
starts with a 16-byte header:

| Offset | Size | Meaning |
|--------|------|---------|
| 00 | u32 | Name hash: bitwise NOT of CRC-32 of the name (`zlib.crc32(name) ^ 0xFFFFFFFF`) |
| 04 | u32 | Type: 4 = 32-bit value, 12 = data blob |
| 08 | u32 | Type 4: the value itself. Type 12: blob length |
| 0C | u32 | Zero |

A type 12 record's data follows its header. Records are stored in ascending
name-hash order.

Records present in the observed save:

| Name | Type | Size |
|------|------|------|
| `settings` | blob | 0x10 |
| `version` | blob | 0x1C |
| `title1` | blob | 0x1B58 |
| `title1_quick` | blob | 0x4E20 |
| `title2` | blob | 0x5DC0 |
| `title2_quick` | blob | 0x17700 |
| `title3` | blob | 0xBB8 |
| `title3_quick` | blob | 0x3E8 |
| `titleN_hash`, `titleN_quick_hash` | value | one per blob above |

`RXC2.exe` also names `title4`, `xchallenge` and `launcher` records (each with
a `_hash`), which don't appear in this save.

`title2` is X7; that's confirmed by the reploid data below. Which games the
other `titleN` records belong to hasn't been worked out.

### Checksums

Both must be updated after any edit, or the game may reject the file:

1. `<record>_hash` = bitwise NOT of CRC-32 of that record's data (the blob
   bytes, not including the 16-byte header).
2. The header SHA-1 at 0x0C, computed after step 1.

### X7 data (`title2`)

```
u32  version            (4)
8 groups of 0x790 bytes:
    0x10   group header
    5 x 0x180   save slots
zero padding to the end of the record
```

The observed save only uses group 1. Its header is `00 01 FF FF FF FF` followed by
zeros. Its slots 0-2 hold the three saves, and slots 3-4 are empty.

Save slot (0x180 bytes):

| Offset | Size | Meaning |
|--------|------|---------|
| 00 | 0x3F | Options/config. Includes what looks like a button map at 0x31-0x3D |
| 1C | u32 | Grows with progress (714, 1937, 2201 in the observed saves). Probably play time in seconds, unconfirmed |
| 40 | 0x40 | 0xFF-filled in used slots. Empty slots have 0xFF only at 0x40-0x5F |
| **80** | **0x80** | **Reploid table, see below** |
| 110 | 2 | Unknown (`06 04` and `02 04` in two saves) |
| 166 | 1 | 0x7B in every used slot |
| 16E, 172 | 1 each | Unknown small values |

A slot counts as used if anything in its first 0x40 bytes is non-zero.

### Reploid table

128 bytes: 8 stages x 16 reploids, one byte each, at slot offset 0x80. `0` =
not rescued and `1` = rescued. The game can also mark reploids as killed, but
no killed reploid appears in the observed saves, so the value for that is
unknown. The tool only ever changes `0` to `1`.

| Row | Stage | Reward reploids (index: reward) |
|-----|-------|---------------------------------|
| 0 | Lava Factory | 2 TREVOR: Weapon-Up, 4 MATTHEW: Chip, 5 GARY: Life-Up, 9 TONY: Weapon-Up, 10 TIM: Chip, 14 B.J.: 1-Up |
| 1 | Tunnel Base | 3 DAN: Life-Up, 4 FAY: Chip, 7 AL: Weapon-Up, 9 MICHAEL: Chip, 12 LEE: 1-Up, 14 DUANE: Weapon-Up |
| 2 | Radio Tower | 0 ALISON: Life-Up, 2 CINDY: Weapon-Up, 6 KEIKO: Chip, 11 TRACY: 1-Up, 12 LILY: Chip, 15 JULIA: Weapon-Up |
| 3 | Battleship | 1 MARKUS: Weapon-Up, 5 CHRIS: 1-Up, 7 PETER: Chip, 8 RICK: Chip, 13 HENLY: Weapon-Up, 14 BILL: Life-Up |
| 4 | Deep Forest | 3 DAVE: Chip, 6 HUEY: Life-Up, 7 ISAAC: 1-Up, 10 LUISE: Weapon-Up, 13 ROGER: Weapon-Up, 14 SIMON: Chip |
| 5 | Air Force | 2 NIGEL: Life-Up, 7 HERBIE: Weapon-Up, 9 BARRY: Chip, 11 DAMON: Chip, 14 MO: 1-Up, 15 BERT: Weapon-Up |
| 6 | Cyber Field | 0 RIN: Chip, 1 DANIEL: Weapon-Up, 5 JELLY: Weapon-Up, 9 TED: Life-Up, 12 DON: 1-Up, 14 MALIBE: Chip |
| 7 | Central Circuit | 2 DOLF: Weapon-Up, 5 ROCK: Chip, 6 MARIO: Life-Up, 9 SCOTT: 1-Up, 11 SAM: Weapon-Up, 15 TANAKA: Chip |

The full list of all 128 names is in `REPLOIDS` in `x7_reploids.py`.

No separate rescue counter was found in the slot. The rescued total appears
to be counted from this table.

### Where the reploid names and rewards come from

`RXC2.exe` contains the rescue-list table the game uses. In the current Steam
build it starts at file offset 0x31C4D50 and holds 256 records of 24 bytes
(this offset will probably move if the game is patched):

| Offset | Size | Meaning |
|--------|------|---------|
| 00 | u16 | 0x100 + stage row |
| 02 | u16 | Reward: 0 none, 1 Life-Up, 2 Weapon-Up, 3 1-Up, 4 Chip |
| 04 | 20 | Name in X7's text encoding, zero-padded |

For each stage there are 16 Japanese entries followed by 16 English entries.
Both lists are in the same order, and that order matches the save's table
index. The rewards were cross-checked against the
[Steam X7 Wounded Reploid Guide](https://steamcommunity.com/sharedfiles/filedetails/?id=1455199363).

X7's text encoding uses 16-bit characters: `A`-`Z` = ASCII - 0x1D, `a`-`z` =
ASCII - 0x23, space = 0x800C, `.` = 0x000B.

### Not yet understood

- `title2_quick`: 8 blocks of 0x2AA5 bytes, each a 0x200 header, 5 x 0x21
  directory entries and 5 x 0x800 slots. Block 1 has three used slots. Its
  relationship to the `title2` saves is unknown, and this tool doesn't touch it.
- The `version` record: seven u32s, `9 6 3 4 4 4 4` in the observed save.

## License

Apache 2.0, see [LICENSE](LICENSE).
