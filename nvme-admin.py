#!/usr/bin/env python3
"""Admin-only userspace NVMe access through vfio-pci: no I/O queues, no reads, ever.

The kernel nvme driver always reads LBA 0 when it attaches, which is what faults this drive in
NORMAL mode, so this tool talks to the controller directly and sends only admin commands.

Prepare (once per plug-in, as root):
    modprobe vfio-pci
    echo > /sys/bus/pci/devices/BDF/reset_method          # stop vfio from issuing an FLR on open
    echo vfio-pci > /sys/bus/pci/devices/BDF/driver_override
    echo BDF > /sys/bus/pci/drivers/vfio-pci/bind

usage (root): nvme-admin.py BDF CMD [CMD ...]
  CMD:  regs                     print CAP/VS/CC/CSTS only (no enable, no commands)
        id                       Identify Controller (summary) + Identify Namespace 1
        smart                    SMART / health log
        errlog                   first 4 error-log entries
        raw:OPC:NSID:CDW10[:CDW11[:LEN]]    any admin command, hex fields, LEN = data-in bytes
        format:LBAF:SES          Format NVM on nsid 1 (needs --really-format)
        nslist                   cntlid, active/allocated namespace lists, controllers attached to ns 1
        detach:NSID:CTRL  attach:NSID:CTRL  delete:NSID  create:NSZE:NCAP:FLBAS:DPS:NMIC   (decimal; need --really-ns;
                                 the run stops at the first one that fails)
        shutdown                 normal NVMe shutdown (CC.SHN=01), waits for CSTS.SHST=complete; must be last
  options: --timeout SECS (per command, default 30; format default 1800), --leave-enabled
Commands run in the order given; the controller is disabled (CC.EN=0) at the end unless --leave-enabled.
"""
import ctypes, fcntl, mmap, os, struct, sys, time

VFIO_GET_API_VERSION = 0x3B64
VFIO_CHECK_EXTENSION = 0x3B65
VFIO_SET_IOMMU = 0x3B66
VFIO_GROUP_GET_STATUS = 0x3B67
VFIO_GROUP_SET_CONTAINER = 0x3B68
VFIO_GROUP_GET_DEVICE_FD = 0x3B6A
VFIO_DEVICE_GET_REGION_INFO = 0x3B6C
VFIO_IOMMU_MAP_DMA = 0x3B71
IOVA = 0x20000000
DMA_SIZE = 0x10000        # 16 pages: 0 = ASQ, 1 = ACQ, 2.. = data
QSZ = 32

args = [a for a in sys.argv[1:] if not a.startswith("--")]
opts = sys.argv[1:]
if len(args) < 2:
    sys.exit(__doc__)
bdf, cmds = args[0], args[1:]
tmo = float(opts[opts.index("--timeout") + 1]) if "--timeout" in opts else None
if tmo is not None:
    cmds = [c for c in cmds if c != opts[opts.index("--timeout") + 1]]


def say(s):
    print(time.strftime("%H:%M:%S") + ".%03d " % (time.time() % 1 * 1000) + s, flush=True)


group = os.path.basename(os.readlink(f"/sys/bus/pci/devices/{bdf}/iommu_group"))
cont = os.open("/dev/vfio/vfio", os.O_RDWR)
assert fcntl.ioctl(cont, VFIO_GET_API_VERSION) == 0
grp = os.open(f"/dev/vfio/{group}", os.O_RDWR)
st = bytearray(struct.pack("II", 8, 0))
fcntl.ioctl(grp, VFIO_GROUP_GET_STATUS, st)
if not struct.unpack("II", st)[1] & 1:
    sys.exit("vfio group not viable (device not bound to vfio-pci?)")
fcntl.ioctl(grp, VFIO_GROUP_SET_CONTAINER, struct.pack("i", cont))
fcntl.ioctl(cont, VFIO_SET_IOMMU, 3)
libc = ctypes.CDLL(None, use_errno=True)
dev = libc.ioctl(grp, VFIO_GROUP_GET_DEVICE_FD, ctypes.c_char_p(bdf.encode()))
if dev < 0:
    sys.exit("VFIO_GROUP_GET_DEVICE_FD failed: " + os.strerror(ctypes.get_errno()))


def region(idx):
    b = bytearray(struct.pack("IIIIQQ", 32, 0, idx, 0, 0, 0))
    fcntl.ioctl(dev, VFIO_DEVICE_GET_REGION_INFO, b)
    _, flags, _, _, size, off = struct.unpack("IIIIQQ", b)
    return off, size


bar_off, bar_size = region(0)
cfg_off, _ = region(7)


def r32(o):
    return struct.unpack("<I", os.pread(dev, 4, bar_off + o))[0]


def w32(o, v):
    os.pwrite(dev, struct.pack("<I", v), bar_off + o)


def r64(o):
    return r32(o) | r32(o + 4) << 32


def regs(tag=""):
    say(f"{tag}CAP {r64(0):016x} VS {r32(8):08x} CC {r32(0x14):08x} CSTS {r32(0x1c):08x} AQA {r32(0x24):08x}")


dma = mmap.mmap(-1, DMA_SIZE, flags=mmap.MAP_SHARED | mmap.MAP_ANONYMOUS | 0x2000 | 0x8000)  # LOCKED|POPULATE
vaddr = ctypes.addressof(ctypes.c_char.from_buffer(dma))
fcntl.ioctl(cont, VFIO_IOMMU_MAP_DMA, struct.pack("IIQQQ", 32, 3, vaddr, IOVA, DMA_SIZE))

cmd_reg = struct.unpack("<H", os.pread(dev, 2, cfg_off + 4))[0]
os.pwrite(dev, struct.pack("<H", cmd_reg | 0x406), cfg_off + 4)      # mem + bus master + INTx off
regs("start: ")
if cmds == ["regs"]:
    sys.exit(0)

cap = r64(0)
dstrd = cap >> 32 & 0xF
cap_to = (cap >> 24 & 0xFF) * 0.5


def wait_rdy(want, limit):
    t0 = time.time()
    while time.time() - t0 < limit:
        c = r32(0x1C)
        if c == 0xFFFFFFFF:
            sys.exit("registers read all-ones: device gone")
        if (c & 1) == want:
            return time.time() - t0
        time.sleep(0.01)
    sys.exit(f"timeout waiting for CSTS.RDY={want} (CSTS {r32(0x1c):08x})")


if r32(0x14) & 1:
    w32(0x14, r32(0x14) & ~1)
    say("was enabled; disabled, RDY=0 after %.2f s" % wait_rdy(0, max(cap_to, 5)))
dma[:0x2000] = bytes(0x2000)
w32(0x0C, 0xFFFFFFFF)                       # mask interrupts
w32(0x24, (QSZ - 1) << 16 | (QSZ - 1))
w32(0x28, IOVA & 0xFFFFFFFF); w32(0x2C, IOVA >> 32)
w32(0x30, (IOVA + 0x1000) & 0xFFFFFFFF); w32(0x34, (IOVA + 0x1000) >> 32)
w32(0x14, 0x00460001)
say("enabled, RDY=1 after %.2f s" % wait_rdy(1, max(cap_to, 5)))

sq_tail = cq_head = 0
phase = 1
cid = 0


def admin(opc, nsid=0, cdw10=0, cdw11=0, cdw12=0, cdw13=0, cdw14=0, cdw15=0, data_len=0, timeout=30.0, data_out=None):
    """Send one admin command; returns (status_field, result_dw0, data)."""
    global sq_tail, cq_head, phase, cid
    cid = (cid + 1) & 0xFFFF
    if data_out is not None:
        data_len = 0x1000
    prp1 = IOVA + 0x2000 if data_len else 0
    prp2 = IOVA + 0x3000 if data_len > 0x1000 else 0
    if data_len:
        dma[0x2000:0x2000 + 0x2000] = bytes(0x2000)
    if data_out is not None:
        dma[0x2000:0x2000 + len(data_out)] = data_out
    sqe = struct.pack("<BBHIQQQQIIIIII", opc, 0, cid, nsid, 0, 0, prp1, prp2, cdw10, cdw11, cdw12, cdw13, cdw14, cdw15)
    assert len(sqe) == 64
    dma[sq_tail * 64:sq_tail * 64 + 64] = sqe
    sq_tail = (sq_tail + 1) % QSZ
    w32(0x1000, sq_tail)
    t0 = time.time()
    while True:
        cqe = dma[0x1000 + cq_head * 16:0x1000 + cq_head * 16 + 16]
        dw0, _, sqhd, _, rcid, stat = struct.unpack("<IIHHHH", cqe)
        if (stat & 1) == phase:
            break
        if time.time() - t0 > timeout:
            regs("TIMEOUT: ")
            return None, None, None
        time.sleep(0.002 if time.time() - t0 < 1 else 0.05)
    cq_head = (cq_head + 1) % QSZ
    if cq_head == 0:
        phase ^= 1
    w32(0x1000 + (4 << dstrd), cq_head)
    if rcid != cid:
        say(f"warning: completion cid {rcid:#x} != {cid:#x}")
    return stat >> 1, dw0, bytes(dma[0x2000:0x2000 + data_len])


def show(name, res, t0):
    stat, dw0, _ = res
    if stat is None:
        say(f"{name}: NO COMPLETION")
        return False
    say(f"{name}: status sct={stat >> 8 & 7} sc={stat & 0xff:#x} dnr={stat >> 14 & 1} result={dw0:#x} ({time.time() - t0:.2f} s)")
    return stat & 0x7FF == 0


ok_all = True
for c in cmds:
    t0 = time.time()
    if c == "regs":
        regs()
    elif c == "id":
        res = admin(0x06, cdw10=1, data_len=0x1000, timeout=tmo or 30)
        if show("identify controller", res, t0):
            d = res[2]
            say("  sn=%s mn=%s fr=%s nn=%d oacs=%#x fna=%#x tnvmcap=%d unvmcap=%d" % (
                d[4:24].decode().strip(), d[24:64].decode().strip(), d[64:72].decode().strip(),
                struct.unpack_from("<I", d, 516)[0], struct.unpack_from("<H", d, 256)[0], d[524],
                int.from_bytes(d[280:296], "little"), int.from_bytes(d[296:312], "little")))
        else:
            ok_all = False
        t0 = time.time()
        res = admin(0x06, nsid=1, cdw10=0, data_len=0x1000, timeout=tmo or 30)
        if show("identify namespace 1", res, t0):
            d = res[2]
            nsze, ncap, nuse = struct.unpack_from("<QQQ", d, 0)
            flbas = d[26]
            lbaf = struct.unpack_from("<I", d, 128 + 4 * (flbas & 0xF))[0]
            say(f"  nsze={nsze} ncap={ncap} nuse={nuse} nlbaf={d[25]} flbas={flbas:#x} lbads={lbaf >> 16 & 0xff} ms={lbaf & 0xffff} dps={d[29]:#x}")
            say("  lbaf table: " + " ".join("%d:%08x" % (i, struct.unpack_from("<I", d, 128 + 4 * i)[0]) for i in range(d[25] + 1)))
        else:
            ok_all = False
    elif c == "smart":
        res = admin(0x02, nsid=0xFFFFFFFF, cdw10=(0x200 // 4 - 1) << 16 | 0x02, data_len=0x200, timeout=tmo or 30)
        if show("smart log", res, t0):
            d = res[2]
            say("  crit_warn=%#x temp=%dK spare=%d%% used=%d%% power_cycles=%d poh=%d unsafe=%d media_err=%d errlog=%d" % (
                d[0], struct.unpack_from("<H", d, 1)[0], d[3], d[5], int.from_bytes(d[112:128], "little"),
                int.from_bytes(d[128:144], "little"), int.from_bytes(d[144:160], "little"),
                int.from_bytes(d[160:176], "little"), int.from_bytes(d[176:192], "little")))
        else:
            ok_all = False
    elif c == "errlog":
        res = admin(0x02, nsid=0xFFFFFFFF, cdw10=(0x100 // 4 - 1) << 16 | 0x01, data_len=0x100, timeout=tmo or 30)
        if show("error log", res, t0):
            for i in range(4):
                e = res[2][i * 64:i * 64 + 64]
                cnt, sqid, ecid, stf, loc, lba, ens = struct.unpack_from("<QHHHHQI", e, 0)
                say(f"  #{cnt} sqid={sqid} cid={ecid:#x} status={stf >> 1:#x} lba={lba} nsid={ens}")
    elif c == "nslist":
        res = admin(0x06, cdw10=1, data_len=0x1000, timeout=tmo or 30)
        if show("identify controller", res, t0):
            say("  cntlid=%d oacs=%#x" % (struct.unpack_from("<H", res[2], 78)[0], struct.unpack_from("<H", res[2], 256)[0]))
        for name, cns, nsid in (("active ns list", 0x02, 0), ("allocated ns list", 0x10, 0),
                                ("controllers attached to ns 1", 0x12, 1), ("all controllers", 0x13, 0)):
            t0 = time.time()
            res = admin(0x06, nsid=nsid, cdw10=cns, data_len=0x1000, timeout=tmo or 30)
            if show(name, res, t0):
                d = res[2]
                if cns in (0x02, 0x10):
                    say("  " + str([x for x in struct.unpack_from("<16I", d, 0) if x]))
                else:
                    n = struct.unpack_from("<H", d, 0)[0]
                    say("  " + str(list(struct.unpack_from("<%dH" % min(n, 16), d, 2))))
    elif c.split(":")[0] in ("attach", "detach", "delete", "create"):
        if "--really-ns" not in opts:
            sys.exit("namespace changes need --really-ns")
        f = c.split(":")
        if f[0] in ("attach", "detach"):
            nsid, ctrl = int(f[1]), int(f[2])
            res = admin(0x15, nsid=nsid, cdw10=0 if f[0] == "attach" else 1, data_out=struct.pack("<HH", 1, ctrl), timeout=tmo or 120)
        elif f[0] == "delete":
            res = admin(0x0D, nsid=int(f[1]), cdw10=1, timeout=tmo or 600)
        else:
            nsze, ncap, flbas, dps, nmic = (int(x) for x in f[1:6])
            buf = bytearray(0x1000)
            struct.pack_into("<QQ", buf, 0, nsze, ncap)
            buf[26], buf[29], buf[30] = flbas, dps, nmic
            res = admin(0x0D, cdw10=0, data_out=bytes(buf), timeout=tmo or 600)
        if not show(c, res, t0):
            ok_all = False
            say("stopping after failed namespace command")
            break
    elif c == "shutdown":
        w32(0x14, (r32(0x14) & ~0xC000) | 0x4000)
        while time.time() - t0 < (tmo or 60) and (r32(0x1C) >> 2 & 3) != 2:
            time.sleep(0.05)
        say("shutdown: CSTS %08x after %.2f s (%s)" % (r32(0x1c), time.time() - t0, "complete" if (r32(0x1C) >> 2 & 3) == 2 else "NOT complete"))
        opts.append("--leave-enabled")
        break
    elif c.startswith("raw:"):
        f = [int(x, 16) for x in c.split(":")[1:]]
        f += [0] * (5 - len(f))
        res = admin(f[0], nsid=f[1], cdw10=f[2], cdw11=f[3], data_len=f[4], timeout=tmo or 30)
        if show(c, res, t0) and f[4]:
            d = res[2]
            for i in range(0, min(len(d), 0x100), 16):
                say("  %04x: %s" % (i, d[i:i + 16].hex(" ")))
    elif c.startswith("format:"):
        if "--really-format" not in opts:
            sys.exit("format needs --really-format")
        lbaf, ses = (int(x) for x in c.split(":")[1:])
        say(f"FORMAT NVM nsid=1 lbaf={lbaf} ses={ses} ...")
        res = admin(0x80, nsid=1, cdw10=lbaf | ses << 9, timeout=tmo or 1800)
        ok_all &= bool(show("format", res, t0))
    else:
        sys.exit(f"unknown command {c}")
regs("end: ")
if "--leave-enabled" not in opts:
    w32(0x14, r32(0x14) & ~1)
    say("disabled, RDY=0 after %.2f s" % wait_rdy(0, max(cap_to, 5)))
sys.exit(0 if ok_all else 1)
