#!/usr/bin/python3 -I
import struct,re
d=open('./2026-11-19-console/be-50000000-live.bin','rb').read()
W=lambda a: struct.unpack_from('<I',d,a)[0]
def refs(v): return [i for i in range(0,0x40000,4) if W(i)==v]
names={}
for m in re.finditer(rb'\d{1,2}C[A-Za-z0-9_]+\x00',d[0x3f000:0x40000]):
    a=0x3f000+m.start(); names[a]=m.group()[:-1].decode()
for a,n in sorted(names.items()):
    for ti in refs(a):
        ti0=ti-4
        for vt in refs(ti0):
            ents=[W(vt+4+4*k) for k in range(40)]
            out=[]
            for e in ents:
                if 0x100<e<0x40000 and e&1: out.append('%x'%e)
                elif e==0: out.append('0')
                else: break
            print(n[:40],'typeinfo %x vtable@%x:'%(ti0,vt+4),' '.join(out))
