# Lmemory team server: the read-only MCP server over HTTP, for one team vault mounted read-only.
#
#   docker build -t lmemory:local .
#   docker run -d --name lmemory-team -p 8787:8787 \
#     -v /srv/team-vault:/vault:ro -v /etc/lmemory/token:/run/secrets/lmemory_token:ro \
#     lmemory:local
#
# The vault is never written; the full-text index lives in the container's own cache. See docs/TEAM.md.
FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/TinkCarlos/Lmemory" \
      org.opencontainers.image.description="Lmemory team server: read-only MCP over HTTP for one team vault" \
      org.opencontainers.image.licenses="MIT"

# Standard library only: no packages to install. (Without ripgrep the router's literal search uses Python.)
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin lmemory

COPY --chown=root:root skill/lmemory /app/skill/lmemory

USER lmemory
ENV PYTHONDONTWRITEBYTECODE=1 \
    LMEMORY_NO_QUERY_LOG=1 \
    LMEMORY_CACHE_DIR=/home/lmemory/.cache/lmemory \
    LMEMORY_STATE_DIR=/home/lmemory/.local/state/lmemory
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
  CMD python -c "import sys,urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=4).status != 200)"
ENTRYPOINT ["python", "/app/skill/lmemory/scripts/mcp_server.py", "--http", "0.0.0.0:8787", \
            "--vault", "/vault", "--token-file", "/run/secrets/lmemory_token"]
CMD ["--label", "team"]
