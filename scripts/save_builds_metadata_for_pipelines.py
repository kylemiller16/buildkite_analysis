import argparse
import datetime as dt
import os

from wayve.robot.hil_tests.tools.buildkite_analysis.lib.cache import get_http_cache_metrics
from wayve.robot.hil_tests.tools.buildkite_analysis.lib.util import (
    BuildkiteConfig,
    get_build_metadata,
    list_finished_builds_for_pipeline,
)


def main() -> None:
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
