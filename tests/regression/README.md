# T3.3 Regression Test Suite for AutoDev Phase 10.1

Fast regression tests using 5 representative SWE-bench Lite tasks to validate the AutoDev hierarchical execution flow.

## Overview

This test suite provides:

- **5 Representative SWE-bench Lite Tasks**: Curated tasks covering different categories (bugfix, enhancement) and complexity levels (low, medium, high)
- **Timing Assertions**: Each task must complete within 15 minutes; full suite in simulated mode must complete within 5 minutes
- **CI/CD Integration**: JSON reports, JUnit XML support, and configurable exit codes
- **Fast Execution**: Simulated mode enables quick validation without LLM calls

## Quick Start

```bash
# Run all regression tests (simulated mode - fast)
cd ~/Projects/hermes-agent
pytest tests/regression/ -v

# Run with timing report
pytest tests/regression/ -v --durations=10

# Run using the CI/CD script
python tests/regression/run_regression.py
```

## Test Tasks

| Task ID | Repository | Category | Complexity | Description |
|---------|------------|----------|------------|-------------|
| django-11039 | django/django | bugfix | medium | Fix URLValidator regex for IPv6 |
| flask-2349 | pallets/flask | bugfix | low | Fix blueprint error handler order |
| pytest-5413 | pytest-dev/pytest | enhancement | high | Handle indirect params in fixtures |
| requests-2863 | psf/requests | bugfix | medium | Fix session retry adapter pooling |
| sphinx-8721 | sphinx-doc/sphinx | bugfix | high | Fix cross-reference for nested classes |

## Timing Requirements

- **Per Task**: < 15 minutes (900 seconds)
- **Full Suite (simulated)**: < 5 minutes (300 seconds)
- **Full Suite (real mode)**: < 75 minutes (5 × 15 min)

## Running Tests

### Simulated Mode (Default)

Fast execution for PR validation and CI pipelines:

```bash
# Run all tests
pytest tests/regression/ -v

# Run specific task tests
pytest tests/regression/test_autodev_regression.py -v -k "django"

# Run timing tests only
pytest tests/regression/test_autodev_regression.py -v -k "timing"
```

### Real Mode (Requires AutoDev)

Full execution with actual AutoDev components:

```bash
REGRESSION_REAL_MODE=1 pytest tests/regression/ -v
```

## CI/CD Integration

### Using the Runner Script

```bash
# Basic run with JSON report
python tests/regression/run_regression.py --output ./artifacts/report.json

# With JUnit XML for Jenkins/GitHub Actions
python tests/regression/run_regression.py \
    --output ./artifacts/report.json \
    --junit-xml ./artifacts/junit.xml

# Fail on time budget exceeded
python tests/regression/run_regression.py --fail-on-timeout

# Real mode
python tests/regression/run_regression.py --real-mode
```

### GitHub Actions Example

```yaml
name: AutoDev Regression Tests

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

jobs:
  regression:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
      
      - name: Run Regression Tests
        run: |
          python tests/regression/run_regression.py \
            --output ${{ github.workspace }}/regression_report.json \
            --junit-xml ${{ github.workspace }}/junit.xml
      
      - name: Upload Report
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: regression-report
          path: |
            ${{ github.workspace }}/regression_report.json
            ${{ github.workspace }}/junit.xml
```

### GitLab CI Example

```yaml
autodev-regression:
  stage: test
  script:
    - pip install -e ".[dev]"
    - python tests/regression/run_regression.py
        --output regression_report.json
        --junit-xml junit.xml
  artifacts:
    when: always
    reports:
      junit: junit.xml
    paths:
      - regression_report.json
  timeout: 15m
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All tests passed |
| 1 | Some tests failed |
| 2 | Test execution error (e.g., timeout) |
| 3 | Time budget exceeded (with `--fail-on-timeout`) |

## Output Format

### JSON Report Structure

```json
{
  "timestamp": "2026-03-24T22:30:00Z",
  "total_tasks": 5,
  "passed": 5,
  "failed": 0,
  "total_duration_seconds": 3.456,
  "average_duration_seconds": 0.691,
  "max_task_time_seconds": 900,
  "max_suite_time_seconds": 300,
  "time_budget_exceeded": false,
  "tasks": [
    {
      "task_id": "django-11039",
      "status": "passed",
      "duration_seconds": 1.0,
      "files_modified": ["django/core/validators.py"],
      "iterations": 2,
      "review_iterations": 1,
      "error_message": null,
      "summary": "Successfully completed bugfix task for django/django"
    }
  ]
}
```

## Test Classes

### TestAutoDevRegressionSuite

Main test class containing the 5 SWE-bench task tests:
- `test_django_11039_ipv6_validator` - Medium complexity bugfix
- `test_flask_2349_blueprint_handlers` - Low complexity bugfix
- `test_pytest_5413_indirect_params` - High complexity enhancement
- `test_requests_2863_session_retry` - Medium complexity bugfix
- `test_sphinx_8721_cross_reference` - High complexity bugfix

### TestSuiteTiming

Timing validation tests:
- `test_suite_total_time` - Validates suite completes within time budget
- `test_generate_regression_report` - Generates final CI/CD report

### TestHierarchicalExecution

Tests for the Manager → Coder → Reviewer flow:
- `test_manager_coder_reviewer_flow` - Validates execution phases
- `test_complexity_based_iterations` - Validates iteration scaling
- `test_file_modification_tracking` - Validates file tracking

### TestCICDIntegration

CI/CD integration tests:
- `test_json_report_generation` - Validates report generation
- `test_environment_mode` - Validates mode detection
- `test_time_budget_constants` - Validates configuration

## Extending the Suite

To add new tasks, update `tests/regression/__init__.py`:

```python
SWE_BENCH_LITE_TASKS = {
    # ... existing tasks ...
    "new-task-123": {
        "repo": "owner/repo",
        "version": "1.0",
        "description": "Task description",
        "category": "bugfix",  # or "enhancement"
        "complexity": "medium",  # low, medium, or high
        "expected_files": ["path/to/file.py"],
    },
}
```

Then add a corresponding test method in `test_autodev_regression.py`.

## Troubleshooting

### Tests timeout

- Ensure you're running in simulated mode (default)
- Check that no external services are blocking
- Reduce task complexity or increase timeout

### Import errors

- Ensure project is installed: `pip install -e ".[dev]"`
- Check PYTHONPATH includes project root

### Real mode fails

- Verify AutoDev components are available
- Check AUTODEV_PATH environment variable
- Ensure API keys are configured for LLM calls
