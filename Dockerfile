# Stage 1: Builder
FROM mirror.gcr.io/library/python:3.13-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

ENV PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PYSETUP_SETUPTOOLS_SCM_PRETEND_VERSION_FOR_PYPI="0.0.0" \
    VENV_PATH="/app/.venv" \
    UV_FROZEN=1

WORKDIR /app

# Copy only dependency files first for better layer caching
COPY pyproject.toml uv.lock* ./

# Install dependencies without workspace members
RUN uv sync --no-dev --no-install-workspace

# Now copy the actual source code
COPY getgather /app/getgather
COPY tests /app/tests
COPY entrypoint.sh /app/entrypoint.sh
COPY .jwmrc /app/.jwmrc

# Install the workspace package
RUN uv sync --no-dev

# Grab additional blocklists
RUN curl -o /app/blocklists-analytics.txt https://raw.githubusercontent.com/hectorm/hmirror/master/data/mozilla-shavar-analytics/list.txt
RUN curl -o /app/blocklists-ads.txt https://raw.githubusercontent.com/hectorm/hmirror/master/data/mozilla-shavar-advertising/list.txt
RUN curl -o /app/blocklists-privacy.txt https://raw.githubusercontent.com/hectorm/hmirror/master/data/easyprivacy/list.txt
RUN curl -o /app/blocklists-adguard.txt https://raw.githubusercontent.com/hectorm/hmirror/master/data/adguard-simplified/list.txt

# Stage 2: Final image
FROM mirror.gcr.io/library/python:3.13-slim-bookworm

RUN apt-get update && apt-get install -y \
    tigervnc-standalone-server \
    chromium \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libxss1 \
    libasound2 \
    libgbm1 \
    libxshmfence1 \
    fonts-liberation \
    libu2f-udev \
    libvulkan1 \
    x11vnc \
    jwm \
    xterm \
    x11-apps \
    x11-utils \
    dbus \
    dbus-x11 \
    iproute2 \
    sudo \
    ca-certificates \
    iptables \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

# Copy Tailscale binaries
COPY --from=docker.io/tailscale/tailscale:stable /usr/local/bin/tailscaled /usr/local/bin/tailscaled
COPY --from=docker.io/tailscale/tailscale:stable /usr/local/bin/tailscale /usr/local/bin/tailscale

# Create Tailscale directories (chown will happen after user creation)
RUN mkdir -p /var/run/tailscale /var/cache/tailscale /var/lib/tailscale

RUN ln -s /usr/bin/chromium /usr/bin/chromium-browser

WORKDIR /app

COPY --from=builder /app/.venv /opt/venv
COPY --from=builder /app/getgather /app/getgather
COPY --from=builder /app/tests /app/tests
COPY --from=builder /app/entrypoint.sh /app/entrypoint.sh
COPY --from=builder /app/.jwmrc /app/.jwmrc
COPY --from=builder /app/blocklists-*.txt /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH"

ENV DISPLAY=:99

ARG PORT=23456
ENV PORT=${PORT}

# port for FastAPI server
EXPOSE ${PORT}
# port for VNC server
EXPOSE 5900

RUN useradd -m -s /bin/bash getgather && \
    chown -R getgather:getgather /app && \
    usermod -aG sudo getgather && \
    echo 'getgather ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

USER getgather

ENTRYPOINT ["/app/entrypoint.sh"]
