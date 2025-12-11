"""Download raw logs for validation jobs from multiple Buildkite pipelines."""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Dict

import requests

# Add lib directory to path for standalone execution
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from cache import get_http_cache_metrics
from util import (
    BuildkiteConfig,
    get_build_metadata,
    list_finished_builds_for_pipeline,
)


def _auth_headers() -> Dict[str, str]:
    """Get authentication headers for Buildkite API requests."""
    return {
        "Authorization": f"Bearer {BuildkiteConfig.load_token()}",
        "Accept": "text/plain",
    }


def download_job_log(url: str, output_path: str) -> None:
    """Download a job log from the given URL and save it to the output path."""
    headers = _auth_headers()
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    # Ensure parent directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Write to temporary file first, then rename atomically
    tmp_path = f"{output_path}.tmp"
    with open(tmp_path, "wb") as f:
        f.write(response.content)
    os.replace(tmp_path, output_path)


def download_job_logs_for_build(
    org_slug: str, pipeline_slug: str, build_number: int, metadata_dir: str
) -> int:
    """Download job logs for validation jobs in a build. Returns count of downloaded logs."""
    # Get the metadata file path (this will fetch and cache if needed)
    metadata_path = get_build_metadata(org_slug, pipeline_slug, build_number)

    # Load the metadata JSON
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load metadata for build {build_number}: {e}")
        return 0

    # Find validation jobs and download their logs
    validation_jobs = []
    for job in metadata.get("jobs", []):
        job_name = job.get("name", "")
        if "validation" in job_name.lower() and "raw_log_url" in job:
            validation_jobs.append(job)

    if not validation_jobs:
        return 0

    # Determine output directory (use provided metadata_dir or same directory as metadata file)
    if metadata_dir:
        output_dir = metadata_dir
    else:
        output_dir = os.path.dirname(metadata_path)

    metadata_basename = os.path.splitext(os.path.basename(metadata_path))[0]

    downloaded_count = 0
    for job in validation_jobs:
        job_name = job.get("name", "")
        job_id = job.get("id", "unknown")
        raw_log_url = job.get("raw_log_url")

        if not raw_log_url:
            continue

        # Create a safe filename from the job name and ID
        safe_job_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in job_name)
        output_filename = f"{metadata_basename}__{job_id}__{safe_job_name}.log"
        output_path = os.path.join(output_dir, output_filename)

        # Skip if already downloaded
        if os.path.exists(output_path):
            continue

        try:
            download_job_log(raw_log_url, output_path)
            downloaded_count += 1
        except Exception as e:
            print(f"Error downloading log for '{job_name}' in build {build_number}: {e}")

    return downloaded_count


def filter_builds_by_branch(
    builds: list, branch: str = None, exclude_branches: list = None
) -> list:
    """Filter builds by branch criteria."""
    if not branch and not exclude_branches:
        return builds

    filtered = []
    exclude_set = set(exclude_branches) if exclude_branches else set()

    for build in builds:
        build_branch = build.get("branch")
        if not isinstance(build_branch, str):
            # Skip builds without valid branch info
            continue

        # Apply exclude filter
        if build_branch in exclude_set:
            continue

        # Apply include filter
        if branch:
            if branch == "non-main":
                if build_branch == "main":
                    continue
            else:
                if build_branch != branch:
                    continue

        filtered.append(build)

    return filtered


def main() -> None:
    """Main entry point for downloading job logs for pipelines."""
    parser = argparse.ArgumentParser(
        description="Download raw logs for validation jobs from all finished builds across pipelines in the last N days",
    )
    parser.add_argument("--org", default=BuildkiteConfig.ORG_SLUG, help="Buildkite organization slug")
    parser.add_argument(
        "--pipeline",
        action="append",
        required=True,
        help="Pipeline slug(s). Repeat flag to include multiple",
    )
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    parser.add_argument(
        "--branch",
        help='Only include builds on this branch. Use "non-main" to filter for all non-main branches (optional)',
    )
    parser.add_argument(
        "--exclude-branch",
        action="append",
        help="Exclude builds on these branches. Can be specified multiple times (optional)",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory to save job logs (default: same as build metadata cache directory)",
    )

    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    created_from = now - dt.timedelta(days=args.days)

    total_downloaded = 0
    total_builds_processed = 0
    total_builds_with_jobs = 0

    for pipeline_slug in args.pipeline:
        print(f"\nProcessing pipeline: {pipeline_slug}")
        builds = list_finished_builds_for_pipeline(
            org_slug=args.org,
            pipeline_slug=pipeline_slug,
            created_from=created_from,
            created_to=now,
            include_retried_jobs=True,
        )
        print(f"Found {len(builds)} finished build(s)")

        # Filter by branch if specified
        if args.branch or args.exclude_branch:
            builds = filter_builds_by_branch(builds, args.branch, args.exclude_branch)
            branch_filter_desc = []
            if args.branch:
                branch_filter_desc.append(f"branch={args.branch}")
            if args.exclude_branch:
                branch_filter_desc.append(f"exclude={','.join(args.exclude_branch)}")
            print(f"After branch filtering ({', '.join(branch_filter_desc)}): {len(builds)} build(s)")

        pipeline_downloaded = 0
        for b in builds:
            number = b.get("number")
            if number is None:
                continue

            total_builds_processed += 1
            downloaded = download_job_logs_for_build(
                args.org, pipeline_slug, int(number), args.output_dir
            )
            if downloaded > 0:
                total_builds_with_jobs += 1
                pipeline_downloaded += downloaded
                total_downloaded += downloaded

        print(f"Downloaded {pipeline_downloaded} job log(s) for pipeline {pipeline_slug}")

    output_location = args.output_dir if args.output_dir else BuildkiteConfig.BUILD_METADATA_DIR
    print(f"\n{'='*60}")
    print(f"Job logs directory: {os.path.abspath(output_location)}")
    print(f"Processed {total_builds_processed} build(s) across {len(args.pipeline)} pipeline(s)")
    print(f"Found validation jobs in {total_builds_with_jobs} build(s)")
    print(f"Downloaded {total_downloaded} job log(s) total")
    metrics = get_http_cache_metrics()
    print(f"Requests made: {metrics['requests_made']} | Cache hits: {metrics['cache_hits']}")


if __name__ == "__main__":
    main()

()

