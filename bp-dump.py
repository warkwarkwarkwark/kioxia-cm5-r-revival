#!/usr/bin/env python3
"""Dump an SPI NOR flash through a Bus Pirate 5 terminal using raw bus syntax.

Built for a hand-held clip: every chunk is read twice and compared, the chip's
JEDEC ID is re-checked before each chunk, and progress is saved so a slipped
clip only costs a retry. Re-run to resume.

usage: bp-dump.py [--size BYTES] [--chunk BYTES] [--out FILE] [--id-only]
"""
import argparse, os, re, select, subprocess, sys, termios, time

PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
SND = "/usr/share/sounds/freedesktop/stereo/"


def sound(name):
    try:
        subprocess.Popen(["pw-play", SND + name + ".oga"], stderr=subprocess.DEVNULL)
    except OSError:
        pass

ap = argparse.ArgumentParser()
ap.add_argument("--size", type=lambda x: int(x, 0), default=0x100000)
ap.add_argument("--chunk", type=lambda x: int(x, 0), default=1000)
ap.add_argument("--out", default="boot.bin")
ap.add_argument("--id-only", action="store_true")
ap.add_argument("--expect-id", default="")
a = ap.parse_args()

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
t = termios.tcgetattr(fd)
t[0] = t[1] = t[3] = 0
t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, t)


def cmd(line, timeout=30.0, blocks=1):
    """Send a line, return text up to the next prompt."""
    while select.select([fd], [], [], 0.02)[0]:
        try:
            os.read(fd, 65536)
        except BlockingIOError:
            break
    os.write(fd, line.encode() + b"\r")
    buf = b""
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if select.select([fd], [], [], 0.05)[0]:
            try:
                buf += os.read(fd, 65536)
            except BlockingIOError:
                pass
            if buf.rstrip().endswith(b">") and (buf.count(b"CS Disabled") >= blocks or b"rror" in buf):
                break
    return buf.decode("ascii", "replace")


def rx_blocks(text):
    return [bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m))
            for m in re.findall(r"RX:(.*?)CS Disabled", text, re.S)]


def raw(line, wait=0.6):
    """Send a menu line and return whatever comes back in `wait` seconds."""
    os.write(fd, line.encode() + b"\r")
    time.sleep(wait)
    try:
        return os.read(fd, 65536).decode("ascii", "replace")
    except BlockingIOError:
        return ""


def check_supply():
    """If the Bus Pirate's supply has tripped or is off, switch it back on at 1.8V."""
    out = raw("v")
    if "ERR" in out or "OFF" in out:
        print("\n  supply was off - re-enabling 1.8V", flush=True)
        for x in ("w", "W", "1.8", "y", "300", "P"):
            raw(x)
        time.sleep(0.5)


def rx_bytes(text):
    m = re.search(r"RX:(.*?)CS Disabled", text, re.S)
    if not m:
        return None
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1)))


def jedec():
    return rx_bytes(cmd("[0x9f r:3]", 5)) or b""


def read_chunk(addr, n):
    """One line: read n bytes, then the JEDEC ID. Returns data only if the ID after it is right."""
    b = rx_blocks(cmd(f"[0x03 0x{addr >> 16 & 255:02x} 0x{addr >> 8 & 255:02x} 0x{addr & 255:02x} r:{n}][0x9f r:3]", blocks=2))
    if len(b) == 2 and len(b[0]) == n and b[1] == want:
        return b[0]
    return None


chip = jedec()
print("JEDEC ID:", chip.hex(" "))
if a.id_only:
    sys.exit(0)
want = bytes.fromhex(a.expect_id) if a.expect_id else chip
if want in (b"\x00\x00\x00", b"\xff\xff\xff", b""):
    sys.exit("No valid chip ID - clip not making contact. Nothing read.")

state = a.out + ".progress"
done = int(open(state).read()) if os.path.exists(state) else 0
f = open(a.out, "r+b" if os.path.exists(a.out) else "w+b")
t0 = time.monotonic()
addr = done
fails = 0
while addr < a.size:
    n = min(a.chunk, a.size - addr)
    ok = False
    one = read_chunk(addr, n)
    two = read_chunk(addr, n) if one else None
    ok = one is not None and one == two
    if not ok:
        fails += 1
        if fails % 8 == 2:
            sound("bell")
            check_supply()
        print(f"\n  contact lost or mismatch at 0x{addr:06x} (retry {fails}) - hold the clip steady", flush=True)
        if fails > 600:
            sys.exit(f"Giving up at 0x{addr:06x}; re-run to resume.")
        time.sleep(0.5)
        continue
    if fails >= 2:
        sound("complete")
    fails = 0
    f.seek(addr)
    f.write(one)
    addr += n
    if (addr // a.chunk) % 8 == 0 or addr == a.size:
        f.flush()
        open(state, "w").write(str(addr))
        el = time.monotonic() - t0
        rate = (addr - done) / el if el else 0
        eta = (a.size - addr) / rate if rate else 0
        print(f"\r  0x{addr:06x} / 0x{a.size:06x}  {100 * addr / a.size:5.1f}%  {rate / 1024:5.1f} KiB/s  ETA {eta:4.0f}s", end="", flush=True)
f.close()
print(f"\nDone: {a.out} ({a.size} bytes), every chunk read twice and matched.")
