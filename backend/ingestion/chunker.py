from langchain.schema import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import json

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n", "\n", " ", ""],
)


def chunk_documents(docs: list[Document]) -> list[Document]:
    return _splitter.split_documents(docs)


def json_to_documents(data: dict | list, source: str) -> list[Document]:
    docs = []

    def _flatten(obj, prefix="") -> str:
        if isinstance(obj, dict):
            return "\n".join(f"{prefix}{k}: {_flatten(v, prefix='  ')}" for k, v in obj.items())
        elif isinstance(obj, list):
            return "\n".join(f"[{i}] {_flatten(item)}" for i, item in enumerate(obj))
        return str(obj)

    if isinstance(data, list):
        for i, item in enumerate(data):
            docs.append(Document(page_content=_flatten(item), metadata={"source": source, "record_index": i}))
    elif isinstance(data, dict):
        for key, value in data.items():
            docs.append(Document(page_content=f"{key}:\n{_flatten(value)}", metadata={"source": source, "section": key}))
    else:
        docs.append(Document(page_content=str(data), metadata={"source": source}))

    return docs
