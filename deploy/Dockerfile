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
WORKDIR /build
COPY requirements.txt pyproject.toml LICENSE ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
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
FROM python:3.12-slim-bookworm
LABEL org.opencontainers.image.licenses="CC-BY-NC-4.0"
ARG INSTALL_BROWSER=1
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONTAINER_RUNTIME=true \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
COPY requirements.txt /tmp/requirements.txt
RUN set -eux; \
    pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt; \
    if [ "$INSTALL_BROWSER" = "1" ]; then \
        python -m playwright install --with-deps chromium; \
        rm -rf /var/lib/apt/lists/*; \
    fi; \
    groupadd --gid 10001 webmonitor; \
    useradd --uid 10001 --gid 10001 --create-home webmonitor; \
    if [ -d /opt/playwright ]; then chmod -R a+rX /opt/playwright; fi
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
