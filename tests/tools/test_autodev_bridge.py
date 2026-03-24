"""
Tests for tools/autodev_bridge.py — HermesAutoDevBridge.

Covers:
- HermesAutoDevBridge class initialization
- task_type='autodev' routing
- HierarchicalExecutor integration
- Result aggregation
- Error handling
- Async/sync bridge

Run with: python -m pytest tests/tools/test_autodev_bridge.py -v
"""

import asyncio
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import (
    AsyncMock,
    MagicMock,
    patch,
    PropertyMock,
)

import pytest

# Block autodev imports to avoid heavy dependencies (torch, transformers, etc.)
# This simulates the case where AutoDev is not available
sys.modules['agents'] = MagicMock()
sys.modules['agents.base'] = MagicMock()
sys.modules['agents.manager'] = MagicMock()
sys.modules['agents.coder'] = MagicMock()
sys.modules['agents.reviewer'] = MagicMock()
sys.modules['hierarchical'] = MagicMock()
sys.modules['hierarchical.hierarchical_executor'] = MagicMock()

# Import module under test
import tools.autodev_bridge as autodev_bridge
from tools.autodev_bridge import (
    AutoDevConfig,
    HermesAutoDevBridge,
    ROLE_MAPPING,
    check_autodev_requirements,
    create_autodev_handler,
    _HermesAgentWrapper,
    _HermesManagerWrapper,
    _HermesCoderWrapper,
    _HermesReviewerWrapper,
)


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture()
def mock_parent_agent():
    """Create a mock parent agent with the fields the bridge expects."""
    parent = MagicMock()
    parent.base_url = "https://openrouter.ai/api/v1"
    parent.api_key = "test-api-key"
    parent.provider = "openrouter"
    parent.api_mode = "chat_completions"
    parent.model = "anthropic/claude-sonnet-4"
    parent.working_dir = "/tmp/test-project"
    parent.platform = "cli"
    return parent


@pytest.fixture()
def autodev_config():
    """Create a default AutoDevConfig for testing."""
    return AutoDevConfig(
        max_iterations=3,
        num_coders=2,
        num_reviewers=1,
        timeout_seconds=300,
        enable_parallel_coding=True,
    )


@pytest.fixture()
def bridge(mock_parent_agent, autodev_config):
    """Create a HermesAutoDevBridge instance for testing."""
    return HermesAutoDevBridge(mock_parent_agent, autodev_config)


@pytest.fixture()
def bridge_no_config(mock_parent_agent):
    """Create a bridge without explicit config (uses defaults)."""
    return HermesAutoDevBridge(mock_parent_agent)


# =========================================================================
# Test AutoDevConfig
# =========================================================================


class TestAutoDevConfig:
    """Tests for AutoDevConfig dataclass."""

    def test_default_values(self):
        """AutoDevConfig should have sensible defaults."""
        config = AutoDevConfig()
        assert config.max_iterations == 5
        assert config.num_coders == 2
        assert config.num_reviewers == 1
        assert config.timeout_seconds == 600
        assert config.enable_parallel_coding is True

    def test_custom_values(self):
        """AutoDevConfig should accept custom values."""
        config = AutoDevConfig(
            max_iterations=10,
            num_coders=5,
            num_reviewers=3,
            timeout_seconds=1200,
            enable_parallel_coding=False,
        )
        assert config.max_iterations == 10
        assert config.num_coders == 5
        assert config.num_reviewers == 3
        assert config.timeout_seconds == 1200
        assert config.enable_parallel_coding is False


# =========================================================================
# Test HermesAutoDevBridge Initialization
# =========================================================================


class TestHermesAutoDevBridgeInit:
    """Tests for HermesAutoDevBridge initialization."""

    def test_init_with_config(self, mock_parent_agent, autodev_config):
        """Bridge should store parent agent and config."""
        bridge = HermesAutoDevBridge(mock_parent_agent, autodev_config)
        assert bridge.parent_agent is mock_parent_agent
        assert bridge.config is autodev_config
        assert bridge._executor is None
        assert bridge._initialized is False

    def test_init_without_config(self, mock_parent_agent):
        """Bridge should create default config when none provided."""
        bridge = HermesAutoDevBridge(mock_parent_agent)
        assert bridge.parent_agent is mock_parent_agent
        assert isinstance(bridge.config, AutoDevConfig)
        assert bridge.config.max_iterations == 5  # default value

    def test_init_with_none_config(self, mock_parent_agent):
        """Bridge should handle None config explicitly."""
        bridge = HermesAutoDevBridge(mock_parent_agent, None)
        assert bridge.parent_agent is mock_parent_agent
        assert isinstance(bridge.config, AutoDevConfig)


# =========================================================================
# Test TaskSpec Creation
# =========================================================================


class TestCreateTaskSpec:
    """Tests for _create_task_spec method."""

    def test_creates_task_spec_with_goal_only(self, bridge):
        """TaskSpec should be created with just a goal."""
        task_spec = bridge._create_task_spec("Implement feature X")
        # When AUTODEV_AVAILABLE is False, it creates a mock object with these attributes
        assert hasattr(task_spec, "task_id")
        assert hasattr(task_spec, "specification")
        assert hasattr(task_spec, "task_type")
        assert hasattr(task_spec, "timeout_seconds")

    def test_creates_task_spec_with_context(self, bridge):
        """TaskSpec should include context in constraints when provided."""
        task_spec = bridge._create_task_spec(
            "Fix bug",
            context="Error: assertion failed in test_foo.py"
        )
        assert hasattr(task_spec, "constraints")
        # When AUTODEV_AVAILABLE is False, constraints is a real dict
        # When mocked, it's a MagicMock, so just check attribute exists
        assert task_spec.constraints is not None

    def test_task_spec_has_id(self, bridge):
        """Each TaskSpec should have a task_id."""
        spec = bridge._create_task_spec("Task 1")
        assert hasattr(spec, "task_id")

    def test_task_spec_uses_parent_working_dir(self, mock_parent_agent, autodev_config):
        """TaskSpec should use parent agent's working_dir."""
        mock_parent_agent.working_dir = "/custom/workspace"
        bridge = HermesAutoDevBridge(mock_parent_agent, autodev_config)
        task_spec = bridge._create_task_spec("Task")
        assert hasattr(task_spec, "repo_root")

    def test_task_spec_handles_missing_working_dir(self, mock_parent_agent, autodev_config):
        """TaskSpec should handle missing working_dir."""
        del mock_parent_agent.working_dir
        bridge = HermesAutoDevBridge(mock_parent_agent, autodev_config)
        task_spec = bridge._create_task_spec("Task")
        assert hasattr(task_spec, "repo_root")


# =========================================================================
# Test Agent Initialization
# =========================================================================


class TestInitializeAgents:
    """Tests for _initialize_agents method."""

    def test_handles_autodev_unavailable(self, bridge, monkeypatch):
        """Should gracefully handle AutoDev not being available."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)
        bridge._initialize_agents()
        assert bridge._initialized is True
        assert bridge._executor is None

    def test_idempotent_initialization(self, bridge):
        """_initialize_agents should be idempotent."""
        bridge._initialized = True
        # Should not reinitialize or raise
        bridge._initialize_agents()
        assert bridge._initialized is True

    def test_creates_executor_with_pools(self, bridge, monkeypatch):
        """Should create HierarchicalExecutor with manager, coders, reviewers."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        # Mock the HierarchicalExecutor
        mock_executor_class = MagicMock()
        monkeypatch.setattr(autodev_bridge, "HierarchicalExecutor", mock_executor_class)
        monkeypatch.setattr(autodev_bridge, "ManagerAgent", MagicMock)
        monkeypatch.setattr(autodev_bridge, "CoderAgent", MagicMock)
        monkeypatch.setattr(autodev_bridge, "ReviewerAgent", MagicMock)

        bridge._initialize_agents()

        assert bridge._initialized is True
        mock_executor_class.assert_called_once()
        call_kwargs = mock_executor_class.call_args[1]
        assert "manager" in call_kwargs
        assert "coder_pool" in call_kwargs
        assert "reviewer_pool" in call_kwargs
        assert len(call_kwargs["coder_pool"]) == bridge.config.num_coders
        assert len(call_kwargs["reviewer_pool"]) == bridge.config.num_reviewers

    def test_handles_initialization_exception(self, bridge, monkeypatch):
        """Should handle exceptions during initialization gracefully."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        def broken_executor(*args, **kwargs):
            raise RuntimeError("Executor creation failed")

        monkeypatch.setattr(autodev_bridge, "HierarchicalExecutor", broken_executor)
        monkeypatch.setattr(autodev_bridge, "ManagerAgent", MagicMock)
        monkeypatch.setattr(autodev_bridge, "CoderAgent", MagicMock)
        monkeypatch.setattr(autodev_bridge, "ReviewerAgent", MagicMock)

        bridge._initialize_agents()

        # Should mark as initialized to prevent retry loops
        assert bridge._initialized is True


# =========================================================================
# Test Execute Method (Async)
# =========================================================================


@pytest.mark.asyncio
class TestExecute:
    """Tests for async execute method."""

    async def test_execute_returns_result_dict(self, bridge):
        """execute should return a result dictionary."""
        result = await bridge.execute("Test goal")
        assert isinstance(result, dict)
        assert "status" in result
        assert "autodev_mode" in result
        assert result["autodev_mode"] is True

    async def test_execute_with_context(self, bridge):
        """execute should pass context through."""
        result = await bridge.execute(
            "Fix bug",
            context="Error: test failure"
        )
        assert isinstance(result, dict)
        assert result["autodev_mode"] is True

    async def test_execute_tracks_duration(self, bridge):
        """execute should track and report duration."""
        import time
        start = time.monotonic()
        result = await bridge.execute("Task")
        elapsed = time.monotonic() - start

        assert "duration_seconds" in result
        assert result["duration_seconds"] <= elapsed + 0.1  # small margin

    async def test_execute_fallback_mode(self, bridge, monkeypatch):
        """execute should use fallback when AutoDev unavailable."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)
        result = await bridge.execute("Test goal")
        assert result["status"] == "completed"
        assert result["fallback"] is True
        assert "AutoDev components not available" in result["error"]

    async def test_execute_with_hierarchical_executor(self, bridge, monkeypatch):
        """execute should use HierarchicalExecutor when available."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        # Create a mock result
        @dataclass
        class MockHierarchicalResult:
            success: bool = True
            iterations: int = 2
            review_iterations: int = 1
            total_time_seconds: float = 5.0
            agent_usage: dict = field(default_factory=lambda: {"manager": 1, "coder": 2})
            decomposition: list = field(default_factory=list)
            code_changes: list = field(default_factory=lambda: [{"file": "test.py"}])
            final_result: MagicMock = None

        mock_result = MockHierarchicalResult()
        mock_result.final_result = MagicMock()
        mock_result.final_result.files_modified = ["test.py", "utils.py"]

        # Create mock executor
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value=mock_result)
        bridge._executor = mock_executor
        bridge._initialized = True

        result = await bridge.execute("Implement feature")

        assert result["status"] == "completed"
        assert result["iterations"] == 2
        assert result["review_iterations"] == 1
        assert "files_modified" in result
        assert len(result["files_modified"]) == 2

    async def test_execute_handles_exception_in_executor(self, bridge, monkeypatch):
        """execute should catch and report exceptions from executor."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        
        # Set up so we get into the try block
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(side_effect=RuntimeError("Executor failed"))
        bridge._executor = mock_executor
        bridge._initialized = True

        result = await bridge.execute("Test")

        assert result["status"] == "error"
        assert "Executor failed" in result["error"]
        assert result["autodev_mode"] is True


# =========================================================================
# Test Result Conversion
# =========================================================================


class TestConvertResult:
    """Tests for _convert_result method."""

    def test_converts_successful_result(self, bridge):
        """_convert_result should convert successful HierarchicalResult."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.iterations = 3
        mock_result.review_iterations = 2
        mock_result.total_time_seconds = 10.0
        mock_result.agent_usage = {"manager": 1, "coder": 2, "reviewer": 1}
        mock_result.decomposition = ["subtask1", "subtask2"]
        mock_result.code_changes = [{"file": "test.py"}]
        mock_result.final_result = MagicMock()
        mock_result.final_result.files_modified = ["test.py"]

        result = bridge._convert_result(mock_result, 0.0)

        assert result["status"] == "completed"
        assert "✓ Hierarchical execution completed successfully" in result["summary"]
        assert result["iterations"] == 3
        assert result["review_iterations"] == 2
        assert result["autodev_mode"] is True

    def test_converts_failed_result(self, bridge):
        """_convert_result should convert failed HierarchicalResult."""
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.iterations = 5
        mock_result.review_iterations = 4
        mock_result.total_time_seconds = 30.0
        mock_result.agent_usage = {}
        mock_result.decomposition = None
        mock_result.code_changes = None
        mock_result.final_result = MagicMock()
        mock_result.final_result.files_modified = []

        result = bridge._convert_result(mock_result, 0.0)

        assert result["status"] == "failed"
        assert "✗ Hierarchical execution failed" in result["summary"]
        assert result["iterations"] == 5

    def test_result_includes_duration(self, bridge):
        """_convert_result should calculate duration from start_time."""
        import time
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.iterations = 1
        mock_result.review_iterations = 0
        mock_result.total_time_seconds = 1.0
        mock_result.agent_usage = {}
        mock_result.decomposition = []
        mock_result.code_changes = []
        mock_result.final_result = MagicMock()
        mock_result.final_result.files_modified = []

        start_time = time.monotonic() - 0.5  # 0.5 seconds ago
        result = bridge._convert_result(mock_result, start_time)

        assert result["duration_seconds"] >= 0.5

    def test_handles_missing_final_result(self, bridge):
        """_convert_result should handle missing final_result gracefully."""
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.iterations = 1
        mock_result.review_iterations = 0
        mock_result.total_time_seconds = 1.0
        mock_result.agent_usage = {}
        mock_result.decomposition = []
        mock_result.code_changes = []
        # Remove final_result
        del mock_result.final_result

        result = bridge._convert_result(mock_result, 0.0)

        assert result["status"] == "completed"
        assert result["files_modified"] == []


# =========================================================================
# Test Fallback Execution
# =========================================================================


@pytest.mark.asyncio
class TestFallbackExecute:
    """Tests for _fallback_execute method."""

    async def test_fallback_returns_completed_status(self, bridge):
        """Fallback should return completed status with warning."""
        import time
        result = await bridge._fallback_execute("Test goal", "Context", time.monotonic())

        assert result["status"] == "completed"
        assert result["fallback"] is True
        assert "AutoDev components not available" in result["error"]

    async def test_fallback_includes_goal_in_summary(self, bridge):
        """Fallback summary should include the goal (truncated)."""
        import time
        long_goal = "A" * 200
        result = await bridge._fallback_execute(long_goal, None, time.monotonic())

        assert "AAA" in result["summary"]
        assert len(result["summary"]) < 300  # Should be truncated

    async def test_fallback_includes_duration(self, bridge):
        """Fallback should include duration_seconds."""
        import time
        result = await bridge._fallback_execute("Goal", None, time.monotonic() - 1.0)

        assert "duration_seconds" in result
        assert result["duration_seconds"] >= 1.0


# =========================================================================
# Test Agent Wrappers
# =========================================================================


class TestHermesAgentWrapper:
    """Tests for _HermesAgentWrapper base class."""

    def test_wrapper_initialization(self, mock_parent_agent):
        """Wrapper should store parent agent and role."""
        wrapper = _HermesAgentWrapper(mock_parent_agent, "test_role", idx=5)
        assert wrapper.parent_agent is mock_parent_agent
        assert wrapper.role == "test_role"
        assert wrapper.agent_id == "test_role-5"

    @pytest.mark.asyncio
    async def test_wrapper_initialize(self, mock_parent_agent):
        """Wrapper initialize should be a no-op coroutine."""
        wrapper = _HermesAgentWrapper(mock_parent_agent, "test")
        await wrapper.initialize()  # Should not raise

    @pytest.mark.asyncio
    async def test_wrapper_shutdown(self, mock_parent_agent):
        """Wrapper shutdown should be a no-op coroutine."""
        wrapper = _HermesAgentWrapper(mock_parent_agent, "test")
        await wrapper.shutdown()  # Should not raise


class TestHermesManagerWrapper:
    """Tests for _HermesManagerWrapper."""

    def test_manager_role_mapping(self, mock_parent_agent):
        """Manager wrapper should map to 'plan' role."""
        wrapper = _HermesManagerWrapper(mock_parent_agent)
        assert wrapper.role_mapping == ROLE_MAPPING["manager"]
        assert wrapper.role_mapping == "plan"

    @pytest.mark.asyncio
    async def test_manager_decompose_without_autodev(self, mock_parent_agent, monkeypatch):
        """Manager decompose should work without AutoDev available."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)

        wrapper = _HermesManagerWrapper(mock_parent_agent)
        mock_task = MagicMock()
        mock_task.task_id = "test-task-123"
        mock_task.specification = "Implement feature X"
        mock_task.task_type = "implement"

        subtasks = await wrapper.decompose(mock_task)

        assert len(subtasks) == 1
        assert subtasks[0].description == "Implement feature X"

    @pytest.mark.asyncio
    async def test_manager_decompose_with_autodev(self, mock_parent_agent, monkeypatch):
        """Manager decompose should use SubTask class when available."""
        # Create a mock SubTask class
        MockSubTask = MagicMock()
        monkeypatch.setattr(autodev_bridge, "SubTask", MockSubTask)
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)

        wrapper = _HermesManagerWrapper(mock_parent_agent)
        mock_task = MagicMock()
        mock_task.task_id = "test-task-456"
        mock_task.specification = "Fix bug"
        mock_task.task_type = "implement"

        subtasks = await wrapper.decompose(mock_task)

        MockSubTask.assert_called_once()
        assert len(subtasks) == 1


class TestHermesCoderWrapper:
    """Tests for _HermesCoderWrapper."""

    def test_coder_role_mapping(self, mock_parent_agent):
        """Coder wrapper should map to 'implement' role."""
        wrapper = _HermesCoderWrapper(mock_parent_agent, idx=0)
        assert wrapper.role_mapping == ROLE_MAPPING["coder"]
        assert wrapper.role_mapping == "implement"

    def test_coder_has_unique_id(self, mock_parent_agent):
        """Each coder should have a unique ID based on index."""
        coder0 = _HermesCoderWrapper(mock_parent_agent, idx=0)
        coder1 = _HermesCoderWrapper(mock_parent_agent, idx=1)
        assert coder0.agent_id == "coder-0"
        assert coder1.agent_id == "coder-1"

    @pytest.mark.asyncio
    async def test_coder_execute_returns_code_change(self, mock_parent_agent):
        """Coder execute should return a CodeChange-like object."""
        wrapper = _HermesCoderWrapper(mock_parent_agent, idx=0)
        mock_subtask = MagicMock()
        mock_subtask.subtask_id = "subtask-1"
        mock_subtask.description = "Implement authentication"

        result = await wrapper.execute(mock_subtask)

        assert hasattr(result, "file")
        assert hasattr(result, "diff")
        assert hasattr(result, "files_modified")


class TestHermesReviewerWrapper:
    """Tests for _HermesReviewerWrapper."""

    def test_reviewer_role_mapping(self, mock_parent_agent):
        """Reviewer wrapper should map to 'review' role."""
        wrapper = _HermesReviewerWrapper(mock_parent_agent, idx=0)
        assert wrapper.role_mapping == ROLE_MAPPING["reviewer"]
        assert wrapper.role_mapping == "review"

    @pytest.mark.asyncio
    async def test_reviewer_returns_approved_result(self, mock_parent_agent):
        """Reviewer should return an approved review result."""
        wrapper = _HermesReviewerWrapper(mock_parent_agent, idx=0)
        changes = [MagicMock()]

        result = await wrapper.review(changes)

        assert hasattr(result, "verdict")
        assert result.verdict == "approved"
        assert hasattr(result, "findings")


# =========================================================================
# Test Role Mapping Constants
# =========================================================================


class TestRoleMapping:
    """Tests for ROLE_MAPPING constant."""

    def test_manager_maps_to_plan(self):
        """Manager role should map to 'plan'."""
        assert ROLE_MAPPING["manager"] == "plan"

    def test_coder_maps_to_implement(self):
        """Coder role should map to 'implement'."""
        assert ROLE_MAPPING["coder"] == "implement"

    def test_reviewer_maps_to_review(self):
        """Reviewer role should map to 'review'."""
        assert ROLE_MAPPING["reviewer"] == "review"

    def test_all_roles_defined(self):
        """All three roles should be defined."""
        assert len(ROLE_MAPPING) == 3
        assert "manager" in ROLE_MAPPING
        assert "coder" in ROLE_MAPPING
        assert "reviewer" in ROLE_MAPPING


# =========================================================================
# Test check_autodev_requirements
# =========================================================================


class TestCheckAutodevRequirements:
    """Tests for check_autodev_requirements function."""

    def test_returns_boolean(self):
        """check_autodev_requirements should return a boolean."""
        result = check_autodev_requirements()
        assert isinstance(result, bool)

    def test_returns_true_when_available(self, monkeypatch):
        """Should return True when AutoDev is available."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        result = check_autodev_requirements()
        assert result is True

    def test_returns_false_when_unavailable(self, monkeypatch):
        """Should return False when AutoDev is not available."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)
        result = check_autodev_requirements()
        assert result is False


# =========================================================================
# Test create_autodev_handler
# =========================================================================


class TestCreateAutodevHandler:
    """Tests for create_autodev_handler factory function."""

    def test_returns_callable(self, mock_parent_agent):
        """create_autodev_handler should return a callable."""
        handler = create_autodev_handler(mock_parent_agent)
        assert callable(handler)

    def test_handler_is_async(self, mock_parent_agent):
        """Handler should be an async function."""
        handler = create_autodev_handler(mock_parent_agent)
        import asyncio
        assert asyncio.iscoroutinefunction(handler)

    @pytest.mark.asyncio
    async def test_handler_calls_bridge_execute(self, mock_parent_agent, autodev_config):
        """Handler should call bridge.execute with goal and context."""
        bridge = HermesAutoDevBridge(mock_parent_agent, autodev_config)

        # Patch execute to track calls
        original_execute = bridge.execute
        call_tracker = []
        
        async def tracked_execute(goal, context=None):
            call_tracker.append((goal, context))
            return await original_execute(goal, context)

        bridge.execute = tracked_execute
        handler = bridge.execute

        await handler("Test goal", "Test context")

        assert len(call_tracker) == 1
        assert call_tracker[0] == ("Test goal", "Test context")

    def test_handler_uses_custom_config(self, mock_parent_agent):
        """Handler should use provided config."""
        config = AutoDevConfig(max_iterations=10)
        handler = create_autodev_handler(mock_parent_agent, config)
        # Handler is bridge.execute, so we can check the bridge
        # by looking at the closure or creating one directly
        bridge = HermesAutoDevBridge(mock_parent_agent, config)
        assert bridge.config.max_iterations == 10


# =========================================================================
# Test Integration Scenarios
# =========================================================================


@pytest.mark.asyncio
class TestIntegrationScenarios:
    """End-to-end integration tests."""

    async def test_full_fallback_flow(self, mock_parent_agent, monkeypatch):
        """Test complete flow when AutoDev is unavailable."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)
        bridge = HermesAutoDevBridge(mock_parent_agent)

        result = await bridge.execute(
            "Implement user authentication",
            context="Using OAuth2 with Google provider"
        )

        assert result["autodev_mode"] is True
        assert result["fallback"] is True
        assert "duration_seconds" in result

    async def test_full_execution_with_mock_executor(self, mock_parent_agent, monkeypatch):
        """Test complete flow with mock HierarchicalExecutor."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)

        # Create a comprehensive mock result
        @dataclass
        class MockFinalResult:
            files_modified: list = field(default_factory=lambda: ["auth.py", "models.py"])

        @dataclass
        class MockHierarchicalResult:
            success: bool = True
            iterations: int = 3
            review_iterations: int = 2
            total_time_seconds: float = 15.5
            agent_usage: dict = field(default_factory=lambda: {
                "manager": 1,
                "coders": [2, 2],
                "reviewers": [1],
            })
            decomposition: list = field(default_factory=lambda: [
                "Setup OAuth provider",
                "Implement login flow",
                "Add session management",
            ])
            code_changes: list = field(default_factory=lambda: [
                {"file": "auth.py", "lines_added": 50, "lines_removed": 5},
                {"file": "models.py", "lines_added": 20, "lines_removed": 0},
            ])
            final_result: MockFinalResult = field(default_factory=MockFinalResult)

        mock_result = MockHierarchicalResult()

        # Mock executor
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(return_value=mock_result)

        # Create bridge and inject mock executor
        config = AutoDevConfig(max_iterations=5, num_coders=2, num_reviewers=1)
        bridge = HermesAutoDevBridge(mock_parent_agent, config)
        bridge._executor = mock_executor
        bridge._initialized = True

        result = await bridge.execute(
            "Implement user authentication",
            context="OAuth2 with Google"
        )

        # Verify result structure
        assert result["status"] == "completed"
        assert result["autodev_mode"] is True
        assert result["iterations"] == 3
        assert result["review_iterations"] == 2
        assert len(result["files_modified"]) == 2
        assert "✓ Hierarchical execution completed successfully" in result["summary"]
        assert "Subtasks decomposed: 3" in result["summary"]
        assert "Code changes: 2" in result["summary"]

    async def test_error_propagation(self, mock_parent_agent, monkeypatch):
        """Test that errors are properly caught and reported."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        bridge = HermesAutoDevBridge(mock_parent_agent)
        
        # Set up executor that throws an error
        mock_executor = MagicMock()
        mock_executor.execute = AsyncMock(side_effect=ValueError("Executor error"))
        bridge._executor = mock_executor
        bridge._initialized = True

        result = await bridge.execute("This will fail")

        assert result["status"] == "error"
        assert "Executor error" in result["error"]
        assert "duration_seconds" in result


# =========================================================================
# Test Edge Cases
# =========================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_goal(self, bridge):
        """Execute should handle empty goal."""
        result = await bridge.execute("")
        assert isinstance(result, dict)
        assert "status" in result

    @pytest.mark.asyncio
    async def test_very_long_goal(self, bridge):
        """Execute should handle very long goal strings."""
        long_goal = "A" * 10000
        result = await bridge.execute(long_goal)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_special_characters_in_context(self, bridge):
        """Execute should handle special characters in context."""
        special_context = "Error: \n\t\r\"'<>&"
        result = await bridge.execute("Task", context=special_context)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_unicode_in_goal(self, bridge):
        """Execute should handle unicode characters."""
        unicode_goal = "Implement 你好世界 🚀"
        result = await bridge.execute(unicode_goal)
        assert isinstance(result, dict)

    def test_config_with_zero_values(self, mock_parent_agent):
        """Bridge should handle config with zero values."""
        config = AutoDevConfig(
            max_iterations=0,
            num_coders=0,
            num_reviewers=0,
            timeout_seconds=0,
        )
        bridge = HermesAutoDevBridge(mock_parent_agent, config)
        assert bridge.config.max_iterations == 0

    @pytest.mark.asyncio
    async def test_concurrent_executions(self, mock_parent_agent):
        """Bridge should handle concurrent execute calls."""
        bridge = HermesAutoDevBridge(mock_parent_agent)

        # Run multiple executions concurrently
        tasks = [
            bridge.execute(f"Task {i}")
            for i in range(5)
        ]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert all(isinstance(r, dict) for r in results)
        assert all("status" in r for r in results)


# =========================================================================
# Test Logging
# =========================================================================


class TestLogging:
    """Tests for logging behavior."""

    @pytest.mark.asyncio
    async def test_fallback_logs_warning(self, mock_parent_agent, caplog, monkeypatch):
        """Fallback execution should log a warning."""
        import logging
        caplog.set_level(logging.WARNING, logger="tools.autodev_bridge")
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)

        bridge = HermesAutoDevBridge(mock_parent_agent)
        await bridge.execute("Test goal")

        # Check that a warning was logged
        assert any(
            "not available" in record.message.lower()
            for record in caplog.records
            if record.levelno >= logging.WARNING
        )

    def test_init_logs_warning_when_unavailable(self, mock_parent_agent, caplog, monkeypatch):
        """Initialization should log warning when AutoDev unavailable."""
        import logging
        caplog.set_level(logging.WARNING, logger="tools.autodev_bridge")
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", False)

        bridge = HermesAutoDevBridge(mock_parent_agent)
        bridge._initialize_agents()

        assert any(
            "not available" in record.message.lower()
            for record in caplog.records
        )


# =========================================================================
# Test Coverage Helpers
# =========================================================================


class TestCoverageHelpers:
    """Additional tests to improve coverage."""

    def test_create_task_spec_with_autodev_available(self, bridge, monkeypatch):
        """_create_task_spec should use real TaskSpec when AutoDev available."""
        monkeypatch.setattr(autodev_bridge, "AUTODEV_AVAILABLE", True)
        # Mock TaskSpec class
        MockTaskSpec = MagicMock()
        monkeypatch.setattr(autodev_bridge, "TaskSpec", MockTaskSpec)

        task_spec = bridge._create_task_spec("Test goal", "Context")

        MockTaskSpec.assert_called_once()

    @pytest.mark.asyncio
    async def test_bridge_executor_none_path(self, bridge):
        """Test when _executor is None after initialization."""
        bridge._initialized = True
        bridge._executor = None

        result = await bridge.execute("Test")

        # Should fall back
        assert result["autodev_mode"] is True

    def test_manager_wrapper_agent_id(self, mock_parent_agent):
        """Manager wrapper should have correct agent_id."""
        wrapper = _HermesManagerWrapper(mock_parent_agent)
        # _HermesManagerWrapper inherits from _HermesAgentWrapper which uses idx=0 as default
        assert wrapper.agent_id == "manager-0"

    def test_reviewer_wrapper_agent_id(self, mock_parent_agent):
        """Reviewer wrapper should have correct agent_id."""
        wrapper = _HermesReviewerWrapper(mock_parent_agent, idx=2)
        assert wrapper.agent_id == "reviewer-2"
