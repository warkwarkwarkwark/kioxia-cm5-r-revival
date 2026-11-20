#!/usr/bin/python3 -I
import sys,struct
D=open('./2026-11-19-console/be-ram-50040000-pre-r1.bin','rb').read()
a=int(sys.argv[1],16); n=int(sys.argv[2],16)
if a>=0x50000000: a-=0x50000000
skipz = len(sys.argv)>3
for o in range(a,a+n,16):
    w=struct.unpack_from('<4I',D,o-0x40000)
    if skipz and not any(w): continue
    print('%05x(+%03x): %08x %08x %08x %08x'%(o,o-a,*w))
