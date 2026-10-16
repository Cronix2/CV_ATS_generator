#!/usr/bin/env bash
# Network/secret isolation of the remote CAPTCHA browser, with the real docker-compose.yml.
# CI only (docker and docker-arm64 jobs). Usage: captcha-isolation.sh <locally built API image>
# Every stage is timestamped and has a hard limit: a stage that does not finish fails the job (exit 124),
# it never counts as a pass. The checks themselves also have per-step limits (isolation_check.py).
set -euo pipefail

started=$SECONDS
log() { echo "[$(date -u +%H:%M:%S) +$((SECONDS - started))s] $*"; }
run() {  # run <limit seconds> <command...>
  local limit=$1 t=$SECONDS rc=0
  shift
  log "start (limit ${limit}s): $*"
  timeout --kill-after=10 "$limit" "$@" || rc=$?
  if [ "$rc" = 124 ] || [ "$rc" = 137 ]; then
    log "TIMEOUT after $((SECONDS - t))s: $*"
  else
    log "exit $rc after $((SECONDS - t))s"
  fi
  return "$rc"
}

docker tag "$1" ghcr.io/cronix2/passefiltre-api:latest
export COMPOSE_PROJECT_NAME=pfci
# Throwaway secrets for the api service: the isolated browser must not see them.
printf 'PASSEFILTRE_TOKEN=%s\nOPENAI_API_KEY=ci-dummy\n' "$(openssl rand -hex 24)" > .env
# A service of the host on every interface (stands for the NAS admin pages): must stay unreachable.
python3 -m http.server 8765 --bind 0.0.0.0 >/dev/null 2>&1 &
server=$!
cleanup() {
  local rc=$?
  log "cleanup (exit $rc)"
  timeout 30 docker compose ps -a || true
  timeout 60 docker compose logs --no-color --timestamps --tail 80 api captcha-browser captcha-egress || true
  timeout 120 docker compose down -v --remove-orphans --timeout 10 || log "docker compose down did not finish"
  kill "$server" 2>/dev/null || true
  rm -f .env
  log "total $((SECONDS - started))s, exit $rc"
  exit "$rc"
}
trap cleanup EXIT

run 240 docker compose up -d --no-build --wait --wait-timeout 180 api captcha-browser captcha-egress

host_ip=$(hostname -I | awk '{print $1}')
forbid=(--forbid "$host_ip:8765" --forbid "172.17.0.1:8765")
for net in pfci_captcha pfci_default; do
  for ip in $(timeout 30 docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Gateway}} {{end}}'); do
    forbid+=(--forbid "$ip:8765")
  done
done
log "Sidecar must not reach: ${forbid[*]}"
run 240 docker compose exec -T captcha-browser python -m app.scraper.isolation_check sidecar "${forbid[@]}"
run 480 docker compose exec -T api python -m app.scraper.isolation_check api --forbid-url "http://$host_ip:8765/"
