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

 **Buildkite API Token**: Create a file at `~/.buildkite_token` containing your Buildkite API token
   ```bash
   echo "your_buildkite_api_token_here" > ~/.buildkite_token
   ```


### Directory Structure

```
buildkite_analysis/
├── README.md                          # This file
├── BUILD                              # Bazel build configuration
├── build_metadata_cache/              # Local cache for build metadata
├── lib/                              # Core library modules
│   ├── analysis.py                   # Main analysis and filtering logic
│   ├── cache.py                      # HTTP request caching
│   ├── filters.py                    # Predefined filter functions
│   └── util.py                       # Buildkite API utilities
└── scripts/                          # Executable scripts
    ├── save_build_metadata.py        # Cache single build metadata
    ├── save_builds_metadata_for_pipelines.py  # Cache multiple builds
    └── analyze_cached_builds.py      # Analyze cached data
```

## Scripts

### 1. save_build_metadata.py

Fetches and caches metadata for a single build.

**Usage:**
```bash

bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:save_build_metadata -- \
  --pipeline PIPELINE_SLUG --build BUILD_NUMBER
```

**Options:**
- `--org`: Buildkite organization slug (default: "wayve-dot-ai")
- `--pipeline`: Pipeline slug (required)
- `--build`: Build number (required)

**Example:**
```bash
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:save_build_metadata -- \
  --pipeline federated-custom-hil-gen2-regression --build 497
```

### 2. save_builds_metadata_for_pipelines.py

Fetches and caches metadata for all finished builds across multiple pipelines within a time window.

**Usage:**
```bash
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:save_builds_metadata_for_pipelines -- \
  --pipeline federated-custom-hil-gen2-regression --pipeline federated-hil-gen2 --pipeline federated-hil-gen2-igpu --days 30

```

**Options:**
- `--org`: Buildkite organization slug (default: "wayve-dot-ai")
- `--pipeline`: Pipeline slug(s) - repeat flag to include multiple pipelines (required)
- `--days`: Lookback window in days (default: 7)


### 3. analyze_cached_builds.py

Analyzes cached build data with flexible filtering and generates statistical reports.

**Usage:**
```bash
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:analyze_cached_builds -- [OPTIONS]
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

Analyze Gen2 Post-submit jobs in the last 28 for main branch
```bash
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:analyze_cached_builds -- \
  --pipeline federated-hil-gen2 \
  --pipeline federated-hil-gen2-igpu \
  --job-name federated-hil-gen2-validation-rcm-aem-evt-1 \
  --job-name federated-hil-gen2-igpu-validation-rcm-aem-evt-1-igpu \
  --pst-start 0 --pst-end 18 \
  --branch main \
  --days 28
```

Analyze Gen2 Post-submit jobs in the last 28 for non-main branch
```bash
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:analyze_cached_builds -- \
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
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:analyze_cached_builds -- \
  --pipeline federated-custom-hil-gen2-regression \
  --job-name federated-custom-hil-gen2-regression-validation-rcm-aem-evt-1 \
  --job-name federated-custom-hil-gen2-regression-validation-rcm-aem-evt-1-igpu \
  --pst-start 0 --pst-end 18 \
  --branch non-main \
  --days 28
```

Export analysis results to Google Sheets
```bash
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:analyze_cached_builds -- \
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
bazel run //wayve/robot/hil_tests/tools/buildkite_analysis:analyze_cached_builds -- \
  --pipeline federated-custom-hil-gen2-regression \
  --exclude-branch main \
  --exclude-branch develop \
  --days 14 \
  --print \
  --sheets-output \
  --sheets-id "https://docs.google.com/spreadsheets/d/abc123xyz/edit" \
  --sheets-credentials "~/.config/gcp/buildkite-analysis-sa.json"
```


## Google Sheets Setup

To use Google Sheets output, you need:

1. **Install dependencies**: `pip install gspread google-auth`
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

