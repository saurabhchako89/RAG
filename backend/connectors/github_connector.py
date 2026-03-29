import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path

from langchain.schema import Document

logger = logging.getLogger(__name__)

REPO_DIR = Path("data/repos")
SUPPORTED_EXT = {".py", ".md", ".ts", ".js", ".yaml", ".yml", ".json", ".txt", ".go", ".rs", ".java"}
SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "dist", "build"}

CONNECTOR_ID = "github"


class GitHubConnector:

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.repos = [r.strip() for r in os.getenv("GITHUB_REPOS", "").split(",") if r.strip()]

    def health(self) -> dict:
        return {
            "status": "ok" if self.token and self.repos else "not_configured",
            "repos":  self.repos,
        }

    def refresh(self) -> list[Document]:
        if not self.token or not self.repos:
            logger.warning("GitHub connector not configured (GITHUB_TOKEN / GITHUB_REPOS missing)")
            return []

        REPO_DIR.mkdir(parents=True, exist_ok=True)
        docs: list[Document] = []
        for repo in self.repos:
            repo_path = REPO_DIR / repo.replace("/", "_")
            try:
                self._clone_or_fetch(repo, repo_path)
                docs.extend(self._read_files(repo_path, repo))
            except Exception as e:
                logger.error("GitHub sync failed for %s: %s", repo, e)
        return docs

    # ── private ──────────────────────────────────────────────────────────────

    def _clone_or_fetch(self, repo: str, path: Path):
        url = f"https://{self.token}@github.com/{repo}.git"
        if path.exists():
            subprocess.run(["git", "-C", str(path), "fetch", "--depth=1"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(path), "reset", "--hard", "origin/HEAD"], check=True, capture_output=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--depth=1", url, str(path)], check=True, capture_output=True)

    def _read_files(self, repo_path: Path, repo: str) -> list[Document]:
        hash_file  = repo_path / ".rag_hashes"
        old_hashes = json.loads(hash_file.read_text()) if hash_file.exists() else {}
        new_hashes: dict[str, str] = {}
        docs: list[Document] = []

        for f in repo_path.rglob("*"):
            if not f.is_file():
                continue
            if f.suffix not in SUPPORTED_EXT:
                continue
            if any(part in SKIP_DIRS for part in f.parts):
                continue

            try:
                content = f.read_text(errors="ignore")
            except Exception:
                continue

            rel_path  = str(f.relative_to(repo_path))
            file_hash = hashlib.md5(content.encode()).hexdigest()
            new_hashes[rel_path] = file_hash

            if old_hashes.get(rel_path) == file_hash:
                continue  # unchanged

            docs.append(Document(
                page_content=content,
                metadata={"source": repo, "path": rel_path, "language": f.suffix.lstrip(".")},
            ))

        hash_file.write_text(json.dumps(new_hashes))
        logger.info("GitHub %s: %d changed files", repo, len(docs))
        return docs
