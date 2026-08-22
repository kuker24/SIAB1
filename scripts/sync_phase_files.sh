#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <relative-path> [<relative-path> ...]" >&2
  exit 1
fi

SYNC_TARGET_USER=${SYNC_TARGET_USER:-"root"}
SYNC_TARGET_HOST=${SYNC_TARGET_HOST:-"ujian-vps"}
SYNC_TARGET_PORT=${SYNC_TARGET_PORT:-22}
SYNC_TARGET_PATH=${SYNC_TARGET_PATH:-"~/ujian_online"}
SSH_KEY_PATH=${SSH_KEY_PATH:-"$HOME/.ssh/id_ed25519"}

SYNC_TARGET="${SYNC_TARGET_USER}@${SYNC_TARGET_HOST}"
if [[ "${SYNC_TARGET_HOST}" == "ujian-vps" ]]; then
  SYNC_TARGET="${SYNC_TARGET_HOST}"
fi

if [[ ! -f "${SSH_KEY_PATH}" ]]; then
  echo "SSH key not found: ${SSH_KEY_PATH}" >&2
  exit 1
fi

SSH_CMD=(ssh -p "${SYNC_TARGET_PORT}" -i "${SSH_KEY_PATH}" -o StrictHostKeyChecking=no)
RSYNC_RSH="ssh -p ${SYNC_TARGET_PORT} -i ${SSH_KEY_PATH} -o StrictHostKeyChecking=no"

for rel_path in "$@"; do
  if [[ "${rel_path}" = /* ]]; then
    echo "Path must be relative to repo root: ${rel_path}" >&2
    exit 1
  fi
  if [[ "${rel_path}" == *".."* ]]; then
    echo "Path traversal is not allowed: ${rel_path}" >&2
    exit 1
  fi
  if [[ ! "${rel_path}" =~ ^[A-Za-z0-9._/-]+$ ]]; then
    echo "Path contains unsupported characters: ${rel_path}" >&2
    exit 1
  fi
  if [[ ! -e "${rel_path}" ]]; then
    echo "Path not found: ${rel_path}" >&2
    exit 1
  fi

done

for rel_path in "$@"; do
  remote_dir="${SYNC_TARGET_PATH%/}/$(dirname "${rel_path}")"
  "${SSH_CMD[@]}" "${SYNC_TARGET}" "mkdir -p ${remote_dir}"
  rsync -az -e "${RSYNC_RSH}" "${rel_path}" "${SYNC_TARGET}:${SYNC_TARGET_PATH%/}/${rel_path}"
  echo "Synced: ${rel_path}"
done

echo "Phase file sync complete to ${SYNC_TARGET}:${SYNC_TARGET_PATH}"
