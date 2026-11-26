#!/bin/bash
while true; do
 sudo ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ExitOnForwardFailure=yes -o ServerAliveInterval=10 -o ServerAliveCountMax=2 -i /workspaces/infinity-state/test-client-key -p 22301 -N -L 127.0.0.1:15901:127.0.0.1:5901 root@127.0.0.1
 sleep 3
done
