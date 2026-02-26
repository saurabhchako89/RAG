#!/bin/bash
set -euo pipefail

# Deploys or updates the RAG stack on a shared OCI VM.
# Assumes this script is executed from the repository root on the remote host.

APP_DIR=${APP_DIR:-$(pwd)}
COMPOSE_FILE=${COMPOSE_FILE:-"$APP_DIR/infra/docker/docker-compose.yml"}
ENV_FILE=${ENV_FILE:-"$APP_DIR/.env"}

echo "[deploy] repository path: $APP_DIR"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "[deploy] compose file not found at $COMPOSE_FILE" >&2
  exit 1
fi

# Ensure Docker is present
if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] docker not found, installing"
  sudo apt-get update -y
  sudo apt-get install -y docker.io docker-compose-plugin
  sudo systemctl enable docker
  sudo systemctl start docker
fi

# Record env vars needed by docker compose / backend
cat > "$ENV_FILE" <<EOF
GITHUB_OWNER=${GITHUB_OWNER}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
GROQ_API_KEY=${GROQ_API_KEY:-}
GEMINI_API_KEY=${GEMINI_API_KEY:-}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
EOF
chmod 640 "$ENV_FILE"

# Authenticate to GHCR if a token is provided
if [ -n "${GITHUB_TOKEN:-}" ]; then
  echo "$GITHUB_TOKEN" | docker login ghcr.io -u "${GITHUB_OWNER}" --password-stdin
fi

echo "[deploy] pulling latest containers"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" pull

echo "[deploy] applying compose stack"
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

echo "[deploy] deployment complete"
