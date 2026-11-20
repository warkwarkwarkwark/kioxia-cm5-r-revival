#!/usr/bin/env python3
"""Talk to the drive monitor through the Bus Pirate in transparent bridge mode.
usage: mon.py 'COMMAND' [quiet_seconds]   (prints raw reply)"""
import os, select, sys, termios, time
PORT = "/dev/serial/by-id/usb-Bus_Pirate_Bus_Pirate_5_123456789012-if00"
def open_port():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    t = termios.tcgetattr(fd); t[0] = t[1] = t[3] = 0; t[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    termios.tcsetattr(fd, termios.TCSANOW, t)
    return fd
def xfer(fd, data, quiet=0.5, maxs=20.0, until=None):
    while select.select([fd], [], [], 0.03)[0]:
        try: os.read(fd, 65536)
        except BlockingIOError: break
    os.write(fd, data)
    buf = b""; t0 = last = time.monotonic()
    while time.monotonic() - t0 < maxs and time.monotonic() - last < quiet:
        if select.select([fd], [], [], 0.02)[0]:
            try: d = os.read(fd, 65536)
            except BlockingIOError: d = b""
            if d:
                buf += d; last = time.monotonic()
                if until and buf.endswith(until): break
    return buf
if __name__ == "__main__":
    fd = open_port()
    q = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
    out = xfer(fd, sys.argv[1].encode() + b"\r", quiet=q)
    sys.stdout.write(out.decode("ascii", "replace").replace("\r\n", "\n").replace("\r", "\n") + "\n")
