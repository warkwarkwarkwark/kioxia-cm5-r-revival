#!/usr/bin/env python3
"""Poll the drive monitor a few times a second and log every change of key state words.
On the first anomaly (FE state != 3, BE main != 3, assert record set) dump the tail of the
BE trace ring and some BE state straight away, before the firmware resets itself.
usage: live-log.py OUTDIR [SECONDS]   (stop early by creating OUTDIR/stop)"""
import os, re, struct, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mon import open_port, xfer

out = sys.argv[1]
dur = float(sys.argv[2]) if len(sys.argv) > 2 else 540
fd = open_port()
log = open(os.path.join(out, "live.log"), "a")


def say(s):
    s = time.strftime("%H:%M:%S") + ".%03d " % (time.time() % 1 * 1000) + s
    print(s, flush=True)
    log.write(s + "\n")
    log.flush()


def words(addr, n, quiet=0.12):
    o = xfer(fd, f"/m {addr:x},{n}\r".encode(), quiet=quiet, maxs=6).decode("ascii", "replace")
    w = []
    for line in o.replace("\r", "\n").split("\n"):
        m = re.match(r"\s*[0-9A-Fa-f]{8}=\s+(.*)", line)
        if m:
            w += [int(x, 16) for x in re.findall(r"\b[0-9A-Fa-f]{8}\b", m.group(1).split("|")[0])]
    return w if len(w) == n else None


def h(w):
    return "-" if w is None else " ".join("%x" % x for x in w)


def dump(tag):
    idx = words(0x810AA82C, 1)
    say(f"{tag}: trace index {h(idx)}")
    if idx:
        end = 0x810AA840 + idx[0] * 4
        start = max(0x810AA840, end - 0x1800)
        buf = b""
        a = start
        while a < end:
            n = min(64, (end - a) // 4)
            w = words(a, n, quiet=0.25)
            if w is None:
                say(f"{tag}: trace read failed at {a:x}")
                break
            buf += struct.pack("<%dI" % n, *w)
            a += n * 4
        open(os.path.join(out, f"trace-{tag}-{start:x}.bin"), "wb").write(buf)
        say(f"{tag}: saved {len(buf)} trace bytes from {start:x}")
    for name, a, n in (("assert", 0x50057688, 4), ("opcodes", 0x50052590, 8), ("bootseq", 0x5005253C, 4),
                       ("mainst", 0x500525E0, 4), ("shutdn", 0x50053094, 4), ("cpufault", 0x50040810, 8),
                       ("ipcerr", 0x812AF400, 8), ("shared", 0x812AE960, 8)):
        say(f"{tag}: {name} {a:x}: {h(words(a, n, quiet=0.25))}")


xfer(fd, b"\x1b\x1b\x1b\x1b", quiet=0.4)
t0 = time.time()
last = None
dumped = 0
silent = 0
while time.time() - t0 < dur and not os.path.exists(os.path.join(out, "stop")):
    st = (words(0x45734, 1), words(0x500525E0, 2), words(0x5005253C, 1), words(0x50057688, 2),
          words(0x812AE970, 1), words(0x810AA82C, 1), words(0x50052590, 2))
    if all(x is None for x in st):
        silent += 1
        if silent == 3:
            say("console silent (firmware reset or probe lost)")
        if silent % 5 == 0:
            o = xfer(fd, b"\x1b\x1b\x1b\x1b", quiet=0.4)
            if b"OK!" in o:
                say("console re-unlocked after a firmware restart")
        time.sleep(0.2)
        continue
    silent = 0
    key = tuple(h(x) for x in st)
    if key != last:
        say("fe=%s main=%s boot=%s assert=%s status=%s tridx=%s ops=%s" % key)
        last = key
    bad = (st[0] and st[0][0] != 3) or (st[1] and st[1][0] != 3) or (st[3] and st[3][0] != 0)
    if bad and dumped < 2:
        dumped += 1
        dump(f"anomaly{dumped}")
    time.sleep(0.15)
say("live log finished")
