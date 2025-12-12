"""Utility functions for Buildkite API access and configuration."""

import datetime as dt
import glob
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .cache import cached_json_get, increment_cache_hits
except ImportError:
    # Fallback for direct imports (standalone execution)
    from cache import cached_json_get, increment_cache_hits


def _compute_tool_root_dir() -> str:
    """Compute the root directory of the buildkite_analysis tool.

    Works both in Bazel (via BUILD_WORKSPACE_DIRECTORY) and standalone.
    """
    ws = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if ws:
        # Bazel environment: check if the old path structure exists
        old_path = os.path.join(ws, "wayve/robot/hil_tests/tools/buildkite_analysis")
        if os.path.exists(old_path):
            return old_path
        # Otherwise use workspace root
        return ws
    # Standalone: parent of lib/ → the buildkite_analysis package dir
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return str(Path(script_dir).resolve().parent)


class BuildkiteConfig:
    """Configuration for Buildkite API access."""

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
        """Load the Buildkite API token from the token file."""
        if not BuildkiteConfig.TOKEN_FILE.exists():
            raise FileNotFoundError(f"Token file not found: {BuildkiteConfig.TOKEN_FILE}")
        return BuildkiteConfig.TOKEN_FILE.read_text(encoding="utf-8").strip()


def _auth_headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {BuildkiteConfig.load_token()}",
        "Accept": "application/json",
    }


def get_build_metadata(
    org_slug: str, pipeline_slug: str, build_number: int, include_retried_jobs: bool = True
) -> str:
    """
    Fetch full build metadata from Buildkite and save to a JSON file.
    Acts as a cache: if the file already exists, returns it without an API call.

    Args:
        org_slug: Buildkite organization slug
        pipeline_slug: Pipeline slug
        build_number: Build number
        include_retried_jobs: If True, include retried jobs in the response (default: True)

    Returns:
        Absolute path to the saved JSON file.
    """
    os.makedirs(BuildkiteConfig.BUILD_METADATA_DIR, exist_ok=True)
    filename = f"{org_slug}__{pipeline_slug}__{build_number}.json"
    safe_filename = filename.replace("/", "_")
    out_path = os.path.join(BuildkiteConfig.BUILD_METADATA_DIR, safe_filename)

    if os.path.exists(out_path):
        # Treat as cache hit to reflect avoided network call
        increment_cache_hits()
        return out_path

    url = (
        f"{BuildkiteConfig.API_URL}/organizations/{org_slug}/"
        f"pipelines/{pipeline_slug}/builds/{build_number}"
    )
    params: Dict[str, str] = {}
    if include_retried_jobs:
        params["include_retried_jobs"] = "true"
    build_json: Dict[str, Any] = cached_json_get(url, headers=_auth_headers(), params=params if params else None)

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
        page_builds: List[Dict[str, Any]] = cached_json_get(
            url, headers=_auth_headers(), params=params
        )
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


def is_build_pass(build: Dict[str, Any]) -> bool:
    """Determine if a build passed."""
    state = build.get("state")
    if state == "passed":
        return True
    if state == "failed":
        return False
    # Fallback: check if all jobs passed
    jobs = build.get("jobs", [])
    if not jobs:
        return False
    for job in jobs:
        job_state = job.get("state")
        if job_state not in ("passed", "skipped", "canceled"):
            return False
    return True


def is_job_pass(job: Dict[str, Any]) -> bool:
    """Determine if a job passed."""
    state = job.get("state")
    if state == "passed":
        return True
    if state == "failed":
        return False
    # Fallback to exit_status when state is not explicit
    exit_status = job.get("exit_status")
    if isinstance(exit_status, int):
        return exit_status == 0
    return False


def find_log_file_for_job(metadata_path: str, job_id: str) -> Optional[str]:
    """Find the log file for a given job ID."""
    metadata_dir = os.path.dirname(metadata_path)
    metadata_basename = os.path.splitext(os.path.basename(metadata_path))[0]

    # Log files follow pattern: {metadata_basename}__{job_id}__*.log
    log_pattern = f"{metadata_basename}__{job_id}__*.log"

    matches = glob.glob(os.path.join(metadata_dir, log_pattern))
    if matches:
        return matches[0]  # Return first match
    return None


def analyze_bazel_targets_from_log(log_file_path: str, job_passed: bool) -> Dict[str, bool]:
    """
    Analyze a log file to extract Bazel target pass/fail information.

    Looks for lines matching:
    - "--- ⛰️  Running bazel-run step"
    - "--- 🏃 Running target //wayve/robot/hil_tests/gen2:<some-name>"

    Since bazel-run steps run sequentially, only the last one could have failed.
    If the job passed overall, all bazel-run steps passed.
    If the job failed, the last bazel-run step failed, and all previous ones passed.

    Args:
        log_file_path: Path to the log file
        job_passed: Whether the job passed overall

    Returns:
        Dictionary mapping target names to pass status (True = passed, False = failed)
        Example: {"//wayve/robot/hil_tests/gen2:target1": True, "//wayve/robot/hil_tests/gen2:target2": False}
    """
    target_results: Dict[str, bool] = {}

    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            log_content = f.read()
    except Exception:
        # If we can't read the file, return empty dict
        return {}

    # Pattern to match: "--- 🏃 Running target //wayve/robot/hil_tests/gen2:<some-name>"
    # The target name is captured in group 1
    target_pattern = r"--- 🏃 Running target (//wayve/robot/hil_tests/gen2:[^\s]+)"

    # Find all target runs in the log
    matches = re.findall(target_pattern, log_content)

    if not matches:
        return {}

    # If job passed, all targets passed
    if job_passed:
        for target in matches:
            target_results[target] = True
    else:
        # If job failed, last target failed, all previous passed
        for i, target in enumerate(matches):
            if i == len(matches) - 1:
                # Last target failed
                target_results[target] = False
            else:
                # Previous targets passed
                target_results[target] = True

    return target_results


def get_all_job_ids(build: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract all job IDs from a build metadata dictionary.

    Args:
        build: Build metadata dictionary from Buildkite API

    Returns:
        List of dictionaries, each containing:
        - job_name: str - The name of the job
        - job_id: str - The unique ID of the job
        - retry: bool - True if this job is a retry, False otherwise
    """
    jobs = build.get("jobs", [])
    result = []

    for job in jobs:
        job_name = job.get("name", "")
        job_id = job.get("id", "")
        retry_source = job.get("retry_source")
        is_retry = retry_source is not None
        raw_log_url = job.get("raw_log_url")

        if job_id:  # Only include jobs with valid IDs
            result.append({
                "job_name": job_name,
                "job_id": job_id,
                "retry": is_retry,
                "raw_log_url": raw_log_url,
            })

    return result


class Build:
    pass

    def __init__(self, metadata_path: str):
        self.metadata_path = metadata_path
        self.metadata = json.load(open(metadata_path, "r", encoding="utf-8"))
        self.number = self.metadata.get("number")
        self.pipeline = self.metadata.get("pipeline")
        self.branch = self.metadata.get("branch")
        self.created_at = self.metadata.get("created_at")
        self.finished_at = self.metadata.get("finished_at")
        self.jobs = self.metadata.get("jobs")

class Job:
    pass
