# Errata Tool MCP Server

FastMCP server for Red Hat Errata Tool integration with AI assistants.

## Quick Start

```bash
# Build and run
./build-container.sh build
./build-container.sh run-sse

# Get interactive shell with working Kerberos
./build-container.sh interactive
kinit your_username@IPA.REDHAT.COM

# Test functions
python -c "from mcp_server import list_products; print(list_products())"
python -c "from mcp_server import get_advisory_info; print(get_advisory_info('149143'))"
```

## Available Functions

- `list_products()` - List available products (RHEL, RHIVOS, etc.) 
- `list_states()` - List advisory states (QE, SHIPPED_LIVE, etc.)
- `list_advisories(product, state, limit)` - List advisories ⚠️ Limited access
- `get_advisory_info(advisory_id)` - Get advisory details ⚠️ Requires auth

## MCP Client Configuration

Add to your MCP client config (e.g., `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "errata-tool": {
      "command": "podman",
      "args": ["run", "-d", "--rm", "--name", "errata-mcp-sse", "-p", "8000:8000", 
               "-v", "/etc/krb5.conf:/etc/krb5.conf:ro", "--network", "host", 
               "localhost/errata-mcp:latest"],
      "transport": { "type": "sse", "url": "http://localhost:8000" }
    }
  }
}
```

## Authentication

**For advisory access**, run inside container:
```bash
kinit your_username@IPA.REDHAT.COM
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| "Pigeon crap. Did it forget to run kinit?" | Run `kinit` inside container |
| Container won't start | Check: `podman --version`, `./build-container.sh logs` |
| SSE connection fails | Verify: `curl http://localhost:8000/sse/` |
| Products/States work but advisories don't | Run `kinit` for authentication |

## Commands

```bash
./build-container.sh build       # Build image
./build-container.sh run-sse     # Run SSE server (port 8000)
./build-container.sh run-stdio   # Run stdio mode (for MCP clients)
./build-container.sh interactive # Open bash shell with working Kerberos
./build-container.sh shell       # Get shell in running container
./build-container.sh logs        # View logs
./build-container.sh stop        # Stop containers
./build-container.sh clean       # Remove all
```
