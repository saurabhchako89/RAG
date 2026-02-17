# RAG Application - OCI Deployment Guide

This guide explains how to deploy your RAG application to Oracle Cloud Infrastructure (OCI) using the same approach as the Hermes project.

## 📋 Prerequisites

### 1. OCI Account Setup
- **OCI Account**: Sign up at https://cloud.oracle.com/
- **Always Free Tier**: Includes:
  - VM.Standard.E2.1.Micro (1 OCPU, 1 GB RAM) - 2 instances
  - OR VM.Standard.A1.Flex (Ampere, up to 4 OCPUs, 24 GB RAM total)
  - 200 GB Block Volume storage
  - 10 GB Object Storage

### 2. API Keys Required
- **OpenAI API Key** (optional): For embeddings/LLM - https://platform.openai.com/api-keys
- **Groq API Key** (free): For free Llama 3 access - https://console.groq.com/keys
- **GitHub Account**: For container registry

### 3. OCI API Keys
Follow: https://docs.oracle.com/en-us/iaas/Content/API/Concepts/apisigningkey.htm

---

## 🚀 Quick Start (3 Options)

### Option A: GitHub Actions (Recommended - Fully Automated)

1. **Fork/Clone this repository**

2. **Set GitHub Secrets** (Settings → Secrets and variables → Actions):

```yaml
# OCI Credentials (REQUIRED)
OCI_USER_OCID=ocid1.user.oc1..aaaaa...
OCI_FINGERPRINT=12:34:56:78:9a:bc:de...
OCI_TENANCY_OCID=ocid1.tenancy.oc1..aaaaa...
OCI_REGION=us-ashburn-1
OCI_PRIVATE_KEY=...
OCI_COMPARTMENT_ID=ocid1.compartment.oc1..aaaaa...
SSH_PUBLIC_KEY=ssh-rsa AAAAB3Nza...

# API Keys (at least one required)
OPENAI_API_KEY=sk-proj-...  (optional)
GROQ_API_KEY=gsk_...         (free tier)

# Security (optional, defaults to 0.0.0.0/0)
ALLOWED_SSH_CIDR=YOUR_IP/32
ALLOWED_WEB_CIDR=YOUR_IP/32
```

3. **Push to main branch** → GitHub Actions will automatically:
   - Build Docker images
   - Push to GitHub Container Registry
   - Deploy to OCI
   - Output: http://YOUR_VM_IP

---

### Option B: Manual Terraform Deployment

```bash
# 1. Clone repo
git clone YOUR_REPO
cd rag-deployment

# 2. Configure Terraform variables
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars

# Edit terraform.tfvars with your values:
# - OCI credentials
# - API keys
# - Security settings

# 3. Deploy
terraform init
terraform plan
terraform apply

# Get your instance IP
terraform output instance_public_ip
```

---

### Option C: Local Docker Development

```bash
# 1. Set environment variables
export OPENAI_API_KEY=sk-proj-...
export GROQ_API_KEY=gsk_...

# 2. Start services
cd infra/docker
docker-compose -f docker-compose.dev.yml up --build

# Access:
# Frontend: http://localhost
# API: http://localhost/api/docs
# Backend: http://localhost:8000
```

---

## 📁 Project Structure

```
rag-deployment/
├── Dockerfile                      # Multi-stage build (backend + frontend)
├── backend/
│   ├── main.py                    # FastAPI application
│   └── requirements.txt           # Python dependencies
├── frontend/
│   └── index.html                 # React single-page app
├── infra/
│   ├── docker/
│   │   ├── docker-compose.dev.yml    # Local development
│   │   └── docker-compose.yml        # Production (GHCR images)
│   ├── terraform/
│   │   ├── main.tf                   # OCI infrastructure
│   │   ├── variables.tf              # Configuration variables
│   │   ├── outputs.tf                # Deployment outputs
│   │   └── terraform.tfvars.example  # Template
│   ├── scripts/
│   │   └── setup-docker.sh           # VM initialization script
│   └── nginx.conf                    # Reverse proxy config
├── .github/
│   └── workflows/
│       └── deploy.yml                # CI/CD pipeline
└── DEPLOYMENT.md                     # This file
```

---

## 🔧 Configuration Details

### Environment Variables

**Backend (`backend/main.py`)**:
```bash
OPENAI_API_KEY=sk-proj-...          # OpenAI (optional)
GROQ_API_KEY=gsk_...                # Groq (free, recommended)
```

**Frontend (`frontend/index.html`)**:
- Automatically connects to backend at `/api/` (via Nginx proxy)

### Terraform Variables

**Required**:
- `compartment_id` - OCI compartment OCID
- `ssh_public_key` - For SSH access to VM
- `github_owner` - Your GitHub username
- `github_token` - GitHub PAT for GHCR

**Optional**:
- `instance_shape` - Default: `VM.Standard.E2.1.Micro` (Always Free)
- `boot_volume_size` - Default: 50 GB
- `allowed_ssh_cidr` - Default: `0.0.0.0/0` (⚠️ change in production)
- `allowed_web_cidr` - Default: `0.0.0.0/0`

---

## 🔒 Security Configuration

### Restrict Access by IP

**Option 1: Exact IP (most secure)**
```bash
# Get your IP
curl ifconfig.me

# Set in GitHub Secrets or terraform.tfvars
ALLOWED_SSH_CIDR=98.207.254.123/32
ALLOWED_WEB_CIDR=98.207.254.123/32
```

**Option 2: IP Range**
```bash
# For ISP range (handles DHCP changes)
ALLOWED_SSH_CIDR=98.207.0.0/16
ALLOWED_WEB_CIDR=98.207.0.0/16
```

**Option 3: VPN with Static IP** (recommended for production)

### Firewall Rules

The Terraform config creates these security rules:

**Ingress** (inbound):
- Port 22 (SSH) - from `allowed_ssh_cidr`
- Port 80 (HTTP) - from `allowed_web_cidr`
- Port 8000 (API) - from `allowed_web_cidr`

**Egress** (outbound):
- Port 443 (HTTPS) - for package updates, API calls
- Port 80 (HTTP) - for package updates
- Port 53 (DNS) - for name resolution

---

## 🎯 Using Free LLMs (No OpenAI Needed)

### Groq (Recommended - Free Tier)

1. Sign up: https://console.groq.com/
2. Get API key
3. Set in GitHub Secrets or `.env`:
   ```bash
   GROQ_API_KEY=gsk_...
   ```

4. Update `backend/main.py`:
   ```python
   from langchain_openai import ChatOpenAI
   
   llm = ChatOpenAI(
       model="llama-3.1-8b-instant",
       openai_api_key=os.getenv("GROQ_API_KEY"),
       openai_api_base="https://api.groq.com/openai/v1"
   )
   ```

### Ollama (Local, Completely Free)

**On your OCI VM**:
```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP

# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull model
ollama pull phi3:mini

# Update docker-compose.yml to expose Ollama
```

**Update backend**:
```python
from langchain_community.chat_models import ChatOllama

llm = ChatOllama(
    model="phi3:mini",
    base_url="http://host.docker.internal:11434"
)
```

---

## 📊 Resource Usage on OCI Free Tier

### VM.Standard.E2.1.Micro (x86)
```
Specs: 1 OCPU, 1 GB RAM, 50 GB disk
Expected usage:
- Backend (FastAPI): ~200-300 MB
- Frontend (Nginx): ~10 MB
- ChromaDB: ~50-100 MB (grows with documents)
- System: ~300 MB

Total: ~600 MB / 1 GB available
Headroom: 400 MB

⚠️ Tight fit - use Groq API (no local LLM)
```

### VM.Standard.A1.Flex (Ampere ARM)
```
Specs: 1-4 OCPUs, 6-24 GB RAM (free tier total)
Recommended: 1 OCPU, 6 GB RAM

Expected usage:
- Backend: ~300 MB
- Frontend: ~10 MB
- ChromaDB: ~100-200 MB
- Ollama (optional): ~2-4 GB with phi3:mini
- System: ~400 MB

Total: ~4.5 GB / 6 GB available
Headroom: 1.5 GB

✅ Can run local LLM with Ollama
```

---

## 🐛 Troubleshooting

### Services Not Starting

```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP

# Check Docker status
docker ps
docker compose logs

# Restart services
cd /home/ubuntu/rag-app
docker compose down
docker compose up -d
```

### Out of Memory

```bash
# Check memory
free -h

# Restart with fewer services
docker compose stop
docker compose up -d rag-backend
docker compose up -d rag-frontend
```

### Cannot Access Frontend

```bash
# Check OCI security lists
oci network security-list list --compartment-id YOUR_COMPARTMENT_ID

# Check Nginx
docker logs rag-frontend

# Check backend
curl http://localhost:8000/health
```

### ChromaDB Errors

```bash
# Clear vector store
docker exec rag-backend rm -rf /app/data/chromadb/*
docker compose restart rag-backend
```

---

## 🔄 Updating Deployment

### Update Code
```bash
# Make changes, commit, push
git add .
git commit -m "Update RAG app"
git push

# GitHub Actions will auto-deploy
```

### Force Re-deployment
```bash
# Increment deployment_trigger in Terraform
cd infra/terraform
terraform apply -var="deployment_trigger=2"
```

### Update Single Service
```bash
# SSH into VM
ssh ubuntu@YOUR_VM_IP
cd /home/ubuntu/rag-app

# Pull new image
docker compose pull rag-backend
docker compose up -d rag-backend
```

---

## 💰 Cost Estimation

**Always Free Resources**:
- 2x VM.Standard.E2.1.Micro (x86) - $0/month
- OR 1x VM.Standard.A1.Flex (4 OCPU, 24 GB) - $0/month
- 200 GB Block Volume - $0/month
- 10 GB Object Storage - $0/month

**Paid Resources (if used)**:
- VM.Standard.E4.Flex (2 OCPU, 8 GB): ~$30/month
- Egress data transfer: $0.0085/GB (first 10 TB)

**API Costs**:
- Groq: Free tier (generous limits)
- OpenAI (if used):
  - ada-002 embeddings: $0.0001/1K tokens
  - GPT-4: $0.03/1K input tokens

**Monthly estimate for modest use** (100 documents, 1000 queries):
- OCI: $0 (Always Free)
- Groq: $0 (free tier)
- **Total: $0/month** 🎉

---

## 📚 Additional Resources

- **OCI Docs**: https://docs.oracle.com/en-us/iaas/
- **Terraform OCI Provider**: https://registry.terraform.io/providers/oracle/oci/
- **Groq API**: https://console.groq.com/docs
- **LangChain Docs**: https://python.langchain.com/
- **ChromaDB Docs**: https://docs.trychroma.com/

---

## ✅ Checklist

Before deploying:
- [ ] OCI account created
- [ ] OCI API keys generated
- [ ] GitHub Secrets configured
- [ ] At least one LLM API key (Groq or OpenAI)
- [ ] SSH key pair generated
- [ ] Security CIDR ranges configured
- [ ] Repository forked/cloned
- [ ] Code pushed to main branch

After deployment:
- [ ] Services healthy at `http://VM_IP/api/health`
- [ ] Frontend accessible at `http://VM_IP`
- [ ] Can upload documents
- [ ] Can query documents
- [ ] Sources displayed correctly

---

**Need help?** Check the Hermes project for reference implementation patterns.
