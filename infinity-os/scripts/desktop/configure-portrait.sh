#!/bin/sh
set -e
export DISPLAY=:1
xrandr | grep -q 480x800 || xrandr --newmode 480x800 35 480 520 568 656 800 803 813 850
xrandr --addmode VNC-0 480x800 2>/tmp/infinity-xrandr.log || cat /tmp/infinity-xrandr.log
xrandr --output VNC-0 --mode 480x800
mkdir -p /root/.config/gtk-3.0
cat > /root/.config/gtk-3.0/settings.ini <<'CFG'
[Settings]
gtk-font-name=Sans 16
gtk-icon-sizes=gtk-menu=24,24:gtk-button=24,24:gtk-small-toolbar=24,24:gtk-large-toolbar=32,32
gtk-cursor-theme-size=32
CFG
cat > /root/.gtkrc-2.0 <<'CFG'
gtk-font-name="Sans 16"
gtk-icon-sizes="gtk-menu=24,24:gtk-button=24,24:gtk-small-toolbar=24,24:gtk-large-toolbar=32,32"
CFG
