import io
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Optional

import oci
from langchain.schema import Document
from langchain_community.document_loaders import PyPDFLoader

from ingestion.chunker import json_to_documents

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OCI_BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "")
OCI_NAMESPACE   = os.getenv("OCI_NAMESPACE", "")
OCI_USE_INSTANCE_PRINCIPAL = os.getenv("OCI_USE_INSTANCE_PRINCIPAL", "false").lower() == "true"


def _secure_filename(filename: str) -> str:
    filename = os.path.basename(filename)
    filename = re.sub(r"[^\w\s\-.]", "", filename).strip()
    return filename or "upload"


def _oci_client() -> Optional[oci.object_storage.ObjectStorageClient]:
    if not OCI_BUCKET_NAME:
        return None
    try:
        if OCI_USE_INSTANCE_PRINCIPAL:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            return oci.object_storage.ObjectStorageClient({}, signer=signer)
        config = oci.config.from_file()
        return oci.object_storage.ObjectStorageClient(config)
    except Exception as e:
        logger.warning("OCI client init failed, falling back to local: %s", e)
        return None


def _oci_namespace(client) -> str:
    return OCI_NAMESPACE or client.get_namespace().data


class FilesConnector:
    CONNECTOR_ID = "files"

    def health(self) -> dict:
        return {
            "status": "ok",
            "storage": "oci" if OCI_BUCKET_NAME else "local",
        }

    def ingest(self, filename: str, raw_bytes: bytes) -> tuple[list[Document], dict]:
        """
        Store file (OCI or local) and return (docs, record_meta).
        Caller is responsible for chunking and vector store insertion.
        """
        safe_name   = _secure_filename(filename)
        suffix      = Path(safe_name).suffix.lower()
        if suffix not in (".pdf", ".json"):
            raise ValueError("Only PDF and JSON files are supported.")

        file_id     = str(uuid.uuid4())[:8]
        object_name = f"uploads/{file_id}_{safe_name}"
        oci_client  = _oci_client()

        if oci_client:
            namespace    = _oci_namespace(oci_client)
            content_type = "application/pdf" if suffix == ".pdf" else "application/json"
            oci_client.put_object(
                namespace_name=namespace,
                bucket_name=OCI_BUCKET_NAME,
                object_name=object_name,
                put_object_body=io.BytesIO(raw_bytes),
                content_type=content_type,
            )
            logger.info("Uploaded to OCI: %s", object_name)

        # Write temp file for PDF loader (needs a path)
        save_path = UPLOAD_DIR / f"{file_id}_{safe_name}"
        save_path.write_bytes(raw_bytes)

        try:
            if suffix == ".pdf":
                docs = PyPDFLoader(str(save_path)).load()
            else:
                data = json.loads(raw_bytes.decode("utf-8"))
                docs = json_to_documents(data, source=safe_name)
        finally:
            if oci_client and save_path.exists():
                save_path.unlink()

        record = {
            "id":               file_id,
            "filename":         safe_name,
            "connector_id":     self.CONNECTOR_ID,
            "type":             suffix.lstrip("."),
            "pages_or_records": len(docs),
            "chunks":           0,   # filled in by caller after chunking
            "storage":          "oci" if oci_client else "local",
            "object_name":      object_name if oci_client else None,
        }
        return docs, record
