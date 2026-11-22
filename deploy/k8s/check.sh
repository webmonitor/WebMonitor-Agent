#!/bin/sh
# Deterministic source assertions plus a real Kustomize render. No cluster is needed.
set -eu

deploy_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
rendered=$(mktemp "${TMPDIR:-/tmp}/webmonitor-k8s.XXXXXX")
trap 'rm -f "$rendered"' EXIT HUP INT TERM

fail() {
    printf 'Kubernetes static check failed: %s\n' "$1" >&2
    exit 1
}
require() {
    file=$1
    text=$2
    grep -F -- "$text" "$file" >/dev/null || fail "$file is missing: $text"
}
forbid() {
    file=$1
    text=$2
    if grep -F -- "$text" "$file" >/dev/null; then
        fail "$file must not contain: $text"
    fi
}

kubectl kustomize "$deploy_dir" >"$rendered"

app=$deploy_dir/k8s/app.yaml
data=$deploy_dir/k8s/data.yaml
net=$deploy_dir/k8s/network.yaml
platform=$deploy_dir/k8s/platform.yaml
secret=$deploy_dir/k8s/secret.example.yaml

[ ! -e "$deploy_dir/k8s/secret.example.env" ] || fail "remove the obsolete Secret env entry point"
for key in POSTGRES_PASSWORD SECRET_KEY S3_ROOT_USER S3_ROOT_PASSWORD OPENAI_API_KEY \
    SMTP_USERNAME SMTP_PASSWORD ADMIN_EMAIL ADMIN_PASSWORD; do
    require "$secret" "  $key:"
done
forbid "$secret" "S3_SECRET_ACCESS_KEY"
forbid "$rendered" "kind: Secret"

[ "$(grep -c 'imagePullPolicy: Always' "$app")" -eq 3 ] || \
    fail "api, worker and web must always pull the mutable application image"
forbid "$app" "replicas: 2"
forbid "$app" "app.kubernetes.io/component: proxy"
if awk '$0 == "kind: Service" {service=1} service && $0 == "  name: api" {found=1} $0 == "---" {service=0} END {exit found ? 0 : 1}' "$rendered"; then
    fail "the directly reachable API Service must remain removed"
fi
require "$app" "replicas: 1"
require "$app" "strategy: {type: Recreate}"
require "$app" "externalTrafficPolicy: Local"
require "$app" "proxy_pass http://127.0.0.1:8000"
for key in S3_ROOT_USER S3_ROOT_PASSWORD; do
    [ "$(grep -c "key: $key" "$app")" -eq 2 ] || \
        fail "$key must feed both API and worker S3 credential pairs"
    [ "$(grep -c "key: $key" "$data")" -eq 1 ] || \
        fail "$key must also configure MinIO"
done

require "$platform" "TRUSTED_PROXY_IP: 127.0.0.1"
require "$platform" "EGRESS_PROXY_URL: http://egress:3128"
require "$platform" 'OPENAI_CONTAINER_BASE_URL: ""'
forbid "$platform" "S3_ACCESS_KEY_ID: webmonitor-admin"

require "$net" "ports: [{protocol: TCP, port: 8080}]"
require "$net" "ports: [{protocol: TCP, port: 465}, {protocol: TCP, port: 587}]"
require "$net" "ports: [{protocol: TCP, port: 80}, {protocol: TCP, port: 443}]"
forbid "$net" "app.kubernetes.io/component: proxy"
forbid "$net" "::ffff:"
forbid "$net" "from: [{podSelector: {matchLabels: {app.kubernetes.io/component: web}}}]"
[ -f "$deploy_dir/k8s/seccomp/chromium.json" ] || fail "missing worker seccomp profile"
require "$app" "localhostProfile: chromium.json"

printf 'Kubernetes static checks passed; rendered %s\n' "$deploy_dir"
