"""Mega Man X Legacy Collection 2 (PC) save editor for X7 reploid rescues.

Save format (savedata.dat):
  - Whole file is Blowfish-ECB, key below, with every 4-byte word byte-swapped
    before and after the cipher.
  - Header: 0x0C..0x20 is SHA-1 of plaintext[0x40:], stored as byte-swapped words.
  - 0x40: table of record offsets. Each record is {~crc32(name), type, size, 0}
    followed by data. "titleN_hash" records hold ~crc32(titleN data).
  - X7 lives in record "title2": u32 version, then 8 groups of
    (0x10 header + 5 slots of 0x180). Each slot's reploid table is 128 bytes at
    +0x80: 8 stages x 16 reploids, 1 byte each, 1 = rescued.

Reploid order and rewards come from the rescue-list table in RXC2.exe.
"""
import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

from Crypto.Cipher import Blowfish

KEY = b"d3pP3Sn5PFFQrcfz"

GROUPS = 8
SLOTS_PER_GROUP = 5
GROUP_SIZE = 0x10 + SLOTS_PER_GROUP * 0x180
SLOT_SIZE = 0x180
TABLE_OFF = 0x80
RESCUED = 1

NONE, LIFE_UP, WEAPON_UP, ONE_UP, CHIP = range(5)
REWARD_NAMES = {NONE: "", LIFE_UP: "Life-Up", WEAPON_UP: "Weapon-Up", ONE_UP: "1-Up", CHIP: "Chip"}

STAGES = [
    "Lava Factory", "Tunnel Base", "Radio Tower", "Battleship",
    "Deep Forest", "Air Force", "Cyber Field", "Central Circuit",
]

REPLOIDS = [
    [("CHUCK", 0), ("PAUL", 0), ("TREVOR", 2), ("GUY", 0), ("MATTHEW", 4), ("GARY", 1), ("ROVIN", 0), ("STEVE", 0), ("ROY", 0), ("TONY", 2), ("TIM", 4), ("ALAN", 0), ("BRUCE", 0), ("LEON", 0), ("B.J.", 3), ("JIM", 0)],
    [("ERIC", 0), ("OTIS", 0), ("GRAHAM", 0), ("DAN", 1), ("FAY", 4), ("KEN", 0), ("JULES", 0), ("AL", 2), ("WALTER", 0), ("MICHAEL", 4), ("CARLOS", 0), ("OLIVER", 0), ("LEE", 3), ("KEITH", 0), ("DUANE", 2), ("GORDON", 0)],
    [("ALISON", 1), ("BERINDA", 0), ("CINDY", 2), ("EMI", 0), ("HOLY", 0), ("JUNE", 0), ("KEIKO", 4), ("LUCIE", 0), ("MARIAN", 0), ("JANIS", 0), ("RITA", 0), ("TRACY", 3), ("LILY", 4), ("BETTY", 0), ("CATE", 0), ("JULIA", 2)],
    [("IAN", 0), ("MARKUS", 2), ("ANTHONY", 0), ("JOE", 0), ("ROBERT", 0), ("CHRIS", 3), ("TODD", 0), ("PETER", 4), ("RICK", 4), ("PHIL", 0), ("BOB", 0), ("MAURO", 0), ("ANDY", 0), ("HENLY", 2), ("BILL", 1), ("FRANK", 0)],
    [("ALEX", 0), ("BEN", 0), ("CHARLY", 0), ("DAVE", 4), ("EDIE", 0), ("FRED", 0), ("HUEY", 1), ("ISAAC", 3), ("JACK", 0), ("KEVIN", 0), ("LUISE", 2), ("MICK", 0), ("NICK", 0), ("ROGER", 2), ("SIMON", 4), ("TOM", 0)],
    [("NEIL", 0), ("DEREK", 0), ("NIGEL", 1), ("HAROLD", 0), ("RAY", 0), ("JEFF", 0), ("KELLY", 0), ("HERBIE", 2), ("KIM", 0), ("BARRY", 4), ("SILVER", 0), ("DAMON", 4), ("EMITT", 0), ("YAMAGUCHI", 0), ("MO", 3), ("BERT", 2)],
    [("RIN", 4), ("DANIEL", 2), ("SU", 0), ("ROSETTA", 0), ("MARRY", 0), ("JELLY", 2), ("MARC", 0), ("DOUG", 0), ("CLIFF", 0), ("TED", 1), ("RICHIE", 0), ("COLIN", 0), ("DON", 3), ("BRIAN", 0), ("MALIBE", 4), ("HIDE", 0)],
    [("DEAN", 0), ("VINNIE", 0), ("DOLF", 2), ("BLACK", 0), ("RUDI", 0), ("ROCK", 4), ("MARIO", 1), ("JOEY", 0), ("SID", 0), ("SCOTT", 3), ("ROB", 0), ("SAM", 2), ("ELTON", 0), ("KATO", 0), ("LUKE", 0), ("TANAKA", 4)],
]

# Hardest stages to rescue in first, so the reploids left for you are the easy ones.
DEFAULT_ORDER = [0, 6, 4, 5, 1, 2, 3, 7]


def _swap_words(b):
    return b"".join(b[i:i + 4][::-1] for i in range(0, len(b), 4))


def decrypt(data):
    return _swap_words(Blowfish.new(KEY, Blowfish.MODE_ECB).decrypt(_swap_words(data)))


def encrypt(data):
    return _swap_words(Blowfish.new(KEY, Blowfish.MODE_ECB).encrypt(_swap_words(data)))


def name_hash(name):
    return zlib.crc32(name.encode()) ^ 0xFFFFFFFF


class Save:
    def __init__(self, raw):
        self.p = bytearray(decrypt(raw))
        table_size = struct.unpack_from("<I", self.p, 0x08)[0]
        offsets = struct.unpack_from("<%dI" % (table_size // 4), self.p, 0x40)
        self.records = {}
        for off in offsets:
            h, _type, size, _ = struct.unpack_from("<4I", self.p, off)
            self.records[h] = (off + 16, size)

    def data_span(self, name):
        return self.records[name_hash(name)]

    def slot_base(self, group, slot):
        start, _ = self.data_span("title2")
        return start + 4 + group * GROUP_SIZE + 0x10 + slot * SLOT_SIZE

    def reploid_table(self, group, slot):
        base = self.slot_base(group, slot) + TABLE_OFF
        return self.p[base:base + 128], base

    def used_slots(self):
        """(group, slot) pairs whose slot has any data before the reploid table."""
        out = []
        for g in range(GROUPS):
            for s in range(SLOTS_PER_GROUP):
                b = self.slot_base(g, s)
                head = self.p[b:b + 0x40]
                if any(head):
                    out.append((g, s))
        return out

    def fix_checksums(self):
        for n in (1, 2, 3, 4):
            for suffix in ("", "_quick"):
                name = "title%d%s" % (n, suffix)
                hash_rec = self.records.get(name_hash(name + "_hash"))
                if name_hash(name) not in self.records or hash_rec is None:
                    continue
                start, size = self.data_span(name)
                crc = zlib.crc32(bytes(self.p[start:start + size])) ^ 0xFFFFFFFF
                # type-4 records keep their value in the size field
                struct.pack_into("<I", self.p, hash_rec[0] - 8, crc)
        digest = hashlib.sha1(bytes(self.p[0x40:])).digest()
        self.p[0x0C:0x20] = _swap_words(digest)

    def to_bytes(self):
        self.fix_checksums()
        return encrypt(bytes(self.p))


def slot_label(slots, g, s):
    number = [x for x in slots if x[0] == g].index((g, s)) + 1
    return "%d" % number if len({x[0] for x in slots}) == 1 else "%d.%d" % (g, number)


def summarize(table):
    rescued = sum(1 for v in table if v == RESCUED)
    plain = sum(1 for i, v in enumerate(table) if v == RESCUED and REPLOIDS[i // 16][i % 16][1] == NONE)
    odd = sorted({v for v in table if v not in (0, RESCUED)})
    return rescued, plain, odd


def cmd_show(save, args):
    slots = save.used_slots()
    if not slots:
        print("No X7 save slots found.")
        return
    for g, s in slots:
        table, _ = save.reploid_table(g, s)
        rescued, plain, odd = summarize(table)
        label = slot_label(slots, g, s)
        extra = "  (other values present: %s)" % odd if odd else ""
        print("Slot %s: %d/128 rescued, %d of them no-reward, %d with rewards%s"
              % (label, rescued, plain, rescued - plain, extra))
        if args.slot is not None and label == args.slot:
            for st in range(8):
                row = table[st * 16:st * 16 + 16]
                print("  %s (%d/16)" % (STAGES[st], sum(1 for v in row if v == RESCUED)))
                for i, v in enumerate(row):
                    name, reward = REPLOIDS[st][i]
                    mark = "x" if v == RESCUED else ("?" if v else " ")
                    print("    [%s] %-10s %s" % (mark, name, REWARD_NAMES[reward]))


def cmd_rescue(save, args):
    slots = save.used_slots()
    labels = {slot_label(slots, g, s): (g, s) for g, s in slots}
    if args.slot not in labels:
        sys.exit("Unknown slot %r. Run 'show' to list slots." % args.slot)
    g, s = labels[args.slot]
    table, base = save.reploid_table(g, s)
    _, plain, _ = summarize(table)
    need = args.target - plain
    if need <= 0:
        print("Slot %s already has %d no-reward reploids rescued; nothing to do." % (args.slot, plain))
        return False
    order = [int(x) for x in args.order.split(",")] if args.order else DEFAULT_ORDER
    marked = []
    for st in order:
        for i, (name, reward) in enumerate(REPLOIDS[st]):
            idx = st * 16 + i
            if need and reward == NONE and table[idx] == 0:
                save.p[base + idx] = RESCUED
                marked.append((st, name))
                need -= 1
    if need:
        sys.exit("Only %d unrescued no-reward reploids available; could not reach %d." % (len(marked), args.target))
    for st in range(8):
        names = [n for x, n in marked if x == st]
        if names:
            print("  %-16s %s" % (STAGES[st] + ":", ", ".join(names)))
    after, _ = save.reploid_table(g, s)
    rescued, plain, _ = summarize(after)
    print("Slot %s now: %d/128 rescued, %d no-reward." % (args.slot, rescued, plain))
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save", type=Path, help="path to savedata.dat")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_show = sub.add_parser("show", help="list X7 slots and rescue counts")
    p_show.add_argument("--slot", help="also list every reploid for this slot")
    p_res = sub.add_parser("rescue", help="mark no-reward reploids as rescued")
    p_res.add_argument("--slot", required=True)
    p_res.add_argument("--target", type=int, default=59,
                       help="total no-reward reploids rescued afterwards (default 59)")
    p_res.add_argument("--order", help="stage fill order as comma-separated 0-7 (default %s)"
                       % ",".join(map(str, DEFAULT_ORDER)))
    p_res.add_argument("--out", type=Path, help="output file (default: <save>.x7mod.dat)")
    args = ap.parse_args()

    raw = args.save.read_bytes()
    save = Save(raw)
    if args.cmd == "show":
        cmd_show(save, args)
        return
    if cmd_rescue(save, args):
        out = args.out or args.save.with_suffix(".x7mod.dat")
        if out.resolve() == args.save.resolve():
            sys.exit("Refusing to overwrite the input file; pass a different --out.")
        out.write_bytes(save.to_bytes())
        print("Wrote %s" % out)


if __name__ == "__main__":
    main()
