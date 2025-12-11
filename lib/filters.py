"""Filter functions for Buildkite job records."""

from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo


def build_pipeline_filter(allowed_pipelines: List[str]) -> Callable[[Dict[str, Any]], bool]:
    """Keep jobs whose pipeline slug is in the provided list."""
    allowed = set(allowed_pipelines)

    def predicate(record: Dict[str, Any]) -> bool:
        return record.get("pipeline_slug") in allowed

    return predicate


def build_job_name_filter(job_names: List[str]) -> Callable[[Dict[str, Any]], bool]:
    """Keep jobs whose name contains any of the given substrings (case-sensitive)."""

    def predicate(record: Dict[str, Any]) -> bool:
        job = record.get("job") or {}
        name = job.get("name")
        if not isinstance(name, str):
            return False
        return any(job_name in name for job_name in job_names)

    return predicate


def build_pst_time_of_day_filter(
    start_hour_inclusive: int, end_hour_inclusive: int
) -> Callable[[Dict[str, Any]], bool]:
    """Keep jobs that started within [start_hour, end_hour] PST (0-23)."""
    tz = ZoneInfo("America/Los_Angeles")

    def predicate(record: Dict[str, Any]) -> bool:
        started = record.get("job_started_at")
        if not started:
            return False
        local = started.astimezone(tz)
        hour = local.hour
        return start_hour_inclusive <= hour <= end_hour_inclusive

    return predicate


def build_branch_filter(branch_name: str) -> Callable[[Dict[str, Any]], bool]:
    """Keep jobs whose build branch matches the given branch name (case-sensitive).

    Special values:
    - "non-main": Keep jobs from all branches except "main"
    """

    def predicate(record: Dict[str, Any]) -> bool:
        build_branch = record.get("build_branch")
        if not isinstance(build_branch, str):
            return False

        if branch_name == "non-main":
            return build_branch != "main"
        return build_branch == branch_name

    return predicate


def build_exclude_branch_filter(excluded_branches: List[str]) -> Callable[[Dict[str, Any]], bool]:
    """Exclude jobs whose build branch is in the provided list (case-sensitive)."""
    excluded = set(excluded_branches)

    def predicate(record: Dict[str, Any]) -> bool:
        build_branch = record.get("build_branch")
        if not isinstance(build_branch, str):
            return True  # Keep records without valid branch info
        return build_branch not in excluded

    return predicate
