from connectors.files_connector import FilesConnector
from connectors.github_connector import GitHubConnector
from connectors.wiki_connector import WikiConnector

_registry = {
    "files":  FilesConnector(),
    "github": GitHubConnector(),
    "wiki":   WikiConnector(),
}


def get(connector_id: str):
    return _registry[connector_id]


def all_connectors() -> dict:
    return _registry


def health_all() -> list[dict]:
    return [
        {"id": cid, "label": cid.capitalize(), **conn.health()}
        for cid, conn in _registry.items()
    ]
