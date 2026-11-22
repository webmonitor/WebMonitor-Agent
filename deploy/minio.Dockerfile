# syntax=docker/dockerfile:1
# Official asset URLs and digests have one source: deploy/minio-artifacts.json.
FROM --platform=$BUILDPLATFORM python:3.12-slim-bookworm AS binaries
ARG TARGETARCH
COPY deploy/minio-artifacts.json /tmp/minio-artifacts.json
RUN python - <<'PY'
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

manifest = json.loads(Path('/tmp/minio-artifacts.json').read_text())
platform = f"linux-{os.environ['TARGETARCH']}"
out = Path('/out')
out.mkdir()
for name in ('minio', 'mc'):
    artifact = manifest[name][platform]
    digest = hashlib.sha256()
    path = out / name
    request = Request(artifact['url'], headers={'User-Agent': 'webmonitor-image-build'})
    with urlopen(request, timeout=60) as response, path.open('wb') as stream:
        if urlsplit(response.geturl()).scheme != 'https':
            raise RuntimeError('MinIO asset redirect left HTTPS')
        while chunk := response.read(1024 * 1024):
            stream.write(chunk)
            digest.update(chunk)
    if digest.hexdigest() != artifact['sha256']:
        raise RuntimeError(f'{name} asset digest mismatch')
    path.chmod(0o755)
PY

FROM debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251
LABEL org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.version="RELEASE.2025-04-22T22-12-26Z" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
COPY --from=binaries /out/minio /out/mc /usr/local/bin/
COPY --from=binaries /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
RUN groupadd --gid 10001 minio \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /tmp minio \
    && mkdir /data \
    && chown 10001:10001 /data
# Mount /data as tmpfs with uid=10001,gid=10001,mode=0700 in Compose.
# A tmpfs hides the directory ownership from this image.
ENV HOME=/tmp MC_CONFIG_DIR=/tmp/.mc MINIO_BROWSER=off
USER 10001:10001
EXPOSE 9000
ENTRYPOINT ["minio"]
CMD ["server", "/data"]
