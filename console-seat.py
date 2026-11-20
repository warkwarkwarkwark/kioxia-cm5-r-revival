#!/usr/bin/env python3
"""Help seat the console probes, then capture drive state + fault table.

Start with the Bus Pirate at its UART> prompt (not in bridge mode), supply on at 1.8 V.
Phase A: poll the pin voltages; bell while IO5 (drive TX, TP1) is low, one chime when it has
         been high for 3 reads in a row.
Phase B: enter bridge mode, unlock the monitor (a reply proves TP2 as well), read state and
         the fault table twice. Two chimes when captured. Exits non-zero if the drive never answers.
usage: console-seat.py OUTDIR
"""
import os, re, select, struct, subprocess, sys, termios, time

PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
S = "/usr/share/sounds/freedesktop/stereo/"
out = sys.argv[1]


def snd(n):
    subprocess.Popen(["pw-play", S + n + ".oga"], stderr=subprocess.DEVNULL)


def say(s):
    print(time.strftime("%T"), s, flush=True)


fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
t = termios.tcgetattr(fd)
t[0] = t[1] = t[3] = 0
t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, t)


def xfer(data, quiet=0.4, maxs=8.0):
    while select.select([fd], [], [], 0.03)[0]:
        try:
            os.read(fd, 65536)
        except BlockingIOError:
            break
    os.write(fd, data)
    buf = b""
    t0 = last = time.monotonic()
    while time.monotonic() - t0 < maxs and time.monotonic() - last < quiet:
        if select.select([fd], [], [], 0.02)[0]:
            try:
                d = os.read(fd, 65536)
            except BlockingIOError:
                d = b""
            if d:
                buf += d
                last = time.monotonic()
    return buf


def io5_volts():
    o = xfer(b"i\r", quiet=0.5).decode("utf-8", "replace")
    o = re.sub(r"\x1b7.*?\x1b8", "", o, flags=re.S)
    o = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", o)
    rows = [l for l in o.replace("\r", "\n").split("\n") if re.match(r"\s*\d+\.\d+V\s", l)]
    if not rows:
        return None
    v = re.findall(r"(\d+\.\d+)V", rows[-1])
    return float(v[6]) if len(v) >= 9 else None


# ---- phase A
t0 = time.time()
good = 0
n = 0
while good < 3:
    if time.time() - t0 > 500:
        say("TP1 never went high")
        sys.exit(2)
    v = io5_volts()
    if v is not None and v >= 1.5:
        good += 1
    else:
        good = 0
        n += 1
        if n % 4 == 1:
            say(f"IO5 (TP1) = {v} V - not touching")
            snd("bell")
    time.sleep(0.6)
say("TP1 high (drive TX seen); entering bridge")
snd("complete")
xfer(b"(1)\r", quiet=0.6)


# ---- phase B
def words(addr, n):
    o = xfer(f"/m {addr:x},{n}\r".encode(), quiet=0.3).decode("ascii", "replace")
    w = []
    for line in o.replace("\r", "\n").split("\n"):
        m = re.match(r"\s*([0-9A-Fa-f]{8})=\s+(.*)", line)
        if m:
            w += [int(x, 16) for x in re.findall(r"\b[0-9A-Fa-f]{8}\b", m.group(2).split("|")[0])]
    return w if len(w) == n else None


t1 = time.time()
n = 0
while time.time() - t1 < 400:
    xfer(b"\x1b\x1b\x1b\x1b", quiet=0.4)
    if words(0x45734, 1) is None:
        n += 1
        if n % 5 == 1:
            say("drive not answering - TP2 (our TX) probably not touching")
            snd("bell")
        time.sleep(0.5)
        continue
    say("drive answers; capturing")
    snd("complete")
    st = {}
    ok = True
    for name, a, c in (("boot", 0x5005253C, 1), ("main", 0x500525E0, 1), ("assert", 0x50057688, 3),
                       ("fe", 0x45734, 1), ("status", 0x812AE970, 1), ("mode", 0x812AE840, 1),
                       ("commit", 0x50053B5C, 1)):
        w = words(a, c)
        if w is None:
            ok = False
            break
        st[name] = " ".join("%08x" % x for x in w)
    tab = b""
    if ok:
        say(str(st))
        for a in range(0x20830000, 0x20830A00, 0x80):
            w1, w2 = words(a, 32), words(a, 32)
            if w1 is None or w1 != w2:
                ok = False
                break
            tab += struct.pack("<32I", *w1)
    if not ok:
        say("contact lost mid-read")
        snd("bell")
        continue
    open(os.path.join(out, "flash-30000.bin"), "wb").write(tab)
    open(os.path.join(out, "state.txt"), "w").write(str(st) + "\n")
    for i in range(0x680, len(tab), 0x80):
        say(hex(0x30000 + i) + " " + " ".join("%08x" % x for x in struct.unpack("<8I", tab[i:i + 32])))
    snd("complete")
    time.sleep(0.6)
    snd("complete")
    say("CAPTURED")
    sys.exit(0)
say("NO ANSWER FROM DRIVE")
sys.exit(3)
