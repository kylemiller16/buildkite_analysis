"""Get the duration of a Buildkite job by job ID."""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Dict, Optional

# Add lib directory to path for standalone execution
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from util import BuildkiteConfig, get_build_metadata  # type: ignore  # noqa: E402


def _parse_iso8601(ts: Optional[str]) -> Optional[dt.datetime]:
    """Parse ISO8601 timestamp string to datetime."""
    if not ts:
        return None
    try:
        # Buildkite uses Z suffix; Python accepts +00:00
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS format."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def find_job_in_cached_builds(job_id: str) -> Optional[Dict]:
    """Search through cached build metadata files to find a job by ID."""
    cache_dir = Path(BuildkiteConfig.BUILD_METADATA_DIR)
    if not cache_dir.exists():
        return None

    for build_file in cache_dir.iterdir():
        if not build_file.is_file() or build_file.suffix != ".json":
            continue

        try:
            with open(build_file, "r", encoding="utf-8") as f:
                build_data = json.load(f)
        except Exception:
            continue

        jobs = build_data.get("jobs", [])
        for job in jobs:
            if job.get("id") == job_id:
                return job

    return None


def get_job_from_build(org_slug: str, pipeline_slug: str, build_number: int, job_id: str) -> Optional[Dict]:
    """Get a job from a specific build (from cache or API)."""
    metadata_path = get_build_metadata(org_slug, pipeline_slug, build_number)

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            build_data = json.load(f)
    except Exception:
        return None

    jobs = build_data.get("jobs", [])
    for job in jobs:
        if job.get("id") == job_id:
            return job

    return None


def calculate_job_duration(job: Dict) -> Optional[float]:
    """Calculate job duration in seconds from started_at and finished_at."""
    started_at_str = job.get("started_at")
    finished_at_str = job.get("finished_at")

    if not started_at_str or not finished_at_str:
        return None

    started_at = _parse_iso8601(started_at_str)
    finished_at = _parse_iso8601(finished_at_str)

    if not started_at or not finished_at:
        return None

    duration = (finished_at - started_at).total_seconds()
    return max(0.0, duration)


def main() -> None:
    """Main entry point for getting job duration."""
    parser = argparse.ArgumentParser(description="Get the duration of a Buildkite job by job ID")
    parser.add_argument("job_id", help="Buildkite job ID")
    parser.add_argument("--org", default=BuildkiteConfig.ORG_SLUG, help="Buildkite organization slug (optional, for direct fetch)")
    parser.add_argument("--pipeline", help="Pipeline slug (optional, for direct fetch)")
    parser.add_argument("--build", type=int, help="Build number (optional, for direct fetch)")
    args = parser.parse_args()

    job: Optional[Dict] = None

    # If org, pipeline, and build are provided, try to fetch directly
    if args.pipeline and args.build:
        job = get_job_from_build(args.org, args.pipeline, args.build, args.job_id)
        if job:
            print(f"Found job in build {args.build} of pipeline {args.pipeline}")

    # Otherwise, search through cached builds
    if not job:
        job = find_job_in_cached_builds(args.job_id)
        if job:
            print(f"Found job in cached build metadata")

    if not job:
        print(f"Error: Job with ID '{args.job_id}' not found")
        if not args.pipeline or not args.build:
            print("Hint: Try providing --pipeline and --build to fetch from API")
        sys.exit(1)

    # Get job information
    job_name = job.get("name", "unknown")
    job_state = job.get("state", "unknown")
    started_at_str = job.get("started_at")
    finished_at_str = job.get("finished_at")

    print(f"\nJob Information:")
    print(f"  Name: {job_name}")
    print(f"  State: {job_state}")
    print(f"  Started at: {started_at_str}")
    print(f"  Finished at: {finished_at_str}")

    # Calculate duration
    duration_seconds = calculate_job_duration(job)

    if duration_seconds is None:
        print(f"\nDuration: Unable to calculate (missing started_at or finished_at)")
        sys.exit(1)

    duration_formatted = _format_duration(duration_seconds)
    print(f"\nDuration: {duration_seconds:.2f} seconds ({duration_formatted})")


if __name__ == "__main__":
    main()
