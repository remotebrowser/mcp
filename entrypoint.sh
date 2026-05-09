#!/bin/sh
set -e

export DISPLAY=:99
export NO_AT_BRIDGE=1
export SESSION_MANAGER=""
export DBUS_SESSION_BUS_ADDRESS=""
export USER=getgather

# Cleanup stale X lock/socket from previous unclean shutdowns
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 || true

echo "Starting TigerVNC server on DISPLAY=$DISPLAY..."
Xvnc -alwaysshared ${DISPLAY} -geometry 1920x1080 -depth 24 -rfbport 5900 -SecurityTypes None -maxclients 2048 &

echo "Waiting for X server at $DISPLAY..."
for i in $(seq 1 20); do
if xdpyinfo -display $DISPLAY >/dev/null 2>&1; then
    echo "SUCCESS: X server ready!"
    break
fi
if [ $i -eq 20 ]; then
    echo "ERROR: X server not ready after 10s"
    exit 1
fi
sleep 0.5
done

echo "TigerVNC server running on DISPLAY=$DISPLAY"

echo "Starting DBus session"
eval $(dbus-launch --sh-syntax)
export SESSION_MANAGER=""

echo "Starting JWM (Joe's Window Manager)"
cp /app/.jwmrc $HOME
jwm >/dev/null 2>&1 &

# So that the desktop is not completely empty
xeyes &

# Start Tailscale with auth key
if [ -n "${TAILSCALE_AUTHKEY}" ]; then
    echo "Starting Tailscale with auth key..."
    
    /usr/local/bin/tailscaled --state=/var/lib/tailscale/tailscaled.state --socket=/var/run/tailscale/tailscaled.sock --tun=userspace-networking &
    sleep 2
    
    /usr/local/bin/tailscale up \
        --auth-key="${TAILSCALE_AUTHKEY}" \
        --advertise-tags="${TAILSCALE_TAG}" \
        --accept-routes
    
    TS_IP=$(/usr/local/bin/tailscale ip -4 2>/dev/null || echo "unknown")
    echo "Tailscale started. IP: ${TS_IP}"
else
    echo "TAILSCALE_AUTHKEY not set, skipping Tailscale setup"
fi

# Start FastAPI server
/opt/venv/bin/python -m uvicorn getgather.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"
