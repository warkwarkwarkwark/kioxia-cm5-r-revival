#!/bin/bash
# Re-detect the drive on its slot with NO kernel nvme driver, then hand it to vfio-pci for nvme-admin.py.
# usage: sudo ./vfio-attach.sh   (bridge 0000:44:08.0, drive 0000:45:00.0 on the M.2 adapter)
set -e
BR=0000:44:08.0; B=0000:45:00.0
modprobe vfio-pci
echo 0 > /sys/bus/pci/drivers_autoprobe
if [ -e /sys/bus/pci/devices/$B ]; then
  [ -e /sys/bus/pci/devices/$B/driver ] && echo $B > /sys/bus/pci/devices/$B/driver/unbind
  echo 1 > /sys/bus/pci/devices/$B/remove
  sleep 1
fi
echo 1 > /sys/bus/pci/devices/$BR/rescan
sleep 1
[ -e /sys/bus/pci/devices/$B ] || { echo "drive not found after rescan"; echo 1 > /sys/bus/pci/drivers_autoprobe; exit 1; }
echo vfio-pci > /sys/bus/pci/devices/$B/driver_override
echo > /sys/bus/pci/devices/$B/reset_method
echo $B > /sys/bus/pci/drivers/vfio-pci/bind
echo 1 > /sys/bus/pci/drivers_autoprobe
echo "bound to $(basename $(readlink /sys/bus/pci/devices/$B/driver)); BAR0 $(setpci -s $B 10.l)"
