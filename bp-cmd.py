#!/usr/bin/env python3
"""Send one line to the Bus Pirate terminal and print the reply (ANSI stripped).
usage: bp.py [--quiet SECS] [--max SECS] [--raw] TEXT   (TEXT '' sends just Enter)"""
import os, re, select, sys, termios, time
PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
args = sys.argv[1:]
quiet, maxs, nocr = 0.8, 15.0, False
while args and args[0].startswith("--"):
    a = args.pop(0)
    if a == "--quiet": quiet = float(args.pop(0))
    elif a == "--max": maxs = float(args.pop(0))
    elif a == "--nocr": nocr = True
text = args[0] if args else ""
fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
t = termios.tcgetattr(fd)
t[0] = 0; t[1] = 0; t[3] = 0
t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
termios.tcsetattr(fd, termios.TCSANOW, t)
# drain
while select.select([fd], [], [], 0.15)[0]:
    try: os.read(fd, 65536)
    except BlockingIOError: break
os.write(fd, text.encode() + (b"" if nocr else b"\r"))
buf = b""; t0 = last = time.monotonic()
while time.monotonic() - t0 < maxs and time.monotonic() - last < quiet:
    if select.select([fd], [], [], 0.1)[0]:
        try: d = os.read(fd, 65536)
        except BlockingIOError: d = b""
        if d: buf += d; last = time.monotonic()
os.close(fd)
s = buf.decode("utf-8", "replace")
# drop status-bar repaint blocks (between cursor save ESC7 and restore ESC8), then other escapes
s = re.sub(r"\x1b7.*?\x1b8", "", s, flags=re.S)
s = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", s)
s = re.sub(r"\x1b[78=>]", "", s)
s = s.replace("\r\n", "\n").replace("\r", "\n")
print(re.sub(r"\n{3,}", "\n\n", s).strip())
