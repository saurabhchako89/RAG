# RAG Document Intelligence

A personal-scale, production-grade Retrieval-Augmented Generation (RAG) system. FastAPI backend, React SPA frontend, multi-connector ingestion (files, GitHub, Notion), connector-scoped ChromaDB collections, SQLite state, and OCI deployment via Terraform + GitHub Actions.

---

## Highlights

- **Provider-agnostic LLM** — set one API key and the backend auto-routes. Priority: Claude → Groq → DeepSeek → OpenAI → Gemini. No model selector exposed to users.
- **Three knowledge connectors** — uploaded files (PDF/JSON), GitHub repos (incremental hash sync), Notion databases. Each gets its own ChromaDB collection.
- **Hybrid query** — standard RAG answer + live file re-read from GitHub clone for additive context. Base answer is never replaced, only supplemented.
- **Persistent state** — SQLite tracks documents, chat history, and connector sync state across container restarts.
- **Chat threads** — `thread_id` generated in the browser, stored in `localStorage`, last 10 turns included in every LLM call.
- **OCI Object Storage** — uploaded files stored in a private bucket; falls back to local disk if not configured.
- **Single Dockerfile / multi-stage** — one image for backend, one for frontend (nginx), used in both local dev and production.
- **OCI infra as code** — Terraform provisions VCN, security list, subnet, and compute. Cloud-init bootstraps Docker and the Compose stack.
- **GitHub Actions CI/CD** — test → build/push to GHCR → Terraform apply → health check.
- **Stack manager script** — interactive menu to restart, rebuild, reset, or sync connectors. Auto-starts Colima if not running.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Browser                                                     │
│  React SPA (frontend/index.html)                             │
│  - Upload panel   - Connector panel   - Chat window          │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP /api proxy (nginx)
┌────────────────────────▼─────────────────────────────────────┐
│  FastAPI Backend (backend/main.py)                           │
│                                                              │
│  Connectors          Ingestion           Query               │
│  ├─ files            ├─ chunker.py       ├─ /query           │
│  ├─ github           └─ vector_store.py  └─ /query/hybrid    │
│  └─ wiki (Notion)                                            │
│                                                              │
│  State                LLM routing                            │
│  └─ SQLite (db.py)    └─ Claude/Groq/DeepSeek/OpenAI/Gemini  │
└──────┬───────────────────────────┬───────────────────────────┘
       │                           │
┌──────▼──────┐           ┌────────▼────────┐
│  ChromaDB   │           │  OCI Object     │
│  (3 colls)  │           │  Storage bucket │
│  files      │           │  (uploads/)     │
│  github     │           └─────────────────┘
│  wiki       │
└─────────────┘
```

---

## Project Layout

```
.
├── backend/
│   ├── main.py                        # FastAPI routes
│   ├── requirements.txt
│   ├── connectors/
│   │   ├── files_connector.py         # PDF/JSON upload + OCI storage
│   │   ├── github_connector.py        # Git clone + incremental hash sync
│   │   ├── wiki_connector.py          # Notion API
│   │   └── registry.py                # Connector registry + health
│   ├── ingestion/
│   │   ├── chunker.py                 # Text splitting + JSON flattening
│   │   └── vector_store.py            # Connector-scoped ChromaDB collections
│   ├── query/                         # Reserved for retriever/synthesizer split
│   └── state/
│       └── db.py                      # SQLite: documents, chat history, sync state
├── frontend/
│   └── index.html                     # React SPA (CDN, no build step)
├── scripts/
│   └── manage.sh                      # Interactive stack manager
├── infra/
│   ├── docker/
│   │   ├── docker-compose.dev.yml     # Local dev (build from source)
│   │   └── docker-compose.yml         # Production (GHCR images)
│   ├── terraform/
│   │   ├── main.tf                    # OCI VCN, subnet, compute
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── scripts/
│   │   ├── setup-docker.sh            # Cloud-init bootstrap
│   │   └── deploy-shared.sh           # SSH redeploy without Terraform
│   └── nginx.conf                     # SPA + /api reverse proxy
├── .github/workflows/deploy.yml       # CI/CD pipeline
├── Dockerfile                         # Multi-stage backend + frontend
├── .env.example                       # All env vars with comments
└── DEPLOYMENT.md                      # Deep-dive ops guide
```

---

## Configuration

### LLM — set exactly one key (priority order)

| Provider | Key | Default model |
|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | `claude-sonnet-4-20250514` |
| Groq | `GROQ_API_KEY` | `llama-3.1-8b-instant` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| OpenAI | `OPENAI_API_KEY` | `gpt-4o-mini` |
| Gemini | `GEMINI_API_KEY` | `gemini-1.5-flash` |

The active provider is shown as a read-only badge in the UI topbar.

### Embeddings

| Variable | Default | Notes |
|---|---|---|
| `EMBEDDING_PROVIDER` | `openai` | Set to `huggingface` for fully local embeddings |
| `OPENAI_EMBED_MODEL` | `text-embedding-3-small` | Used when provider is `openai` |
| `HF_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Used when provider is `huggingface` |

### Connectors

| Variable | Purpose |
|---|---|
| `GITHUB_TOKEN` | Personal access token for cloning repos |
| `GITHUB_REPOS` | Comma-separated `owner/repo` list e.g. `myorg/api,myorg/docs` |
| `NOTION_TOKEN` | Notion integration token |
| `NOTION_DATABASE_IDS` | Comma-separated Notion database IDs |

### OCI Object Storage

| Variable | Notes |
|---|---|
| `OCI_BUCKET_NAME` | Private bucket name. Leave blank to use local disk |
| `OCI_NAMESPACE` | Tenancy namespace (not OCID) |
| `OCI_REGION` | e.g. `us-ashburn-1` |
| `OCI_USE_INSTANCE_PRINCIPAL` | Set `true` on OCI VM — uses instance auth, no key file needed |

### OCI Infrastructure (Terraform + CI/CD)

| Secret | Purpose |
|---|---|
| `OCI_USER_OCID` | User OCID |
| `OCI_TENANCY_OCID` | Tenancy OCID |
| `OCI_COMPARTMENT_ID` | Compartment OCID (or use tenancy OCID for root) |
| `OCI_REGION` | Region identifier |
| `OCI_FINGERPRINT` | API key fingerprint |
| `OCI_PRIVATE_KEY` | Full PEM private key (with headers) |
| `SSH_PUBLIC_KEY` | SSH public key for VM access |
| `ALLOWED_SSH_CIDR` | IP range allowed to SSH (e.g. `1.2.3.4/32`) |
| `ALLOWED_WEB_CIDR` | IP range allowed to reach HTTP/8000 |

---

## Getting Started

### Local development

```bash
# 1. Copy and fill in at least one LLM key
cp .env.example .env

# 2. Start everything (auto-starts Colima if needed)
bash scripts/manage.sh
# → choose 1 (restart + sync) or 2 (rebuild + sync)

# Access
# Frontend  →  http://localhost
# API docs  →  http://localhost:8000/docs
# Health    →  http://localhost:8000/health
```

Data persists in `infra/docker/dev-data/` across restarts.

### Stack manager options

```
1  Restart containers + sync connectors
2  Rebuild images + restart + sync
3  Restart + reset vector store + sync
4  Sync connectors only
5  Show status
6  Exit
```

### OCI deployment (CI/CD)

1. Fork the repository.
2. Add GitHub Secrets (Settings → Secrets → Actions) — see the OCI Infrastructure table above plus your LLM key(s), connector tokens, and bucket config.
3. Push to `main`. The pipeline:
   - Installs dependencies and runs backend tests
   - Builds and pushes backend + frontend images to GHCR
   - Runs Terraform to provision/update OCI infrastructure
   - Cloud-init installs Docker, clones the repo, writes `.env`, starts the Compose stack
   - Waits for `/api/health` to return 200 and prints the deployment URLs

### Manual redeploy (no Terraform)

```bash
# SSH into the VM, then:
git pull
bash infra/scripts/deploy-shared.sh
```

---

## API Reference

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Active LLM, embedding provider, connector status |
| `/documents` | GET | All ingested documents (optionally filter by `?connector_id=`) |
| `/upload` | POST multipart | Ingest PDF or JSON file |
| `/query` | POST JSON | RAG query against all collections |
| `/query/hybrid` | POST JSON | RAG query + live GitHub supplement |
| `/chat/history/{thread_id}` | GET | Retrieve chat thread history |
| `/sync/connectors` | GET | Connector health + last sync state |
| `/sync/connectors/{id}/refresh` | POST | Trigger incremental sync for `github` or `wiki` |
| `/reset` | DELETE | Reset all collections (or `?connector_id=` for one) |
| `/docs` | GET | Swagger UI |

Query request body:

```json
{
  "question": "What does the auth module do?",
  "top_k": 5,
  "temperature": 0.0,
  "connector_id": null,
  "thread_id": "abc123",
  "hybrid": false
}
```

---

## Backend Internals

**Ingestion flow**
1. File arrives at `/upload` → `FilesConnector.ingest()` stores it in OCI (or local disk)
2. `chunker.chunk_documents()` splits into 1k-char chunks with 200-char overlap
3. `vector_store.add_documents()` embeds and persists to the `files` ChromaDB collection
4. Record written to SQLite `documents` table

**GitHub sync** (`/sync/connectors/github/refresh`)
- Clones or fetches each configured repo into `data/repos/`
- MD5-hashes every supported file (`.py`, `.md`, `.ts`, `.yaml`, etc.)
- Skips files whose hash matches the previous run — only changed files are re-embedded
- Hash state stored in `.rag_hashes` per repo

**Query flow**
- Embeds the question and searches all three ChromaDB collections (or a specific one if `connector_id` is set)
- Tags each retrieved chunk with its source connector
- Builds context with connector + source + page citations
- Includes last 10 chat turns from SQLite if `thread_id` is provided
- Calls the configured LLM and returns answer + sources + latency

**Hybrid query** (`/query/hybrid`)
- Runs the standard query first
- If any sources came from the `github` collection, re-reads the actual file from the local clone
- Asks the LLM for additive information only — never replaces the base answer
- Appends supplement under a `Live update:` separator

---

## OCI Resources (Terraform)

- **VCN** `10.0.0.0/16` + Internet Gateway + Route Table
- **Security List** — ingress 22/80/8000 from your CIDRs; egress 80/443/53
- **Subnet** — `/24` public subnet
- **Compute** — default `VM.Standard.E2.1.Micro` (Always Free) or `VM.Standard.A1.Flex` (Ampere)
- **Cloud-init** — installs Docker, clones repo, writes `.env` with all secrets, starts Compose stack

Increment `deployment_trigger` in `terraform.tfvars` to force a VM reprovision without code changes.

---

## Ops & Troubleshooting

**View logs**
```bash
docker compose -f infra/docker/docker-compose.dev.yml logs -f rag-backend
docker compose -f infra/docker/docker-compose.dev.yml logs -f rag-frontend
```

**Reset vector store**
```bash
curl -X DELETE http://localhost:8000/reset
# or reset a single connector:
curl -X DELETE "http://localhost:8000/reset?connector_id=github"
```

**Force re-sync a connector**
```bash
curl -X POST http://localhost:8000/sync/connectors/github/refresh
curl -X POST http://localhost:8000/sync/connectors/wiki/refresh
```

**OOM on free tier VM**
```bash
docker compose stop rag-frontend   # free ~50MB RAM while debugging ingestion
```

**OCI auth failures**
- Verify `OCI_FINGERPRINT` matches the key uploaded in OCI Console → User Settings → API Keys
- On the VM, `OCI_USE_INSTANCE_PRINCIPAL=true` — no key file needed
- Locally, `~/.oci/config` is mounted read-only into the container

---

## Roadmap

1. Pytest suite wired into the GitHub Actions test stage
2. Google Docs connector (OAuth) as a second wiki source
3. Pinecone or OCI Vector DB for multi-instance / shared deployments
4. Observability: structured logs → OCI Logging, metrics → Grafana
5. Slack bot integration for query-from-chat
