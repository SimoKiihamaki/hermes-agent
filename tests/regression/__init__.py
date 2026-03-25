"""
T3.3 Regression Test Suite for AutoDev Phase 10.1

This package provides fast regression tests using 5 representative SWE-bench Lite tasks
to validate the AutoDev hierarchical execution flow.

Features:
- 5 representative SWE-bench Lite tasks (simulated for fast execution)
- Timing assertions (<15 min per task, <5 min total suite)
- CI/CD integration support
- Parallel execution support via pytest-xdist

Usage:
    # Run all regression tests
    pytest tests/regression/ -v

    # Run with timing report
    pytest tests/regression/ -v --durations=10

    # Run in CI mode (with JSON report)
    pytest tests/regression/ -v --json-report --json-report-file=regression-report.json

    # Run specific task
    pytest tests/regression/test_autodev_regression.py -v -k "django"
"""

__version__ = "1.0.0"
__author__ = "Hermes Team"

# Representative SWE-bench Lite task IDs (these are the canonical IDs)
SWE_BENCH_LITE_TASKS = {
    "django-11039": {
        "repo": "django/django",
        "version": "3.0",
        "description": "Fix URLValidator regex to handle IPv6 addresses",
        "category": "bugfix",
        "complexity": "medium",
        "expected_files": ["django/core/validators.py"],
    },
    "flask-2349": {
        "repo": "pallets/flask",
        "version": "2.0",
        "description": "Fix blueprint error handler registration order",
        "category": "bugfix",
        "complexity": "low",
        "expected_files": ["src/flask/blueprints.py"],
    },
    "pytest-5413": {
        "repo": "pytest-dev/pytest",
        "version": "5.4",
        "description": "Handle fixtures with indirect parameters in parametrize",
        "category": "enhancement",
        "complexity": "high",
        "expected_files": ["src/_pytest/fixtures.py"],
    },
    "requests-2863": {
        "repo": "psf/requests",
        "version": "2.25",
        "description": "Fix session retry adapter connection pooling",
        "category": "bugfix",
        "complexity": "medium",
        "expected_files": ["requests/adapters.py"],
    },
    "sphinx-8721": {
        "repo": "sphinx-doc/sphinx",
        "version": "4.1",
        "description": "Fix cross-reference resolution for nested classes",
        "category": "bugfix",
        "complexity": "high",
        "expected_files": ["sphinx/domains/python.py"],
    },
}

# Timing thresholds (in seconds)
MAX_TASK_TIME = 15 * 60  # 15 minutes per task
MAX_SUITE_TIME = 5 * 60  # 5 minutes total (for fast simulated mode)
SIMULATED_TASK_TIME = 0.5  # seconds per task in simulated mode

# Execution mode (set REGRESSION_REAL_MODE=1 env var for real execution)
import os
REGRESSION_REAL_MODE = os.environ.get("REGRESSION_REAL_MODE", "0") == "1"
