"""Save Buildkite build metadata for multiple pipelines to cached JSON files."""

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

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
    """Main entry point for saving build metadata for pipelines."""
    parser = argparse.ArgumentParser(
        description="Save Buildkite build metadata for all finished builds across pipelines in the last N days",
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

    args = parser.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    created_from = now - dt.timedelta(days=args.days)

    total_saved = 0
    for pipeline_slug in args.pipeline:
        builds = list_finished_builds_for_pipeline(
            org_slug=args.org,
            pipeline_slug=pipeline_slug,
            created_from=created_from,
            created_to=now,
            include_retried_jobs=True,
        )
        print(f"Found {len(builds)} finished build(s) for pipeline {pipeline_slug}")

        # Filter by branch if specified
        if args.branch or args.exclude_branch:
            builds = filter_builds_by_branch(builds, args.branch, args.exclude_branch)
            branch_filter_desc = []
            if args.branch:
                branch_filter_desc.append(f"branch={args.branch}")
            if args.exclude_branch:
                branch_filter_desc.append(f"exclude={','.join(args.exclude_branch)}")
            print(f"After branch filtering ({', '.join(branch_filter_desc)}): {len(builds)} build(s)")

        for b in builds:
            number = b.get("number")
            if number is None:
                continue
            get_build_metadata(args.org, pipeline_slug, int(number))
            total_saved += 1

    print(f"Metadata directory: {os.path.abspath(BuildkiteConfig.BUILD_METADATA_DIR)}")
    print(f"Saved metadata for {total_saved} build(s) across {len(args.pipeline)} pipeline(s)")
    metrics = get_http_cache_metrics()
    print(f"Requests made: {metrics['requests_made']} | Cache hits: {metrics['cache_hits']}")


if __name__ == "__main__":
    main()
