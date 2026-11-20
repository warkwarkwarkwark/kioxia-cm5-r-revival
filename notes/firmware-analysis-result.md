
Full history of this drive is in the other project's memory: earlier notes (not published). Logs live in `./`.

Findings on 2026-11-13 (the "firmware analysis" plan from 2026-11-12):
- HPE `.rel` firmware image (KACM5ALSHPK3.rel) is encrypted: 256-byte clear header, then entropy 8.0, incompressible, no repeated blocks. Static disassembly from the update file is not possible.
- Host telemetry dump (`2026-11-12-probe/tel-host.bin`, 10.6 MB) is a bit-inverted binary trace (12-byte records: event id, timestamp, argument) with no strings; undecodable without firmware symbols.
- HPE log 0xD6 is an hourly workload/temperature history ("HPWLK0"), 0xD7 firmware slot history, 0xD8 a version string, 0xF8 SMART thresholds. None carry fault detail.
- Commands-supported log: vendor admin 0xC4 and 0xF4 are supported and declare no effects; 0xC0 declares LBCC+NCC. 0xC4 was sent 2026-11-13 with the user's explicit go-ahead (zero cdws; nsid 0, 1, 0xffffffff; also as a 4 KiB read): returns success, zero data, no change to id-ns or vendor logs, reads still fail. Parameter walk done 2026-11-13 (user approved; logs in `./2026-11-13-walk/`, reusable `walk.py`): 0xC4 cdw10 0..255 all success/result 0, no effect (non-zero takes ~0.18 s). 0xF4 decodes only cdw10 low 2 bits: 1 = success result 0, 2 = success result 3, 0/3 = Invalid Field; result 3 is constant regardless of nsid, cdw11..13 or prior mode-1 calls with assorted values. No data returned, no log/identify change, reads still fail. Vendor commands are exhausted as a software route.
- Log 0xF8 beyond offset 0x400 is a rolling internal event log of 0x90-byte records with a sequence number; each failed host read appends one record. Format undocumented.
- nvme-cli 3.2: `admin-passthru -o` is output-format, use `--opcode=`.

**Why:** avoids redoing the encryption/telemetry checks.
**How to apply:** remaining routes are the hardware UART console, vendor service, or selling as faulty. Do not re-run the format/sanitize ladder.
