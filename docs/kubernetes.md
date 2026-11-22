# Kubernetes deployment and acceptance

This variant is for a **local or single-node development cluster**. It is not an HA or
production ingress design. PostgreSQL and MinIO use `emptyDir`: recreating either Pod
loses its data, and there are no migrations or bundled backups. The API stays at one
replica because login and template throttles are process-local; `Recreate` prevents a
rolling update from briefly creating a second set of throttle buckets.

The commands below are the deployment and acceptance procedure, not a claim that a
cluster run has already passed. Run them from `WebMonitor-Agent/` in a disposable
cluster. Never paste real credentials into rendered manifests, shell history, logs or
issue reports.

## 1. Prerequisites

1. **NetworkPolicy enforcement.** The CNI must enforce ingress and egress policies,
   `ipBlock.except`, namespace/Pod selectors, and NodePort `externalTrafficPolicy:
   Local`. A CNI that ignores NetworkPolicy makes this deployment unsafe. The DNS
   policy assumes CoreDNS is in the labeled `kube-system` namespace on TCP/UDP 53;
   adapt `deploy/k8s/network.yaml` in an overlay for a different DNS deployment.
2. **Worker seccomp profile.** Install the OCI profile on every node eligible to run
   `worker`, using the kubelet's seccomp root (normally `/var/lib/kubelet/seccomp`):

   ```sh
   sudo install -d -m 0755 /var/lib/kubelet/seccomp
   sudo install -m 0644 deploy/k8s/seccomp/chromium.json \
     /var/lib/kubelet/seccomp/chromium.json
   ```

   Keep `securityContext.seccompProfile: Localhost` and
   `localhostProfile: chromium.json`. Do not replace it with `Unconfined` or an
   unsandboxed browser. The other containers use `RuntimeDefault`.
3. **Images.** The application image defaults to
   `ghcr.io/webmonitor/webmonitor-agent:latest`; api, worker and web explicitly use
   `imagePullPolicy: Always`, so a node cannot silently reuse an old `latest`. A
   production overlay should replace that mutable tag with an immutable digest.
   `webmonitor-egress:local` and `webmonitor-minio:local` are source-built images, not
   published artifacts. Build and push both to a registry reachable by the cluster,
   then set their `newName`/`newTag` in a Kustomize overlay. Do not use `latest` with
   `IfNotPresent` for any of them.
4. **Single-node publication.** The only public endpoint is NodePort `30080`.
   `externalTrafficPolicy: Local` preserves the client source address but drops
   traffic arriving on a node without a local api/proxy Pod. Use one node, or publish
   the exact node running that Pod; this manifest deliberately does not add an
   external load balancer. `APP_ORIGIN` must match the browser-visible origin.

## 2. Create the one Secret

`deploy/k8s/secret.example.yaml` is the **only** supported Secret entry point. There is
no `secret.example.env`, and no `kubectl create secret --from-literal` alternative to
keep synchronized. Copy the example outside the checkout, edit the copy, and apply it:

```sh
install -m 0600 /dev/null /tmp/webmonitor-secrets.yaml
cp deploy/k8s/secret.example.yaml /tmp/webmonitor-secrets.yaml
${EDITOR:-vi} /tmp/webmonitor-secrets.yaml
kubectl apply -f deploy/k8s/namespace.yaml
kubectl apply -f /tmp/webmonitor-secrets.yaml
```

Replace every `replace-with-...` value. `SECRET_KEY` must contain at least 32
characters. `S3_ROOT_USER` and `S3_ROOT_PASSWORD` are the single source for both
MinIO's root login and the application's `S3_ACCESS_KEY_ID` /
`S3_SECRET_ACCESS_KEY`; there is intentionally no second S3 username or credential in
the Secret or ConfigMap.

`OPENAI_API_KEY` and a non-empty `OPENAI_MODEL` in the ConfigMap are required for
conversation features. SMTP credentials may both be empty only when `SMTP_HOST` and
`MAIL_FROM` are also empty. Leave `ADMIN_EMAIL` and `ADMIN_PASSWORD` empty to skip
initial administrator creation, or set both for first boot. To create an administrator
later without putting an administrator secret in the command line:

```sh
kubectl -n webmonitor exec -it deploy/api -c api -- \
  webmonitor admin-create --email admin@example.com
```

The Secret is deliberately not in `deploy/kustomization.yaml`; Kustomize must not
render the example or a configured credential file.

## 3. Configure, render and deploy

Edit `deploy/k8s/platform.yaml` in a Kustomize overlay. At minimum set `OPENAI_MODEL`
and the actual `APP_ORIGIN` (default `http://localhost:30080`). Plain HTTP requires
`DEVELOPMENT_MODE=true` and belongs only to this local/development deployment.

Run the deterministic source assertions and a real Kustomize render before applying:

```sh
deploy/k8s/check.sh
kubectl kustomize deploy > /tmp/webmonitor-k8s.yaml
kubectl apply -f /tmp/webmonitor-k8s.yaml
kubectl -n webmonitor rollout status deploy/postgres
kubectl -n webmonitor rollout status deploy/s3
kubectl -n webmonitor rollout status deploy/egress
kubectl -n webmonitor rollout status deploy/api
kubectl -n webmonitor rollout status deploy/web
kubectl -n webmonitor rollout status deploy/worker
```

The check script requires `kubectl`, but needs no cluster connection. It verifies the
resource references through `kubectl kustomize` and guards the Secret keys, S3 key
source, one-replica API, pull policies, loopback proxy, NodePort source preservation,
seccomp reference and bounded egress rules.

## 4. Network contract

Default deny applies to every Pod. The explicit exceptions are:

| Source | Destination | Ports |
| --- | --- | --- |
| NodePort clients | api Pod's nginx sidecar | TCP 8080 |
| nginx sidecar | API in the same Pod | loopback TCP 8000 |
| api/proxy Pod | web | TCP 3000 |
| api and worker | PostgreSQL / MinIO | TCP 5432 / 9000 |
| api and worker | Squid | TCP 3128 |
| Squid | public targets, webhooks and public model endpoints | TCP 80, 443 only |
| worker | public SMTP endpoints | TCP 465, 587 only |
| all Pods | cluster DNS in `kube-system` | TCP/UDP 53 |

There is no API Service and no NetworkPolicy ingress rule for remote TCP 8000. Do not
add one to simplify debugging: that would bypass the trusted-proxy boundary. Private,
loopback, link-local and special-use destination ranges are excluded from the public
SMTP and Squid rules. IPv4-mapped destinations are covered by the IPv4 rules;
Kubernetes rejects explicit IPv4-mapped CIDRs in NetworkPolicy. Squid additionally applies its destination ACLs after DNS
resolution. An explicitly selected internal model is the only direct internal-model
exception, described below; no arbitrary cluster or internet egress is required.

### Public model

Leave `OPENAI_CONTAINER_BASE_URL` empty. `OPENAI_BASE_URL` must be a public HTTPS
endpoint on port 443 (the default is `https://api.openai.com/v1`). Both AsyncOpenAI
construction paths use `EGRESS_PROXY_URL=http://egress:3128` for this public route.
Target collection and HTTPS webhooks use the same proxy. Public model traffic must not
be “fixed” by adding direct worker egress to TCP 443.

An internal URL placed in `OPENAI_BASE_URL` is not the internal-model contract: it
still selects the proxied public route and Squid correctly refuses private addresses.

### SMTP

SMTP is a direct TLS connection from worker, not an HTTP request through Squid. Only
these two configurations are supported:

| Mode | `SMTP_PORT` | `SMTP_USE_SSL` | `SMTP_STARTTLS` |
| --- | --- | --- | --- |
| Implicit TLS | `"465"` | `"true"` | `"false"` |
| STARTTLS | `"587"` | `"false"` | `"true"` |

Set `SMTP_HOST`, `MAIL_FROM`, and (when required by the provider) both Secret SMTP
credentials. Port 25, plaintext mail, private/cluster SMTP servers and arbitrary
custom ports are outside this deployment's support boundary. The base policy opens
both supported public SMTP ports so either documented mode works; an overlay may
remove the unused port, but must not add others.

Native NetworkPolicy selects IP ranges and ports, not a DNS hostname. Therefore this
boundary is **public IP + TCP 465/587**, not a guarantee that only one provider's
hostname is reachable. If policy requires one exact SMTP server, enforce that at an
external firewall or introduce a separately audited dedicated relay; do not broaden
worker egress or point `SMTP_HOST` at a private relay under these manifests.

## 5. Trusted proxy and real source IP

The nginx proxy is a sidecar in the single api Pod. Its generated configuration comes
from the same `deploy/proxy/nginx.conf` as Compose, with only `http://api:8000`
rewritten to `http://127.0.0.1:8000`. Nginx overwrites `X-Forwarded-For` and
`X-Real-IP` with `$remote_addr`; it does not append or trust client-provided chains.
The API sets `TRUSTED_PROXY_IP=127.0.0.1`, so uvicorn accepts forwarding headers only
from that sidecar.

`externalTrafficPolicy: Local` is required to make `$remote_addr` the actual NodePort
client instead of a SNAT address. Do not change it to `Cluster`. An additional ingress,
load balancer or host proxy is unsupported unless it preserves the original TCP
source address all the way to NodePort; never compensate by trusting `0.0.0.0/0`, the
whole Pod network, or arbitrary `X-Forwarded-For` values.

## 6. Optional internal model Service

Direct internal model traffic is denied by default. Before enabling it, create a
dedicated Service whose endpoints have stable, unique labels; a Service that also
selects unrelated Pods would make the exception too broad. The example below assumes
a Service named `model` in `webmonitor`, port 8000, selecting only Pods labeled
`app.kubernetes.io/name: internal-model`.

Create `overlays/internal-model/kustomization.yaml`:

```yaml
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: webmonitor
resources:
  - ../../deploy
  - internal-model-networkpolicy.yaml
patches:
  - target:
      group: ""
      version: v1
      kind: ConfigMap
      name: webmonitor-env
    patch: |-
      - op: replace
        path: /data/OPENAI_CONTAINER_BASE_URL
        value: http://model:8000/v1
```

Create `overlays/internal-model/internal-model-networkpolicy.yaml`:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: internal-model
spec:
  podSelector:
    matchExpressions:
      - key: app.kubernetes.io/component
        operator: In
        values: [api, worker]
  policyTypes: [Egress]
  egress:
    - to:
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: internal-model
      ports:
        - protocol: TCP
          port: 8000
```

Render and apply that overlay instead of the base. A non-empty
`OPENAI_CONTAINER_BASE_URL` selects the direct AsyncOpenAI path; `EGRESS_PROXY_URL`
still handles targets, webhooks and any public model configuration. For a model in
another namespace, add an explicit `namespaceSelector` alongside the dedicated Pod
selector. Do not replace the selector with a cluster CIDR or a broad port range.

## 7. Database initialization contract

On first boot, api and worker can initialize concurrently. The backend must hold one
PostgreSQL transaction-level advisory lock around **both** `create_all` and the initial
administrator check/create. Keep those operations in the same lock critical section;
an external one-Pod init Job is not a substitute. The one-replica API limit is about
process-local throttling, not a replacement for this database lock.

## 8. Real-cluster acceptance

Use a fresh disposable namespace/cluster with the initial administrator configured.
Record actual results separately; a successful static render is not evidence of CNI,
source-IP, model or SMTP behavior.

1. **Static and startup checks**

   ```sh
   deploy/k8s/check.sh
   kubectl -n webmonitor get pods
   curl --fail http://localhost:30080/api/v1/health/ready
   ```

   Every Deployment must become ready. A worker that cannot start its browser sandbox
   is a failed prerequisite, not a reason to disable seccomp. Complete a browser-based
   preview and verify it does not report `browser_unavailable`.

2. **Secret and S3 source checks (no values printed)**

   ```sh
   kubectl -n webmonitor exec deploy/api -c api -- python -c \
     'import os; required={"POSTGRES_PASSWORD","SECRET_KEY","S3_ROOT_USER","S3_ROOT_PASSWORD","OPENAI_API_KEY","SMTP_USERNAME","SMTP_PASSWORD","ADMIN_EMAIL","ADMIN_PASSWORD"}; assert required <= os.environ.keys(); assert len(os.environ["SECRET_KEY"]) >= 32; assert os.environ["S3_ACCESS_KEY_ID"] == os.environ["S3_ROOT_USER"]; assert os.environ["S3_SECRET_ACCESS_KEY"] == os.environ["S3_ROOT_PASSWORD"]'
   kubectl -n webmonitor exec deploy/worker -- python -c \
     'import os; assert os.environ["S3_ACCESS_KEY_ID"] == os.environ["S3_ROOT_USER"]; assert os.environ["S3_SECRET_ACCESS_KEY"] == os.environ["S3_ROOT_PASSWORD"]'
   kubectl -n webmonitor exec deploy/s3 -- bash -ec \
     '[[ -n $MINIO_ROOT_USER && -n $MINIO_ROOT_PASSWORD ]]'
   ```

   Upload evidence through a completed production collection, then confirm its
   evidence URL opens from an authenticated monitor details page.

3. **Initialization race**

   On the first concurrent api/worker start, query the fresh database:

   ```sh
   kubectl -n webmonitor exec deploy/postgres -- \
     psql -U webmonitor -d webmonitor -Atc \
     "SELECT count(*) FROM users WHERE role = 'admin';"
   ```

   The result must be exactly `1`, with no duplicate-key initialization failure in
   either application Pod. Do not perform this acceptance on a database containing
   real users.

4. **No direct API or arbitrary public egress**

   ```sh
   API_POD_IP=$(kubectl -n webmonitor get pod -l app.kubernetes.io/component=api \
     -o jsonpath='{.items[0].status.podIP}')
   if kubectl -n webmonitor exec deploy/web -- node -e \
     "fetch('http://$API_POD_IP:8000/api/v1/health/live',{signal:AbortSignal.timeout(3000)}).then(()=>process.exit(0)).catch(()=>process.exit(1))"; then
     echo 'unexpected direct API access' >&2
     exit 1
   fi
   if kubectl -n webmonitor exec deploy/worker -- python -c \
     'import socket; socket.create_connection(("1.1.1.1",443),3).close()'; then
     echo 'unexpected direct public HTTPS egress' >&2
     exit 1
   fi
   ```

   Both direct connections are expected to fail. If either succeeds, stop and fix the
   CNI/policy before using the deployment.

5. **Public model through Squid**

   ```sh
   kubectl -n webmonitor exec deploy/worker -- python -c \
     'import socket; s=socket.create_connection(("egress",3128),5); s.sendall(b"CONNECT api.openai.com:443 HTTP/1.1\r\nHost: api.openai.com:443\r\n\r\n"); response=s.recv(4096); assert response.startswith(b"HTTP/1.1 200") or response.startswith(b"HTTP/1.0 200"), response; s.close()'
   ```

   Then run a real conversation through to a saved Draft and approved monitor. The
   model call must succeed without adding direct TCP 443 worker egress. For the
   internal-model overlay, repeat the conversation using the internal Service and
   verify that another same-namespace Pod not selected by `internal-model` remains
   unreachable from worker.

6. **Source IP and forwarding-header behavior**

   From two machines with different source IPs, make repeated failed login attempts
   for the same nonexistent account. After one source reaches its login limit, the
   other source must not inherit that source-IP throttle. Once throttled, retrying
   with a forged `X-Forwarded-For` must not bypass the limit. Also verify that nodes
   without a local api/proxy endpoint are not used as alternate NodePort entry points.

7. **SMTP boundary and delivery**

   With the chosen documented SMTP mode, the configured endpoint must connect:

   ```sh
   kubectl -n webmonitor exec deploy/worker -- python -c \
     'import os,socket; socket.create_connection((os.environ["SMTP_HOST"],int(os.environ["SMTP_PORT"])),5).close()'
   ```

   Complete baseline collection, make a deterministic target change, and verify one
   change event plus SMTP acceptance. Direct worker access to public TCP 443 was
   already shown to fail above; also verify that no private SMTP relay or port 25 is
   reachable. SMTP acceptance is at-least-once, not proof of inbox delivery.
