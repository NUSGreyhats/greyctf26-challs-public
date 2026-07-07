#!/bin/bash

set -eu

exec qemu-system-x86_64 -m 512M -nographic -no-reboot \
  -monitor none \
  -cpu qemu64,+smep,+smap -smp cores=2 \
  -kernel bzImage \
  -initrd rootfs.cpio.gz \
  -append "console=ttyS0 oops=panic quiet loglevel=0 panic=-1 kaslr"
