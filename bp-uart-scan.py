#!/usr/bin/env python3
"""Baud scan for the drive's debug monitor through a Bus Pirate 5 (factory firmware) terminal.

At each rate: put the Bus Pirate in UART mode at 1.8V, send six ESC bytes (four unlock
the monitor), and read back what the drive says. The unlock reply contains "OK!".

usage: bp-uart-scan.py [baud ...]
"""
import os, re, select, sys, termios, time

PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
RATES = [int(x) for x in sys.argv[1:]] or [115200, 921600, 460800, 230400, 57600, 38400,
                                           19200, 9600, 1500000, 2000000, 3000000, 1000000, 500000, 250000]

fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
t = termios.tcgetattr(fd)
t[0] = t[1] = t[3] = 0
t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, t)


def send(line, quiet=0.5, maxs=8.0):
    while select.select([fd], [], [], 0.05)[0]:
        try:
            os.read(fd, 65536)
        except BlockingIOError:
            break
    os.write(fd, line.encode() + b"\r")
    buf = b""
    t0 = last = time.monotonic()
    while time.monotonic() - t0 < maxs and time.monotonic() - last < quiet:
        if select.select([fd], [], [], 0.05)[0]:
            try:
                d = os.read(fd, 65536)
            except BlockingIOError:
                d = b""
            if d:
                buf += d
                last = time.monotonic()
    return buf.decode("ascii", "replace")


def set_baud(baud):
    out = send("m")
    out = send("3")
    if "y/n" in out:
        out = send("n")
    out = send(str(baud))
    for _ in range(4):
        if "UART>" in out:
            break
        out = send("")
    m = re.search(r"Actual speed: (\d+)", out)
    for x in ("W", "1.8", "y", "50"):
        send(x)
    time.sleep(0.3)
    return int(m.group(1)) if m else None


def rx_of(text):
    """Bytes the Bus Pirate reports having received."""
    body = text.split("RX:", 1)[1] if "RX:" in text else ""
    body = body.split("UART CLOSE")[0]
    body = re.sub(r"0x00\s+\(No data to read\)", "", body)
    return bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", body))


def show(b):
    return "".join(chr(c) if 32 <= c < 127 else f"\\x{c:02x}" for c in b)


for baud in RATES:
    actual = set_baud(baud)
    drain = rx_of(send("[r:60]", maxs=6))            # anything already waiting
    reply = rx_of(send("[0x1b 0x1b 0x1b 0x1b 0x1b 0x1b D:30 r:80]", maxs=8))
    hit = b"OK!" in reply or b">" in reply.replace(b"\x1b", b"")
    print(f"{baud:>8} (actual {actual}): pre={show(drain)!r} reply={show(reply)!r}{'   <== ANSWER' if hit else ''}", flush=True)
    if b"OK!" in reply:
        print(f"\nMonitor answered at {baud} baud.")
        break
else:
    print("\nNo 'OK!' at any rate tried.")
