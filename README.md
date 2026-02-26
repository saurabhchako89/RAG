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
| LLM (Groq) | `GROQ_API_KEY`, `GROQ_MODEL` | Uses Groq's OpenAI-compatible endpoint (default `llama-3.1-8b-instant`) |
| LLM (DeepSeek) | `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_API_BASE` | Defaults to `deepseek-chat` via `https://api.deepseek.com` |
| LLM (OpenAI) | `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL` | e.g. `gpt-4o-mini` |
| LLM (Gemini) | `GEMINI_API_KEY`, `GEMINI_MODEL` | Defaults to `gemini-1.5-flash` |
| Embeddings (OpenAI) | `OPENAI_EMBED_MODEL` | default `text-embedding-3-small` |
| Embeddings (local) | `EMBEDDING_PROVIDER=huggingface`, `HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` | removes OpenAI dependency |
| OCI provisioning | `OCI_USER_OCID`, `OCI_TENANCY_OCID`, `OCI_COMPARTMENT_ID`, `OCI_REGION`, `OCI_FINGERPRINT`, `OCI_PRIVATE_KEY`, `SSH_PUBLIC_KEY` | required for Terraform + cloud-init |
| Network CIDRs | `ALLOWED_SSH_CIDR`, `ALLOWED_WEB_CIDR` | restrict ingress to your IP(s) |
| GitHub | `GITHUB_TOKEN`, `GITHUB_OWNER` | token auto-provided by Actions for GHCR login |

Store secrets in GitHub Actions → Settings → Secrets. Local dev can use a `.env` next to `docker-compose.dev.yml`.

> At least one of `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY` must be present for the backend to serve queries.

---

## 🚀 Getting Started
### 1. Local Development (Docker)
```bash
# Environment (pick at least one key)
export GROQ_API_KEY=gsk_...
# or: export DEEPSEEK_API_KEY=dsk_...
# or: export OPENAI_API_KEY=sk-...
# or: export GEMINI_API_KEY=AIza...
# optional offline embeddings
export EMBEDDING_PROVIDER=huggingface

# Bring up stack
docker compose -f infra/docker/docker-compose.dev.yml up --build

# Access
Frontend   -> http://localhost
Backend    -> http://localhost:8000/docs
```
Volumes land in `infra/docker/dev-data` so uploads persist across restarts.

### 2. Automated CI/CD (Terraform)
1. Fork this repository.
2. Configure secrets (GitHub → Settings → Secrets → Actions):
   ```
   OCI_USER_OCID=ocid1.user.oc1..aaaa
   OCI_TENANCY_OCID=ocid1.tenancy.oc1..aaaa
   OCI_COMPARTMENT_ID=ocid1.compartment.oc1..aaaa
   OCI_REGION=us-ashburn-1
   OCI_FINGERPRINT=aa:bb:cc:dd:...
   OCI_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----
   SSH_PUBLIC_KEY=ssh-rsa AAAAB3Nza...
   ALLOWED_SSH_CIDR=YOUR_IP/32
   ALLOWED_WEB_CIDR=YOUR_IP/32

   # at least one LLM key
   GROQ_API_KEY=gsk_... / DEEPSEEK_API_KEY=... / OPENAI_API_KEY=... / GEMINI_API_KEY=...
   ```
3. Push to `main`. Workflow steps:
   - **test-backend** – dependency install + placeholder tests.
   - **build-images** – build/push backend & frontend images to GHCR.
   - **deploy** – run Terraform (`infra/terraform`) to provision/update the VCN, security list, and VM; cloud-init runs `infra/scripts/setup-docker.sh`, which pulls the latest images and starts the Compose stack.
4. The pipeline waits for `http://$INSTANCE_IP/api/health` to return 200 and then prints URLs (frontend, docs, health) in the job summary.

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

> Need to redeploy without re-running Terraform? SSH into the VM, `git pull`, and run `infra/scripts/deploy-shared.sh` to reapply the Docker Compose stack.

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

> These Terraform manifests are now optional. Use them only when you need to provision a fresh VM; the GitHub Action deploys to an existing shared host via SSH.

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
