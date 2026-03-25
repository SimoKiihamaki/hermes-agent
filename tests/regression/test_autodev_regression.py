"""
T3.3 AutoDev Regression Test Suite - Phase 10.1

This module contains 5 representative SWE-bench Lite tasks for fast regression testing
of the AutoDev hierarchical execution flow.

Task Categories:
- Bugfix: django-11039, flask-2349, requests-2863, sphinx-8721
- Enhancement: pytest-5413

Complexity Distribution:
- Low: flask-2349
- Medium: django-11039, requests-2863
- High: pytest-5413, sphinx-8721

Timing Requirements:
- Each task: < 15 minutes (900 seconds)
- Full suite: < 5 minutes (300 seconds) in simulated mode

Run with:
    pytest tests/regression/test_autodev_regression.py -v

For CI/CD with JSON report:
    pytest tests/regression/test_autodev_regression.py -v \\
        --json-report --json-report-file=regression-report.json
"""

import asyncio
import time
from pathlib import Path
from typing import Dict

import pytest

from tests.regression import (
    SWE_BENCH_LITE_TASKS,
    MAX_TASK_TIME,
    MAX_SUITE_TIME,
    SIMULATED_TASK_TIME,
    REGRESSION_REAL_MODE,
)
from tests.regression.conftest import (
    SWEBenchTask,
    TaskExecutionResult,
    simulate_task_execution,
    real_task_execution,
    generate_regression_report,
)


# =========================================================================
# Test Suite Start Time
# =========================================================================

_suite_start_time: float = 0
_suite_results: list = []


def pytest_runtest_setup(item):
    """Record suite start time before first test."""
    global _suite_start_time
    if _suite_start_time == 0:
        _suite_start_time = time.monotonic()


def pytest_runtest_teardown(item, nextitem):
    """Collect results after each test."""
    global _suite_results


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture
def task_django_11039(swebench_tasks) -> SWEBenchTask:
    """Django URLValidator IPv6 bugfix task (medium complexity)."""
    return swebench_tasks["django-11039"]


@pytest.fixture
def task_flask_2349(swebench_tasks) -> SWEBenchTask:
    """Flask blueprint error handler task (low complexity)."""
    return swebench_tasks["flask-2349"]


@pytest.fixture
def task_pytest_5413(swebench_tasks) -> SWEBenchTask:
    """Pytest fixtures with indirect parameters task (high complexity)."""
    return swebench_tasks["pytest-5413"]


@pytest.fixture
def task_requests_2863(swebench_tasks) -> SWEBenchTask:
    """Requests session retry adapter task (medium complexity)."""
    return swebench_tasks["requests-2863"]


@pytest.fixture
def task_sphinx_8721(swebench_tasks) -> SWEBenchTask:
    """Sphinx cross-reference resolution task (high complexity)."""
    return swebench_tasks["sphinx-8721"]


# =========================================================================
# Test Class: AutoDev Regression Suite
# =========================================================================

@pytest.mark.regression
@pytest.mark.swebench
@pytest.mark.timing
class TestAutoDevRegressionSuite:
    """
    AutoDev Regression Test Suite for Phase 10.1.
    
    Tests hierarchical execution flow with 5 representative SWE-bench tasks.
    Each test validates:
    1. Task executes without errors
    2. Execution completes within time budget
    3. Files are properly identified for modification
    4. Iteration counts are within expected ranges
    """
    
    @pytest.mark.asyncio
    @pytest.mark.order(1)
    async def test_django_11039_ipv6_validator(
        self,
        task_django_11039: SWEBenchTask,
        mock_autodev_bridge,
        timing_assertion,
        regression_results_dir,
    ):
        """
        Task: django-11039
        Category: Bugfix
        Complexity: Medium
        
        Tests fix for URLValidator regex to properly handle IPv6 addresses.
        Expected files: django/core/validators.py
        Time budget: < 15 minutes (real) or < 1 second (simulated)
        """
        start_time = time.monotonic()
        
        if REGRESSION_REAL_MODE:
            result = await real_task_execution(task_django_11039, mock_autodev_bridge)
        else:
            result = await simulate_task_execution(
                task_django_11039,
                duration=SIMULATED_TASK_TIME * 2,  # Medium complexity
            )
        
        elapsed = time.monotonic() - start_time
        
        # Timing assertion
        timing_assertion(elapsed, MAX_TASK_TIME, "django-11039")
        
        # Status assertion
        assert result.status == "passed", f"Task failed: {result.error_message}"
        
        # File modification assertion
        assert len(result.files_modified) > 0, "No files were modified"
        assert "django/core/validators.py" in result.files_modified or \
               any("validators" in f for f in result.files_modified), \
               f"Expected validators.py in modified files, got: {result.files_modified}"
        
        # Iteration assertion (medium complexity = 2 iterations expected in sim mode)
        assert result.iterations >= 1, f"Expected at least 1 iteration, got {result.iterations}"
        
        _suite_results.append(result)
    
    @pytest.mark.asyncio
    @pytest.mark.order(2)
    async def test_flask_2349_blueprint_handlers(
        self,
        task_flask_2349: SWEBenchTask,
        mock_autodev_bridge,
        timing_assertion,
        regression_results_dir,
    ):
        """
        Task: flask-2349
        Category: Bugfix
        Complexity: Low
        
        Tests fix for blueprint error handler registration order.
        Expected files: src/flask/blueprints.py
        Time budget: < 15 minutes (real) or < 0.5 second (simulated)
        """
        start_time = time.monotonic()
        
        if REGRESSION_REAL_MODE:
            result = await real_task_execution(task_flask_2349, mock_autodev_bridge)
        else:
            result = await simulate_task_execution(
                task_flask_2349,
                duration=SIMULATED_TASK_TIME,  # Low complexity
            )
        
        elapsed = time.monotonic() - start_time
        
        # Timing assertion
        timing_assertion(elapsed, MAX_TASK_TIME, "flask-2349")
        
        # Status assertion
        assert result.status == "passed", f"Task failed: {result.error_message}"
        
        # File modification assertion
        assert len(result.files_modified) > 0, "No files were modified"
        assert "blueprints.py" in str(result.files_modified) or \
               any("blueprint" in f for f in result.files_modified), \
               f"Expected blueprints.py in modified files, got: {result.files_modified}"
        
        # Iteration assertion (low complexity = 1 iteration expected)
        assert result.iterations >= 1, f"Expected at least 1 iteration, got {result.iterations}"
        
        _suite_results.append(result)
    
    @pytest.mark.asyncio
    @pytest.mark.order(3)
    async def test_pytest_5413_indirect_params(
        self,
        task_pytest_5413: SWEBenchTask,
        mock_autodev_bridge,
        timing_assertion,
        regression_results_dir,
    ):
        """
        Task: pytest-5413
        Category: Enhancement
        Complexity: High
        
        Tests handling of fixtures with indirect parameters in parametrize.
        Expected files: src/_pytest/fixtures.py
        Time budget: < 15 minutes (real) or < 1.5 seconds (simulated)
        """
        start_time = time.monotonic()
        
        if REGRESSION_REAL_MODE:
            result = await real_task_execution(task_pytest_5413, mock_autodev_bridge)
        else:
            result = await simulate_task_execution(
                task_pytest_5413,
                duration=SIMULATED_TASK_TIME * 3,  # High complexity
            )
        
        elapsed = time.monotonic() - start_time
        
        # Timing assertion
        timing_assertion(elapsed, MAX_TASK_TIME, "pytest-5413")
        
        # Status assertion
        assert result.status == "passed", f"Task failed: {result.error_message}"
        
        # File modification assertion
        assert len(result.files_modified) > 0, "No files were modified"
        assert "fixtures.py" in str(result.files_modified) or \
               any("fixtures" in f for f in result.files_modified), \
               f"Expected fixtures.py in modified files, got: {result.files_modified}"
        
        # Iteration assertion (high complexity = 3 iterations expected in sim mode)
        assert result.iterations >= 2, f"Expected at least 2 iterations for high complexity, got {result.iterations}"
        
        _suite_results.append(result)
    
    @pytest.mark.asyncio
    @pytest.mark.order(4)
    async def test_requests_2863_session_retry(
        self,
        task_requests_2863: SWEBenchTask,
        mock_autodev_bridge,
        timing_assertion,
        regression_results_dir,
    ):
        """
        Task: requests-2863
        Category: Bugfix
        Complexity: Medium
        
        Tests fix for session retry adapter connection pooling.
        Expected files: requests/adapters.py
        Time budget: < 15 minutes (real) or < 1 second (simulated)
        """
        start_time = time.monotonic()
        
        if REGRESSION_REAL_MODE:
            result = await real_task_execution(task_requests_2863, mock_autodev_bridge)
        else:
            result = await simulate_task_execution(
                task_requests_2863,
                duration=SIMULATED_TASK_TIME * 2,  # Medium complexity
            )
        
        elapsed = time.monotonic() - start_time
        
        # Timing assertion
        timing_assertion(elapsed, MAX_TASK_TIME, "requests-2863")
        
        # Status assertion
        assert result.status == "passed", f"Task failed: {result.error_message}"
        
        # File modification assertion
        assert len(result.files_modified) > 0, "No files were modified"
        assert "adapters.py" in str(result.files_modified) or \
               any("adapter" in f for f in result.files_modified), \
               f"Expected adapters.py in modified files, got: {result.files_modified}"
        
        # Iteration assertion
        assert result.iterations >= 1, f"Expected at least 1 iteration, got {result.iterations}"
        
        _suite_results.append(result)
    
    @pytest.mark.asyncio
    @pytest.mark.order(5)
    async def test_sphinx_8721_cross_reference(
        self,
        task_sphinx_8721: SWEBenchTask,
        mock_autodev_bridge,
        timing_assertion,
        regression_results_dir,
    ):
        """
        Task: sphinx-8721
        Category: Bugfix
        Complexity: High
        
        Tests fix for cross-reference resolution for nested classes.
        Expected files: sphinx/domains/python.py
        Time budget: < 15 minutes (real) or < 1.5 seconds (simulated)
        """
        start_time = time.monotonic()
        
        if REGRESSION_REAL_MODE:
            result = await real_task_execution(task_sphinx_8721, mock_autodev_bridge)
        else:
            result = await simulate_task_execution(
                task_sphinx_8721,
                duration=SIMULATED_TASK_TIME * 3,  # High complexity
            )
        
        elapsed = time.monotonic() - start_time
        
        # Timing assertion
        timing_assertion(elapsed, MAX_TASK_TIME, "sphinx-8721")
        
        # Status assertion
        assert result.status == "passed", f"Task failed: {result.error_message}"
        
        # File modification assertion
        assert len(result.files_modified) > 0, "No files were modified"
        assert "python.py" in str(result.files_modified) or \
               any("domain" in f for f in result.files_modified), \
               f"Expected python.py or domain file in modified files, got: {result.files_modified}"
        
        # Iteration assertion (high complexity = 3 iterations expected in sim mode)
        assert result.iterations >= 2, f"Expected at least 2 iterations for high complexity, got {result.iterations}"
        
        _suite_results.append(result)


# =========================================================================
# Suite-Level Timing Test
# =========================================================================

@pytest.mark.regression
@pytest.mark.timing
class TestSuiteTiming:
    """Tests for overall suite timing and performance."""
    
    @pytest.mark.asyncio
    @pytest.mark.order(6)
    async def test_suite_total_time(self, regression_results_dir):
        """
        Validates that the entire regression suite completes within time budget.
        
        In simulated mode: < 5 minutes total
        In real mode: < 75 minutes total (5 tasks × 15 minutes each)
        """
        global _suite_start_time
        
        # This test runs after all task tests, so we can check total time
        if _suite_start_time > 0:
            total_elapsed = time.monotonic() - _suite_start_time
            
            # In simulated mode, suite should be very fast
            if not REGRESSION_REAL_MODE:
                assert total_elapsed < MAX_SUITE_TIME, (
                    f"Suite exceeded time budget: {total_elapsed:.2f}s > {MAX_SUITE_TIME}s. "
                    "Check for slow tests or test configuration issues."
                )
            
            print(f"\n✓ Suite completed in {total_elapsed:.2f} seconds")
    
    def test_generate_regression_report(self, regression_results_dir):
        """Generate final regression report for CI/CD."""
        global _suite_results, _suite_start_time
        
        if _suite_results:
            total_elapsed = time.monotonic() - _suite_start_time if _suite_start_time > 0 else 0
            
            report_path = regression_results_dir / "regression_report.json"
            report = generate_regression_report(_suite_results, report_path)
            
            print(f"\n{'='*60}")
            print("REGRESSION TEST REPORT")
            print(f"{'='*60}")
            print(f"Total Tasks: {report['total_tasks']}")
            print(f"Passed: {report['passed']}")
            print(f"Failed: {report['failed']}")
            print(f"Total Duration: {report['total_duration_seconds']:.3f}s")
            print(f"Report saved to: {report_path}")
            print(f"{'='*60}\n")
            
            # Assert all tasks passed
            assert report['failed'] == 0, (
                f"{report['failed']} tasks failed. Check report at {report_path}"
            )


# =========================================================================
# Hierarchical Execution Tests
# =========================================================================

@pytest.mark.regression
class TestHierarchicalExecution:
    """Tests for AutoDev hierarchical execution flow."""
    
    @pytest.mark.asyncio
    async def test_manager_coder_reviewer_flow(self, mock_autodev_bridge):
        """
        Validates the Manager → Coder → Reviewer execution flow.
        
        The hierarchical flow should:
        1. Manager decomposes the task
        2. Coder implements the solution
        3. Reviewer validates the changes
        """
        # Create a simple task
        task = SWEBenchTask(
            task_id="test-flow",
            repo="test/repo",
            version="1.0",
            description="Test hierarchical flow",
            category="test",
            complexity="low",
            expected_files=["test.py"],
        )
        
        # Execute
        result = await simulate_task_execution(task, duration=0.1)
        
        # Validate flow executed
        assert result.status == "passed"
        assert result.iterations >= 1, "Manager-Coder flow should execute at least once"
        assert result.review_iterations >= 1, "Reviewer should validate at least once"
    
    @pytest.mark.asyncio
    async def test_complexity_based_iterations(self):
        """
        Validates that task complexity affects iteration count.
        
        High complexity tasks should require more iterations.
        """
        low_task = SWEBenchTask(
            task_id="low-complexity",
            repo="test/repo",
            version="1.0",
            description="Low complexity task",
            category="test",
            complexity="low",
            expected_files=["test.py"],
        )
        
        high_task = SWEBenchTask(
            task_id="high-complexity",
            repo="test/repo",
            version="1.0",
            description="High complexity task",
            category="test",
            complexity="high",
            expected_files=["test.py"],
        )
        
        low_result = await simulate_task_execution(low_task, duration=0.1)
        high_result = await simulate_task_execution(high_task, duration=0.1)
        
        # High complexity should have more iterations
        assert high_result.iterations > low_result.iterations, (
            f"High complexity ({high_result.iterations} iters) should exceed "
            f"low complexity ({low_result.iterations} iters)"
        )
    
    @pytest.mark.asyncio
    async def test_file_modification_tracking(self):
        """
        Validates that expected files are tracked for modification.
        """
        task = SWEBenchTask(
            task_id="file-track-test",
            repo="test/repo",
            version="1.0",
            description="File tracking test",
            category="test",
            complexity="low",
            expected_files=["file1.py", "file2.py", "file3.py"],
        )
        
        result = await simulate_task_execution(task, duration=0.1)
        
        assert len(result.files_modified) == 3
        assert "file1.py" in result.files_modified
        assert "file2.py" in result.files_modified
        assert "file3.py" in result.files_modified


# =========================================================================
# CI/CD Integration Tests
# =========================================================================

@pytest.mark.regression
class TestCICDIntegration:
    """Tests for CI/CD integration and reporting."""
    
    def test_json_report_generation(self, regression_results_dir):
        """Test that JSON reports can be generated for CI/CD."""
        report_path = regression_results_dir / "test_report.json"
        
        # Create a sample result
        result = TaskExecutionResult(
            task_id="ci-test",
            status="passed",
            duration_seconds=0.5,
            files_modified=["test.py"],
            iterations=1,
            review_iterations=1,
            summary="CI test passed",
        )
        
        report = generate_regression_report([result], report_path)
        
        assert report_path.exists(), "Report file should be created"
        assert report["total_tasks"] == 1
        assert report["passed"] == 1
        assert report["failed"] == 0
    
    def test_environment_mode(self, regression_mode):
        """Test that regression mode is correctly detected."""
        # This validates the environment variable is read correctly
        assert regression_mode in ("simulated", "real")
        
        if REGRESSION_REAL_MODE:
            assert regression_mode == "real"
        else:
            assert regression_mode == "simulated"
    
    def test_time_budget_constants(self):
        """Validate time budget constants are set correctly."""
        assert MAX_TASK_TIME == 900, "MAX_TASK_TIME should be 15 minutes (900s)"
        assert MAX_SUITE_TIME == 300, "MAX_SUITE_TIME should be 5 minutes (300s)"


# =========================================================================
# Entry Point for Standalone Execution
# =========================================================================

if __name__ == "__main__":
    """Run regression tests directly for quick validation."""
    import sys
    
    print("Running AutoDev Regression Suite (standalone mode)...")
    print(f"Mode: {'Real' if REGRESSION_REAL_MODE else 'Simulated'}")
    print(f"Max task time: {MAX_TASK_TIME}s")
    print(f"Max suite time: {MAX_SUITE_TIME}s")
    print("-" * 40)
    
    # Run pytest programmatically
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        f"--json-report-file=regression_report.json" 
        if "--json-report" in sys.argv else "",
    ])
    
    sys.exit(exit_code)
