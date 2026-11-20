#!/usr/bin/env python3
"""List the monitor's command tables on the live drive (read-only, uses /m)."""
import re, struct, sys
sys.path.insert(0, '.')
from mon import open_port, xfer
fd = open_port()
line_re = re.compile(rb"([0-9a-fA-F]{8})=((?:[ \t]+[0-9a-fA-F]{8})+)")
def rd(addr, nbytes):
    addr0 = addr & ~3; n = ((addr + nbytes + 3) & ~3) - addr0
    raw = xfer(fd, b"/m %x,%x\r" % (addr0, n // 4), quiet=0.4, maxs=15, until=b"ok\r\n>")
    data = bytearray()
    for m in line_re.finditer(raw):
        data += b"".join(struct.pack("<I", int(w, 16)) for w in m.group(2).split())
    return bytes(data[addr - addr0: addr - addr0 + nbytes])
ptrs = struct.unpack("<3I", rd(0x40500, 12))
print("table pointers (+0x100, +0x104, +0x108):", [hex(p) for p in ptrs])
for which, p in zip(("+0x100", "+0x104", "+0x108"), ptrs):
    if not p: continue
    print(f"\n== table {which} at {p:#x}")
    ents = []; off = 0
    while len(ents) < 200:
        blk = rd(p + off, 12 * 16)
        stop = False
        for i in range(0, len(blk), 12):
            n, l, h = struct.unpack_from("<III", blk, i)
            if n == 0: stop = True; break
            ents.append((n, l, h))
        if stop or len(blk) < 12 * 16: break
        off += 12 * 16
    for n, l, h in ents:
        name = rd(n, 16).split(b"\0")[0].decode("ascii", "replace")
        print(f"  {name!r:14} len={l} handler={h:#010x}")
