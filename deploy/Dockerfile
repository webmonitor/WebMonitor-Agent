# One image for the whole product: the Python API/worker process and the built
# Next.js frontend live in the same artifact. Compose runs two services from this
# image with different entrypoints, and GHCR publishes exactly one tag.
#
#   api service: ENTRYPOINT webmonitor serve      (FastAPI + every background loop)
#   web service: ENTRYPOINT node /app/web/server.js (Next.js standalone server)
#
# Node is copied from the official image into the Python runtime because the
# project pins Python 3.12, which Debian bookworm does not package; both images
# are bookworm, so node's system library dependencies (libstdc++, libgcc, glibc)
# resolve against the same base.
#
# Chromium is installed by default. INSTALL_BROWSER=0 exists for environments whose
# network blocks the Playwright CDN: HTTP collection works, browser collection does not.

# ---------------------------------------------------------------------------
# Stage 1: Python wheel
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS py
ENV PIP_DEFAULT_TIMEOUT=120
WORKDIR /build
COPY pyproject.toml LICENSE ./
COPY src ./src
RUN pip wheel --no-deps --wheel-dir /wheel .

# ---------------------------------------------------------------------------
# Stage 2: Next.js standalone build
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install -g pnpm@10.34.8
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm run build

# ---------------------------------------------------------------------------
# Stage 3: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime
LABEL org.opencontainers.image.licenses="CC-BY-NC-4.0"
ARG INSTALL_BROWSER=1
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PLAYWRIGHT_DOWNLOAD_CONNECTION_TIMEOUT=120000 \
    CONTAINER_RUNTIME=true \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/opt/playwright \
    set -eux; \
    sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    pip install --require-hashes -r /tmp/requirements.txt; \
    mkdir -p /opt/browser-export; \
    if [ "$INSTALL_BROWSER" = "1" ]; then \
        python -m playwright install --with-deps chromium; \
        cp -a /opt/playwright/. /opt/browser-export/; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    groupadd --gid 10001 webmonitor; \
    useradd --uid 10001 --gid 10001 --create-home webmonitor; \
    if [ -d /opt/browser-export ]; then chmod -R a+rX /opt/browser-export; fi
# Node runtime for the frontend service. Only the binary is needed; its shared
# libraries are already present in this base image.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=web --chown=10001:10001 /app/.next/standalone /app/web
COPY --from=web --chown=10001:10001 /app/.next/static /app/web/.next/static
COPY --from=py /wheel /wheel
RUN pip install --no-cache-dir --no-deps /wheel/*.whl && rm -rf /wheel /tmp/requirements.txt
# The image can run its own regression suite; pytest reads this for testpaths and
# asyncio_mode, and tests/integration/conftest.py provisions its disposable database.
COPY pyproject.toml /app/pyproject.toml
COPY LICENSE /app/LICENSE
COPY tests /app/tests
USER 10001:10001
WORKDIR /app
ENTRYPOINT ["webmonitor"]
CMD ["serve"]

# The download cache is not part of the runtime stage. Export a normal image
# layer so retries resume missing downloads without losing the browser in the
# final artifact. INSTALL_BROWSER=0 deliberately produces an empty directory.
FROM runtime AS final
COPY --from=runtime /opt/browser-export /opt/playwright
