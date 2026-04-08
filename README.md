# Get Gather

GetGather is a containerized service that allows MCP clients to interact with your data and act on your behalf.

## Quickstart

### 0. Prerequisite

Install [Docker](https://www.docker.com/products/docker-desktop/).

### 1. Start the container

#### 1.A: Use docker-compose

Download the [docker-compose.yml](https://github.com/mcp-getgather/mcp-getgather/blob/main/docker-compose.yml) file and run

```bash
docker-compose up
```

#### 1.B: Use docker run directly

Run the container with Docker or Podman:

```bash
docker run  -v /etc/localtime:/etc/localtime:ro -p 23456:23456 ghcr.io/mcp-getgather/mcp-getgather
```

On MacOS `-v /etc/localtime:/etc/localtime:ro` is needed for the service to use your local timezone,
and on Linux it's `-v /etc/timezone:/etc/timezone:ro` instead.
On windows, the timezone has to be set directly as `-e TZ=America/Los_Angeles`.

Optionally, with `--env-file` if you have an env file.

```bash
docker run --env-file ~/getgather.env -p 23456:23456 ghcr.io/mcp-getgather/mcp-getgather
```

### 2. Connect to MCP clients

For VS Code, Cursor, and other MCP clients which support remote MCP servers:

```json
{
  "mcpServers": {
    "getgather": {
      "url": "http://127.0.0.1:23456/mcp"
    }
  }
}
```

For Claude Desktop:

```json
{
  "mcpServers": {
    "getgather": {
      "command": "npx",
      "args": ["mcp-remote", "http://127.0.0.1:23456/mcp", "--allow-http"]
    }
  }
}
```

For Codex CLI, use a [`~/.codex/config.toml`](https://github.com/openai/codex/blob/main/docs/config.md#mcp_servers) file:

```toml
[mcp_servers.getgather]
command = "npx"
args = ["mcp-remote", "http://127.0.0.1:23456/mcp", "--allow-http"]
```

#### (Optional) Enable url opener tool

Choose one of the following options if you'd like the MCP clients to automatically open the authentication link in a browser.

1. Add [playwright-mcp](https://github.com/microsoft/playwright-mcp/) server.
2. In Claude Desktop, enable "Control Chrome" in "Settings" -> "Extensions".

### 3. Read more

To live stream the container desktop, go to `http://localhost:23456/live`.

Development documentation is located in the [docs](./docs) directory:

- [Local Development Setup](./docs/local-development.md)
- [Deploying on Dokku](./docs/deploy_dokku.md)
- [Deploying on Fly.io](./docs/deploy_fly.md)
- [Deploying on Railway](./docs/deploy_railway.md)

Access AI-enhanced documentation for this repository at [deepwiki.com/mcp-getgather/mcp-getgather](https://deepwiki.com/mcp-getgather/mcp-getgather).

## Build and run locally

After cloning the repo:

```bash
docker build -t mcp-getgather .
docker run -p 23456:23456 mcp-getgather
```
