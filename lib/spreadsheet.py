import datetime as dt
import re

# Google Sheets imports (optional dependencies)
try:
    import gspread
    from google.oauth2.service_account import Credentials

    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    gspread = None
    Credentials = None


def extract_sheet_id(sheets_id_or_url: str) -> str:
    """Extract Google Sheets ID from URL or return as-is if already an ID."""
    # Match Google Sheets URL pattern
    url_pattern = r"/spreadsheets/d/([a-zA-Z0-9-_]+)"
    match = re.search(url_pattern, sheets_id_or_url)
    if match:
        return match.group(1)
    return sheets_id_or_url  # Assume it's already an ID


def connect_to_sheets(credentials_path: str, sheets_id: str, worksheet_name: str):
    """Connect to Google Sheets and return the worksheet."""
    if not SHEETS_AVAILABLE:
        raise RuntimeError("Google Sheets dependencies not available")

    # Authenticate and connect
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_file(credentials_path, scopes=scope)
    client = gspread.authorize(creds)

    # Open the spreadsheet and worksheet
    sheet_id = extract_sheet_id(sheets_id)
    spreadsheet = client.open_by_key(sheet_id)

    try:
        worksheet = spreadsheet.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        # Create the worksheet if it doesn't exist
        worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)

    return worksheet


def format_data_for_sheets(job_daily_stats, sorted_job_keys, grand_totals, daily_averages, hil_resources):
    """Format the analysis data for Google Sheets output."""
    data = []

    # Add header with timestamp
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data.append([f"Buildkite Analysis Report - Generated: {timestamp}"])
    data.append([])  # Empty row

    # Add daily summaries for each job
    data.append(["DAILY SUMMARIES BY JOB"])
    data.append([])

    for job_key in sorted_job_keys:
        pipeline, job_name = job_key
        daily_stats = job_daily_stats[job_key]

        data.append([f"{pipeline} / {job_name}"])
        data.append(
            [
                "Day",
                "Date",
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

        # Add daily rows
        for d in sorted(daily_stats.keys()):
            stat = daily_stats[d]
            day_name = d.strftime("%a")
            date_str = d.strftime("%m/%d")
            all_durations = stat["durations_pass"] + stat["durations_fail"]

            def _fmt_duration(sec_list):
                if not sec_list:
                    return "-"
                avg = sum(sec_list) / len(sec_list)
                mins, secs = divmod(int(avg), 60)
                hrs, mins = divmod(mins, 60)
                return f"{hrs:02d}:{mins:02d}:{secs:02d}"

            total_duration_str = _fmt_duration([sum(all_durations)]) if all_durations else "-"

            data.append(
                [
                    day_name,
                    date_str,
                    stat["count"],
                    total_duration_str,
                    _fmt_duration(all_durations),
                    _fmt_duration(stat["durations_pass"]),
                    _fmt_duration(stat["durations_fail"]),
                    _fmt_duration(stat["waits"]),
                    stat["pass"],
                    stat["fail"],
                ]
            )

        data.append([])  # Empty row between jobs

    # Add grand totals
    data.append(["GRAND TOTALS"])
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
    data.append(["All Jobs"] + grand_totals)
    data.append([])

    # Add daily averages
    data.append(["DAILY AVERAGES"])
    data.append(["Type", "Count/Day", "Duration/Day", "Pass/Day", "Fail/Day"])
    data.append(["All Jobs"] + daily_averages)
    data.append([])

    # Add HiL resources if available
    if hil_resources:
        data.append(["HIL RESOURCES"])
        data.append(["Metric", "Value"])
        for key, value in hil_resources.items():
            data.append([key, value])

    return data


def write_to_sheets(worksheet, data):
    """Write data to Google Sheets worksheet."""
    # Clear the worksheet
    worksheet.clear()

    # Write all data at once for efficiency
    if data:
        # Pad rows to ensure consistent column count
        max_cols = max(len(row) for row in data) if data else 1
        padded_data = []
        for row in data:
            padded_row = row + [""] * (max_cols - len(row))
            padded_data.append(padded_row)

        # Write to sheets
        worksheet.update(f'A1:{chr(ord("A") + max_cols - 1)}{len(padded_data)}', padded_data)

    return worksheet.url


def is_sheets_available() -> bool:
    """Check if Google Sheets dependencies are available."""
    return SHEETS_AVAILABLE
