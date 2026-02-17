#!/bin/bash
set -euo pipefail
LOG_FILE=/var/log/rag-setup.log
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[setup] Updating apt packages"
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates \
  curl \
  gnupg \
  lsb-release \
  git \
  docker.io \
  docker-compose-plugin

systemctl enable docker
systemctl start docker

usermod -aG docker ubuntu || true

APP_DIR=/home/ubuntu/rag-app
if [ ! -d "$APP_DIR" ]; then
  sudo -u ubuntu git clone https://${GITHUB_OWNER}:${GITHUB_TOKEN}@github.com/${GITHUB_OWNER}/${GITHUB_REPO}.git "$APP_DIR"
else
  cd "$APP_DIR"
  sudo -u ubuntu git pull
fi

chown -R ubuntu:ubuntu "$APP_DIR"
cd "$APP_DIR"

cat > .env <<ENVVARS
GITHUB_OWNER=${GITHUB_OWNER}
OPENAI_API_KEY=${OPENAI_API_KEY}
GROQ_API_KEY=${GROQ_API_KEY}
ENVVARS

chmod 640 .env
chown ubuntu:ubuntu .env

if [ -n "${GITHUB_TOKEN}" ]; then
  echo "[setup] Logging into ghcr.io"
  echo "${GITHUB_TOKEN}" | docker login ghcr.io -u "${GITHUB_OWNER}" --password-stdin
fi

docker compose -f infra/docker/docker-compose.yml pull || true
docker compose -f infra/docker/docker-compose.yml up -d --remove-orphans

echo "[setup] Deployment complete"
