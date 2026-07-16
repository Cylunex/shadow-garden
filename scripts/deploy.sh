#!/usr/bin/env bash
# 部署 shadow-garden：目标信息从 scripts/deploy.env 读取（不入库）。
# 始终同步 site/ 静态站；配置了 DEPLOY_SERVER_DIR 时同步后端并重启服务。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SITE_DIR="${ROOT_DIR}/site"
SERVER_DIR="${ROOT_DIR}/server"
ENV_FILE="${SCRIPT_DIR}/deploy.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "缺少 ${ENV_FILE}，先: cp ${SCRIPT_DIR}/deploy.env.example ${ENV_FILE} 并填写" >&2
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
: "${DEPLOY_REMOTE:?deploy.env 里需要 DEPLOY_REMOTE}"
: "${DEPLOY_WEBROOT:?deploy.env 里需要 DEPLOY_WEBROOT}"

echo "==> [前端] rsync ${SITE_DIR}/ -> ${DEPLOY_REMOTE}:${DEPLOY_WEBROOT}/"
rsync -avz --delete \
  --exclude '.DS_Store' \
  "${SITE_DIR}/" "${DEPLOY_REMOTE}:${DEPLOY_WEBROOT}/"

echo "==> [前端] 修正权限"
ssh "${DEPLOY_REMOTE}" "chmod -R a+rX ${DEPLOY_WEBROOT}"

if [[ -n "${DEPLOY_SERVER_DIR:-}" ]]; then
  echo "==> [后端] rsync ${SERVER_DIR}/ -> ${DEPLOY_REMOTE}:${DEPLOY_SERVER_DIR}/"
  rsync -avz --delete \
    --exclude '.DS_Store' \
    --exclude '.venv/' \
    --exclude 'data/' \
    --exclude '.env' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude 'tests/' \
    "${SERVER_DIR}/" "${DEPLOY_REMOTE}:${DEPLOY_SERVER_DIR}/"

  echo "==> [后端] 安装依赖（首次会创建 venv）"
  ssh "${DEPLOY_REMOTE}" "cd ${DEPLOY_SERVER_DIR} \
    && (test -d .venv || python3 -m venv .venv) \
    && .venv/bin/pip install -q -r requirements.txt"

  if [[ -n "${DEPLOY_SERVICE:-}" ]]; then
    echo "==> [后端] 重启 ${DEPLOY_SERVICE}"
    ssh "${DEPLOY_REMOTE}" "sudo systemctl restart ${DEPLOY_SERVICE} \
      && sudo systemctl --no-pager --lines=0 status ${DEPLOY_SERVICE}"
  fi
fi

if [[ -n "${DEPLOY_VERIFY_URL:-}" ]]; then
  echo "==> 线上验证"
  curl -s --noproxy '*' --max-time 10 -o /dev/null -w "${DEPLOY_VERIFY_URL} -> %{http_code}\n" "${DEPLOY_VERIFY_URL}"
fi
echo "done."
