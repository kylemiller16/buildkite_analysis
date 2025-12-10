import hashlib
import json
import os
from typing import Any, Dict, Optional

import requests

# Cache directory (local to this toolset)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# Use absolute path to avoid issues with working directory
_HTTP_CACHE_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), ".http_cache")

# Simple counters for observability
_COUNTERS: Dict[str, int] = {"requests_made": 0, "cache_hits": 0}
_DEFAULT_TIMEOUT_SECONDS = 30


def _ensure_http_cache_dir() -> None:
    os.makedirs(_HTTP_CACHE_DIR, exist_ok=True)


def _canonicalize_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not params:
        return {}
    return {k: params[k] for k in sorted(params.keys())}


def _cache_key(url: str, params: Optional[Dict[str, Any]]) -> str:
    key_obj = {"url": url, "params": _canonicalize_params(params)}
    raw = json.dumps(key_obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _cache_path(url: str, params: Optional[Dict[str, Any]]) -> str:
    return os.path.join(_HTTP_CACHE_DIR, f"{_cache_key(url, params)}.json")


def increment_cache_hits() -> None:
    _COUNTERS["cache_hits"] += 1


def cached_json_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = _DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    """
    Fetch JSON with persistent on-disk caching. Updates request/cache counters.
    """
    _ensure_http_cache_dir()
    path = _cache_path(url, params)
    if os.path.exists(path):
        increment_cache_hits()
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    _COUNTERS["requests_made"] += 1
    resp = requests.get(url, headers=headers, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp_path, path)
    return data


def get_http_cache_metrics() -> Dict[str, int]:
    return dict(_COUNTERS)
