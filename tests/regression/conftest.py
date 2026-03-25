"""
Configuration and fixtures for AutoDev Regression Tests.

Provides:
- Simulated SWE-bench task fixtures
- Timing measurement utilities
- Mock AutoDev components for fast execution
- CI/CD integration helpers
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =========================================================================
# IMPORTANT: Block autodev imports BEFORE importing project modules
# This prevents loading heavy dependencies (torch, transformers, etc.)
# =========================================================================

# Block autodev-related imports to avoid heavy dependencies
_BLOCKED_MODULES = [
    'agents', 'agents.base', 'agents.manager', 'agents.coder', 'agents.reviewer',
    'hierarchical', 'hierarchical.hierarchical_executor', 'hierarchical.agent_pipeline',
    'training', 'training.grpo_trainer',
]
for _mod in _BLOCKED_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.regression import SWE_BENCH_LITE_TASKS, MAX_TASK_TIME, MAX_SUITE_TIME


# =========================================================================
# Test Timing Configuration
# =========================================================================

# Use simulated mode by default for fast CI/CD execution
# Set REGRESSION_REAL_MODE=1 to run with actual AutoDev execution
REGRESSION_REAL_MODE = os.environ.get("REGRESSION_REAL_MODE", "0") == "1"

# Time budget for simulated tasks (fast mode)
SIMULATED_TASK_TIME = 0.5  # seconds per task


# =========================================================================
# SWE-bench Task Data Structures
# =========================================================================

@dataclass
class SWEBenchTask:
    """Represents a SWE-bench Lite task for testing."""
    task_id: str
    repo: str
    version: str
    description: str
    category: str
    complexity: str
    expected_files: List[str]
    problem_statement: str = ""
    hints_text: str = ""
    test_patch: str = ""
    
    @classmethod
    def from_dict(cls, task_id: str, data: Dict[str, Any]) -> "SWEBenchTask":
        """Create a SWEBenchTask from dictionary data."""
        return cls(
            task_id=task_id,
            repo=data["repo"],
            version=data["version"],
            description=data["description"],
            category=data["category"],
            complexity=data["complexity"],
            expected_files=data["expected_files"],
            problem_statement=data.get("problem_statement", f"Problem: {data['description']}"),
            hints_text=data.get("hints_text", ""),
            test_patch=data.get("test_patch", ""),
        )


@dataclass
class TaskExecutionResult:
    """Result of executing a SWE-bench task."""
    task_id: str
    status: str  # "passed", "failed", "timeout", "error"
    duration_seconds: float
    files_modified: List[str] = field(default_factory=list)
    iterations: int = 0
    review_iterations: int = 0
    error_message: Optional[str] = None
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "duration_seconds": round(self.duration_seconds, 3),
            "files_modified": self.files_modified,
            "iterations": self.iterations,
            "review_iterations": self.review_iterations,
            "error_message": self.error_message,
            "summary": self.summary,
        }


# =========================================================================
# Fixtures
# =========================================================================

@pytest.fixture(scope="session")
def regression_mode():
    """Return the current regression test mode."""
    return "real" if REGRESSION_REAL_MODE else "simulated"


@pytest.fixture(scope="session")
def regression_results_dir(tmp_path_factory):
    """Create a directory for regression test results."""
    results_dir = tmp_path_factory.mktemp("regression_results")
    return results_dir


@pytest.fixture(scope="session")
def swebench_tasks() -> Dict[str, SWEBenchTask]:
    """Return the 5 representative SWE-bench Lite tasks."""
    return {
        task_id: SWEBenchTask.from_dict(task_id, data)
        for task_id, data in SWE_BENCH_LITE_TASKS.items()
    }


@pytest.fixture
def mock_parent_agent():
    """Create a mock parent agent for AutoDev bridge testing."""
    agent = MagicMock()
    agent.base_url = "https://openrouter.ai/api/v1"
    agent.api_key = "test-key"
    agent.provider = "openrouter"
    agent.api_mode = "chat_completions"
    agent.model = "anthropic/claude-sonnet-4"
    agent.working_dir = "/tmp/test-project"
    agent.platform = "cli"
    return agent


@pytest.fixture
def mock_autodev_bridge(mock_parent_agent):
    """Create a mock AutoDev bridge for fast testing."""
    # Block autodev imports to avoid heavy dependencies (torch, transformers, etc.)
    import sys
    from unittest.mock import MagicMock
    
    # Block the autodev path to prevent import of heavy dependencies
    blocked_modules = [
        'agents', 'agents.base', 'agents.manager', 'agents.coder', 'agents.reviewer',
        'hierarchical', 'hierarchical.hierarchical_executor', 'hierarchical.agent_pipeline',
        'training', 'training.grpo_trainer',
    ]
    for mod in blocked_modules:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()
    
    # Now import autodev_bridge (will use mocked modules)
    import tools.autodev_bridge as autodev_bridge
    
    # Force AUTODEV_AVAILABLE to False for simulated mode
    autodev_bridge.AUTODEV_AVAILABLE = False
    
    bridge = autodev_bridge.HermesAutoDevBridge(
        mock_parent_agent,
        autodev_bridge.AutoDevConfig(
            max_iterations=2,
            num_coders=1,
            num_reviewers=1,
            timeout_seconds=60,
            enable_parallel_coding=False,
        )
    )
    return bridge


@pytest.fixture
def timing_assertion():
    """Factory fixture for timing assertions."""
    def _assert_timing(duration: float, max_time: float, task_id: str = "task"):
        """Assert that execution completed within time limit."""
        if duration > max_time:
            pytest.fail(
                f"{task_id} exceeded time limit: {duration:.2f}s > {max_time}s"
            )
        return True
    return _assert_timing


# =========================================================================
# Helper Functions
# =========================================================================

async def simulate_task_execution(
    task: SWEBenchTask,
    duration: float = SIMULATED_TASK_TIME,
) -> TaskExecutionResult:
    """
    Simulate execution of a SWE-bench task.
    
    In simulated mode, this mimics the hierarchical execution flow
    without actually invoking LLMs or modifying files.
    """
    start_time = time.monotonic()
    
    # Simulate execution time
    await asyncio.sleep(duration)
    
    # Simulate hierarchical execution phases
    # Phase 1: Manager decomposes task
    # Phase 2: Coder implements solution
    # Phase 3: Reviewer validates
    
    iterations = 1
    review_iterations = 1
    
    # Simulate different complexities
    if task.complexity == "high":
        iterations = 3
        review_iterations = 2
    elif task.complexity == "medium":
        iterations = 2
        review_iterations = 1
    
    elapsed = time.monotonic() - start_time
    
    return TaskExecutionResult(
        task_id=task.task_id,
        status="passed",
        duration_seconds=elapsed,
        files_modified=task.expected_files.copy(),
        iterations=iterations,
        review_iterations=review_iterations,
        summary=f"Successfully completed {task.category} task for {task.repo}",
    )


async def real_task_execution(
    task: SWEBenchTask,
    bridge,
) -> TaskExecutionResult:
    """
    Execute a real SWE-bench task using AutoDev bridge.
    
    This mode requires AutoDev components to be available.
    """
    start_time = time.monotonic()
    
    try:
        # Execute through AutoDev bridge
        result = await bridge.execute(
            goal=task.problem_statement,
            context=f"Repository: {task.repo}\nVersion: {task.version}\n{task.hints_text}",
        )
        
        elapsed = time.monotonic() - start_time
        
        return TaskExecutionResult(
            task_id=task.task_id,
            status="passed" if result.get("status") == "completed" else "failed",
            duration_seconds=elapsed,
            files_modified=result.get("files_modified", []),
            iterations=result.get("iterations", 0),
            review_iterations=result.get("review_iterations", 0),
            error_message=result.get("error"),
            summary=result.get("summary", ""),
        )
        
    except Exception as e:
        elapsed = time.monotonic() - start_time
        return TaskExecutionResult(
            task_id=task.task_id,
            status="error",
            duration_seconds=elapsed,
            error_message=str(e),
        )


def generate_regression_report(
    results: List[TaskExecutionResult],
    output_path: Path,
) -> Dict[str, Any]:
    """Generate a JSON report of regression test results."""
    total_duration = sum(r.duration_seconds for r in results)
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status != "passed")
    
    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_tasks": len(results),
        "passed": passed,
        "failed": failed,
        "total_duration_seconds": round(total_duration, 3),
        "average_duration_seconds": round(total_duration / len(results), 3) if results else 0,
        "max_task_time_seconds": MAX_TASK_TIME,
        "max_suite_time_seconds": MAX_SUITE_TIME,
        "time_budget_exceeded": total_duration > MAX_SUITE_TIME,
        "tasks": [r.to_dict() for r in results],
    }
    
    # Write report to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)
    
    return report


# =========================================================================
# Pytest Hooks
# =========================================================================

def pytest_configure(config):
    """Configure custom markers for regression tests."""
    config.addinivalue_line(
        "markers", "regression: mark test as part of the regression suite"
    )
    config.addinivalue_line(
        "markers", "swebench: mark test as a SWE-bench task test"
    )
    config.addinivalue_line(
        "markers", "timing: mark test with timing assertions"
    )
    config.addinivalue_line(
        "markers", "order: mark test with execution order (requires pytest-ordering)"
    )


def pytest_collection_modifyitems(config, items):
    """Add markers to regression tests automatically."""
    for item in items:
        # Mark all tests in the regression directory
        if "regression" in str(item.fspath):
            item.add_marker(pytest.mark.regression)
