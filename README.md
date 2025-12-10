# Buildkite Analysis Tools

A collection of Python scripts for analyzing Buildkite build data, with intelligent caching to avoid too-many-requests errors.

## Overview

This toolset helps you analyze Buildkite build performance and reliability by:
- Fetching build metadata from the Buildkite API
- Caching data locally to avoid repeated API calls
- Providing flexible filtering and analysis capabilities
- Generating statistical summaries of build performance

## Setup

### Prerequisites

1. **Python 3.8+**: Ensure you have Python 3.8 or later installed
2. **Buildkite API Token**: Create a file at `~/.buildkite_token` containing your Buildkite API token
   ```bash
   echo "your_buildkite_api_token_here" > ~/.buildkite_token
   ```

### Installation

1. **Create and activate a virtual environment** (recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

   This installs:
   - `requests` - For Buildkite API calls
   - `gspread` - For Google Sheets integration (optional)
   - `google-auth` - For Google Sheets authentication (optional)

### Directory Structure

```
buildkite_analysis/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── build_metadata_cache/              # Local cache for build metadata
├── lib/                              # Core library modules
│   ├── __init__.py                   # Package marker
│   ├── analysis.py                   # Main analysis and filtering logic
│   ├── cache.py                      # HTTP request caching
│   ├── filters.py                    # Predefined filter functions
│   ├── spreadsheet.py                 # Google Sheets integration
│   └── util.py                       # Buildkite API utilities
└── scripts/                          # Executable scripts
    ├── save_build_metadata.py        # Cache single build metadata
    ├── save_builds_metadata_for_pipelines.py  # Cache multiple builds
    ├── analyze_cached_builds.py      # Analyze cached data
    ├── aggregate_sheet_summary.py    # Aggregate Google Sheets data
    ├── save_job_output.py            # Download job logs for single build
    └── save_job_output_for_pipelines.py  # Download job logs for multiple builds
```

## Scripts

### 1. save_build_metadata.py

Fetches and caches metadata for a single build.

**Usage:**
```bash
python scripts/save_build_metadata.py --pipeline PIPELINE_SLUG --build BUILD_NUMBER
```

**Options:**
- `--org`: Buildkite organization slug (default: "wayve-dot-ai")
- `--pipeline`: Pipeline slug (required)
- `--build`: Build number (required)

**Example:**
```bash
python scripts/save_build_metadata.py \
  --pipeline federated-custom-hil-gen2-regression --build 497
```

### 2. save_builds_metadata_for_pipelines.py

Fetches and caches metadata for all finished builds across multiple pipelines within a time window.

**Usage:**
```bash
python scripts/save_builds_metadata_for_pipelines.py \
  --pipeline PIPELINE_SLUG [--pipeline PIPELINE_SLUG ...] [--days DAYS] [--branch BRANCH] [--exclude-branch BRANCH ...]
```

**Options:**
- `--org`: Buildkite organization slug (default: "wayve-dot-ai")
- `--pipeline`: Pipeline slug(s) - repeat flag to include multiple pipelines (required)
- `--days`: Lookback window in days (default: 7)
- `--branch`: Only include builds on this branch. Use "non-main" to filter for all non-main branches (optional)
- `--exclude-branch`: Exclude builds on these branches. Can be specified multiple times (optional)

**Examples:**

Save metadata for all builds in the last 30 days:
```bash
python scripts/save_builds_metadata_for_pipelines.py \
  --pipeline federated-custom-hil-gen2-regression \
  --pipeline federated-hil-gen2 \
  --pipeline federated-hil-gen2-igpu \
  --days 30
```

Save metadata only for main branch builds:
```bash
python scripts/save_builds_metadata_for_pipelines.py \
  --pipeline federated-hil-gen2 \
  --branch main \
  --days 14
```

Save metadata for non-main branches, excluding specific ones:
```bash
python scripts/save_builds_metadata_for_pipelines.py \
  --pipeline federated-custom-hil-gen2-regression \
  --branch non-main \
  --exclude-branch develop \
  --exclude-branch 'kyle.miller/testing_gen2_pipeline_stability2' \
  --days 28
```


### 3. analyze_cached_builds.py

Analyzes cached build data with flexible filtering and generates statistical reports.

**Usage:**
```bash
python scripts/analyze_cached_builds.py [OPTIONS]
```

**Options:**
- `--days`: How many days back to analyze (default: 7)
- `--pipeline`: Pipeline slug(s) to include - repeat for multiple pipelines
- `--job-name`: Only include jobs whose name contains any of these substrings - repeat for multiple job names
- `--branch`: Only include jobs from builds on this branch (use "non-main" for all non-main branches)
- `--exclude-branch`: Exclude jobs from builds on these branches - repeat for multiple branches
- `--pst-start`: PST hour (0-23) to start time-of-day filter (default: 0)
- `--pst-end`: PST hour (0-23) to end time-of-day filter (default: 18)
- `--no-pst-filter`: Disable PST time-of-day filtering
- `--print`: Print detailed results for each matching job
- `--sheets-output`: Export results to Google Sheets
- `--sheets-id`: Google Sheets ID or full URL for output
- `--sheets-tab`: Worksheet tab name (default: BuildkiteAnalysis)
- `--sheets-credentials`: Path to Google Sheets service account credentials JSON file

**Examples:**

Analyze Gen2 Post-submit jobs in the last 28 days for main branch
```bash
python scripts/analyze_cached_builds.py \
  --pipeline federated-hil-gen2 \
  --pipeline federated-hil-gen2-igpu \
  --job-name federated-hil-gen2-validation-rcm-aem-evt-1 \
  --job-name federated-hil-gen2-igpu-validation-rcm-aem-evt-1-igpu \
  --pst-start 0 --pst-end 18 \
  --branch main \
  --days 28
```

Analyze Gen2 Post-submit jobs in the last 28 days for non-main branch
```bash
python scripts/analyze_cached_builds.py \
  --pipeline federated-hil-gen2 \
  --pipeline federated-hil-gen2-igpu \
  --job-name federated-hil-gen2-validation-rcm-aem-evt-1 \
  --job-name federated-hil-gen2-igpu-validation-rcm-aem-evt-1-igpu \
  --pst-start 0 --pst-end 18 \
  --branch non-main \
  --exclude-branch 'kyle.miller/testing_gen2_pipeline_stability2' \
  --days 28
```

Analyze Gen2 Pre-submit jobs in the last 28 days for all feature branches
```bash
python scripts/analyze_cached_builds.py \
  --pipeline federated-custom-hil-gen2-regression \
  --job-name federated-custom-hil-gen2-regression-validation-rcm-aem-evt-1 \
  --job-name federated-custom-hil-gen2-regression-validation-rcm-aem-evt-1-igpu \
  --pst-start 0 --pst-end 18 \
  --branch non-main \
  --days 28
```

Export analysis results to Google Sheets
```bash
python scripts/analyze_cached_builds.py \
  --pipeline federated-hil-gen2 \
  --job-name validation \
  --days 7 \
  --sheets-output \
  --sheets-id "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" \
  --sheets-credentials "/path/to/service-account.json" \
  --sheets-tab "WeeklyAnalysis"
```

Combine console output with Google Sheets export
```bash
python scripts/analyze_cached_builds.py \
  --pipeline federated-custom-hil-gen2-regression \
  --exclude-branch main \
  --exclude-branch develop \
  --days 14 \
  --print \
  --sheets-output \
  --sheets-id "https://docs.google.com/spreadsheets/d/abc123xyz/edit" \
  --sheets-credentials "~/.config/gcp/buildkite-analysis-sa.json"
```


### 4. aggregate_sheet_summary.py

Aggregates data across all tabs in a Google Sheet and creates a summary tab.

**Usage:**
```bash
python scripts/aggregate_sheet_summary.py \
  --sheets-id SHEET_ID \
  --sheets-credentials CREDENTIALS_PATH \
  [--summary-tab TAB_NAME] \
  [--exclude-tabs TAB_NAME ...]
```

**Options:**
- `--sheets-id`: Google Sheets ID or URL (required)
- `--sheets-credentials`: Path to Google Sheets service account credentials JSON file (required)
- `--summary-tab`: Name for the summary tab (default: "Summary")
- `--exclude-tabs`: Tab names to exclude from aggregation (can be specified multiple times)

**Example:**
```bash
python scripts/aggregate_sheet_summary.py \
  --sheets-id "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms" \
  --sheets-credentials "~/.config/gcp/buildkite-analysis-sa.json" \
  --summary-tab "Aggregated" \
  --exclude-tabs "Summary" \
  --exclude-tabs "Aggregated"
```

### 5. save_job_output.py

Downloads raw logs for validation jobs from Buildkite build metadata.

**Usage:**
```bash
python scripts/save_job_output.py --pipeline PIPELINE_SLUG --build BUILD_NUMBER
```

**Options:**
- `--org`: Buildkite organization slug (default: "wayve-dot-ai")
- `--pipeline`: Pipeline slug (required)
- `--build`: Build number (required)

**Example:**
```bash
python scripts/save_job_output.py \
  --pipeline federated-custom-hil-gen2-regression \
  --build 497
```

### 6. save_job_output_for_pipelines.py

Downloads raw logs for validation jobs from all finished builds across multiple pipelines within a time window.

**Usage:**
```bash
python scripts/save_job_output_for_pipelines.py \
  --pipeline PIPELINE_SLUG [--pipeline PIPELINE_SLUG ...] [--days DAYS] [--branch BRANCH] [--exclude-branch BRANCH ...] [--output-dir DIR]
```

**Options:**
- `--org`: Buildkite organization slug (default: "wayve-dot-ai")
- `--pipeline`: Pipeline slug(s) - repeat flag to include multiple pipelines (required)
- `--days`: Lookback window in days (default: 7)
- `--branch`: Only include builds on this branch. Use "non-main" to filter for all non-main branches (optional)
- `--exclude-branch`: Exclude builds on these branches. Can be specified multiple times (optional)
- `--output-dir`: Directory to save job logs (default: same as build metadata cache directory)

**Examples:**

Download job logs for all builds in the last 30 days:
```bash
python scripts/save_job_output_for_pipelines.py \
  --pipeline federated-custom-hil-gen2-regression \
  --pipeline federated-hil-gen2 \
  --pipeline federated-hil-gen2-igpu \
  --days 30
```

Download job logs only for main branch builds:
```bash
python scripts/save_job_output_for_pipelines.py \
  --pipeline federated-hil-gen2 \
  --branch main \
  --days 14
```

Download job logs for non-main branches, excluding specific branches:
```bash
python scripts/save_job_output_for_pipelines.py \
  --pipeline federated-custom-hil-gen2-regression \
  --branch non-main \
  --exclude-branch develop \
  --exclude-branch 'kyle.miller/testing_gen2_pipeline_stability2' \
  --days 28
```

This script will:
- Fetch build metadata for all finished builds in the specified time window
- Find all validation jobs in each build (jobs with "validation" in the name)
- Download the raw logs for those jobs
- Save logs in the same directory as build metadata (or specified output directory)
- Skip logs that have already been downloaded

## Google Sheets Setup

To use Google Sheets output, you need:

1. **Install dependencies** (already included in requirements.txt): `pip install gspread google-auth`
2. **Create a Google Cloud service account**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create/select a project
   - Enable Google Sheets API
   - Create a service account
   - Download the credentials JSON file
3. **Share your Google Sheet** with the service account email
4. **Get the Sheet ID** from the URL: `https://docs.google.com/spreadsheets/d/SHEET_ID/edit`

The script will:
- Create a new worksheet tab if it doesn't exist
- Clear and overwrite existing data
- Include all analysis sections (daily summaries, totals, averages, HiL resources)
- Add timestamp to track when the analysis was run


## Output Format

The analysis script generates several types of output:

### Summary Statistics
- **Matches**: Total number of jobs matching filters
- **Daily Summaries**: Separate per-job, per-day breakdown (Monday-Friday only) for each pipeline/job combination, showing:
  - Day and date
  - Job count
  - Total duration
  - Average duration (overall, pass-only, fail-only)
  - Average wait time
  - Pass/fail counts

### Overall Statistics
Separate statistics for each pipeline/job combination:
- **Count per day**: Min/max/median/average job counts
- **Average duration per day**: Min/max/median/average durations
- **Total duration per day**: Min/max/median/average total time

### Detailed Job List (with --print)
When using `--print`, each matching job shows:
- Pipeline slug
- Build number
- Job name
- Web URL

