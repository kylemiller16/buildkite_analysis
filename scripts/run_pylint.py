#!/usr/bin/env python3
"""Run pylint across the repository."""

import argparse
import subprocess
import sys
from pathlib import Path


def find_python_files(root_dir: Path, exclude_dirs: set[str]) -> list[Path]:
    """Find all Python files in the repository, excluding specified directories."""
    python_files = []

    for py_file in root_dir.rglob("*.py"):
        # Skip files in excluded directories
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        python_files.append(py_file)

    return sorted(python_files)


def run_pylint(files: list[Path], args: argparse.Namespace) -> int:
    """Run pylint on the specified files."""
    pylint_args = ["pylint"]

    # Add output format
    if args.format:
        pylint_args.extend(["--output-format", args.format])

    # Add score option
    if args.score:
        pylint_args.append("--score=yes")
    else:
        pylint_args.append("--score=no")

    # Add exit-zero option if specified
    if args.exit_zero:
        pylint_args.append("--exit-zero")

    # Add any additional pylint arguments
    if args.pylint_args:
        pylint_args.extend(args.pylint_args.split())

    # Add files to check
    pylint_args.extend([str(f) for f in files])

    # Run pylint
    try:
        result = subprocess.run(pylint_args, check=False)
        return result.returncode
    except FileNotFoundError:
        print("Error: pylint not found. Please install it with: pip install pylint", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nPylint interrupted by user", file=sys.stderr)
        return 130


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run pylint across the repository",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run pylint on all Python files
  %(prog)s --format colorized       # Use colorized output
  %(prog)s --score                  # Show score
  %(prog)s --exit-zero              # Don't fail on errors
  %(prog)s --pylint-args "--disable=C0111"  # Disable specific checks
        """,
    )

    parser.add_argument(
        "--format",
        choices=["text", "colorized", "json", "parseable", "msvs"],
        default="colorized",
        help="Output format (default: colorized)",
    )

    parser.add_argument(
        "--score",
        action="store_true",
        help="Show score",
    )

    parser.add_argument(
        "--exit-zero",
        action="store_true",
        help="Always return exit code 0, even if linting errors are found",
    )

    parser.add_argument(
        "--pylint-args",
        type=str,
        help="Additional arguments to pass to pylint (space-separated)",
    )

    parser.add_argument(
        "--exclude",
        nargs="+",
        default=["venv", "__pycache__", ".git"],
        help=(
            "Directories to exclude (default: venv __pycache__ .git)"
        ),
    )

    args = parser.parse_args()

    # Get repository root (parent of scripts directory)
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    # Find all Python files
    exclude_dirs = set(args.exclude)
    python_files = find_python_files(repo_root, exclude_dirs)

    if not python_files:
        print("No Python files found to lint.", file=sys.stderr)
        return 1

    print(f"Found {len(python_files)} Python file(s) to lint")
    print(f"Excluding: {', '.join(sorted(exclude_dirs))}")
    print()

    # Run pylint
    return run_pylint(python_files, args)


if __name__ == "__main__":
    sys.exit(main())
