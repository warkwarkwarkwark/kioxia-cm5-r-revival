#!/usr/bin/python3 -I
# pk2live: map sibling-build K address to live K address by byte matching; mven: resolve pm veneer -> pk target -> live
import sys,struct
S='./scratch/'
live=open('./2026-11-19-console/be-50000000-live.bin','rb').read()
pk=open(S+'re5/pk.bin','rb').read(); pm=open(S+'re5/pm.bin','rb').read()
def pk2live(a):
    a&=~1
    for n in (24,16,12,8):
        for sh in (0,2,4,6,8):
            k=pk[a+sh:a+sh+n]
            c=[];i=live.find(k)
            while i>=0: c.append(i-sh); i=live.find(k,i+1)
            if len(c)==1: return c[0],'uniq%d+%d'%(n,sh)
            if c: 
                best=min(c,key=lambda x:abs(x-a)); return best,'near%d of %d'%(n,len(c))
    return None,'nomatch'
def mven(a):
    o=(a&~3)-0x80c20000
    w=struct.unpack_from('<I',pm,o)[0]
    if w==0xe51ff004: return struct.unpack_from('<I',pm,o+4)[0]
if __name__=='__main__':
    for x in sys.argv[1:]:
        v=int(x,16)
        if v>=0x80c20000:
            t=mven(v)
            if t is None: print(x,'not veneer'); continue
            l=pk2live(t); print('%x -> pk %x -> live %s (%s)'%(v,t,hex(l[0]) if l[0] is not None else None,l[1]))
        else:
            l=pk2live(v); print('pk %x -> live %s (%s)'%(v,hex(l[0]) if l[0] is not None else None,l[1]))
