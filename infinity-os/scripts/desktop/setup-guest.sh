#!/bin/bash
set -e
export DISPLAY=:1
mkdir -p /root/.config/openbox
cat > /root/.config/openbox/menu.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?><openbox_menu xmlns="http://openbox.org/3.4/menu"><menu id="root-menu" label="INFINITY OS"><item label="Terminal"><action name="Execute"><command>xterm -fa Monospace -fs 14</command></action></item><item label="Files"><action name="Execute"><command>xterm -e sh -c 'ls -lah /root; exec bash'</command></action></item></menu></openbox_menu>
EOF
cat > /usr/local/bin/infinity-desktop <<'EOF'
#!/bin/sh
export DISPLAY=:1
/usr/bin/Xtigervnc :1 -geometry 480x800 -depth 24 -localhost yes -SecurityTypes None -AlwaysShared > /var/log/infinity-display.log 2>&1 &
X_PID=$!
sleep 2
xsetroot -solid '#173259'
dbus-launch --exit-with-session openbox-session > /var/log/infinity-window-manager.log 2>&1 &
xterm -geometry 78x24+35+55 -fa Monospace -fs 13 -bg '#0b1424' -fg '#e4edff' -T 'INFINITY OS | Real Linux Desktop' -e sh -c 'printf "INFINITY OS - Linux desktop\n\n"; hostname; printf "\nThis terminal runs inside your private Debian guest.\nRight-click the desktop for the menu.\n\n"; exec bash' &
wait "$X_PID"
EOF
chmod 755 /usr/local/bin/infinity-desktop
cat > /etc/systemd/system/infinity-desktop.service <<'EOF'
[Unit]
Description=INFINITY private guest desktop
After=network.target
[Service]
Type=simple
ExecStart=/usr/local/bin/infinity-desktop
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now infinity-desktop
systemctl is-active infinity-desktop
