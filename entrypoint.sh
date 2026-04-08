#!/bin/sh
set -e

export USER=getgather

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
