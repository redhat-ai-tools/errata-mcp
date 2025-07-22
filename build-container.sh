#!/bin/bash

# Errata Tool MCP Server - Container Build and Management Script

set -e

CONTAINER_NAME="errata-mcp"
CONTAINER_TAG="latest"
IMAGE_NAME="localhost/${CONTAINER_NAME}:${CONTAINER_TAG}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 {build|run-sse|run-stdio|interactive|stop|logs|shell|clean}"
    echo ""
    echo "Commands:"
    echo "  build       - Build the container image"
    echo "  run-sse     - Run container with SSE transport on port 8000"
    echo "  run-stdio   - Run container with stdio transport (for MCP client)"
    echo "  interactive - Open bash shell with working Kerberos setup"
    echo "  stop        - Stop running containers"
    echo "  logs        - Show container logs"
    echo "  shell       - Get shell access to running container"
    echo "  clean       - Remove container and image"
    echo ""
    echo "Authentication:"
    echo "  Use './build-container.sh interactive' then run 'kinit your_username@IPA.REDHAT.COM'"
}

build_image() {
    echo -e "${BLUE}Building Errata Tool MCP container...${NC}"
    podman build -t ${IMAGE_NAME} .
    echo -e "${GREEN}Build completed: ${IMAGE_NAME}${NC}"
}

run_sse() {
    echo -e "${BLUE}Starting Errata Tool MCP server with SSE transport...${NC}"
    podman run -d \
        --rm \
        --name "${CONTAINER_NAME}-sse" \
        -p 8000:8000 \
        -e MCP_TRANSPORT=sse \
        -e MCP_PORT=8000 \
        -v "/etc/krb5.conf:/etc/krb5.conf:ro" \
        --network host \
        --security-opt label=disable \
        ${IMAGE_NAME}
    echo -e "${GREEN}Container started in background${NC}"
    echo "SSE endpoint: http://localhost:8000"
    echo "For authentication: $0 shell → kinit your_username@IPA.REDHAT.COM"
    echo "View logs: $0 logs"
}

run_stdio() {
    echo -e "${BLUE}Starting Errata Tool MCP server with stdio transport...${NC}"
    podman run -it \
        --rm \
        --name "${CONTAINER_NAME}-stdio" \
        -e MCP_TRANSPORT=stdio \
        -v "/etc/krb5.conf:/etc/krb5.conf:ro" \
        --network host \
        --security-opt label=disable \
        ${IMAGE_NAME}
}

interactive() {
    echo -e "${BLUE}Starting interactive container with working Kerberos setup...${NC}"
    echo -e "${YELLOW}This will open a bash shell where you can run:${NC}"
    echo -e "${YELLOW}  1. kinit your_username@IPA.REDHAT.COM${NC}"
    echo -e "${YELLOW}  2. python -c \"from mcp_server import get_advisory_info; print(get_advisory_info('149143'))\"${NC}"
    echo ""
    
    podman run -it \
        --rm \
        --name "${CONTAINER_NAME}-interactive" \
        -v "/etc/krb5.conf:/etc/krb5.conf:ro" \
        --network host \
        --security-opt label=disable \
        -e KRB5CCNAME="FILE:/tmp/krb5cc_root" \
        ${IMAGE_NAME} \
        bash
}

stop_containers() {
    echo -e "${BLUE}Stopping Errata Tool MCP containers...${NC}"
    podman stop "${CONTAINER_NAME}-sse" 2>/dev/null || true
    podman stop "${CONTAINER_NAME}-stdio" 2>/dev/null || true
    echo -e "${GREEN}Containers stopped${NC}"
}

show_logs() {
    echo -e "${BLUE}Showing logs for Errata Tool MCP container...${NC}"
    podman logs -f "${CONTAINER_NAME}-sse" 2>/dev/null || \
    podman logs -f "${CONTAINER_NAME}-stdio" 2>/dev/null || \
    echo -e "${RED}No running containers found${NC}"
}

shell_access() {
    echo -e "${BLUE}Opening shell in Errata Tool MCP container...${NC}"
    podman exec -it "${CONTAINER_NAME}-sse" /bin/bash 2>/dev/null || \
    podman exec -it "${CONTAINER_NAME}-stdio" /bin/bash 2>/dev/null || \
    echo -e "${RED}No running containers found${NC}"
}

clean_all() {
    echo -e "${BLUE}Cleaning up Errata Tool MCP containers and images...${NC}"
    stop_containers
    podman rmi ${IMAGE_NAME} 2>/dev/null || true
    echo -e "${GREEN}Cleanup completed${NC}"
}



# Check if podman is available
if ! command -v podman &> /dev/null; then
    echo -e "${RED}Error: podman is not installed or not in PATH${NC}"
    exit 1
fi

# Main command handling
case "${1}" in
    build)
        build_image
        ;;
    run-sse)
        build_image
        run_sse
        ;;
    run-stdio)
        build_image
        run_stdio
        ;;
    interactive)
        build_image
        interactive
        ;;
    stop)
        stop_containers
        ;;
    logs)
        show_logs
        ;;
    shell)
        shell_access
        ;;
    clean)
        clean_all
        ;;

    *)
        print_usage
        exit 1
        ;;
esac 