# RAG Document Intelligence on OCI

A production-grade Retrieval-Augmented Generation (RAG) stack that mirrors the "Hermes" deployment framework—FastAPI backend, React SPA frontend, Dockerized workloads, Terraform-provisioned Oracle Cloud Infrastructure (OCI), and GitHub Actions CI/CD.

---

## 🔥 Highlights
- **Multi-provider LLM support** – plug in Groq (free tier), OpenAI, or local HuggingFace/Ollama models with a single env toggle (`model=auto`).
- **PDF + JSON ingestion** – uploads are chunked, embedded, and stored in ChromaDB with full provenance metadata.
- **Single Dockerfile / Multi-stage build** – consistent images for backend + frontend used in local dev and production.
- **OCI as code** – Terraform spins up VCN, security lists, and compute, then cloud-init scripts bootstrap Docker + your repo.
- **Hermes-style CI/CD** – GitHub Actions test → build/push to GHCR → Terraform apply → health verification.
- **Dark-mode React console** – UX for uploads, chunk stats, chat, and inline source citations.

---

## 🧱 Architecture
```
┌─────────────┐      upload/query       ┌──────────────────────────┐
│ React SPA   │  ───────────────────▶  │ FastAPI RAG Backend      │
│ (frontend/) │      HTTPS /80         │ (backend/main.py)        │
└─────┬───────┘                        │  - PyPDF + JSON loaders   │
      │                                │  - Recursive chunking     │
      │ /api proxy                     │  - OpenAI/Groq/HF LLMs    │
┌─────▼───────┐                        │  - Chroma vector store    │
│ Nginx Proxy │◀───────────────────────┤                          │
└─────┬───────┘    docker network      └──────────┬───────────────┘
      │                                           │
      │                                ┌──────────▼──────────┐
      │                                │ Persistent volumes  │
      │                                │  uploads/           │
      │                                │  data/chromadb      │
      │                                └──────────┬──────────┘
      │                                   Terraform/OCI infra
      ▼
OCI VM (Docker engine, git clone via cloud-init)
```

---

## 📁 Project Layout
```
.
├── backend/                  # FastAPI app
│   ├── main.py               # Upload/query endpoints, LLM adapters
│   └── requirements.txt      # LangChain, Chroma, sentence-transformers
├── frontend/
│   └── index.html            # React SPA (served by nginx)
├── infra/
│   ├── docker/
│   │   ├── docker-compose.dev.yml   # Local dev build
│   │   ├── docker-compose.yml       # Production (GHCR images)
│   │   └── dev-data/                # Local persisted volumes
│   ├── terraform/
│   │   ├── main.tf / variables.tf / outputs.tf / terraform.tfvars.example
│   │   └── …                        # OCI network + compute
│   ├── scripts/setup-docker.sh      # Cloud-init bootstrap
│   └── nginx.conf                   # SPA + /api reverse proxy
├── .github/workflows/deploy.yml     # CI/CD pipeline
├── Dockerfile                       # Multi-stage build (backend/frontend)
├── docker-compose.yml               # Convenience wrapper for dev stack
├── DEPLOYMENT.md                    # Deep-dive guide
└── README.md
```

---

## ⚙️ Configuration Matrix
| Purpose | Variable | Notes |
|---------|----------|-------|
| LLM (hosted) | `GROQ_API_KEY` | Pointing to `https://api.groq.com/openai/v1`, default model `llama-3.1-8b-instant` |
| LLM (OpenAI) | `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL` | e.g. `gpt-4o-mini` |
| Embeddings (OpenAI) | `OPENAI_EMBED_MODEL` | default `text-embedding-3-small` |
| Embeddings (local) | `EMBEDDING_PROVIDER=huggingface`, `HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` | removes OpenAI dependency |
| Security | `ALLOWED_SSH_CIDR`, `ALLOWED_WEB_CIDR` | Restrict ingress for Terraform security lists |
| OCI | `OCI_*` secrets + `OCI_COMPARTMENT_ID` | required for IaC + CLI |
| GitHub | `GITHUB_TOKEN`, `GITHUB_OWNER`, `github_repo` terraform var | used for GHCR + git clone |

Store secrets in GitHub Actions → Settings → Secrets. Local dev can use a `.env` next to `docker-compose.dev.yml`.

---

## 🚀 Getting Started
### 1. Local Development (Docker)
```bash
# Environment (pick at least one key)
export GROQ_API_KEY=gsk_...
# or: export OPENAI_API_KEY=sk-...
# optional offline embeddings
export EMBEDDING_PROVIDER=huggingface

# Bring up stack
docker compose -f infra/docker/docker-compose.dev.yml up --build

# Access
Frontend   -> http://localhost
Backend    -> http://localhost:8000/docs
```
Volumes land in `infra/docker/dev-data` so uploads persist across restarts.

### 2. Automated CI/CD (Hermes workflow)
1. Fork this repository.
2. Add the secrets listed above in GitHub → Settings → Secrets → Actions.
3. Push to `main`. Workflow steps:
   - **test-backend** – pip install + placeholder tests.
   - **build-images** – build multi-stage Dockerfile, push `rag-backend` & `rag-frontend` to GHCR.
   - **deploy** – setup Terraform + OCI CLI, apply infra, run `setup-docker.sh`, wait on `/api/health`.
4. Output includes the public IP for the SPA, API docs, and health endpoint.

### 3. Manual Terraform (Optional)
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# fill in OCI creds, GitHub repo info, API keys
terraform init
terraform apply
terraform output instance_public_ip
```
SSH with the key you configured and use `docker compose -f infra/docker/docker-compose.yml ps` to manage services.

---

## 🧠 Backend Behavior
- `/upload` accepts PDF + JSON. PDFs go through `PyPDFLoader`; JSON is flattened recursively to preserve nested context. Chunks (1k chars, 20% overlap) get embedded and persisted in Chroma with metadata (`source`, `page`, `record_index`).
- `/query` embeds the question, retrieves top-K chunks, formats them with citations, then invokes whichever LLM is configured. `QueryRequest.model="auto"` lets `backend/main.py` route to Groq/OpenAI automatically.
- `/health` reports key availability (`openai_key_set`, `groq_key_set`, `embedding_provider`) to simplify ops dashboards.

---

## ☁️ OCI Resources (Terraform)
- **VCN (10.0.0.0/16)** + Internet Gateway + Route Table.
- **Security List** – ingress 22/80/8000 from the CIDRs you specify; egress 80/443/53.
- **Subnet** – /24 public subnet for the VM.
- **Compute Instance** – default `VM.Standard.E2.1.Micro` (Always Free) or `VM.Standard.A1.Flex` (Ampere). Boot volume size configurable.
- **Cloud-init script** – installs Docker, clones repo with PAT, logs into GHCR, writes `.env`, runs compose.

Use `deployment_trigger` variable to force redeploy without code changes.

---

## 🧪 API Cheat Sheet
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Service + key status |
| `/documents` | GET | Summary of ingested docs |
| `/upload` | POST multipart | Ingest PDF/JSON |
| `/query` | POST JSON | Ask grounded question (`question`, `top_k`, `temperature`, `model`) |
| `/reset` | DELETE | Clear Chroma + metadata |
| `/docs` | GET | Swagger UI |

---

## 🛠 Ops & Troubleshooting
- **Logs:** `docker compose logs rag-backend` / `rag-frontend` on the VM.
- **Reset vector store:** `docker exec rag-backend rm -rf /app/data/chromadb/*` then restart backend.
- **OOM on free tier:** stop frontend (`docker compose stop rag-frontend`) while debugging ingestion.
- **Network issues:** verify OCI security list + GitHub secret CIDRs, then `curl http://<ip>/api/health` from your client.

---

## 🧭 Roadmap Ideas
1. Add automated backend tests (pytest) and plug them into the GitHub Action.
2. Introduce Pinecone or OCI Vector DB for multi-instance deployments.
3. Integrate Slack bot + Confluence sync scripts for enterprise adoption.
4. Observability: ship metrics/logs to OCI Logging + Grafana.

---

Need more detail? Check [DEPLOYMENT.md](DEPLOYMENT.md) for step-by-step instructions, or reuse components with your Hermes projects.
