from __future__ import annotations

from urllib.parse import urlsplit

from fastapi import Request


def normalize_path_prefix(path_prefix: str | None) -> str:
    if not path_prefix:
        return ""

    cleaned = path_prefix.strip()
    if not cleaned or cleaned == "/":
        return ""

    normalized = cleaned if cleaned.startswith("/") else f"/{cleaned}"
    normalized = normalized.rstrip("/")
    return "" if normalized == "/" else normalized


def public_path_prefix_from_base_url(public_base_url: str | None) -> str:
    if not public_base_url:
        return ""
    return normalize_path_prefix(urlsplit(public_base_url).path)


def build_app_path(root_path: str | None, path: str) -> str:
    normalized_root_path = normalize_path_prefix(root_path)
    normalized_path = path if path.startswith("/") else f"/{path}"
    return (
        f"{normalized_root_path}{normalized_path}"
        if normalized_root_path
        else normalized_path
    )


def build_request_app_path(request: Request, path: str) -> str:
    return build_app_path(request.scope.get("root_path"), path)


def path_has_prefix(path: str, path_prefix: str) -> bool:
    normalized_prefix = normalize_path_prefix(path_prefix)
    if not normalized_prefix:
        return False
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def strip_path_prefix(path: str, path_prefix: str) -> str:
    normalized_prefix = normalize_path_prefix(path_prefix)
    if not normalized_prefix or not path_has_prefix(path, normalized_prefix):
        return path

    trimmed = path[len(normalized_prefix) :]
    if not trimmed:
        return "/"
    return trimmed if trimmed.startswith("/") else f"/{trimmed}"
