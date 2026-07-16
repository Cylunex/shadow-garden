#!/usr/bin/env bash
# 部署 shadow-garden：目标信息从 scripts/deploy.env 读取（不入库）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$(cd "${SCRIPT_DIR}/../site" && pwd)"
ENV_FILE="${SCRIPT_DIR}/deploy.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 ${ENV_FILE}，先: cp ${SCRIPT_DIR}/deploy.env.example ${ENV_FILE} 并填写" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
: "${DEPLOY_REMOTE:?deploy.env 里需要 DEPLOY_REMOTE}"
: "${DEPLOY_WEBROOT:?deploy.env 里需要 DEPLOY_WEBROOT}"

echo "==> rsync ${SITE_DIR}/ -> ${DEPLOY_REMOTE}:${DEPLOY_WEBROOT}/"
rsync -avz --delete \
  --exclude '.DS_Store' \
  "${SITE_DIR}/" "${DEPLOY_REMOTE}:${DEPLOY_WEBROOT}/"

echo "==> 修正权限"
ssh "${DEPLOY_REMOTE}" "chmod -R a+rX ${DEPLOY_WEBROOT}"

if [[ -n "${DEPLOY_VERIFY_URL:-}" ]]; then
  echo "==> 线上验证"
  curl -s --noproxy '*' --max-time 10 -o /dev/null -w "${DEPLOY_VERIFY_URL} -> %{http_code}\n" "${DEPLOY_VERIFY_URL}"
fi
echo "done."
