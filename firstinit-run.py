#!/usr/bin/env python3
"""Re-run the firmware's first-time initialisation from the TROUBLE-final state (run 3 recipe),
then trigger the BE's own shutdown so the system area is closed with a commit record.
usage: firstinit-run.py LOGFILE [--dry]   (--dry: pre-checks and reset list only, no writes)"""
import re, struct, sys, time
import mon

LOG = open(sys.argv[1], "a")
DRY = "--dry" in sys.argv
fd = mon.open_port()


def say(s):
    line = time.strftime("%H:%M:%S ") + s
    print(line, flush=True)
    LOG.write(line + "\n"); LOG.flush()


def cmd(c):
    out = mon.xfer(fd, c.encode() + b"\r", quiet=0.4, until=b"\n>").decode("ascii", "replace")
    flat = " | ".join(x.strip() for x in out.replace("\r", "\n").split("\n") if x.strip() and x.strip() != ">")
    say(f"{c} -> {flat}")
    return out


def rd(addr, n=1):
    for _ in range(3):
        out = cmd(f"/m {addr:x},{n}")
        words = []
        for l in out.replace("\r", "\n").split("\n"):
            m = re.match(r"\s*[0-9a-fA-F]{8}=\s+(.*)", l)
            if m:
                words += [int(x, 16) for x in m.group(1).split()]
        if len(words) >= n and "ok" in out:
            return words[:n]
    sys.exit(f"read of {addr:x} failed")


def wr(c):
    out = cmd(c)
    if "ok" not in out:
        sys.exit(f"write failed: {c}")


def die(msg):
    say("ABORT: " + msg)
    sys.exit(1)


# unlock (harmless if already unlocked)
mon.xfer(fd, b"\x1b\x1b\x1b\x1b", quiet=0.5)

# ---- pre-checks -------------------------------------------------------------------------
PRE = [(0x5005253C, 0x3E7), (0x500525E0, 6), (0x500525E4, 1), (0x50052540, 0), (0x50052FA8, 0),
       (0x50057930, 7), (0x500531F8, 9), (0x50043E94, 0), (0x500443D8, 1), (0x50057688, 0), (0x50053B5C, 0)]
for a, want in PRE:
    got = rd(a)[0]
    if got != want:
        die(f"pre-check {a:x}: {got:x}, expected {want:x}")
rd(0x81671400, 4)

ORIG = {0x50013814: "4b96", 0x500138DE: "e166",
        0x500138E8: "4864 2100 30af f011 f811 4b5f 20c9 2200 6020 2100 4608 e0cf",
        0x50013900: "485e 2100 30ca f011 f805 20ca 6020 e8bd 41f0 495b 2000 f00b"}
NEW = {0x50013814: "e004", 0x500138DE: "e173",
       0x500138E8: "4803 4904 f028 fcfa 2064 6020 e76b bf00 1000 924b 2000 0700",
       0x50013900: "206d 6020 2003 f001 fee5 4802 e8bd 41f0 f004 bc42 34b5 0001"}


def halfwords(addr, n):
    base = addr & ~3
    w = rd(base, (addr + 2 * n - base + 3) // 4)
    raw = b"".join(struct.pack("<I", x) for x in w)
    off = addr - base
    return [struct.unpack_from("<H", raw, off + 2 * i)[0] for i in range(n)]


for a, txt in ORIG.items():
    want = [int(x, 16) for x in txt.split()]
    got = halfwords(a, len(want))
    new = [int(x, 16) for x in NEW[a].split()]
    if got != want and got != new:
        die(f"code at {a:x} is {[hex(x) for x in got]}, not the expected original")

# ---- Persistence_Ctrl reset list ---------------------------------------------------------
init = open("2026-11-20-revive/be-ram-stalled.bin", "rb").read()[0x131D0:0x131D0 + 0xAA0]
CTRL = 0x500531D0
cur = []
for off in range(0, 0xAA0, 0x40):
    cur += rd(CTRL + off, 16)
cur = cur[:0xAA0 // 4]
resets = []
for i, v in enumerate(cur):
    want = struct.unpack_from("<I", init, 4 * i)[0]
    if v != want and 4 * i != 0x194:
        resets.append((CTRL + 4 * i, want))
say(f"reset list: {len(resets)} words: " + " ".join(f"{a:x}={v:x}" for a, v in resets))
if DRY:
    sys.exit(0)
if len(resets) > 140:
    die("reset list is unexpectedly long")

# ---- patches -----------------------------------------------------------------------------
for a, txt in NEW.items():
    for i, h in enumerate(txt.split()):
        wr(f"/ww {a + 2 * i:x},{h}")
for a, txt in NEW.items():
    want = [int(x, 16) for x in txt.split()]
    if halfwords(a, len(want)) != want:
        die(f"patch at {a:x} did not verify")
for a, v in resets:
    wr(f"/wl {a:x},{v:x}")
for a, v in resets:
    if rd(a)[0] != v:
        die(f"ctrl word {a:x} did not verify")

# ---- go ----------------------------------------------------------------------------------
wr("/wl 500525e4,0")
wr("/wl 5005253c,c8")
wr("/wl 500525e0,0")
say("initialisation started")
t0 = time.time()
last = None
while True:
    time.sleep(4)
    bs, ms = rd(0x5005253C)[0], rd(0x500525E0)[0]
    prog, ass, fc = rd(0x812AEAB8)[0], rd(0x50057688)[0], rd(0x500525FC)[0]
    st = (bs, ms, prog, ass, fc)
    if st != last:
        say(f"STATE boot={bs:x} main={ms:x} progress={prog:x} assert={ass:x} fc={fc:x} t={time.time() - t0:.0f}s")
        last = st
    if ass:
        rd(0x50057688, 16)
        die("BE assert during initialisation")
    if bs == 0x6D and ms == 3 and fc == 1:
        break
    if time.time() - t0 > 600:
        die("timed out waiting for initialisation to finish")
say("initialisation finished; settling 15 s")
time.sleep(15)
if rd(0x5005253C)[0] != 0x6D or rd(0x500525E0)[0] != 3 or rd(0x50057688)[0] != 0:
    die("state changed while settling")

# ---- BE shutdown (writes commit + dump) --------------------------------------------------
wr("/wl 5005253c,c9")
wr("/wl 500525e0,0")
t0 = time.time()
while True:
    time.sleep(2)
    ms, stg, ass = rd(0x500525E0)[0], rd(0x50053094)[0], rd(0x50057688)[0]
    if ass:
        rd(0x50057688, 16)
        die("BE assert during shutdown")
    if ms == 7 and stg == 0xB:
        break
    if time.time() - t0 > 180:
        die(f"shutdown did not finish (main={ms:x} stage={stg:x})")
rd(0x500530A0); rd(0x500531E8); rd(0x45734); rd(0x812AE970); rd(0x81671400, 4)
say("DONE: shutdown complete (stage B, main state 7). Safe to power off.")
