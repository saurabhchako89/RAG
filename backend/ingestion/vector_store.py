from pathlib import Path
from langchain_community.vectorstores import Chroma
from langchain.schema import Document

CHROMA_DIR = Path("data/chromadb")
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

_collections: dict[str, Chroma] = {}
_embeddings = None   # set by main.py after embeddings are initialised


def set_embeddings(emb):
    global _embeddings
    _embeddings = emb


def get_collection(connector_id: str) -> Chroma:
    if connector_id not in _collections:
        _collections[connector_id] = Chroma(
            collection_name=connector_id,
            persist_directory=str(CHROMA_DIR),
            embedding_function=_embeddings,
        )
    return _collections[connector_id]


def add_documents(docs: list[Document], connector_id: str) -> int:
    col = get_collection(connector_id)
    col.add_documents(docs)
    col.persist()
    return len(docs)


def query_all(question: str, top_k: int = 5) -> list[Document]:
    results: list[Document] = []
    for cid, col in _collections.items():
        hits = col.similarity_search(question, k=top_k)
        for doc in hits:
            doc.metadata["connector"] = cid
        results.extend(hits)
    return results


def query_collection(question: str, connector_id: str, top_k: int = 5) -> list[Document]:
    col = get_collection(connector_id)
    hits = col.similarity_search(question, k=top_k)
    for doc in hits:
        doc.metadata["connector"] = connector_id
    return hits


def reset_collection(connector_id: str):
    col = get_collection(connector_id)
    col.delete_collection()
    _collections.pop(connector_id, None)


def reset_all():
    import shutil
    if CHROMA_DIR.exists():
        shutil.rmtree(CHROMA_DIR)
    CHROMA_DIR.mkdir(parents=True)
    _collections.clear()
