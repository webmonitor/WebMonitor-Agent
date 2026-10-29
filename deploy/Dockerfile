# One backend image: HTTP API, scheduler, collectors, agent and mailer in one process.
FROM python:3.12-slim-bookworm AS build
WORKDIR /build
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY src ./src
RUN pip wheel --no-deps --wheel-dir /wheel .

FROM python:3.12-slim-bookworm
# Chromium is installed by default. INSTALL_BROWSER=0 exists for environments whose
# network blocks the Playwright CDN: HTTP collection works, browser collection does not.
ARG INSTALL_BROWSER=1
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    CONTAINER_RUNTIME=true \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
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
COPY --from=build /wheel /wheel
RUN pip install --no-cache-dir --no-deps /wheel/*.whl && rm -rf /wheel /tmp/requirements.txt
# The image can run its own regression suite; pytest reads this for testpaths and
# asyncio_mode, and tests/integration/conftest.py provisions its disposable database.
COPY pyproject.toml /app/pyproject.toml
COPY tests /app/tests
USER 10001:10001
WORKDIR /app
ENTRYPOINT ["webmonitor"]
CMD ["serve"]
