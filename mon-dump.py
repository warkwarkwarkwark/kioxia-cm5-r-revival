#!/usr/bin/env python3
"""Dump memory through the drive monitor's /m command (Bus Pirate in bridge mode).
Each block is read twice and compared. usage: mon-dump.py START_HEX LEN_HEX OUTFILE"""
import re, struct, sys, time
from mon import open_port, xfer
start, length, out = int(sys.argv[1], 16), int(sys.argv[2], 16), sys.argv[3]
BLK = 0x400
fd = open_port()
line_re = re.compile(rb"([0-9a-fA-F]{8})=((?:[ \t]+[0-9a-fA-F]{8})+)")
def read_block(addr, nbytes):
    raw = xfer(fd, b"/m %x,%x\r" % (addr, nbytes // 4), quiet=0.4, maxs=15, until=b"ok\r\n>")
    data = bytearray(); expect = addr
    for m in line_re.finditer(raw):
        if int(m.group(1), 16) != expect: return None, raw
        words = m.group(2).split()
        data += b"".join(struct.pack("<I", int(w, 16)) for w in words)
        expect += 4 * len(words)
    return (bytes(data), raw) if len(data) == nbytes else (None, raw)
f = open(out, "wb"); t0 = time.monotonic(); addr = start; bad = 0
while addr < start + length:
    n = min(BLK, start + length - addr)
    a, raw = read_block(addr, n)
    b, _ = read_block(addr, n) if a else (None, None)
    if a is None or a != b:
        bad += 1
        print(f"\n  bad read at {addr:08x} (try {bad}): {raw[-80:]!r}", flush=True)
        if bad >= 3 and a is not None and "--loose" in sys.argv:
            print(f"  accepting changing block at {addr:08x} (live data)", flush=True)
        elif bad >= 4:
            print(f"stopping at {addr:08x}"); break
        else:
            time.sleep(0.3); continue
    bad = 0; f.write(a); addr += n
    if (addr - start) % 0x2000 == 0 or addr == start + length:
        el = time.monotonic() - t0
        print(f"\r  {addr:08x}  {100*(addr-start)/length:5.1f}%  {(addr-start)/el/1024:5.2f} KiB/s", end="", flush=True)
f.close(); print(f"\nwrote {addr-start:#x} bytes to {out}")
