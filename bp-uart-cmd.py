#!/usr/bin/env python3
"""Send one line to the drive's monitor through the Bus Pirate (UART mode already set) and print the reply.
usage: bp-uart-cmd.py 'TEXT' [read_count] [delay_ms]"""
import os, re, select, sys, termios, time
PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
text = sys.argv[1]; n = int(sys.argv[2]) if len(sys.argv) > 2 else 300; dly = int(sys.argv[3]) if len(sys.argv) > 3 else 150
fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
t = termios.tcgetattr(fd); t[0] = t[1] = t[3] = 0; t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, t)
def send(line, quiet=0.6, maxs=12.0):
    while select.select([fd], [], [], 0.05)[0]:
        try: os.read(fd, 65536)
        except BlockingIOError: break
    os.write(fd, line.encode() + b"\r")
    buf = b""; t0 = last = time.monotonic()
    while time.monotonic() - t0 < maxs and time.monotonic() - last < quiet:
        if select.select([fd], [], [], 0.05)[0]:
            try: d = os.read(fd, 65536)
            except BlockingIOError: d = b""
            if d: buf += d; last = time.monotonic()
    return buf.decode("ascii", "replace")
tx = " ".join(f"0x{c:02x}" for c in text.encode()) + " 0x0d" if text else ""
out = send(f"[{tx} D:{dly} r:{n}]")
body = out.split("RX:", 1)[1].split("UART CLOSE")[0] if "RX:" in out else out
body = re.sub(r"0x00\s+\(No data to read\)", "", body)
b = bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", body))
sys.stdout.write(b.decode("ascii", "replace").replace("\r\n", "\n").replace("\r", "\n") + "\n")
