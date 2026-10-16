#!/usr/bin/env bash
# Network/secret isolation of the remote CAPTCHA browser, with the real docker-compose.yml.
# CI only (docker and docker-arm64 jobs). Usage: captcha-isolation.sh <locally built API image>
set -euo pipefail

docker tag "$1" ghcr.io/cronix2/passefiltre-api:latest
export COMPOSE_PROJECT_NAME=pfci
# Throwaway secrets for the api service: the isolated browser must not see them.
printf 'PASSEFILTRE_TOKEN=%s\nOPENAI_API_KEY=ci-dummy\n' "$(openssl rand -hex 24)" > .env
# A service of the host on every interface (stands for the NAS admin pages): must stay unreachable.
python3 -m http.server 8765 --bind 0.0.0.0 >/dev/null 2>&1 &
server=$!
cleanup() {
  docker compose logs --no-color --tail 40 captcha-browser captcha-egress || true
  docker compose down -v --remove-orphans || true
  kill "$server" 2>/dev/null || true
  rm -f .env
}
trap cleanup EXIT

docker compose up -d --no-build --wait --wait-timeout 180 api captcha-browser captcha-egress

host_ip=$(hostname -I | awk '{print $1}')
forbid=(--forbid "$host_ip:8765" --forbid "172.17.0.1:8765")
for net in pfci_captcha pfci_default; do
  for ip in $(docker network inspect "$net" --format '{{range .IPAM.Config}}{{.Gateway}} {{end}}'); do
    forbid+=(--forbid "$ip:8765")
  done
done
echo "Sidecar must not reach: ${forbid[*]}"
docker compose exec -T captcha-browser python -m app.scraper.isolation_check sidecar "${forbid[@]}"
docker compose exec -T api python -m app.scraper.isolation_check api --forbid-url "http://$host_ip:8765/"
