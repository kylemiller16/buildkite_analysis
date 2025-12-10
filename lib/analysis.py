import datetime as dt
import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

try:
    from .util import BuildkiteConfig
except ImportError:
    # Fallback for direct imports (standalone execution)
    from util import BuildkiteConfig


def _parse_iso8601(ts: Optional[str]) -> Optional[dt.datetime]:
    if not ts:
        return None
    try:
        # Buildkite uses Z suffix; Python accepts +00:00
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _iter_cached_build_files() -> Iterable[Path]:
    cache_dir = Path(BuildkiteConfig.BUILD_METADATA_DIR)
    if not cache_dir.exists():
        return []
    return (p for p in cache_dir.iterdir() if p.is_file() and p.suffix == ".json")


def _load_jobs_from_build_file(path: Path) -> List[Dict[str, Any]]:
    """
    Load a single build metadata file and flatten its jobs into a list of job records
    with helpful build/pipeline context fields.
    """
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    jobs: List[Dict[str, Any]] = []
    build_number = content.get("number")
    pipeline = content.get("pipeline") or {}
    pipeline_slug = pipeline.get("slug")
    build_created_at = _parse_iso8601(content.get("created_at"))
    build_finished_at = _parse_iso8601(content.get("finished_at"))
    build_branch = content.get("branch")

    for job in content.get("jobs") or []:
        record: Dict[str, Any] = {
            "pipeline_slug": pipeline_slug,
            "build_number": build_number,
            "build_created_at": build_created_at,
            "build_finished_at": build_finished_at,
            "build_branch": build_branch,
            "job": job,
            "job_started_at": _parse_iso8601(job.get("started_at")),
            "job_finished_at": _parse_iso8601(job.get("finished_at")),
        }
        jobs.append(record)
    return jobs


def filter_cached_jobs(
    filter_callbacks: List[Callable[[Dict[str, Any]], bool]],
    *,
    started_from: Optional[dt.datetime] = None,
    started_to: Optional[dt.datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Iterate through all cached build metadata files and produce a list of job records
    filtered by a time window and a sequence of filter callbacks.

    Filtering flow:
    1) Load all jobs from all cached build files
    2) Apply a built-in timestamp filter using job.started_at within [started_from, started_to]
    3) Apply each callback in order, removing any jobs for which the callback returns False

    Each job record has keys:
    - pipeline_slug: str | None
    - build_number: int | None
    - build_created_at: datetime | None
    - build_finished_at: datetime | None
    - build_branch: str | None
    - job: dict (original Buildkite job payload)
    - job_started_at: datetime | None
    - job_finished_at: datetime | None
    """
    # Step 1: load all jobs
    jobs: List[Dict[str, Any]] = []
    for file_path in _iter_cached_build_files():
        jobs.extend(_load_jobs_from_build_file(Path(file_path)))

    # Step 2: built-in timestamp filter on job start time
    if started_from or started_to:
        filtered_by_time: List[Dict[str, Any]] = []
        for rec in jobs:
            js = rec.get("job_started_at")
            if started_from and (js is None or js < started_from):
                continue
            if started_to and (js is None or js > started_to):
                continue
            filtered_by_time.append(rec)
        jobs = filtered_by_time

    # Step 3: sequentially apply provided callbacks
    for predicate in filter_callbacks or []:
        remaining: List[Dict[str, Any]] = []
        for rec in jobs:
            try:
                if predicate(rec):
                    remaining.append(rec)
            except Exception:
                # Defensive: if a predicate raises, treat as non-match
                continue
        jobs = remaining

    return jobs
