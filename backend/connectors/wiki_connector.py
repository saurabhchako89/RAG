import logging
import os

from langchain.schema import Document

logger = logging.getLogger(__name__)

CONNECTOR_ID = "wiki"


class WikiConnector:

    def __init__(self):
        self.token        = os.getenv("NOTION_TOKEN", "")
        self.database_ids = [d.strip() for d in os.getenv("NOTION_DATABASE_IDS", "").split(",") if d.strip()]

    def health(self) -> dict:
        if not self.token:
            return {"status": "not_configured"}
        try:
            from notion_client import Client
            Client(auth=self.token).users.me()
            return {"status": "ok", "databases": len(self.database_ids)}
        except Exception as e:
            return {"status": "auth_error", "detail": str(e)}

    def refresh(self) -> list[Document]:
        if not self.token or not self.database_ids:
            logger.warning("Wiki connector not configured (NOTION_TOKEN / NOTION_DATABASE_IDS missing)")
            return []

        try:
            from notion_client import Client
        except ImportError:
            logger.error("notion-client not installed. Add notion-client to requirements.txt")
            return []

        client = Client(auth=self.token)
        docs: list[Document] = []

        for db_id in self.database_ids:
            try:
                pages = client.databases.query(database_id=db_id).get("results", [])
                for page in pages:
                    content = self._extract_content(client, page["id"])
                    title   = self._extract_title(page)
                    if content.strip():
                        docs.append(Document(
                            page_content=content,
                            metadata={
                                "source":      "notion",
                                "page_id":     page["id"],
                                "title":       title,
                                "last_edited": page.get("last_edited_time", ""),
                            },
                        ))
            except Exception as e:
                logger.error("Notion sync failed for db %s: %s", db_id, e)

        logger.info("Wiki connector: %d pages synced", len(docs))
        return docs

    # ── private ──────────────────────────────────────────────────────────────

    def _extract_content(self, client, page_id: str) -> str:
        blocks = client.blocks.children.list(block_id=page_id).get("results", [])
        texts  = []
        for block in blocks:
            btype = block.get("type", "")
            inner = block.get(btype, {})
            for rt in inner.get("rich_text", []):
                texts.append(rt.get("plain_text", ""))
        return "\n".join(texts)

    def _extract_title(self, page: dict) -> str:
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title" and prop.get("title"):
                return prop["title"][0].get("plain_text", "Untitled")
        return "Untitled"
