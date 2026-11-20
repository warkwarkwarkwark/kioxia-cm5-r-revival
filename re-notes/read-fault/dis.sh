#!/bin/sh
# Rebuild the working disassemblies used for the read-fault analysis (output in $1, default ./work).
# BE-local address + 0x50000000 = console address.  usage: dis.sh [outdir]; then: dis.py START END [file.asm]
D=./; O=${1:-work}; mkdir -p "$O"
mk() { llvm-objcopy -I binary -O elf32-littlearm --rename-section=.data=.text,code,alloc "$1" "$O/$2.elf" &&
  llvm-objdump -d --triple=thumbv7r --adjust-vma="$3" "$O/$2.elf" | sed -E 's/ <_binary[^>]*>//g; s/@ imm = #-?0x[0-9a-f]+//' > "$O/$2.asm"; }
mk $D/2026-11-19-console/be-50000000-live.bin be 0
mk $D/2026-11-19-console/ram-00000000-live.bin fe 0
mk $D/2026-11-20-firstinit/m-80c20000-live.bin m 0x80c20000
