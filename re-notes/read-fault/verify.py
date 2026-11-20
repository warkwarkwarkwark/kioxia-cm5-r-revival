#!/usr/bin/python3 -I
"""Spot-check of the raw bytes behind the key claims in report.md (BE image, image M, flash fault records)."""
import struct
D='./'
be=open(D+'2026-11-19-console/be-50000000-live.bin','rb').read()
m=open(D+'2026-11-20-firstinit/m-80c20000-live.bin','rb').read()
W=lambda a:struct.unpack_from('<I',be,a)[0]; H=lambda a:struct.unpack_from('<H',be,a)[0]
def chk(name,got,exp): print('%-58s %-10s %s'%(name,'%x'%got,'OK' if got==exp else 'MISMATCH (expected %x)'%exp))
chk('IRQ table type 15 [0x272d4] -> handler 0x282d4',W(0x272d4),0x282d5)
chk('IRQ table type 17 [0x272dc] -> handler 0x283a8',W(0x272dc),0x283a9)
chk('handler literal [0x285b8] status reg',W(0x285b8),0x53180000)
chk('handler literal [0x285bc] mem-error info reg',W(0x285bc),0x53180400)
chk('assert code literal [0x285d0]',W(0x285d0),0x04030009)
chk('normal mask for 0x53180010 [0x28a40]',W(0x28a40),0x05555555)
chk('normal mask for 0x53180110 [0x28a3c]',W(0x28a3c),0x0088ffff)
chk('0x2854c mvn r1,#0x30000000 (TROUBLE mask) hw0',H(0x2854c),0xf06f); chk('  hw1',H(0x2854e),0x5140)
chk('0x28aae mvn r1,#0x10000000 (memtest mask) hw0',H(0x28aae),0xf06f); chk('  hw1',H(0x28ab0),0x5180)
chk('0x28354 cbz r5 -> 0x283a4 (unknown-bit test)',H(0x28354),0xb335)
chk('0x282e6 lsls r0,r5,#4 (bit 27 test)',H(0x282e6),0x0128)
chk('0x28316 tst r5,#0x30000000 hw0',H(0x28316),0xf015); chk('  hw1',H(0x28318),0x5f40)
chk('0x18912 movs r0,#2 (NS delete: not-exist status)',H(0x18912),0x2002)
chk('opcode table op 0x11 [0x3e210] format',W(0x3e210),0x14ee1)
chk('opcode table op 0x16 [0x3e224] ns unmap',W(0x3e224),0x15345)
chk('opcode table op 0x18 [0x3e22c] ns create',W(0x3e22c),0x153a3)
chk('opcode table op 0x19 [0x3e230] ns delete',W(0x3e230),0x153e3)
chk('NS state1 table [0x3e294] first-time init step',W(0x3e294),0x186ef)
chk('NS state2 table [0x3e2a4] boot verify step',W(0x3e2a4),0x18737)
chk('NS table common step [0x3e29c] program HW regs',W(0x3e29c),0x18783)
chk('NS HW size reg base [0x18d34]',W(0x18d34),0x53181400)
chk('NS HW per-ns reg base [0x18d30]',W(0x18d30),0x53181800)
chk("NS allocation magic 'PSAN' [0x191c4]",W(0x191c4),0x4e415350)
print('handler dump offsets (0x3e738, idx 0..19):',' '.join('%x'%H(0x3e738+2*i) for i in range(20)))
print('sequencer literal pool 0x37dd0.. (code base -> adjacent destructor): 5a020000->%x 5a0a0000->%x 5a120000->%x 53020000->%x 530a0000->%x 53120000->%x 54020000->%x'%(W(0x37de0),W(0x37df4),W(0x37e08),W(0x37e1c),W(0x37e34),W(0x37e48),W(0x37e5c)))
print('  dtors: Sc 3d62d, Ra 3d475, Cmpl 3d9a1, Lut0 3dd11, Lut1 3dec5, Comp 3db59, L3d 3d7e5 (vtables via rtti.py)')
offs=[struct.unpack_from('<H',be,0x3e738+2*i)[0] for i in range(20)]
for f,o in (('2026-11-20-hostboot/flash-30000.bin',0x680),('2026-11-20-hostboot2/flash-30000.bin',0x700),('2026-11-20-m2adapter/flash-30000.bin',0x780),('2026-11-20-warmtest/flash-30000.bin',0x800)):
    d=open(D+f,'rb').read(); w=struct.unpack_from('<32I',d,o)
    regs={offs[i]:w[12+i] for i in range(20)}
    print('fault record flash 0x3%04x: code %x LR %x status %x  nonzero regs:'%(o,w[8],w[9],w[11]),{('+%x'%k):hex(v) for k,v in regs.items() if v})
# register dump list of block 0x53180000 in image M (count = low 12 bits words, skip = rest)
o=0x80c29dc4-0x80c20000; a=0; out=[]
for i in range(0x35):
    w=struct.unpack_from('<I',m,o+4*i)[0]; c=w&0xfff; out.append('%x-%x'%(a,a+4*c)); a+=4*(c+(w>>12))
print('M dump ranges of 0x53180000:',' '.join(out))
