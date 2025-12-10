import argparse
import datetime as dt
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List
from zoneinfo import ZoneInfo

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
from spreadsheet import (
    connect_to_sheets,
    format_data_for_sheets,
    is_sheets_available,
    write_to_sheets,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze cached Buildkite builds with filter callbacks")
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
        "--print",
        dest="print_results",
        action="store_true",
        help="Print matching jobs (pipeline, build, job name, web_url)",
    )
    parser.add_argument(
        "--sheets-output",
        action="store_true",
        help="Output results to Google Sheets",
    )
    parser.add_argument(
        "--sheets-id",
        help="Google Sheets ID or URL for output",
    )
    parser.add_argument(
        "--sheets-tab",
        default="BuildkiteAnalysis",
        help="Google Sheets tab/worksheet name (default: BuildkiteAnalysis)",
    )
    parser.add_argument(
        "--sheets-credentials",
        help="Path to Google Sheets service account credentials JSON file",
    )

    args = parser.parse_args()

    # Validate Google Sheets arguments
    if args.sheets_output:
        if not is_sheets_available():
            raise RuntimeError(
                "Google Sheets output requires 'gspread' and 'google-auth' packages. "
                "Install with: pip install gspread google-auth"
            )
        if not args.sheets_id:
            raise ValueError("--sheets-id is required when using --sheets-output")
        if not args.sheets_credentials:
            raise ValueError("--sheets-credentials is required when using --sheets-output")

    # Validate cache history depth: ensure we have at least one job older than cutoff
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=args.days)
    all_cached = filter_cached_jobs([])
    has_old_enough = any(
        (rec.get("job_started_at") is not None) and (rec["job_started_at"] <= cutoff) for rec in all_cached
    )
    if not has_old_enough:
        raise RuntimeError(
            f"Cache does not contain any jobs older than the requested history window of {args.days} day(s)."
        )

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

    matches = filter_cached_jobs(callbacks, started_from=cutoff)

    print(f"Matches: {len(matches)}")
    if args.print_results:
        for rec in matches:
            job = rec.get("job") or {}
            pipeline = rec.get("pipeline_slug")
            build_number = rec.get("build_number")
            name = job.get("name")
            url = job.get("web_url")
            print(f"{pipeline}\t{build_number}\t{name}\t{url}")

    # Use PST timezone for date bucketization
    tz = ZoneInfo("America/Los_Angeles")

    def _duration_seconds(rec: Dict[str, Any]) -> float | None:
        start = rec.get("job_started_at")
        end = rec.get("job_finished_at")
        if not start or not end:
            return None
        return max(0.0, (end - start).total_seconds())

    def _is_pass(rec: Dict[str, Any]) -> bool:
        job = rec.get("job") or {}
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

    def _is_fail(rec: Dict[str, Any]) -> bool:
        job = rec.get("job") or {}
        state = job.get("state")
        if state == "failed":
            return True
        if state == "passed":
            return False
        exit_status = job.get("exit_status")
        if isinstance(exit_status, int):
            return exit_status != 0
        return False

    def _parse_job_ts(job: Dict[str, Any], key: str):
        val = job.get(key)
        if not isinstance(val, str):
            return None
        try:
            return dt.datetime.fromisoformat(val.replace("Z", "+00:00"))
        except Exception:
            return None

    def _wait_seconds(rec: Dict[str, Any]) -> float | None:
        job = rec.get("job") or {}
        started = rec.get("job_started_at")
        if not started:
            return None
        base = _parse_job_ts(job, "runnable_at") or _parse_job_ts(job, "created_at")
        if not base:
            return None
        return max(0.0, (started - base).total_seconds())

    def _fmt_avg(sec_list: list[float]) -> str:
        if not sec_list:
            return "-"
        avg = sum(sec_list) / len(sec_list)
        mins, secs = divmod(int(avg), 60)
        hrs, mins = divmod(mins, 60)
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"

    # Daily summary (Mon-Fri) including calendar date (MM/DD) grouped by job
    from collections import defaultdict

    # Group by (pipeline, job_name) then by date
    job_daily_stats: Dict[tuple[str, str], Dict[dt.date, Dict[str, Any]]] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "count": 0,
                "durations_pass": [],
                "durations_fail": [],
                "waits": [],
                "pass": 0,
                "fail": 0,
            }
        )
    )

    for rec in matches:
        started = rec.get("job_started_at")
        if not started:
            continue
        local = started.astimezone(tz)
        if local.weekday() > 4:  # skip weekends
            continue

        # Get job identification
        job = rec.get("job") or {}
        pipeline = rec.get("pipeline_slug", "unknown")
        job_name = job.get("name", "unknown")
        job_key = (pipeline, job_name)

        date_key = local.date()
        stat = job_daily_stats[job_key][date_key]
        stat["count"] += 1
        dur = _duration_seconds(rec)
        if _is_pass(rec):
            stat["pass"] += 1
            if dur is not None:
                stat["durations_pass"].append(dur)
        elif _is_fail(rec):
            stat["fail"] += 1
            if dur is not None:
                stat["durations_fail"].append(dur)
        wsec = _wait_seconds(rec)
        if wsec is not None:
            stat["waits"].append(wsec)

    # Generate separate daily summary for each job
    print("\nDaily summaries (Mon-Fri) by job:")

    # Sort jobs by pipeline, then job name for consistent output
    sorted_job_keys = sorted(job_daily_stats.keys())

    # Initialize grand totals across all jobs
    grand_total_count = 0
    grand_all_durations_combined: list[float] = []
    grand_all_durations_pass_combined: list[float] = []
    grand_all_durations_fail_combined: list[float] = []
    grand_all_waits_combined: list[float] = []
    grand_total_pass = 0
    grand_total_fail = 0

    for job_key in sorted_job_keys:
        pipeline, job_name = job_key
        daily_stats = job_daily_stats[job_key]

        print(f"\n=== {pipeline} / {job_name} ===")
        header_daily = (
            f"{'Day':<3}  {'Date':<5}  {'Count':>5}  "
            f"{'TotalDuration':>14}  {'AvgDuration':>12}  {'AvgDuration(pass)':>18}  {'AvgDuration(fail)':>18}  "
            f"{'AvgWait':>12}  {'Pass':>5}  {'Fail':>5}"
        )
        print(header_daily)
        print("-" * len(header_daily))

        # Collect totals for aggregation
        total_count = 0
        all_durations_combined: list[float] = []
        all_durations_pass_combined: list[float] = []
        all_durations_fail_combined: list[float] = []
        all_waits_combined: list[float] = []
        total_pass = 0
        total_fail = 0

        for d in sorted(daily_stats.keys()):
            stat = daily_stats[d]
            day_name = d.strftime("%a")
            date_str = d.strftime("%m/%d")
            all_durations: list[float] = stat["durations_pass"] + stat["durations_fail"]
            total_duration_str = _fmt_avg([sum(all_durations)]) if all_durations else "-"
            line = (
                f"{day_name:<3}  {date_str:<5}  {stat['count']:>5}  "
                f"{total_duration_str:>14}  {_fmt_avg(all_durations):>12}  {_fmt_avg(stat['durations_pass']):>18}  {_fmt_avg(stat['durations_fail']):>18}  "
                f"{_fmt_avg(stat['waits']):>12}  {stat['pass']:>5}  {stat['fail']:>5}"
            )
            print(line)

            # Accumulate totals
            total_count += stat["count"]
            all_durations_combined.extend(all_durations)
            all_durations_pass_combined.extend(stat["durations_pass"])
            all_durations_fail_combined.extend(stat["durations_fail"])
            all_waits_combined.extend(stat["waits"])
            total_pass += stat["pass"]
            total_fail += stat["fail"]

        # Print total row (shifted left by 2 characters)
        print("-" * len(header_daily))
        total_duration_combined_str = _fmt_avg([sum(all_durations_combined)]) if all_durations_combined else "-"
        total_line = (
            f"{'Total':<3}{'':>7}{total_count:>5}  "
            f"{total_duration_combined_str:>14}  {_fmt_avg(all_durations_combined):>12}  {_fmt_avg(all_durations_pass_combined):>18}  {_fmt_avg(all_durations_fail_combined):>18}  "
            f"{_fmt_avg(all_waits_combined):>12}  {total_pass:>5}  {total_fail:>5}"
        )
        print(total_line)

        # Accumulate grand totals
        grand_total_count += total_count
        grand_all_durations_combined.extend(all_durations_combined)
        grand_all_durations_pass_combined.extend(all_durations_pass_combined)
        grand_all_durations_fail_combined.extend(all_durations_fail_combined)
        grand_all_waits_combined.extend(all_waits_combined)
        grand_total_pass += total_pass
        grand_total_fail += total_fail

    # Print grand total summary across all pipelines and jobs
    print("\n" + "=" * 120)
    print("GRAND TOTAL SUMMARY (All Pipelines & Jobs)")
    print("=" * 120)

    header_grand = (
        f"{'Type':<15}  {'Count':>5}  "
        f"{'TotalDuration':>14}  {'AvgDuration':>12}  {'AvgDuration(pass)':>18}  {'AvgDuration(fail)':>18}  "
        f"{'AvgWait':>12}  {'Pass':>5}  {'Fail':>5}"
    )
    print(header_grand)
    print("-" * len(header_grand))

    grand_total_duration_str = _fmt_avg([sum(grand_all_durations_combined)]) if grand_all_durations_combined else "-"
    grand_summary_line = (
        f"{'All Jobs':<15}  {grand_total_count:>5}  "
        f"{grand_total_duration_str:>14}  {_fmt_avg(grand_all_durations_combined):>12}  {_fmt_avg(grand_all_durations_pass_combined):>18}  {_fmt_avg(grand_all_durations_fail_combined):>18}  "
        f"{_fmt_avg(grand_all_waits_combined):>12}  {grand_total_pass:>5}  {grand_total_fail:>5}"
    )
    print(grand_summary_line)

    # Calculate number of unique work days across all jobs
    all_work_days: set[dt.date] = set()
    for job_key in sorted_job_keys:
        daily_stats = job_daily_stats[job_key]
        all_work_days.update(daily_stats.keys())

    num_work_days = len(all_work_days)

    if num_work_days > 0:
        print("\n" + "=" * 80)
        print("GRAND TOTAL DAILY AVERAGE")
        print("=" * 80)

        header_daily_avg = f"{'Type':<15}  {'Count/Day':>9}  " f"{'Duration/Day':>14}  {'Pass/Day':>8}  {'Fail/Day':>8}"
        print(header_daily_avg)
        print("-" * len(header_daily_avg))

        daily_avg_count = round(grand_total_count / num_work_days, 1)
        daily_avg_pass = round(grand_total_pass / num_work_days, 1)
        daily_avg_fail = round(grand_total_fail / num_work_days, 1)

        # Calculate average duration per day
        total_duration_seconds = sum(grand_all_durations_combined) if grand_all_durations_combined else 0
        avg_duration_per_day = total_duration_seconds / num_work_days if num_work_days > 0 else 0
        daily_avg_duration_str = _fmt_avg([avg_duration_per_day]) if avg_duration_per_day > 0 else "-"

        daily_avg_line = (
            f"{'All Jobs':<15}  {daily_avg_count:>9}  "
            f"{daily_avg_duration_str:>14}  {daily_avg_pass:>8}  {daily_avg_fail:>8}"
        )
        print(daily_avg_line)
        print(f"\n(Based on {num_work_days} work days analyzed)")

        # Calculate required HiL resources
        if not args.no_pst_filter and avg_duration_per_day > 0:
            pst_hours = args.pst_end - args.pst_start
            if pst_hours > 0:
                daily_duration_hours = avg_duration_per_day / 3600  # Convert seconds to hours
                required_resources = daily_duration_hours / pst_hours

                print("\n" + "=" * 60)
                print("REQUIRED HIL RESOURCES")
                print("=" * 60)
                print(f"Daily workload: {daily_avg_duration_str}")
                print(f"Available time window: {pst_hours} hours ({args.pst_start}:00 - {args.pst_end}:00 PST)")
                print(f"Required parallel resources: {required_resources:.1f}")
                print(f"(To complete daily workload within time window)")

    # Google Sheets output
    if args.sheets_output:
        print("\n" + "=" * 60)
        print("EXPORTING TO GOOGLE SHEETS")
        print("=" * 60)

        try:
            # Collect data for sheets
            grand_totals_data = [
                grand_total_count,
                grand_total_duration_str,
                _fmt_avg(grand_all_durations_combined),
                _fmt_avg(grand_all_durations_pass_combined),
                _fmt_avg(grand_all_durations_fail_combined),
                _fmt_avg(grand_all_waits_combined),
                grand_total_pass,
                grand_total_fail,
            ]

            daily_averages_data = []
            hil_resources_data = {}

            if num_work_days > 0:
                daily_averages_data = [daily_avg_count, daily_avg_duration_str, daily_avg_pass, daily_avg_fail]

                # Add HiL resources if calculated
                if not args.no_pst_filter and avg_duration_per_day > 0:
                    pst_hours = args.pst_end - args.pst_start
                    if pst_hours > 0:
                        daily_duration_hours = avg_duration_per_day / 3600
                        required_resources = daily_duration_hours / pst_hours
                        hil_resources_data = {
                            "Daily workload": daily_avg_duration_str,
                            "Available time window": f"{pst_hours} hours ({args.pst_start}:00 - {args.pst_end}:00 PST)",
                            "Required parallel resources": f"{required_resources:.1f}",
                            "Work days analyzed": num_work_days,
                        }

            # Connect to Google Sheets
            worksheet = connect_to_sheets(args.sheets_credentials, args.sheets_id, args.sheets_tab)

            # Format and write data
            sheet_data = format_data_for_sheets(
                job_daily_stats, sorted_job_keys, grand_totals_data, daily_averages_data, hil_resources_data
            )

            sheet_url = write_to_sheets(worksheet, sheet_data)

            print(f"✅ Successfully exported to Google Sheets!")
            print(f"📊 Sheet URL: {sheet_url}")
            print(f"📝 Worksheet: {args.sheets_tab}")

        except Exception as e:
            print(f"❌ Failed to export to Google Sheets: {e}")
            print("Console output is still available above.")


if __name__ == "__main__":
    main()
