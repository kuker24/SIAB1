#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_CMD=(docker compose -f "${ROOT_DIR}/docker-compose.production.yml")

DOMAIN="${LE_DOMAIN:?LE_DOMAIN is required}"
EMAIL="${LE_EMAIL:?LE_EMAIL is required}"
LE_CONFIG_DIR="${LE_CONFIG_DIR:-/root/letsencrypt}"
LE_LIB_DIR="${LE_LIB_DIR:-/root/letsencrypt-lib}"
WEBROOT_DIR="${ROOT_DIR}/docker/certbot/www"
CERT_DEST_DIR="${ROOT_DIR}/docker/certs"
LOCK_FILE="/tmp/renew_tls_letsencrypt.lock"

if ! mkdir "${LOCK_FILE}" 2>/dev/null; then
  echo "Another renewal process is running. Exit."
  exit 0
fi
trap 'rmdir "${LOCK_FILE}" >/dev/null 2>&1 || true' EXIT

mkdir -p "${WEBROOT_DIR}" "${LE_CONFIG_DIR}" "${LE_LIB_DIR}" "${CERT_DEST_DIR}"

echo "[renew] requesting/renewing certificate for ${DOMAIN}"
docker run --rm \
  -v "${WEBROOT_DIR}:/var/www/certbot" \
  -v "${LE_CONFIG_DIR}:/etc/letsencrypt" \
  -v "${LE_LIB_DIR}:/var/lib/letsencrypt" \
  certbot/certbot certonly \
  --webroot \
  -w /var/www/certbot \
  --non-interactive \
  --agree-tos \
  -m "${EMAIL}" \
  -d "${DOMAIN}" \
  --keep-until-expiring

echo "[renew] syncing certificate into nginx mount"
cp "${LE_CONFIG_DIR}/live/${DOMAIN}/fullchain.pem" "${CERT_DEST_DIR}/cloudflare-origin.crt"
cp "${LE_CONFIG_DIR}/live/${DOMAIN}/privkey.pem" "${CERT_DEST_DIR}/cloudflare-origin.key"
chmod 644 "${CERT_DEST_DIR}/cloudflare-origin.crt"
chmod 600 "${CERT_DEST_DIR}/cloudflare-origin.key"

echo "[renew] reloading nginx"
if [ -z "$("${COMPOSE_CMD[@]}" ps -q nginx)" ]; then
  "${COMPOSE_CMD[@]}" up -d nginx >/dev/null
fi
"${COMPOSE_CMD[@]}" exec -T nginx nginx -t >/dev/null
"${COMPOSE_CMD[@]}" exec -T nginx nginx -s reload >/dev/null

echo "[renew] done"
