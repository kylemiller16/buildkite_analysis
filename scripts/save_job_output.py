"""Download raw logs for validation jobs from Buildkite build metadata."""

import argparse
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

from cache import get_http_cache_metrics  # type: ignore  # noqa: E402
from util import BuildkiteConfig, get_build_metadata  # type: ignore  # noqa: E402


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
    """Main entry point for downloading job logs."""
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

    # Find validation jobs and retried jobs to download their logs
    jobs_to_download = []
    jobs_by_id = {}
    validation_job_ids = set()
    
    # First pass: collect all jobs and index by ID, identify validation jobs
    for job in metadata.get("jobs", []):
        job_id = job.get("id")
        if job_id:
            jobs_by_id[job_id] = job
            job_name = job.get("name", "")
            if "validation" in job_name.lower():
                validation_job_ids.add(job_id)
    
    def is_validation_job_or_retry(job_id: str, visited: set = None) -> bool:
        """
        Recursively check if a job is a validation job or a retry of one.
        
        Note: When include_retried_jobs=True, Buildkite only includes retry jobs
        in the metadata, not the original jobs. So original_job_id may not be
        in jobs_by_id, and we return False in that case (can't verify it's a validation job).
        """
        if visited is None:
            visited = set()
        
        if job_id in visited:
            return False  # Prevent infinite loops
        visited.add(job_id)
        
        if job_id in validation_job_ids:
            return True
        
        job = jobs_by_id.get(job_id)
        if not job:
            # Original job not in metadata (common when include_retried_jobs=True)
            # We can't verify if it's a validation job, so return False
            return False
        
        retry_source = job.get("retry_source")
        if retry_source and isinstance(retry_source, dict):
            original_job_id = retry_source.get("job_id")
            if original_job_id:
                return is_validation_job_or_retry(original_job_id, visited)
        
        return False
    
    # Second pass: find validation jobs and all retries in their chain
    for job in metadata.get("jobs", []):
        job_id = job.get("id")
        job_name = job.get("name", "")
        retry_source = job.get("retry_source")
        
        # Include validation jobs (only if they have raw_log_url)
        if "validation" in job_name.lower() and "raw_log_url" in job:
            if job not in jobs_to_download:
                jobs_to_download.append(job)
        
        # Include retried jobs (check recursively if any ancestor is a validation job)
        # Note: When include_retried_jobs=True, Buildkite only includes retry jobs in metadata,
        # not the original jobs. So we can only download logs for retries that are present.
        if retry_source and "raw_log_url" in job:
            if is_validation_job_or_retry(job_id):
                if job not in jobs_to_download:
                    jobs_to_download.append(job)

    if not jobs_to_download:
        print(f"No validation jobs or retries found in build {args.build}")
        return

    # Determine output directory (same directory as metadata file)
    metadata_dir = os.path.dirname(metadata_path)
    metadata_basename = os.path.splitext(os.path.basename(metadata_path))[0]

    downloaded_count = 0
    for job in jobs_to_download:
        job_name = job.get("name", "")
        job_id = job.get("id", "unknown")
        raw_log_url = job.get("raw_log_url")
        retry_source = job.get("retry_source")
        is_retry = retry_source is not None

        if not raw_log_url:
            print(f"Warning: Job '{job_name}' (id: {job_id}) has no raw_log_url, skipping")
            continue

        # Create a safe filename from the job name and ID
        safe_job_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in job_name)
        retry_suffix = ""
        if is_retry:
            retry_type = retry_source.get("retry_type", "retry") if isinstance(retry_source, dict) else "retry"
            retry_suffix = f"__{retry_type}"
        output_filename = f"{metadata_basename}__{job_id}__{safe_job_name}{retry_suffix}.log"
        output_path = os.path.join(metadata_dir, output_filename)

        # Skip if already downloaded
        if os.path.exists(output_path):
            retry_label = " (retry)" if is_retry else ""
            print(f"Skipping '{job_name}'{retry_label} - log already exists: {output_path}")
            continue

        try:
            retry_label = " (retry)" if is_retry else ""
            print(f"Downloading log for '{job_name}'{retry_label}...")
            download_job_log(raw_log_url, output_path)
            print(f"Saved: {output_path}")
            downloaded_count += 1
        except Exception as e:
            print(f"Error downloading log for '{job_name}': {e}")

    print(f"\nDownloaded {downloaded_count} job log(s) (validation jobs and retries)")
    metrics = get_http_cache_metrics()
    print(f"Requests made: {metrics['requests_made']} | Cache hits: {metrics['cache_hits']}")


if __name__ == "__main__":
    main()

