import argparse
import datetime as dt
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Chart generation imports (optional)
try:
    import matplotlib
    matplotlib.use("Agg")  # Use non-interactive backend
    import matplotlib.pyplot as plt
    CHART_AVAILABLE = True
except ImportError:
    CHART_AVAILABLE = False
    plt = None

# Add lib directory to path for standalone execution
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from analysis import filter_cached_jobs  # type: ignore  # noqa: E402
from filters import (  # type: ignore  # noqa: E402
    build_branch_filter,
    build_exclude_branch_filter,
    build_job_name_filter,
    build_pipeline_filter,
    build_pst_time_of_day_filter,
)
from util import (  # type: ignore  # noqa: E402
    BuildkiteConfig,
    analyze_bazel_targets_from_log,
    find_log_file_for_job,
    is_build_pass,
    is_job_pass,
)


def generate_bazel_target_charts(
    bazel_target_stats: Dict[str, Dict[str, int]],
    job_stats_by_name: Dict[str, Dict[str, int]],
    output_format: str,
    output_path: Optional[str] = None
) -> None:
    """
    Generate a single pie chart showing job pass/fail and categorized target failures.
    
    Args:
        bazel_target_stats: Dictionary mapping target names to pass/fail counts
        job_stats_by_name: Dictionary mapping job names to pass/fail counts
        output_format: "png" or "html"
        output_path: Optional path to save the chart (default: bazel_targets_chart.{format})
    """
    if not CHART_AVAILABLE:
        print("Warning: matplotlib is not available. Install with: pip install matplotlib")
        return
    
    # Calculate total job passes (sum across all jobs)
    total_job_passes = sum(stats["pass"] for stats in job_stats_by_name.values())
    
    # Count failures for specific target names (exact match on the target name after the colon)
    device_recovery_failures = 0
    setup_device_failures = 0
    regression_tests_failures = 0
    
    for target_name, stats in bazel_target_stats.items():
        fail_count = stats["fail"]
        # Extract the target name part after the colon
        if ":" in target_name:
            target_part = target_name.split(":")[-1]
        else:
            target_part = target_name
        
        # Match exact target names
        if target_part == "device_recovery":
            device_recovery_failures += fail_count
        elif target_part == "setup_device":
            setup_device_failures += fail_count
        elif target_part == "regression_tests_rcm_aem_evt_1":
            regression_tests_failures += fail_count
    
    # Prepare data for pie chart
    labels = []
    sizes = []
    colors = []
    
    if total_job_passes > 0:
        labels.append("Job Passed")
        sizes.append(total_job_passes)
        colors.append("#2ecc71")  # Green
    
    if device_recovery_failures > 0:
        labels.append("device_recovery failures")
        sizes.append(device_recovery_failures)
        colors.append("#9b59b6")  # Purple
    
    if setup_device_failures > 0:
        labels.append("setup_device failures")
        sizes.append(setup_device_failures)
        colors.append("#f39c12")  # Orange
    
    if regression_tests_failures > 0:
        labels.append("regression_tests_rcm_aem_evt_1 failures")
        sizes.append(regression_tests_failures)
        colors.append("#e74c3c")  # Red
    
    if not sizes:
        print("No data to generate charts")
        return
    
    # Determine output path
    if output_path:
        chart_path = output_path
    else:
        chart_path = f"bazel_targets_chart.{output_format}"
    
    if output_format == "png":
        _generate_png_charts(labels, sizes, colors, chart_path)
    elif output_format == "html":
        _generate_html_charts(labels, sizes, colors, chart_path)
    else:
        print(f"Unknown output format: {output_format}")
        return
    
    print(f"\nChart saved to: {os.path.abspath(chart_path)}")


def _generate_png_charts(labels: List[str], sizes: List[int], colors: List[str], output_path: str) -> None:
    """Generate a single PNG pie chart."""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    # Calculate percentages for labels
    total = sum(sizes)
    percentages = [(size / total * 100) for size in sizes]
    labels_with_pct = [f"{label}\n({pct:.1f}%)" for label, pct in zip(labels, percentages)]
    
    # Create pie chart
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=labels_with_pct,
        colors=colors,
        autopct="",
        startangle=90,
        textprops={"fontsize": 12, "fontweight": "bold"},
    )
    
    ax.set_title("Job and Target Failure Statistics", fontsize=16, fontweight="bold", pad=20)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()


def _generate_html_charts(labels: List[str], sizes: List[int], colors: List[str], output_path: str) -> None:
    """Generate HTML file with embedded PNG chart."""
    # Generate PNG first, then embed in HTML
    png_path = output_path.replace(".html", ".png")
    _generate_png_charts(labels, sizes, colors, png_path)
    
    # Create HTML file
    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>Bazel Target Statistics</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            text-align: center;
        }}
        .chart-container {{
            background-color: white;
            padding: 20px;
            margin: 20px auto;
            max-width: 1200px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        img {{
            max-width: 100%;
            height: auto;
            display: block;
            margin: 0 auto;
        }}
        .timestamp {{
            text-align: center;
            color: #666;
            margin-top: 20px;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="chart-container">
        <h1>Bazel Target Pass/Fail Statistics</h1>
        <img src="{os.path.basename(png_path)}" alt="Bazel Target Statistics">
        <div class="timestamp">
            Generated: {dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"HTML file saved to: {os.path.abspath(output_path)}")
    print(f"PNG chart saved to: {os.path.abspath(png_path)}")


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
    from analysis import _iter_cached_build_files  # type: ignore  # pylint: disable=import-outside-toplevel

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
                log_file = find_log_file_for_job(builds_by_key[build_key]["metadata_path"], job_id)
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
    parser.add_argument(
        "--chart-output",
        choices=["png", "html"],
        help="Generate pie charts for Bazel target statistics. Options: png or html",
    )
    parser.add_argument(
        "--chart-path",
        help="Path to save the chart file (default: bazel_targets_chart.png or .html in current directory)",
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
        if is_build_pass(build_metadata):
            build_stats["pass"] += 1
        else:
            build_stats["fail"] += 1

        # Job-level statistics (per job name)
        for job, log_file_path in jobs_with_logs:
            job_name = job.get("name", "unknown")
            job_passed = is_job_pass(job)
            
            if job_passed:
                job_stats_by_name[job_name]["pass"] += 1
            else:
                job_stats_by_name[job_name]["fail"] += 1

            # Bazel target statistics (if log file exists)
            if log_file_path and os.path.exists(log_file_path):
                try:
                    target_results = analyze_bazel_targets_from_log(log_file_path, job_passed)
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
        
        # Generate charts if requested
        if args.chart_output and (bazel_target_stats or job_stats_by_name):
            generate_bazel_target_charts(bazel_target_stats, job_stats_by_name, args.chart_output, args.chart_path)
    else:
        print(f"\nBAZEL TARGET STATISTICS: No target data found (log analysis not implemented)")


if __name__ == "__main__":
    main()

