FROM registry.redhat.io/ubi9/python-311

WORKDIR /app

COPY requirements.txt .
USER root
RUN chmod -R 0770 /etc/pki/ca-trust/ /etc/pki/tls/certs/

# Install build tools and Kerberos client for errata-tool dependencies and authentication
RUN dnf install -y gcc gcc-c++ make krb5-devel krb5-workstation curl --allowerasing && dnf clean all

RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server.py .

ENV RH_CERT_DIR="/etc/pki/ca-trust/source/anchors"
ENV REQUESTS_CA_BUNDLE="/etc/pki/tls/certs/ca-bundle.crt"
ENV RH_CERT_FILE="Current-IT-Root-CAs.pem"

RUN mkdir -p "$RH_CERT_DIR"
RUN curl -k "https://certs.corp.redhat.com/certs/$RH_CERT_FILE" \
  -o "$RH_CERT_DIR/$RH_CERT_FILE" && \
  update-ca-trust
RUN export GIT_SSL_CAINFO="$REQUESTS_CA_BUNDLE"
RUN export SSL_CERT_FILE="$REQUESTS_CA_BUNDLE"
RUN export REQUESTS_CA_BUNDLE

# Environment variables for SSE transport (default)
ENV MCP_TRANSPORT=sse
ENV MCP_PORT=8000
ENV PYTHONUNBUFFERED=1

# Expose port for SSE transport
EXPOSE 8000

# Health check for SSE transport
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD if [ "$MCP_TRANSPORT" = "sse" ]; then \
            curl -f http://localhost:${MCP_PORT}/health || exit 1; \
        else \
            echo "stdio transport - no health check needed"; \
        fi

CMD ["python", "mcp_server.py"]
