import argparse
import os

from wayve.robot.hil_tests.tools.buildkite_analysis.lib.cache import get_http_cache_metrics
from wayve.robot.hil_tests.tools.buildkite_analysis.lib.util import BuildkiteConfig, get_build_metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Save Buildkite build metadata to a cached JSON file")
    parser.add_argument("--org", default=BuildkiteConfig.ORG_SLUG, help="Buildkite organization slug")
    parser.add_argument("--pipeline", required=True, help="Pipeline slug")
    parser.add_argument("--build", type=int, required=True, help="Build number")
    args = parser.parse_args()

    path = get_build_metadata(args.org, args.pipeline, args.build)
    print(f"Metadata directory: {os.path.abspath(BuildkiteConfig.BUILD_METADATA_DIR)}")
    print(path)
    metrics = get_http_cache_metrics()
    print(f"Requests made: {metrics['requests_made']} | Cache hits: {metrics['cache_hits']}")


if __name__ == "__main__":
    main()
