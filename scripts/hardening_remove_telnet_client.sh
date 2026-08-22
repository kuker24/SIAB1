#!/usr/bin/env bash
set -euo pipefail

APPLY=0
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
fi

if ! command -v telnet >/dev/null 2>&1; then
  echo "[OK] telnet client tidak ditemukan. Tidak ada aksi hardening yang dibutuhkan."
  exit 0
fi

TELNET_PATH="$(command -v telnet)"
echo "[INFO] telnet client terdeteksi: ${TELNET_PATH}"

REMOVE_CMD=""
if command -v pacman >/dev/null 2>&1; then
  OWNER_LINE="$(pacman -Qo "${TELNET_PATH}" 2>/dev/null || true)"
  PKG_NAME="$(awk '{print $5}' <<<"${OWNER_LINE}")"
  if [[ -z "${PKG_NAME}" ]]; then
    PKG_NAME="inetutils"
  fi
  REMOVE_CMD="pacman -Rns ${PKG_NAME}"
elif command -v dpkg >/dev/null 2>&1; then
  PKG_NAME="$(dpkg -S "${TELNET_PATH}" 2>/dev/null | head -n1 | cut -d: -f1 || true)"
  if [[ -z "${PKG_NAME}" ]]; then
    PKG_NAME="inetutils-telnet"
  fi
  REMOVE_CMD="apt-get remove --purge -y ${PKG_NAME}"
elif command -v rpm >/dev/null 2>&1; then
  PKG_NAME="$(rpm -qf "${TELNET_PATH}" 2>/dev/null || true)"
  if [[ -z "${PKG_NAME}" ]]; then
    PKG_NAME="telnet"
  fi
  REMOVE_CMD="dnf remove -y ${PKG_NAME}"
else
  echo "[WARN] Package manager tidak dikenali. Hapus paket telnet secara manual."
  exit 0
fi

echo "[INFO] Saran command hardening: sudo ${REMOVE_CMD}"

if [[ "${APPLY}" -ne 1 ]]; then
  echo "[INFO] Dry-run mode. Gunakan --apply untuk mengeksekusi hardening."
  exit 0
fi

if [[ "${EUID}" -eq 0 ]]; then
  sh -lc "${REMOVE_CMD}"
  echo "[OK] Hardening telnet selesai (run as root)."
  exit 0
fi

if sudo -n true 2>/dev/null; then
  sudo sh -lc "${REMOVE_CMD}"
  echo "[OK] Hardening telnet selesai (sudo non-interactive)."
  exit 0
fi

echo "[WARN] Butuh autentikasi sudo interaktif. Jalankan manual:"
echo "       sudo ${REMOVE_CMD}"
exit 2
