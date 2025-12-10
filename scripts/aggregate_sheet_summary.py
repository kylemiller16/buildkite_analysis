#!/usr/bin/env python3
"""
Script to aggregate data across all tabs in a Google Sheet and create a summary tab.
Reads existing buildkite analysis data from multiple worksheets and creates consolidated totals.
"""

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add lib directory to path for standalone execution
_SCRIPT_DIR = Path(__file__).resolve().parent
_LIB_DIR = _SCRIPT_DIR.parent / "lib"
sys.path.insert(0, str(_LIB_DIR))

from spreadsheet import (
    connect_to_sheets,
    is_sheets_available,
    write_to_sheets,
)


def parse_duration_to_seconds(duration_str: str) -> float:
    """Parse duration string (HH:MM:SS) to seconds."""
    if duration_str == "-" or not duration_str.strip():
        return 0.0

    try:
        parts = duration_str.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        return 0.0
    except ValueError:
        return 0.0


def seconds_to_duration_str(seconds: float) -> str:
    """Convert seconds to HH:MM:SS format."""
    if seconds <= 0:
        return "-"

    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def parse_grand_totals_from_sheet(worksheet_data: List[List[str]]) -> Optional[Dict[str, Any]]:
    """Parse grand totals section from worksheet data."""
    try:
        # Find the GRAND TOTALS section
        grand_totals_start = None
        for i, row in enumerate(worksheet_data):
            if row and row[0] == "GRAND TOTALS":
                grand_totals_start = i
                break

        if grand_totals_start is None:
            return None

        # Look for the "All Jobs" data row (usually 2 rows after header)
        for i in range(grand_totals_start + 1, min(len(worksheet_data), grand_totals_start + 5)):
            row = worksheet_data[i]
            if len(row) >= 9 and row[0] == "All Jobs":
                return {
                    "count": int(row[1]) if row[1].isdigit() else 0,
                    "total_duration": row[2],
                    "avg_duration": row[3],
                    "avg_duration_pass": row[4],
                    "avg_duration_fail": row[5],
                    "avg_wait": row[6],
                    "pass": int(row[7]) if row[7].isdigit() else 0,
                    "fail": int(row[8]) if row[8].isdigit() else 0,
                }
    except (ValueError, IndexError) as e:
        print(f"Warning: Could not parse grand totals: {e}")

    return None


def parse_daily_averages_from_sheet(worksheet_data: List[List[str]]) -> Optional[Dict[str, Any]]:
    """Parse daily averages section from worksheet data."""
    try:
        # Find the DAILY AVERAGES section
        daily_avg_start = None
        for i, row in enumerate(worksheet_data):
            if row and row[0] == "DAILY AVERAGES":
                daily_avg_start = i
                break

        if daily_avg_start is None:
            return None

        # Look for the "All Jobs" data row
        for i in range(daily_avg_start + 1, min(len(worksheet_data), daily_avg_start + 5)):
            row = worksheet_data[i]
            if len(row) >= 5 and row[0] == "All Jobs":
                return {
                    "count_per_day": float(row[1]) if row[1].replace(".", "").isdigit() else 0.0,
                    "duration_per_day": row[2],
                    "pass_per_day": float(row[3]) if row[3].replace(".", "").isdigit() else 0.0,
                    "fail_per_day": float(row[4]) if row[4].replace(".", "").isdigit() else 0.0,
                }
    except (ValueError, IndexError) as e:
        print(f"Warning: Could not parse daily averages: {e}")

    return None


def parse_hil_resources_from_sheet(worksheet_data: List[List[str]]) -> Optional[Dict[str, str]]:
    """Parse HIL resources section from worksheet data."""
    try:
        # Find the HIL RESOURCES section
        hil_start = None
        for i, row in enumerate(worksheet_data):
            if row and row[0] == "HIL RESOURCES":
                hil_start = i
                break

        if hil_start is None:
            return None

        hil_data = {}
        # Parse key-value pairs
        for i in range(hil_start + 2, len(worksheet_data)):  # Skip header row
            row = worksheet_data[i]
            if len(row) >= 2 and row[0] and row[1]:
                hil_data[row[0]] = row[1]
            elif not row or not row[0]:  # Empty row, end of section
                break

        return hil_data if hil_data else None
    except (ValueError, IndexError) as e:
        print(f"Warning: Could not parse HIL resources: {e}")

    return None


def aggregate_data(all_worksheet_data: Dict[str, List[List[str]]]) -> Tuple[Dict, Dict, Dict]:
    """Aggregate grand totals, daily averages, and HIL resources across all worksheets."""

    # Aggregate grand totals
    total_count = 0
    total_pass = 0
    total_fail = 0
    all_durations = []
    all_durations_pass = []
    all_durations_fail = []
    all_waits = []

    # Aggregate daily averages
    total_count_per_day = 0.0
    total_pass_per_day = 0.0
    total_fail_per_day = 0.0
    all_daily_durations = []

    # Aggregate HIL resources
    all_hil_data: Dict[str, List[str]] = {}

    tab_count = 0

    for tab_name, worksheet_data in all_worksheet_data.items():
        if tab_name.lower() in ["summary", "aggregated", "total"]:  # Skip existing summary tabs
            continue

        print(f"Processing tab: {tab_name}")

        # Parse grand totals
        grand_totals = parse_grand_totals_from_sheet(worksheet_data)
        if grand_totals:
            total_count += grand_totals["count"]
            total_pass += grand_totals["pass"]
            total_fail += grand_totals["fail"]

            # Convert duration strings to seconds for aggregation
            if grand_totals["avg_duration"] != "-":
                avg_duration_secs = parse_duration_to_seconds(grand_totals["avg_duration"])
                if avg_duration_secs > 0:
                    all_durations.extend([avg_duration_secs] * grand_totals["count"])

            if grand_totals["avg_duration_pass"] != "-":
                avg_pass_secs = parse_duration_to_seconds(grand_totals["avg_duration_pass"])
                if avg_pass_secs > 0:
                    all_durations_pass.extend([avg_pass_secs] * grand_totals["pass"])

            if grand_totals["avg_duration_fail"] != "-":
                avg_fail_secs = parse_duration_to_seconds(grand_totals["avg_duration_fail"])
                if avg_fail_secs > 0:
                    all_durations_fail.extend([avg_fail_secs] * grand_totals["fail"])

            if grand_totals["avg_wait"] != "-":
                avg_wait_secs = parse_duration_to_seconds(grand_totals["avg_wait"])
                if avg_wait_secs > 0:
                    all_waits.extend([avg_wait_secs] * grand_totals["count"])

        # Parse daily averages
        daily_avg = parse_daily_averages_from_sheet(worksheet_data)
        if daily_avg:
            total_count_per_day += daily_avg["count_per_day"]
            total_pass_per_day += daily_avg["pass_per_day"]
            total_fail_per_day += daily_avg["fail_per_day"]

            if daily_avg["duration_per_day"] != "-":
                daily_duration_secs = parse_duration_to_seconds(daily_avg["duration_per_day"])
                if daily_duration_secs > 0:
                    all_daily_durations.append(daily_duration_secs)

        # Parse HIL resources
        hil_resources = parse_hil_resources_from_sheet(worksheet_data)
        if hil_resources:
            for key, value in hil_resources.items():
                if key not in all_hil_data:
                    all_hil_data[key] = []
                all_hil_data[key].append(value)

        tab_count += 1

    # Calculate aggregated grand totals
    aggregated_grand_totals = {
        "count": total_count,
        "total_duration": seconds_to_duration_str(sum(all_durations)) if all_durations else "-",
        "avg_duration": seconds_to_duration_str(sum(all_durations) / len(all_durations)) if all_durations else "-",
        "avg_duration_pass": (
            seconds_to_duration_str(sum(all_durations_pass) / len(all_durations_pass)) if all_durations_pass else "-"
        ),
        "avg_duration_fail": (
            seconds_to_duration_str(sum(all_durations_fail) / len(all_durations_fail)) if all_durations_fail else "-"
        ),
        "avg_wait": seconds_to_duration_str(sum(all_waits) / len(all_waits)) if all_waits else "-",
        "pass": total_pass,
        "fail": total_fail,
    }

    # Calculate aggregated daily averages
    aggregated_daily_averages = {
        "count_per_day": round(total_count_per_day, 1),
        "duration_per_day": seconds_to_duration_str(sum(all_daily_durations)) if all_daily_durations else "-",
        "pass_per_day": round(total_pass_per_day, 1),
        "fail_per_day": round(total_fail_per_day, 1),
    }

    # Aggregate HIL resources (summarize/combine values)
    aggregated_hil_resources = {}
    for key, values in all_hil_data.items():
        if "Required parallel resources" in key:
            # Sum the resource requirements
            try:
                numeric_values = [float(v.split()[0]) for v in values if v and v.split()[0].replace(".", "").isdigit()]
                if numeric_values:
                    aggregated_hil_resources[key] = f"{sum(numeric_values):.1f}"
            except (ValueError, IndexError):
                aggregated_hil_resources[key] = ", ".join(values)
        elif "Work days analyzed" in key:
            # Sum work days
            try:
                numeric_values = [int(v) for v in values if v.isdigit()]
                if numeric_values:
                    aggregated_hil_resources[key] = str(sum(numeric_values))
            except ValueError:
                aggregated_hil_resources[key] = ", ".join(values)
        else:
            # For other fields, just combine or take the most common
            aggregated_hil_resources[key] = ", ".join(set(values))

    print(f"Aggregated data from {tab_count} tabs")
    return aggregated_grand_totals, aggregated_daily_averages, aggregated_hil_resources


def create_summary_sheet_data(
    grand_totals: Dict, daily_averages: Dict, hil_resources: Dict, tabs_processed: List[str]
) -> List[List[str]]:
    """Create the data structure for the summary sheet."""
    data = []

    # Header with timestamp
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data.append([f"Aggregated Buildkite Analysis Summary - Generated: {timestamp}"])
    data.append([f"Aggregated from {len(tabs_processed)} tabs: {', '.join(tabs_processed)}"])
    data.append([])  # Empty row

    # Grand totals section
    data.append(["AGGREGATED GRAND TOTALS"])
    data.append(
        [
            "Type",
            "Count",
            "TotalDuration",
            "AvgDuration",
            "AvgDuration(pass)",
            "AvgDuration(fail)",
            "AvgWait",
            "Pass",
            "Fail",
        ]
    )
    data.append(
        [
            "All Jobs",
            grand_totals["count"],
            grand_totals["total_duration"],
            grand_totals["avg_duration"],
            grand_totals["avg_duration_pass"],
            grand_totals["avg_duration_fail"],
            grand_totals["avg_wait"],
            grand_totals["pass"],
            grand_totals["fail"],
        ]
    )
    data.append([])  # Empty row

    # Daily averages section
    data.append(["AGGREGATED DAILY AVERAGES"])
    data.append(["Type", "Count/Day", "Duration/Day", "Pass/Day", "Fail/Day"])
    data.append(
        [
            "All Jobs",
            daily_averages["count_per_day"],
            daily_averages["duration_per_day"],
            daily_averages["pass_per_day"],
            daily_averages["fail_per_day"],
        ]
    )
    data.append([])  # Empty row

    # HIL resources section
    if hil_resources:
        data.append(["AGGREGATED HIL RESOURCES"])
        data.append(["Metric", "Value"])
        for key, value in hil_resources.items():
            data.append([key, value])

    return data


def main():
    parser = argparse.ArgumentParser(description="Aggregate buildkite analysis data across all tabs in a Google Sheet")
    parser.add_argument("--sheets-id", required=True, help="Google Sheets ID or URL")
    parser.add_argument(
        "--sheets-credentials", required=True, help="Path to Google Sheets service account credentials JSON file"
    )
    parser.add_argument("--summary-tab", default="Summary", help="Name for the summary tab (default: Summary)")
    parser.add_argument(
        "--exclude-tabs",
        action="append",
        help="Tab names to exclude from aggregation (can be specified multiple times)",
    )

    args = parser.parse_args()

    # Validate dependencies
    if not is_sheets_available():
        raise RuntimeError("Google Sheets dependencies not available. " "Install with: pip install gspread google-auth")

    print("Connecting to Google Sheets...")

    # Connect to sheets and get all worksheets
    try:
        # Connect to any worksheet first to get the spreadsheet object
        temp_worksheet = connect_to_sheets(args.sheets_credentials, args.sheets_id, "temp")
        spreadsheet = temp_worksheet.spreadsheet

        # Get all worksheets
        all_worksheets = spreadsheet.worksheets()
        print(f"Found {len(all_worksheets)} worksheets")

        # Read data from all worksheets
        all_worksheet_data = {}
        exclude_tabs = set(args.exclude_tabs or [])
        exclude_tabs.add(args.summary_tab.lower())  # Don't process existing summary tab

        for ws in all_worksheets:
            if ws.title.lower() in exclude_tabs:
                print(f"Skipping excluded tab: {ws.title}")
                continue

            print(f"Reading data from: {ws.title}")
            try:
                ws_data = ws.get_all_values()
                if ws_data:  # Only include non-empty worksheets
                    all_worksheet_data[ws.title] = ws_data
                else:
                    print(f"  -> Empty worksheet, skipping")
            except Exception as e:
                print(f"  -> Error reading worksheet {ws.title}: {e}")

        if not all_worksheet_data:
            raise RuntimeError("No valid worksheet data found to aggregate")

        print(f"\nAggregating data from {len(all_worksheet_data)} tabs...")

        # Aggregate the data
        grand_totals, daily_averages, hil_resources = aggregate_data(all_worksheet_data)

        # Create summary sheet data
        tabs_processed = list(all_worksheet_data.keys())
        summary_data = create_summary_sheet_data(grand_totals, daily_averages, hil_resources, tabs_processed)

        # Write to summary worksheet
        print(f"\nWriting summary to '{args.summary_tab}' tab...")
        try:
            summary_worksheet = spreadsheet.worksheet(args.summary_tab)
        except Exception:
            # Create the worksheet if it doesn't exist
            summary_worksheet = spreadsheet.add_worksheet(title=args.summary_tab, rows=1000, cols=20)

        sheet_url = write_to_sheets(summary_worksheet, summary_data)

        print(f"✅ Successfully created aggregated summary!")
        print(f"📊 Sheet URL: {sheet_url}")
        print(f"📝 Summary Tab: {args.summary_tab}")
        print(f"📈 Aggregated from: {', '.join(tabs_processed)}")

    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
