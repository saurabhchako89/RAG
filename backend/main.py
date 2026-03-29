"""
RAG API Backend — FastAPI
Claude-first, multi-connector, connector-scoped ChromaDB, SQLite state.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Local modules ─────────────────────────────────────────────────────────────
import ingestion.vector_store as vs
from ingestion.chunker import chunk_documents
from state.db import (
    append_chat_turn,
    get_chat_history,
    get_sync_states,
    init_db,
    insert_document,
    list_documents,
    upsert_sync_state,
)
import connectors.registry as registry

# ── Bootstrap ─────────────────────────────────────────────────────────────────
init_db()


def _embedding_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "openai").lower()


def _build_embeddings():
    provider = _embedding_provider()
    if provider == "huggingface":
        return HuggingFaceEmbeddings(
            model_name=os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        )
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise RuntimeError("OPENAI_API_KEY required unless EMBEDDING_PROVIDER=huggingface")
    return OpenAIEmbeddings(
        model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
        openai_api_key=openai_key,
    )


vs.set_embeddings(_build_embeddings())


def get_llm(model: Optional[str] = None, temperature: float = 0.0):
    m = None if (not model or model.lower() == "auto") else model

    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    groq_key      = os.getenv("GROQ_API_KEY")
    deepseek_key  = os.getenv("DEEPSEEK_API_KEY")
    openai_key    = os.getenv("OPENAI_API_KEY")
    gemini_key    = os.getenv("GEMINI_API_KEY")

    if anthropic_key:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=m or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            temperature=temperature,
            anthropic_api_key=anthropic_key,
        )
    if groq_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=m or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=temperature,
            openai_api_key=groq_key,
            openai_api_base=os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1"),
        )
    if deepseek_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=m or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            temperature=temperature,
            openai_api_key=deepseek_key,
            openai_api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com"),
        )
    if openai_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=m or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
            temperature=temperature,
            openai_api_key=openai_key,
        )
    if gemini_key:
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=m or os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
            temperature=temperature,
            api_key=gemini_key,
            convert_system_message_to_human=True,
        )

    raise RuntimeError("Set at least one of: ANTHROPIC_API_KEY, GROQ_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="RAG Document Q&A API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    model: str = "auto"
    temperature: float = 0.0
    connector_id: Optional[str] = None   # None = search all collections
    thread_id: Optional[str] = None
    hybrid: bool = False


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[dict]
    latency_ms: float
    connectors_searched: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_docs(docs) -> str:
    return "\n\n".join(
        f"[connector={d.metadata.get('connector','?')} source={d.metadata.get('source','?')} "
        f"page/record={d.metadata.get('page', d.metadata.get('record_index', d.metadata.get('section', 'N/A')))}]\n"
        f"{d.page_content}"
        for d in docs
    )


RAG_PROMPT = ChatPromptTemplate.from_template(
    """You are a helpful assistant. Answer using ONLY the provided context.
If the answer is not in the context, say "I couldn't find this in the provided documents."
Cite the connector and source for each fact.

{history}Context:
{context}

Question: {question}

Answer (with citations):"""
)


def _run_query(req: QueryRequest) -> QueryResponse:
    t0 = time.time()

    # Retrieve
    if req.connector_id:
        docs = vs.query_collection(req.question, req.connector_id, req.top_k)
        searched = [req.connector_id]
    else:
        docs = vs.query_all(req.question, req.top_k)
        searched = list({d.metadata.get("connector", "unknown") for d in docs})

    # Chat history
    history_text = ""
    if req.thread_id:
        turns = get_chat_history(req.thread_id)
        if turns:
            history_text = "Previous conversation:\n" + "\n".join(
                f"{t['role'].capitalize()}: {t['content']}" for t in turns
            ) + "\n\n"

    try:
        llm = get_llm(model=req.model, temperature=req.temperature)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    chain = RAG_PROMPT | llm | StrOutputParser()
    try:
        answer = chain.invoke({
            "context":  _format_docs(docs),
            "question": req.question,
            "history":  history_text,
        })
    except Exception as e:
        logger.error("LLM error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # Persist chat turn
    if req.thread_id:
        turns = get_chat_history(req.thread_id)
        turn_n = len(turns)
        append_chat_turn(req.thread_id, turn_n,     "user",      req.question)
        append_chat_turn(req.thread_id, turn_n + 1, "assistant", answer)

    sources = [
        {
            "connector": d.metadata.get("connector", "unknown"),
            "source":    d.metadata.get("source", "Unknown"),
            "page":      d.metadata.get("page", d.metadata.get("record_index", d.metadata.get("section", "N/A"))),
            "preview":   d.page_content[:300],
        }
        for d in docs
    ]

    return QueryResponse(
        question=req.question,
        answer=answer,
        sources=sources,
        latency_ms=round((time.time() - t0) * 1000, 1),
        connectors_searched=searched,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "RAG API v2 running", "docs": "/docs"}


@app.get("/health")
def health():
    active_llm = (
        "claude"   if os.getenv("ANTHROPIC_API_KEY") else
        "groq"     if os.getenv("GROQ_API_KEY")      else
        "deepseek" if os.getenv("DEEPSEEK_API_KEY")  else
        "openai"   if os.getenv("OPENAI_API_KEY")    else
        "gemini"   if os.getenv("GEMINI_API_KEY")    else
        "none"
    )
    return {
        "status":             "ok",
        "embedding_provider": _embedding_provider(),
        "active_llm":         active_llm,
        "storage":            "oci" if os.getenv("OCI_BUCKET_NAME") else "local",
        "connectors":         registry.health_all(),
    }


@app.get("/documents")
def get_documents(connector_id: Optional[str] = None):
    return {"documents": list_documents(connector_id)}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    raw_bytes = await file.read()
    connector = registry.get("files")
    try:
        docs, record = connector.ingest(file.filename, raw_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Upload error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    chunks      = chunk_documents(docs)
    chunk_count = vs.add_documents(chunks, "files")
    record["chunks"] = chunk_count
    insert_document(record)
    upsert_sync_state("files", "ok", len(list_documents("files")))

    return {"message": "File ingested successfully", **record}


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    return _run_query(req)


@app.post("/query/hybrid", response_model=QueryResponse)
def query_hybrid(req: QueryRequest):
    base = _run_query(req)

    # Gather live snippets from GitHub sources
    github_sources = [s for s in base.sources if s.get("connector") == "github"]
    if not github_sources:
        return base

    live_parts = []
    repo_dir = Path("data/repos")
    for src in github_sources[:2]:
        repo_slug = src["source"].replace("/", "_")
        file_path = repo_dir / repo_slug / src.get("page", "")
        if file_path.is_file():
            live_parts.append(f"[live: {src['source']}/{src.get('page','')}]\n{file_path.read_text(errors='ignore')[:2000]}")

    if not live_parts:
        return base

    try:
        llm = get_llm(model=req.model, temperature=req.temperature)
        supplement_prompt = (
            f"Base answer:\n{base.answer}\n\n"
            f"Live context:\n{''.join(live_parts)}\n\n"
            "Provide ONLY information from the live context that adds to or corrects the base answer. "
            "If nothing to add, respond with exactly: NO_SUPPLEMENT"
        )
        supplement = llm.invoke(supplement_prompt).content
        if "NO_SUPPLEMENT" not in supplement:
            base.answer += f"\n\n---\n**Live update:**\n{supplement}"
    except Exception as e:
        logger.warning("Hybrid supplement failed: %s", e)

    return base


@app.get("/chat/history/{thread_id}")
def chat_history(thread_id: str, last_n: int = 20):
    return {"thread_id": thread_id, "history": get_chat_history(thread_id, last_n)}


@app.get("/sync/connectors")
def sync_status():
    states = {s["connector_id"]: s for s in get_sync_states()}
    return {
        "connectors": [
            {**h, **(states.get(h["id"]) or {})}
            for h in registry.health_all()
        ]
    }


@app.post("/sync/connectors/{connector_id}/refresh")
def sync_connector(connector_id: str):
    if connector_id not in ("github", "wiki"):
        raise HTTPException(status_code=400, detail="Only github and wiki connectors support refresh.")

    conn = registry.get(connector_id)
    try:
        docs    = conn.refresh()
        chunks  = chunk_documents(docs)
        count   = vs.add_documents(chunks, connector_id)
        upsert_sync_state(connector_id, "ok", len(list_documents(connector_id)))
        return {"connector_id": connector_id, "docs_processed": len(docs), "chunks_added": count}
    except Exception as e:
        upsert_sync_state(connector_id, "error", 0)
        logger.error("Sync error [%s]: %s", connector_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/reset")
def reset(connector_id: Optional[str] = None):
    if connector_id:
        vs.reset_collection(connector_id)
        return {"message": f"Collection '{connector_id}' reset."}
    vs.reset_all()
    return {"message": "All collections reset."}
