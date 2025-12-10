import datetime as dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .cache import cached_json_get, increment_cache_hits


def _compute_tool_root_dir() -> str:
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if ws:
        return os.path.join(ws, "wayve/robot/hil_tests/tools/buildkite_analysis")
    # Fallback: parent of lib/ → the buildkite_analysis package dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return str(Path(script_dir).resolve().parent)


class BuildkiteConfig:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    TOKEN_FILE = Path.home() / ".buildkite_token"
    ORG_SLUG = "wayve-dot-ai"
    API_URL = "https://api.buildkite.com/v2"

    # Prefer saving artifacts inside the local repository rather than Bazel runfiles.
    # Use BUILD_WORKSPACE_DIRECTORY when available (bazel run), otherwise fall back to this
    # package's directory (works outside Bazel too).
    BUILD_METADATA_DIR = os.path.join(_compute_tool_root_dir(), "build_metadata_cache")
    HTTP_CACHE_DIR = f"{script_dir}/../.http_cache"

    @staticmethod
    def load_token() -> str:
        if not BuildkiteConfig.TOKEN_FILE.exists():
            raise FileNotFoundError(f"Token file not found: {BuildkiteConfig.TOKEN_FILE}")
        return BuildkiteConfig.TOKEN_FILE.read_text(encoding="utf-8").strip()


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {BuildkiteConfig.load_token()}",
        "Accept": "application/json",
    }


def get_build_metadata(org_slug: str, pipeline_slug: str, build_number: int) -> str:
    """
    Fetch full build metadata from Buildkite and save to a JSON file.
    Acts as a cache: if the file already exists, returns it without an API call.

    Returns absolute path to the saved JSON file.
    """
    os.makedirs(BuildkiteConfig.BUILD_METADATA_DIR, exist_ok=True)
    filename = f"{org_slug}__{pipeline_slug}__{build_number}.json"
    safe_filename = filename.replace("/", "_")
    out_path = os.path.join(BuildkiteConfig.BUILD_METADATA_DIR, safe_filename)

    if os.path.exists(out_path):
        # Treat as cache hit to reflect avoided network call
        increment_cache_hits()
        return out_path

    url = f"{BuildkiteConfig.API_URL}/organizations/{org_slug}/pipelines/{pipeline_slug}/builds/{build_number}"
    build_json: Dict[str, Any] = cached_json_get(url, headers=_auth_headers(), params=None)

    tmp_path = f"{out_path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(build_json, f, indent=2, sort_keys=True)
    os.replace(tmp_path, out_path)
    return out_path


def _isoformat(dt_obj: dt.datetime) -> str:
    """Return ISO8601 with Z suffix, trimming microseconds."""
    return dt_obj.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def list_finished_builds_for_pipeline(
    org_slug: str,
    pipeline_slug: str,
    created_from: dt.datetime,
    created_to: Optional[dt.datetime] = None,
    include_retried_jobs: bool = True,
) -> List[Dict[str, Any]]:
    """
    List builds for a pipeline whose finished_at lies within [created_from, created_to].
    Falls back to client-side filtering for correctness and handles pagination.
    """
    url = f"{BuildkiteConfig.API_URL}/organizations/{org_slug}/pipelines/{pipeline_slug}/builds"
    params: Dict[str, str] = {"per_page": "100"}
    if include_retried_jobs:
        params["include_retried_jobs"] = "true"
    # Best-effort server-side created window; final filter done client-side by finished_at
    if created_from:
        params["created_from"] = _isoformat(created_from)
    if created_to:
        params["created_to"] = _isoformat(created_to)

    all_builds: List[Dict[str, Any]] = []
    page = 1
    while True:
        params["page"] = str(page)
        page_builds: List[Dict[str, Any]] = cached_json_get(url, headers=_auth_headers(), params=params)
        if not page_builds:
            break
        all_builds.extend(page_builds)

        # Early stop if last page item created before from-date
        last_created_at_str = page_builds[-1].get("created_at")
        if last_created_at_str:
            last_created_at = dt.datetime.fromisoformat(last_created_at_str.replace("Z", "+00:00"))
            if last_created_at < created_from:
                break
        page += 1

    # Client-side filter by finished_at window
    filtered: List[Dict[str, Any]] = []
    for b in all_builds:
        finished_at_str = b.get("finished_at")
        if not finished_at_str:
            continue
        finished_at = dt.datetime.fromisoformat(finished_at_str.replace("Z", "+00:00"))
        if finished_at < created_from:
            continue
        if created_to and finished_at > created_to:
            continue
        filtered.append(b)

    return filtered
    # cache helpers moved to cache.py
