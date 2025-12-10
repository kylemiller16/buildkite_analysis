import argparse
import datetime as dt
import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Add lib directory to path for standalone execution
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from analysis import filter_cached_jobs
from filters import (
    build_branch_filter,
    build_exclude_branch_filter,
    build_job_name_filter,
    build_pipeline_filter,
    build_pst_time_of_day_filter,
)
from util import BuildkiteConfig


def _is_build_pass(build: Dict[str, Any]) -> bool:
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


def _is_job_pass(job: Dict[str, Any]) -> bool:
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


def _find_log_file_for_job(metadata_path: str, job_id: str) -> Optional[str]:
    """Find the log file for a given job ID."""
    metadata_dir = os.path.dirname(metadata_path)
    metadata_basename = os.path.splitext(os.path.basename(metadata_path))[0]
    
    # Log files follow pattern: {metadata_basename}__{job_id}__*.log
    log_pattern = f"{metadata_basename}__{job_id}__*.log"
    
    matches = glob.glob(os.path.join(metadata_dir, log_pattern))
    if matches:
        return matches[0]  # Return first match
    return None


def analyze_bazel_targets_from_log(log_file_path: str) -> Dict[str, bool]:
    """
    Analyze a log file to extract Bazel target pass/fail information.
    
    This is a stub function - implement the actual log parsing logic here.
    
    Args:
        log_file_path: Path to the log file
        
    Returns:
        Dictionary mapping target names to pass status (True = passed, False = failed)
        Example: {"//path/to:target1": True, "//path/to:target2": False}
    """
    # TODO: Implement log parsing logic
    # For now, return empty dict
    return {}


def load_cached_builds_with_logs(
    filter_callbacks: List[Callable[[Dict[str, Any]], bool]],
    *,
    started_from: Optional[dt.datetime] = None,
    started_to: Optional[dt.datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Load cached builds and their associated log files.
    
    Returns a list of build records with log file information.
    Each record contains:
    - build_metadata: The full build metadata dict
    - jobs_with_logs: List of (job, log_file_path) tuples
    """
    from analysis import _iter_cached_build_files
    
    # Get all job records using existing filter logic
    job_records = filter_cached_jobs(filter_callbacks, started_from=started_from, started_to=started_to)
    
    # Group by build
    builds_by_key: Dict[Tuple[str, int], Dict[str, Any]] = {}
    
    # First, collect all unique builds
    build_keys_seen: Set[Tuple[str, int]] = set()
    for job_record in job_records:
        pipeline_slug = job_record.get("pipeline_slug")
        build_number = job_record.get("build_number")
        if pipeline_slug and build_number is not None:
            build_keys_seen.add((pipeline_slug, build_number))
    
    # Load build metadata for all unique builds
    for build_file in _iter_cached_build_files():
        try:
            with open(build_file, "r", encoding="utf-8") as f:
                build_data = json.load(f)
            pipeline_slug = build_data.get("pipeline", {}).get("slug")
            build_number = build_data.get("number")
            if pipeline_slug and build_number is not None:
                build_key = (pipeline_slug, build_number)
                if build_key in build_keys_seen:
                    metadata_path = str(build_file)
                    builds_by_key[build_key] = {
                        "build_metadata": build_data,
                        "metadata_path": metadata_path,
                        "jobs_with_logs": [],
                    }
        except Exception:
            continue
    
    # Now match jobs to builds and find log files
    for job_record in job_records:
        pipeline_slug = job_record.get("pipeline_slug")
        build_number = job_record.get("build_number")
        if not pipeline_slug or build_number is None:
            continue
        
        build_key = (pipeline_slug, build_number)
        if build_key in builds_by_key:
            job = job_record.get("job", {})
            job_id = job.get("id")
            if job_id:
                log_file = _find_log_file_for_job(builds_by_key[build_key]["metadata_path"], job_id)
                builds_by_key[build_key]["jobs_with_logs"].append((job, log_file))
    
    return list(builds_by_key.values())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze cached Buildkite builds with log file analysis for Bazel targets"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="How many days back to look in the cache (default: 7)",
    )
    parser.add_argument(
        "--pipeline",
        action="append",
        help="Pipeline slug(s) to include. If omitted, do not filter by pipeline",
    )
    parser.add_argument(
        "--job-name",
        action="append",
        help="Only include jobs whose name contains any of these substrings. Can be specified multiple times (optional)",
    )
    parser.add_argument(
        "--branch",
        help='Only include jobs from builds on this branch. Use "non-main" to filter for all non-main branches (optional)',
    )
    parser.add_argument(
        "--exclude-branch",
        action="append",
        help="Exclude jobs from builds on these branches. Can be specified multiple times (optional)",
    )
    parser.add_argument(
        "--pst-start",
        type=int,
        default=0,
        help="PST hour (0-23) inclusive to start time-of-day filter (default: 0)",
    )
    parser.add_argument(
        "--pst-end",
        type=int,
        default=18,
        help="PST hour (0-23) inclusive to end time-of-day filter (default: 18)",
    )
    parser.add_argument(
        "--no-pst-filter",
        action="store_true",
        help="Disable the PST time-of-day filter",
    )

    args = parser.parse_args()

    # Build filter callbacks
    callbacks: List[Callable[[Dict[str, Any]], bool]] = []
    if args.pipeline:
        callbacks.append(build_pipeline_filter(args.pipeline))
    if args.job_name:
        callbacks.append(build_job_name_filter(args.job_name))
    if args.branch:
        callbacks.append(build_branch_filter(args.branch))
    if args.exclude_branch:
        callbacks.append(build_exclude_branch_filter(args.exclude_branch))
    if not args.no_pst_filter:
        callbacks.append(build_pst_time_of_day_filter(args.pst_start, args.pst_end))

    # Calculate time window
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=args.days)

    # Load builds with logs
    print("Loading cached builds and log files...")
    builds_with_logs = load_cached_builds_with_logs(callbacks, started_from=cutoff)
    print(f"Found {len(builds_with_logs)} build(s) matching filters")

    # Statistics
    build_stats = {"pass": 0, "fail": 0}
    job_stats_by_name: Dict[str, Dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0, "no_log": 0})
    bazel_target_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"pass": 0, "fail": 0})

    # Process each build
    for build_record in builds_with_logs:
        build_metadata = build_record["build_metadata"]
        jobs_with_logs = build_record["jobs_with_logs"]

        # Build-level statistics
        if _is_build_pass(build_metadata):
            build_stats["pass"] += 1
        else:
            build_stats["fail"] += 1

        # Job-level statistics (per job name)
        for job, log_file_path in jobs_with_logs:
            job_name = job.get("name", "unknown")
            
            if _is_job_pass(job):
                job_stats_by_name[job_name]["pass"] += 1
            else:
                job_stats_by_name[job_name]["fail"] += 1

            # Bazel target statistics (if log file exists)
            if log_file_path and os.path.exists(log_file_path):
                try:
                    target_results = analyze_bazel_targets_from_log(log_file_path)
                    for target_name, passed in target_results.items():
                        if passed:
                            bazel_target_stats[target_name]["pass"] += 1
                        else:
                            bazel_target_stats[target_name]["fail"] += 1
                except Exception as e:
                    print(f"Warning: Error analyzing log {log_file_path}: {e}")
            else:
                job_stats_by_name[job_name]["no_log"] += 1

    # Print summary
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)

    # Build statistics
    total_builds = build_stats["pass"] + build_stats["fail"]
    if total_builds > 0:
        build_pass_pct = (build_stats["pass"] / total_builds) * 100
        build_fail_pct = (build_stats["fail"] / total_builds) * 100
        print(f"\nBUILD STATISTICS:")
        print(f"  Total builds: {total_builds}")
        print(f"  Passed: {build_stats['pass']} ({build_pass_pct:.1f}%)")
        print(f"  Failed: {build_stats['fail']} ({build_fail_pct:.1f}%)")
    else:
        print("\nBUILD STATISTICS: No builds found")

    # Job statistics (per job name)
    if job_stats_by_name:
        print(f"\nJOB STATISTICS:")
        
        # Sort by total runs (pass + fail) descending
        sorted_jobs = sorted(
            job_stats_by_name.items(),
            key=lambda x: x[1]["pass"] + x[1]["fail"],
            reverse=True,
        )
        
        for job_name, stats in sorted_jobs:
            job_total = stats["pass"] + stats["fail"]
            if job_total > 0:
                job_pass_pct = (stats["pass"] / job_total) * 100
                job_fail_pct = (stats["fail"] / job_total) * 100
                print(f"    {job_name}:")
                print(f"      Total: {job_total}")
                print(f"      Passed: {stats['pass']} ({job_pass_pct:.1f}%)")
                print(f"      Failed: {stats['fail']} ({job_fail_pct:.1f}%)")
                if stats["no_log"] > 0:
                    print(f"      Without log files: {stats['no_log']}")
    else:
        print("\nJOB STATISTICS: No jobs found")

    # Bazel target statistics
    if bazel_target_stats:
        print(f"\nBAZEL TARGET STATISTICS:")
        print(f"  Total unique targets: {len(bazel_target_stats)}")
        
        # Sort by total runs (pass + fail) descending
        sorted_targets = sorted(
            bazel_target_stats.items(),
            key=lambda x: x[1]["pass"] + x[1]["fail"],
            reverse=True,
        )
        
        print(f"\n  Top targets by total runs:")
        for target_name, stats in sorted_targets[:20]:  # Show top 20
            total_runs = stats["pass"] + stats["fail"]
            if total_runs > 0:
                pass_pct = (stats["pass"] / total_runs) * 100
                fail_pct = (stats["fail"] / total_runs) * 100
                print(f"    {target_name}:")
                print(f"      Total runs: {total_runs}")
                print(f"      Passed: {stats['pass']} ({pass_pct:.1f}%)")
                print(f"      Failed: {stats['fail']} ({fail_pct:.1f}%)")
        
        # Overall target statistics
        total_target_runs = sum(s["pass"] + s["fail"] for s in bazel_target_stats.values())
        total_target_passes = sum(s["pass"] for s in bazel_target_stats.values())
        total_target_fails = sum(s["fail"] for s in bazel_target_stats.values())
        if total_target_runs > 0:
            overall_pass_pct = (total_target_passes / total_target_runs) * 100
            overall_fail_pct = (total_target_fails / total_target_runs) * 100
            print(f"\n  Overall target statistics:")
            print(f"    Total target runs: {total_target_runs}")
            print(f"    Total passes: {total_target_passes} ({overall_pass_pct:.1f}%)")
            print(f"    Total failures: {total_target_fails} ({overall_fail_pct:.1f}%)")
    else:
        print(f"\nBAZEL TARGET STATISTICS: No target data found (log analysis not implemented)")


if __name__ == "__main__":
    main()

