#!/bin/bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$APP_DIR/infra/docker/docker-compose.dev.yml"
ENV_FILE="$APP_DIR/.env"
API_BASE="http://localhost:8000"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()  { echo -e "${CYAN}[rag]${RESET} $*"; }
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
warn() { echo -e "${YELLOW}[!]${RESET} $*"; }
err()  { echo -e "${RED}[✗]${RESET} $*"; }

compose_cmd() {
  BUILDX_NO_DEFAULT_ATTESTATIONS=1 \
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
}

cleanup_local_build_images() {
  # Compose auto-tags these as <project>-<service>:latest; this avoids
  # occasional BuildKit export collisions on Docker+Colima.
  for image in docker-rag-backend docker-rag-frontend; do
    if docker image inspect "${image}:latest" >/dev/null 2>&1; then
      log "Removing local image tag ${image}:latest (pre-rebuild cleanup)..."
      docker image rm -f "${image}:latest" >/dev/null 2>&1 || true
    fi
  done
}

wait_for_backend() {
  log "Waiting for backend to be ready..."
  for i in $(seq 1 30); do
    if curl -sf "$API_BASE/health" >/dev/null 2>&1; then
      ok "Backend is up"
      return 0
    fi
    sleep 2
  done
  err "Backend did not start within 60s"
  return 1
}

sync_connectors() {
  log "Syncing connectors..."
  for connector in github wiki; do
    printf "  → %-8s " "$connector:"
    RESP=$(curl -sf -X POST "$API_BASE/sync/connectors/$connector/refresh" 2>&1)
    if [ $? -eq 0 ]; then
      SUMMARY=$(echo "$RESP" | python3 -c \
        "import sys,json; d=json.load(sys.stdin); print(f\"{d.get('docs_processed',0)} docs, {d.get('chunks_added',0)} chunks\")" 2>/dev/null || echo "ok")
      echo -e "${GREEN}${SUMMARY}${RESET}"
    else
      echo -e "${YELLOW}skipped (not configured or error)${RESET}"
    fi
  done
  ok "Sync complete"
}

force_reset() {
  warn "This will wipe ALL vector collections and document history. Continue? [y/N]"
  read -r confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    log "Aborted reset."
    return
  fi
  curl -sf -X DELETE "$API_BASE/reset" >/dev/null
  ok "Vector store reset"
}

show_status() {
  echo ""
  HEALTH=$(curl -sf "$API_BASE/health" 2>/dev/null || echo "")
  if [ -z "$HEALTH" ]; then
    warn "Backend not reachable at $API_BASE"
    return
  fi
  echo -e "${BOLD}  Backend${RESET}"
  echo "$HEALTH" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"  LLM        : {d.get('active_llm','?')}\")
print(f\"  Embeddings : {d.get('embedding_provider','?')}\")
print(f\"  Storage    : {d.get('storage','?')}\")
print()
print('  Connectors :')
for c in d.get('connectors', []):
    status = c.get('status','?')
    icon = '✓' if status == 'ok' else '·'
    print(f\"    {icon} {c['id']:<10} {status}\")
" 2>/dev/null || echo "$HEALTH"
  echo ""
}

print_menu() {
  echo ""
  echo -e "${BOLD}  RAG Stack Manager${RESET}"
  echo    "  ───────────────────────────────────────"
  echo -e "  ${CYAN}1${RESET}  Restart containers + sync connectors"
  echo -e "  ${CYAN}2${RESET}  Rebuild images + restart + sync"
  echo -e "  ${CYAN}3${RESET}  Restart + reset vector store + sync"
  echo -e "  ${CYAN}4${RESET}  Sync connectors only"
  echo -e "  ${CYAN}5${RESET}  Show status"
  echo -e "  ${CYAN}6${RESET}  Force clean build + rebuild + sync"
  echo -e "  ${CYAN}7${RESET}  Reset Colima VM + full clean rebuild + sync"
  echo -e "  ${CYAN}8${RESET}  Exit"
  echo    "  ───────────────────────────────────────"
  printf  "  Choice: "
}

do_restart_sync() {
  log "Restarting containers..."
  if ! compose_cmd up -d --remove-orphans --no-build; then
    err "Restart failed (images may not be built yet). Run option 2 to rebuild images first."
    return 1
  fi
  wait_for_backend && sync_connectors
  show_status
}

do_rebuild_sync() {
  log "Rebuilding images (no cache)..."
  cleanup_local_build_images
  compose_cmd build --no-cache
  log "Starting containers..."
  compose_cmd up -d --remove-orphans
  wait_for_backend && sync_connectors
  show_status
}

do_restart_reset_sync() {
  log "Restarting containers..."
  if ! compose_cmd up -d --remove-orphans --no-build; then
    err "Restart failed (images may not be built yet). Run option 2 to rebuild images first."
    return 1
  fi
  wait_for_backend
  force_reset
  sync_connectors
  show_status
}

do_sync_only() {
  wait_for_backend && sync_connectors
  show_status
}

do_force_clean_rebuild() {
  warn "This will prune ALL BuildKit build cache and remove local image tags. Continue? [y/N]"
  read -r confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    log "Aborted."
    return
  fi
  log "Pruning Docker build cache..."
  docker builder prune -f
  log "Stopping containers..."
  compose_cmd down --remove-orphans 2>/dev/null || true
  cleanup_local_build_images
  log "Rebuilding images (no cache)..."
  compose_cmd build --no-cache
  log "Starting containers..."
  compose_cmd up -d --remove-orphans
  wait_for_backend && sync_connectors
  show_status
}

do_reset_colima_rebuild() {
  warn "This will DELETE the Colima VM (all containers/images/volumes inside it will be lost) and recreate it. Continue? [y/N]"
  read -r confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    log "Aborted."
    return
  fi
  log "Stopping containers..."
  compose_cmd down --remove-orphans 2>/dev/null || true
  log "Stopping Colima..."
  colima stop 2>/dev/null || true
  log "Deleting Colima VM (fixes overlayfs I/O errors)..."
  colima delete --force 2>/dev/null || true
  log "Starting fresh Colima VM..."
  colima start --cpu 2 --memory 4 --disk 80
  ok "Colima VM recreated"
  log "Rebuilding images (no cache)..."
  compose_cmd build --no-cache
  log "Starting containers..."
  compose_cmd up -d --remove-orphans
  wait_for_backend && sync_connectors
  show_status
}

ensure_colima() {
  if ! colima status 2>/dev/null | grep -q "Running"; then
    log "Colima is not running. Starting..."
    colima start --cpu 2 --memory 4 --disk 60
    ok "Colima started"
  else
    ok "Colima is running"
  fi
}

# ── entrypoint ────────────────────────────────────────────────────────────────
if [ ! -f "$ENV_FILE" ]; then
  warn ".env not found — copy .env.example and fill in your keys before running"
fi

ensure_colima

while true; do
  print_menu
  read -r choice
  case "$choice" in
    1) do_restart_sync ;;
    2) do_rebuild_sync ;;
    3) do_restart_reset_sync ;;
    4) do_sync_only ;;
    5) show_status ;;
    6) do_force_clean_rebuild ;;
    7) do_reset_colima_rebuild ;;
    8) log "Bye."; exit 0 ;;
    *) warn "Invalid choice, try again" ;;
  esac
done
