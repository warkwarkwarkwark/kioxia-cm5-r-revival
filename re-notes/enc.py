#!/usr/bin/python3 -I
import struct
D=open('./2026-11-19-console/be-50000000-live.bin','rb').read()
def bl(pc,target):
    off=target-(pc+4); assert off%2==0
    s=(off>>24)&1; i1=(off>>23)&1; i2=(off>>22)&1; imm10=(off>>12)&0x3ff; imm11=(off>>1)&0x7ff
    j1=(~(i1^s))&1; j2=(~(i2^s))&1
    return (0xF000|(s<<10)|imm10, 0xD000|(j1<<13)|(j2<<11)|imm11)
def b(pc,target):
    off=(target-(pc+4))>>1; return 0xE000|(off&0x7ff)
def hw(a): return struct.unpack_from('<H',D,a)[0]
# self-check against existing instructions
assert bl(0x1c0d0,0x24914)==(hw(0x1c0d0),hw(0x1c0d2)), (bl(0x1c0d0,0x24914),hex(hw(0x1c0d0)),hex(hw(0x1c0d2)))
assert bl(0x1e024,0x1b8e4)==(hw(0x1e024),hw(0x1e026))
assert bl(0x1e028,0x1b49a)==(hw(0x1e028),hw(0x1e02a))
assert b(0x1c0de,0x1c08e)==hw(0x1c0de)
print('orig 0x1c0ca..0x1c0e0:',' '.join('%04x'%hw(a) for a in range(0x1c0ca,0x1c0e0,2)))
patch=[(0x1c0ca,0x2001)]
x=bl(0x1c0cc,0x1b8e4); patch+= [(0x1c0cc,x[0]),(0x1c0ce,x[1])]
x=bl(0x1c0d0,0x1b49a); patch+= [(0x1c0d0,x[0]),(0x1c0d2,x[1])]
patch+=[(0x1c0d4,b(0x1c0d4,0x1c08e))]
for a,v in patch: print('0x500%05X halfword %04X (orig %04X)'%(a,v,hw(a)))
for a in (0x1c0d8,0x242c4,0x13bb6,0x1ea24): print(hex(a),'%04x'%hw(a))
