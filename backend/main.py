"""
RAG API Backend - FastAPI
Production-ready RAG system with PDF + JSON ingestion and query endpoints
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import json
import uuid
import time
import shutil
from pathlib import Path
from typing import Optional
import logging

# ── LangChain imports ────────────────────────────────────────────────────────
from langchain_community.document_loaders import PyPDFLoader
from langchain.schema import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.vectorstores import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
CHROMA_DIR = Path("data/chromadb")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="RAG Document Q&A API",
    description="Production-grade Retrieval-Augmented Generation API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Shared state ──────────────────────────────────────────────────────────────
_embeddings = None
_vector_store: Optional[Chroma] = None
ingested_docs: list[dict] = []          # simple in-memory registry


def _embedding_provider() -> str:
    return os.getenv("EMBEDDING_PROVIDER", "openai").lower()


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        provider = _embedding_provider()
        if provider == "huggingface":
            model_name = os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
            _embeddings = HuggingFaceEmbeddings(model_name=model_name)
        else:
            openai_key = os.getenv("OPENAI_API_KEY")
            if not openai_key:
                raise RuntimeError("OPENAI_API_KEY is required unless EMBEDDING_PROVIDER=huggingface")
            _embeddings = OpenAIEmbeddings(
                model=os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small"),
                openai_api_key=openai_key
            )
    return _embeddings


def get_vector_store() -> Chroma:
    global _vector_store
    if _vector_store is None:
        _vector_store = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=get_embeddings()
        )
    return _vector_store


def get_llm(model: Optional[str] = None, temperature: float = 0.0):
    requested_model = model
    if requested_model and requested_model.lower() == "auto":
        requested_model = None

    groq_key = os.getenv("GROQ_API_KEY")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if groq_key:
        resolved_model = requested_model or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            openai_api_key=groq_key,
            openai_api_base=os.getenv("GROQ_API_BASE", "https://api.groq.com/openai/v1")
        )

    if deepseek_key:
        resolved_model = requested_model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            openai_api_key=deepseek_key,
            openai_api_base=os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        )

    if openai_key:
        resolved_model = requested_model or os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini")
        return ChatOpenAI(
            model=resolved_model,
            temperature=temperature,
            openai_api_key=openai_key
        )

    if gemini_key:
        resolved_model = requested_model or os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
        return ChatGoogleGenerativeAI(
            model=resolved_model,
            temperature=temperature,
            api_key=gemini_key,
            convert_system_message_to_human=True,
        )

    raise RuntimeError("Set one of GROQ_API_KEY, DEEPSEEK_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY to query the knowledge base.")


# ── Helpers ───────────────────────────────────────────────────────────────────

def chunk_and_ingest(docs: list[Document], source_name: str) -> int:
    """Chunk documents and upsert into ChromaDB. Returns number of chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    chunks = splitter.split_documents(docs)
    logger.info(f"Ingesting {len(chunks)} chunks from '{source_name}'")

    vs = get_vector_store()
    vs.add_documents(chunks)
    vs.persist()
    return len(chunks)


def json_to_documents(data: dict | list, source: str) -> list[Document]:
    """
    Flatten a JSON file into LangChain Documents.
    Each top-level key (or array item) becomes a separate document chunk
    so the vector store can pinpoint exactly where an answer came from.
    """
    docs = []

    def _flatten(obj, prefix="") -> str:
        if isinstance(obj, dict):
            return "\n".join(
                f"{prefix}{k}: {_flatten(v, prefix='  ')}" for k, v in obj.items()
            )
        elif isinstance(obj, list):
            return "\n".join(
                f"[{i}] {_flatten(item)}" for i, item in enumerate(obj)
            )
        else:
            return str(obj)

    if isinstance(data, list):
        for i, item in enumerate(data):
            text = _flatten(item)
            docs.append(Document(
                page_content=text,
                metadata={"source": source, "record_index": i}
            ))
    elif isinstance(data, dict):
        for key, value in data.items():
            text = f"{key}:\n{_flatten(value)}"
            docs.append(Document(
                page_content=text,
                metadata={"source": source, "section": key}
            ))
    else:
        docs.append(Document(
            page_content=str(data),
            metadata={"source": source}
        ))

    return docs


# ── Pydantic models ───────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    top_k: int = 5
    model: str = "auto"
    temperature: float = 0.0


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list[dict]
    latency_ms: float


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "RAG API is running", "docs": "/docs"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "groq_key_set": bool(os.getenv("GROQ_API_KEY")),
        "embedding_provider": _embedding_provider(),
        "documents_ingested": len(ingested_docs),
    }


@app.get("/documents")
def list_documents():
    """List all ingested documents."""
    return {"documents": ingested_docs}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload and ingest a PDF or JSON file.
    Returns chunk count and document metadata.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".json"):
        raise HTTPException(status_code=400, detail="Only PDF and JSON files are supported.")

    # Save to disk
    file_id = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f"{file_id}_{file.filename}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info(f"Saved upload: {save_path}")

    try:
        if suffix == ".pdf":
            loader = PyPDFLoader(str(save_path))
            docs = loader.load()

        elif suffix == ".json":
            with open(save_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            docs = json_to_documents(data, source=file.filename)

        chunk_count = chunk_and_ingest(docs, source=file.filename)

        record = {
            "id": file_id,
            "filename": file.filename,
            "type": suffix.lstrip("."),
            "pages_or_records": len(docs),
            "chunks": chunk_count,
        }
        ingested_docs.append(record)

        return {"message": "File ingested successfully", **record}

    except Exception as e:
        logger.error(f"Ingestion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest):
    """
    Query the knowledge base. Returns an LLM-generated answer
    grounded in retrieved document chunks, plus source citations.
    """
    t0 = time.time()

    vs = get_vector_store()
    retriever = vs.as_retriever(search_kwargs={"k": req.top_k})

    # Retrieve source docs for citation display
    source_docs = retriever.invoke(req.question)

    # Build prompt
    prompt = ChatPromptTemplate.from_template(
        """You are a helpful assistant that answers questions based strictly on the provided context.
If the answer is not in the context, say "I couldn't find this in the provided documents."
Always cite which document and section/page the information came from.

Context:
{context}

Question: {question}

Answer (with citations):"""
    )

    def format_docs(docs):
        return "\n\n".join(
            f"[Source: {d.metadata.get('source','?')}, "
            f"Page/Record: {d.metadata.get('page', d.metadata.get('record_index', d.metadata.get('section', 'N/A')))}]\n"
            f"{d.page_content}"
            for d in docs
        )

    try:
        llm = get_llm(model=req.model, temperature=req.temperature)
    except RuntimeError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    try:
        answer = rag_chain.invoke(req.question)
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    latency_ms = round((time.time() - t0) * 1000, 1)

    sources = [
        {
            "source": d.metadata.get("source", "Unknown"),
            "page": d.metadata.get("page", d.metadata.get("record_index", d.metadata.get("section", "N/A"))),
            "preview": d.page_content[:300],
        }
        for d in source_docs
    ]

    return QueryResponse(
        question=req.question,
        answer=answer,
        sources=sources,
        latency_ms=latency_ms,
    )


@app.delete("/reset")
def reset_knowledge_base():
    """Clear the entire vector store and document registry."""
    global _vector_store, ingested_docs
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True)
    _vector_store = None
    ingested_docs = []
    return {"message": "Knowledge base reset successfully."}
