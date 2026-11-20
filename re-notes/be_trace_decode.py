#!/usr/bin/python3 -I
"""Decode the BE trace ring.  usage: be_trace_decode.py dump.bin [start_word [end_word]]
dump.bin = raw bytes read from 0x810AA800 (header 0x40 bytes + ring words).
Record: w0=(fmt<<4)|nargs, w1=timer(*0x51001214), then nargs words.  fmt ids are
'string addresses' 0x810Axxxx-0x810Cxxxx (strings are not on the drive); the map
file gives the BE call site(s) (addresses in the 0x50000000 image) that emit each id."""
import sys,struct,os
R=os.path.dirname(os.path.abspath(__file__))
fm={}
for l in open(os.path.join(R,'be_trace_fmt_map.txt')):
    p=l.split(); fm[int(p[0],16)]=' '.join(p[1:])
NOTE={0x810b3b6e:'state init: mode bit0 -> BE state TROUBLE',0x810b3b87:'state init: mode bit2 -> WRITE_PROTECTED',0x810b3ba3:'state init: NORMAL',
0x810b3bbb:'main state := arg0',0x810b1f68:'boot seq: warm start (0xD7)',0x810b1f86:'boot seq: cold start (0xC8)',0x810b1f9d:'boot seq: 0x157f0 check failed -> 0x3E7',
0x810b211e:'boot seq C8',0x810b2139:'boot seq C9 (SA root scan start)',0x810b2163:'boot seq CA: TROUBLE branch, restore skipped',0x810b2185:'boot seq CA->CB (normal)',
0x810b21a8:'boot seq CB->CF',0x810b21c5:'boot seq CF->CC (sends 0x1004)',0x810b251f:'SA scan returned -1: send 0x1001 status 2, hang',0x810b2327:'boot seq D6 -> 0x3E7 (done)',
0x810b68e7:'SA scan: 0x1c018 hit',0x810b6904:'SA scan: no usable checkpoint -> result -1',0x810b6b08:'SA scan finished',0x810b84cb:'ERROR/ASSERT report: code, LR, SP'}
D=open(sys.argv[1],'rb').read()
h=struct.unpack_from('<16I',D,0)
print('sig',D[:16],'en',h[4],'w14',hex(h[5]),'wraps',h[6],'slot',h[7])
for i in range(4): print(' slot',i,'fwtag %08x'%h[8+2*i],'idx %x'%h[9+2*i])
n=(len(D)-0x40)//4
i=int(sys.argv[2],16) if len(sys.argv)>2 else 0
end=int(sys.argv[3],16) if len(sys.argv)>3 else min(n,h[9+2*(h[7]&3)])
while i+2<=end:
    w0,t=struct.unpack_from('<II',D,0x40+4*i); na=w0&0xf; fmt=0x80000000|(w0>>4)
    if not (0x810a0000<=fmt<0x810d0000): print('%06x: ?? %08x (resync)'%(i,w0)); i+=1; continue
    args=struct.unpack_from('<%dI'%na,D,0x40+4*i+8) if i+2+na<=n else ()
    print('%06x: t=%08x fmt=%08x %-28s %s  %s'%(i,t,fmt,'['+fm.get(fmt,'?')+']',' '.join('%x'%x for x in args),NOTE.get(fmt,'')))
    i+=2+na
