# Reviving a "dead" HPE VO015360KWUEE (KIOXIA CM5-R 15.36 TB) NVMe SSD

Status on 2026-11-20: the drive works (firmware HPK0 era, controller TC58NC1033GTC). It passed read/write tests across the full capacity, two
power cycles, a warm PC restart and a cold boot. The full lab notebook (addresses, patches, every attempt) is in `notes/`. Firmware dumps and
session logs are not published, so scripts that compare against saved dumps need your own.

## What was wrong

The drive identified normally but every read returned Internal Error, and format, sanitize and
namespace commands all failed. Three separate problems were stacked on top of each other. Only the
first was the original fault; the other two were created during the recovery.

| # | Problem | Origin | Fix |
|---|---------|--------|-----|
| 1 | The back-end (NAND manager) journal ended without a "shutdown commit" record, so at every boot its checkpoint scan gave up and the drive entered its TROUBLE mode. Nothing on NAND was unreadable; the firmware simply has no fallback. | Original fault: an unsafe power loss whose power-loss dump never completed. | Run the firmware's own first-time-initialisation path in place from the debug console, then its own shutdown dump, so a fresh, properly closed system area exists. |
| 2 | Crash records in the boot flash's fault table. Any record whose first word has a top nibble of 3 or more makes the front end choose TROUBLE mode at every boot. | Added by this work: each firmware assert or crash during the experiments wrote one. | Program one byte per record (0x4x to 0x0x) on the flash chip. This only clears bits, so no erase is needed. |
| 3 | The back end had no namespace 1, while the front end still listed one. The first host READ made the hardware lookup unit raise an error the firmware does not handle (assert 0x04030009), and the drive reset itself into TROUBLE. | Side effect of fix 1: first-time init gives all capacity to the free pool. | Delete and recreate the namespace with admin commands only, before any read reaches the drive. |

## What we did, in order

1. **Software routes (September, 12-13 November).** Format, sanitize, namespace delete, HPE firmware
   update and vendor admin commands 0xC4/0xF4 were all tried. None helped. The HPE firmware file
   is encrypted and the telemetry log is undecodable, so no analysis was possible from the host.
2. **Hardware access (13-19 November).** Found the boot flash (Winbond W25Q80EW, 1.8 V) and dumped
   it with the Bus Pirate. It is not encrypted and contains a debug monitor. Found the console on
   the corner test points: TP1 = drive TX, TP2 = drive RX, TP3 = ground, 115200 8N1 at 1.8 V,
   unlocked by sending ESC four times.
3. **Reverse engineering over the console (19-20 November).** Dumped the mask ROM, the running
   front-end code and the back-end code from RAM. `/sys` showed "BE state: TROUBLE". Decoding the
   back end's trace ring showed the scan reading everything successfully and failing only on the
   missing commit record (problem 1).
4. **Nine attempts to fake a successful restore** by patching back-end code in RAM. Each got further
   and hit another consistency check. Abandoned in favour of first-time init.
5. **First-time init in place.** Run 1 hung (the code assumes zeroed tables); run 2 completed but
   left the new area unclosed; run 3 added zeroing of the right DRAM regions and a stub that runs
   the back end's shutdown dump afterwards. After a power cycle the scan found its commit. This
   became `firstinit-run.py`.
6. **Fault-table fix.** Programmed the top-nibble bytes with needle probes on the flash chip
   (`bp-fix-faulttable.py`). The drive then booted NORMAL unaided.
7. **Every start with the PC attached faulted again** (five times). Each one cost a re-close
   (`firstinit-run.py`) plus one more flash byte. Theories that turned out wrong: the MCIO cable,
   PCIe reset timing during boot, and the kernel's controller reset.
8. **Trigger found.** With the kernel driver kept away and the console logged live, enumeration and
   controller enable/disable were harmless; the first READ caused the assert within a second. Your
   observation that the BIOS stage was slow pointed the same way: the BIOS was hanging on reads.
9. **Namespace recreated.** Built `nvme-admin.py`, a userspace admin-only NVMe tool over vfio that
   never issues a read. Console confirmed the back end had zero segments assigned to namespace 1.
   Detach, delete, create and attach all succeeded and the tables then showed the namespace.
10. **Verification.** Reads at ~750 MB/s; 256 MiB random write and read-back at the start, ~1 TB in
    and ~13.4 TiB in; clean shutdown; two unplug/replug cycles; warm restart (BIOS 37 s instead of
    2 min 50 s); cold boot. Test data intact each time, no new fault record,
    `unsafe_shutdowns` unchanged after the OS shutdown.

## Shortest path to a fix

This is what I would do to an identical drive in the original state (identifies, reads fail,
console `/sys` says BE state TROUBLE). It has not been run end to end in this order; each step is
one that worked here. It wipes the drive.

Equipment: a 1.8 V UART (Bus Pirate 5), three needle probes, a Linux PC. If nothing asserts along
the way, the flash chip never needs touching and the drive never needs opening beyond the chassis
window over the test points.

1. **Console.** Probes on TP1/TP2/TP3 by the data-matrix sticker. Bus Pirate: `m`, `3`, `y`, `W`,
   `1.8`, `y`, `50`, `(1)`. Send ESC x4, expect `OK!>`. Check `/sys` shows BE state TROUBLE.
2. **Free the controller from the host.** Unbind the kernel nvme driver, then toggle CC.EN through
   the device's `resource0` (write 0, then 0x00460001) to return the back end to its idle
   TROUBLE state.
3. **Re-initialise and close the system area.**
   ```bash
   python3 firstinit-run.py LOGFILE
   ```
   About four minutes. It must end with `DONE: shutdown complete (stage B, main state 7)`.
4. **Stop the kernel driver from binding**, then power-cycle only the drive (unplug and replug with
   the PC running). Do not restart the PC yet: the BIOS would read the drive.
   ```bash
   echo 0 | sudo tee /sys/bus/pci/drivers_autoprobe
   ```
   The drive should reach NORMAL in about 25 s. The PCIe link after a hot-plug is hit and miss;
   replug until `/sys` shows Port0 state `0x1000001e104311`.
5. **Recreate the namespace before any read.**
   ```bash
   sudo ./vfio-attach.sh
   ```
   On the console: `/ww 50018912,2000` (lets the back end accept deleting a namespace it does not
   have). Then:
   ```bash
   sudo python3 nvme-admin.py 0000:45:00.0 --really-ns detach:1:1 detach:1:2 delete:1 create:3750232064:3750232064:1:0:1 attach:1:1 attach:1:2
   ```
   On the console: `/ww 50018912,2002` to restore, and `/m 924af48c,3` should read
   `4E415350 0000000F 0000037F`.
6. **Hand it to the kernel.** Rebind the device to the nvme driver, restore
   `drivers_autoprobe` to 1, test, and shut down cleanly before removing power.

The PCI address, bridge address and namespace size in the scripts are for this PC and this model;
check them first. Always identify the drive by serial number before any write.

**If it asserts at any point**, it will be back in TROUBLE with a new fault record. Read the table
at console address 0x20830000, repeat step 3, then clear byte 3 of the new record on the flash chip
(`bp-fix-faulttable.py`, probes on pins 1, 2, 5, 6, 8 and ground), then continue from step 4.

## What made it take longer than that

- I read an unmapped address (0x50060000) while exploring. The firmware crashed and wrote the first
  blocking fault record. Never probe addresses the firmware does not reference itself.
- The attempts to patch around the failed restore (step 4 of the history) were a dead end.
- Problem 3 was misdiagnosed three times before the step-by-step test isolated the first READ.

## Caveats on the revived drive

- **Wear is unknown.** SMART shows 1 % spare and 0 % used; neither is trustworthy. The grown
  bad-block list was lost (the factory list was kept). Lifetime figures: 4.52 PB written, about
  43,900 power-on hours. Do not make it the only copy of anything important.
- **Shut down cleanly.** Its power-loss dump worked every time it was tested today, but an
  unfinished one is what killed it originally.
- **A relapse needs the bench again**, and the recovery wipes the drive.
- The debug monitor is still in its restricted mode; nothing about the lock was changed.
- The boot flash still holds 18 neutralised fault records. They are harmless.

## Files

| File | Purpose |
|------|---------|
| `mon.py`, `mon-dump.py`, `bp-cmd.py` | Console command, console memory dump, Bus Pirate terminal helper |
| `firstinit-run.py` | In-place first-time init plus shutdown dump (fix 1) |
| `bp-fix-faulttable.py` | Verified one-byte flash programming (fix 2) |
| `vfio-attach.sh`, `nvme-admin.py` | Admin-only NVMe access with no reads (fix 3) |
| `live-log.py` | Live console state logger used to catch the read fault |
| `re-notes/` | Disassembly notes, trace decoder, read-fault analysis |
| `notes/` | Lab notebook: pinouts, console commands, firmware analysis, every attempt and result |

## Disclaimer

This is a record of what worked on one drive, written up from working notes (which were kept by an
AI assistant during the sessions, hence their style). The scripts contain addresses specific to one
firmware build and one PC. They write to drive RAM and boot flash and can brick a drive. Use at your
own risk.
