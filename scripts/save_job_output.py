import argparse
import json
import os
from typing import Dict

import requests

from wayve.robot.hil_tests.tools.buildkite_analysis.lib.cache import get_http_cache_metrics
from wayve.robot.hil_tests.tools.buildkite_analysis.lib.util import BuildkiteConfig, get_build_metadata


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Download raw logs for validation jobs from Buildkite build metadata")
    parser.add_argument("--org", default=BuildkiteConfig.ORG_SLUG, help="Buildkite organization slug")
    parser.add_argument("--pipeline", required=True, help="Pipeline slug")
    parser.add_argument("--build", type=int, required=True, help="Build number")
    args = parser.parse_args()

    # Get the metadata file path
    metadata_path = get_build_metadata(args.org, args.pipeline, args.build)

    # Load the metadata JSON
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Find validation jobs and download their logs
    validation_jobs = []
    for job in metadata.get("jobs", []):
        job_name = job.get("name", "")
        if "validation" in job_name.lower() and "raw_log_url" in job:
            validation_jobs.append(job)

    if not validation_jobs:
        print(f"No validation jobs found in build {args.build}")
        return

    # Determine output directory (same directory as metadata file)
    metadata_dir = os.path.dirname(metadata_path)
    metadata_basename = os.path.splitext(os.path.basename(metadata_path))[0]

    downloaded_count = 0
    for job in validation_jobs:
        job_name = job.get("name", "")
        job_id = job.get("id", "unknown")
        raw_log_url = job.get("raw_log_url")

        if not raw_log_url:
            print(f"Warning: Job '{job_name}' (id: {job_id}) has no raw_log_url, skipping")
            continue

        # Create a safe filename from the job name and ID
        safe_job_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in job_name)
        output_filename = f"{metadata_basename}__{job_id}__{safe_job_name}.log"
        output_path = os.path.join(metadata_dir, output_filename)

        # Skip if already downloaded
        if os.path.exists(output_path):
            print(f"Skipping '{job_name}' - log already exists: {output_path}")
            continue

        try:
            print(f"Downloading log for '{job_name}'...")
            download_job_log(raw_log_url, output_path)
            print(f"Saved: {output_path}")
            downloaded_count += 1
        except Exception as e:
            print(f"Error downloading log for '{job_name}': {e}")

    print(f"\nDownloaded {downloaded_count} validation job log(s)")
    metrics = get_http_cache_metrics()
    print(f"Requests made: {metrics['requests_made']} | Cache hits: {metrics['cache_hits']}")


if __name__ == "__main__":
    main()

