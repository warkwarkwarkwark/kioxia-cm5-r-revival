#!/usr/bin/python3 -I
"""Print a slice of a disassembly made by dis.sh.  usage: dis.py START END [asmfile]  (hex addresses)"""
import sys,re
a=int(sys.argv[1],16); b=int(sys.argv[2],16)
f=sys.argv[3] if len(sys.argv)>3 else 'work/be.asm'
for l in open(f):
    m=re.match(r'\s*([0-9a-f]+):',l)
    if m and a<=int(m.group(1),16)<b: sys.stdout.write(l)
