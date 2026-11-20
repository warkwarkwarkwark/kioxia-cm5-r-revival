#!/usr/bin/env python3
"""Clear the top nibble of six fault-table records in the W25Q80EW boot flash (no erase).

Run with the Bus Pirate 5 already in SPI mode at 1.8V and the clip held on the chip.
Each byte is only programmed after the chip ID and the current table contents have been
verified, and is read back afterwards. Safe to re-run: bytes already fixed are skipped.

usage: bp-fix-faulttable.py [--check-only]
"""
import os, re, select, subprocess, sys, termios, time

PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
SND = "/usr/share/sounds/freedesktop/stereo/"
EXPECT = "2026-11-20-handsoff/flash-30000.bin"   # table as read through the drive console
TARGETS = [(0x30883, 0x42, 0x02)]
TABLE, TLEN = 0x30000, 0xb00
CHECK_ONLY = "--check-only" in sys.argv
JEDEC = bytes.fromhex("ef6014")


def sound(name):
    try:
        subprocess.Popen(["pw-play", SND + name + ".oga"], stderr=subprocess.DEVNULL)
    except OSError:
        pass


fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
t = termios.tcgetattr(fd)
t[0] = t[1] = t[3] = 0
t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, t)


def cmd(line, timeout=10.0, blocks=1):
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


def rd(op, n):
    b = rx_blocks(cmd(f"[{op} r:{n}]"))
    return b[0] if b and len(b[0]) == n else None


def jedec_ok(times=3):
    return all(rd("0x9f", 3) == JEDEC for _ in range(times))


def read(addr, n):
    """Read n bytes twice (chunks of <= 0x200) and return them only if both passes agree."""
    out = b""
    for a in range(addr, addr + n, 0x200):
        m = min(0x200, addr + n - a)
        op = f"0x03 0x{a >> 16 & 255:02x} 0x{a >> 8 & 255:02x} 0x{a & 255:02x}"
        one, two = rd(op, m), rd(op, m)
        if one is None or one != two:
            return None
        out += one
    return out


def wait_contact():
    n = 0
    while not jedec_ok():
        n += 1
        if n % 6 == 1:
            sound("bell")
            print("  no chip ID - adjust the clip", flush=True)
        time.sleep(0.5)
    sound("complete")


want = bytearray(open(EXPECT, "rb").read()[:TLEN])
print("waiting for contact...", flush=True)
wait_contact()
sr1, sr2 = rd("0x05", 1), rd("0x35", 1)
print("JEDEC ok; status registers SR1 SR2 =", sr1.hex() if sr1 else None, sr2.hex() if sr2 else None, flush=True)
if sr1 is None or sr2 is None:
    sys.exit("could not read status registers")
if sr1[0] & 0x7C:
    sys.exit("block-protect bits are set in SR1; not writing. Report this value.")

cur = read(TABLE, TLEN)
if cur is None:
    sys.exit("table read unstable; re-seat the clip and re-run")
# accept any mix of old/new at the six target bytes, everything else must match exactly
chk = bytearray(cur)
for a, old, new in TARGETS:
    if chk[a - TABLE] in (old, new):
        chk[a - TABLE] = old
if bytes(chk) != bytes(want):
    diff = [hex(TABLE + i) for i in range(TLEN) if chk[i] != want[i]][:10]
    sys.exit(f"table on chip differs from the expected contents at {diff}; nothing written")
print("table matches expected contents", flush=True)
if CHECK_ONLY:
    print("check only: target bytes now =", [hex(cur[a - TABLE]) for a, _, _ in TARGETS])
    sys.exit(0)

for a, old, new in TARGETS:
    for attempt in range(8):
        b = read(a, 1)
        if b is not None and b[0] == new:
            print(f"  0x{a:05x}: already 0x{new:02x}", flush=True)
            break
        if b is None or b[0] != old or not jedec_ok():
            wait_contact()
            continue
        cmd("[0x06]")
        s = rd("0x05", 1)
        if s is None or not s[0] & 0x02:
            print("  write-enable did not latch; retrying", flush=True)
            wait_contact()
            continue
        cmd(f"[0x02 0x{a >> 16 & 255:02x} 0x{a >> 8 & 255:02x} 0x{a & 255:02x} 0x{new:02x}]")
        for _ in range(50):
            s = rd("0x05", 1)
            if s is not None and not s[0] & 0x01:
                break
            time.sleep(0.05)
        b = read(a, 1)
        print(f"  0x{a:05x}: programmed, reads back {b.hex() if b else None}", flush=True)
        if b is not None and b[0] == new:
            break
    else:
        sound("bell")
        sys.exit(f"could not program 0x{a:05x}; re-run the script")

for a, old, new in TARGETS:
    want[a - TABLE] = new
final = read(TABLE, TLEN)
if final is None or bytes(final) != bytes(want):
    sound("bell")
    sys.exit("final verify FAILED or unstable; re-run with --check-only")
open("2026-11-20-handsoff/flash-30000-after-fix6.bin", "wb").write(final)
sound("complete")
time.sleep(0.6)
sound("complete")
print("Done: the byte programmed and the whole table verified.")
