# Read fault: BE assert 0x04030009, block 0x53180000, status 0x00080000 (analysis 2026-11-20)

Condensed from the analysis agent's hand-back. BE-local addresses (+0x50000000 for the console) unless marked.
VERIFIED = read in disassembly/raw bytes (see verify.py); INFERENCE = interpretation.

## Conclusion
Most likely cause (ranked first, not yet proven on the drive): **the back end has no namespace 1**. The in-place
first-time init gives all segments to the free pool (index 0) and zeroes entries 1-31; the FE system area was
preserved and still says "NS 1 created", so the FE forwards reads for a namespace whose BE limit is 0.
The hardware meaning of status bit 19 could not be determined.

## Block 0x53180000 = hardware LUT unit (LBA -> physical translation on the host I/O path)
- VERIFIED: RTTI 0x3f181-0x3f66a names CHuB, CHuLut, CHuMgr, CHuMmg, CHuNdc<0..8>, CHuUdm and sequencers
  CSqBlkEx<Cpu2X_Fifo> X = Ra, Sc, L3d, Cmpl, Comp, Lut0, Lut1. Ctor 0x26e38; CHuLut at 0x55000000 IRQ types 15,16,17.
  IRQ table 0x27298+4N: type 15 -> 0x282D4 (reads 0x53180000), type 17 -> 0x283A8 (0x54080800), type 16 -> 0x391DC.
- Sequencer CPUs (boot step C8 "sub-CPUs"): 0x5A020000 Sc, 0x5A0A0000 Ra, 0x5A120000 Cmpl, 0x53020000 Lut0,
  0x530A0000 Lut1, 0x53120000 Comp, 0x54020000 L3d.
- BE users of the block (namespace manager 0x18500-0x1A200): per-ns size limit 0x53181400+8*ns (writers 0x18BC2/0x18C0C),
  per-ns table offset 0x53181800+4*ns (0x18BA6), segment size 0x531803A0/A4/B0 (0x27DCC), enable bit0 0x53181200 (0x27DF2),
  command channel 0x53181234/38 start 0x53181230 reply 0x53181240/44 done bit1 0x531812E0 (0x27FE0/0x286A2),
  per-ns counters 0x53290000+8*ns (0x18C36).
- Host reads never pass through BE firmware (no trace record precedes the interrupt). Lookup is Lut0/Lut1 microcode (in no dump).

## Handler 0x282D4 (VERIFIED)
status = [0x53180000] & ~[0x53180010]. Bit 27 with [0x53180400] != 0 -> memory-error event 0x4204000E, no assert.
Bits 28/29 -> sequencer fault path. Anything else -> trace 0x28368, dump 20 registers (offset table 0x3E738), 0x2597A(0x04030009).
Masks written by 0x28538 from init 0x288DE: [0x53180010] = 0x05555555, [0x53180110] = 0x0088FFFF. In TROUBLE mode
(halfword [0x5B08C+0x116] != 0) the mask is 0xCFFFFFFF, i.e. the firmware itself masks these errors in TROUBLE mode.
Across all fault records: status 0x00080000, +0x8400 = 0xC3, +0x4000 = 1 or 2, other 18 registers 0. Deterministic.

## Namespace tables (VERIFIED in code)
- NS manager object BE RAM 0x53118. Persistent tables in DRAM set 0: region 0x4D at 0x92984A40; 64-bit sizes in
  512-byte sectors at 0x92984C40 (lo, hi; 8 bytes per index); allocation block magic 0x4E415350 at 0x924AF48C.
- Index 0 = free pool, namespaces are index >= 1. Create 0x18858 needs size[nsid]==0 and size[0] >= request;
  delete 0x188D2 needs size[nsid] != 0 (else status 2 at 0x1890A).
- First-time init (NS state 1, steps 0x186EE, 0x1A11C, 0x18782, 0x18716; from boot state 0x65): 0x18EAE gives all
  segments to index 0 and zeroes 1-31; 0x1906A zeroes sizes and sets size[0] = full capacity.
- Every boot: 0x18782 writes [0x53181800+4n] = n<<10 and [0x53181400+8n] = size[n]; a normal boot only checks the magic
  and the ns count, so it reaches NORMAL with limit 0 for ns 1.
- Only FE->BE opcode 0x18 (handler 0x153A2) creates a namespace. Capacity: 0x6FC400000 sectors = 3,750,232,064 4K blocks
  = 0x37F segments of 16 GiB (+0xF spare, pool 0x38E).
- Not verified: whether the FE re-syncs namespaces into the BE at boot (if it does, this hypothesis is wrong).

## BE opcode table (entry N at 0x3E1D0+4*(N-1))
0x11 whole-device LUT format (0x14EE0), no ns creation. 0x16 unmap range of one ns (0x15344 -> 0x18ACA), no existence
check. 0x17 sanitize-type (image M 0x80C23CC4). 0x18 ns create (nsid, size lo, size hi in sectors). 0x19 ns delete
(0x153E2 -> 0x188D2). 0x1A ns resize. Format NVM cannot create a namespace and may assert on an empty one.

## RAM-only pokes (volatile; originals in brackets)
- M1 mask bit 19 only: `/wl 53180010,055d5555` [0x05555555]. M2 TROUBLE-mode mask: `/wl 53180010,cfffffff`.
  (peripheral write from the console: never done before; stops the assert, does not make reads work.)
- M3 (only with M1/M2): `/ww 50028354,e026` [0xB335].
- N1 let the BE accept delete of a non-existent namespace: `/ww 50018912,2000` [0x2002] (delete returns 0 instead of 2).

## Suggested order
1. NORMAL boot, autoprobe off. `/m 924af48c,3` -> 4E415350, pool segments, NS1 segments (A predicts NS1 = 0, pool 0x38E;
   0x37F refutes). `/m 92984c40,4` -> A predicts FC400000 00000006 00000000 00000000. Do not read these in TROUBLE mode.
2. If confirmed: apply N1; admin-only: detach NSID 1 from controller 1, delete NSID 1, create (NSZE = NCAP = 3750232064,
   FLBAS 1, DPS 0, NMIC 1), attach; re-read the tables (expect ~0x37F segments, size FC400000/6); restore 0x50018912; one read.
3. Clean NVMe shutdown so the new table is committed.
4. Fallback if the FE refuses: call BE create 0x18858(1, 0xFC400000, 6) from a stub (callback word at [sp+0x14]); undesigned.

## Other candidates
B: LUT directory contents wrong for the hardware (set 1 zeroed then rebuilt); delete/create covers it too.
Low: media key (separate FE interrupt), skipped sub-CPU restart (irrelevant after power cycle), region 0x47 (was dumped),
NAND-level items. Post-assert trace records are the NAND manager re-identifying all 72 chip-enables (no diagnostic value).
