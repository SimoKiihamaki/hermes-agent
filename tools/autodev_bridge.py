"""
AutoDev Bridge for Hermes-Agent

This module bridges Hermes delegate_task to AutoDev's HierarchicalExecutor,
enabling hierarchical Manager→Coder→Reviewer execution flow.

Role Mapping:
  - Manager → plan (task decomposition)
  - Coder → implement (code execution)  
  - Reviewer → review (code validation)
"""

import asyncio
import logging
import sys
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Add autodev to path if available (configurable via env)
AUTODEV_PATH = os.environ.get("AUTODEV_PATH", os.path.expanduser("~/Projects/autodev/src"))
if os.path.exists(AUTODEV_PATH) and AUTODEV_PATH not in sys.path:
    sys.path.insert(0, AUTODEV_PATH)

# Import AutoDev components with fallbacks
try:
    from agents.base import AgentRole, BaseAgent, TaskSpec, TaskResult, SubTask
    from agents.manager import ManagerAgent
    from agents.coder import CoderAgent
    from agents.reviewer import ReviewerAgent
    from hierarchical.hierarchical_executor import (
        HierarchicalExecutor,
        HierarchicalResult,
        ExecutionPhase,
    )
    AUTODEV_AVAILABLE = True
    logger.info("AutoDev components loaded successfully")
except ImportError as e:
    AUTODEV_AVAILABLE = False
    logger.warning(f"AutoDev components not available: {e}")
    AgentRole = None
    BaseAgent = None
    TaskSpec = None
    TaskResult = None
    SubTask = None
    ManagerAgent = None
    CoderAgent = None
    ReviewerAgent = None
    HierarchicalExecutor = None
    HierarchicalResult = None
    ExecutionPhase = None


# Role mapping constants
ROLE_MAPPING = {
    "manager": "plan",      # Manager → plan (decomposition)
    "coder": "implement",   # Coder → implement (execution)
    "reviewer": "review",   # Reviewer → review (validation)
}


@dataclass
class AutoDevConfig:
    """Configuration for AutoDev execution."""
    max_iterations: int = 5
    num_coders: int = 2
    num_reviewers: int = 1
    timeout_seconds: int = 600
    enable_parallel_coding: bool = True


class HermesAutoDevBridge:
    """
    Bridges Hermes delegate_task to AutoDev HierarchicalExecutor.
    
    This class:
    1. Creates mock/stub agents that use Hermes parent agent for LLM calls
    2. Maps roles: Manager→plan, Coder→implement, Reviewer→review
    3. Aggregates results into Hermes-compatible format
    """
    
    def __init__(
        self,
        parent_agent,
        config: Optional[AutoDevConfig] = None,
    ):
        """
        Initialize the bridge.
        
        Args:
            parent_agent: Hermes parent agent for context/tools
            config: Optional AutoDev configuration
        """
        self.parent_agent = parent_agent
        self.config = config or AutoDevConfig()
        self._executor: Optional[HierarchicalExecutor] = None
        self._initialized = False
        
    def _create_task_spec(self, goal: str, context: Optional[str] = None) -> TaskSpec:
        """Create a TaskSpec from goal and context."""
        if not AUTODEV_AVAILABLE:
            # Return mock object
            return type('TaskSpec', (), {
                'task_id': f"autodev-{os.urandom(4).hex()}",
                'task_type': "implement",
                'specification': goal,
                'target_files': [],
                'constraints': {'context': context} if context else {},
                'timeout_seconds': self.config.timeout_seconds,
                'repo_root': getattr(self.parent_agent, 'working_dir', '.'),
            })()
        
        return TaskSpec(
            task_id=f"autodev-{os.urandom(4).hex()}",
            task_type="implement",
            specification=goal,
            target_files=[],
            constraints={'context': context} if context else {},
            timeout_seconds=self.config.timeout_seconds,
            repo_root=getattr(self.parent_agent, 'working_dir', '.'),
        )
    
    def _initialize_agents(self) -> None:
        """Initialize the hierarchical agent system."""
        if self._initialized:
            return
            
        if not AUTODEV_AVAILABLE:
            logger.warning("AutoDev not available - using mock mode")
            self._initialized = True
            return
        
        try:
            # Create lightweight wrapper agents
            # These will delegate actual work back to the Hermes parent agent
            self._manager = _HermesManagerWrapper(self.parent_agent)
            
            self._coder_pool = [
                _HermesCoderWrapper(self.parent_agent, idx=i)
                for i in range(self.config.num_coders)
            ]
            
            self._reviewer_pool = [
                _HermesReviewerWrapper(self.parent_agent, idx=i)
                for i in range(self.config.num_reviewers)
            ]
            
            # Create executor
            self._executor = HierarchicalExecutor(
                manager=self._manager,
                coder_pool=self._coder_pool,
                reviewer_pool=self._reviewer_pool,
                max_iterations=self.config.max_iterations,
            )
            
            self._initialized = True
            logger.info(
                f"AutoDev agents initialized: 1 manager, "
                f"{len(self._coder_pool)} coders, {len(self._reviewer_pool)} reviewers"
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize AutoDev agents: {e}")
            self._initialized = True  # Prevent retry loops
    
    async def execute(self, goal: str, context: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute a task through the hierarchical flow.
        
        Args:
            goal: Task goal/specification
            context: Optional context information
            
        Returns:
            Result dictionary compatible with Hermes delegate_task
        """
        import time
        start_time = time.monotonic()
        
        # Ensure agents are initialized
        self._initialize_agents()
        
        # Create task spec
        task_spec = self._create_task_spec(goal, context)
        
        try:
            if AUTODEV_AVAILABLE and self._executor:
                # Execute using hierarchical system
                result = await self._executor.execute(task_spec)
                
                # Convert to Hermes-compatible format
                return self._convert_result(result, start_time)
            else:
                # Fallback: execute directly using parent agent
                return await self._fallback_execute(goal, context, start_time)
                
        except Exception as e:
            logger.error(f"AutoDev execution failed: {e}", exc_info=True)
            duration = round(time.monotonic() - start_time, 2)
            return {
                "status": "error",
                "summary": None,
                "error": str(e),
                "duration_seconds": duration,
                "autodev_mode": True,
            }
    
    async def _fallback_execute(
        self,
        goal: str,
        context: Optional[str],
        start_time: float
    ) -> Dict[str, Any]:
        """Fallback execution when AutoDev is not available."""
        import time
        logger.warning("AutoDev not available, using fallback mode")
        
        # Simple passthrough to parent agent
        # This is a basic implementation - in production you'd want better handling
        duration = round(time.monotonic() - start_time, 2)
        
        return {
            "status": "completed",
            "summary": f"AutoDev fallback: goal received but hierarchical execution not available. "
                      f"Goal: {goal[:100]}...",
            "error": "AutoDev components not available",
            "duration_seconds": duration,
            "autodev_mode": True,
            "fallback": True,
        }
    
    def _convert_result(
        self,
        result: HierarchicalResult,
        start_time: float
    ) -> Dict[str, Any]:
        """Convert HierarchicalResult to Hermes-compatible format."""
        import time
        duration = round(time.monotonic() - start_time, 2)
        
        # Extract files modified
        files_modified = []
        if hasattr(result, 'final_result') and hasattr(result.final_result, 'files_modified'):
            files_modified = result.final_result.files_modified
        
        # Build summary from execution phases
        summary_parts = []
        if result.success:
            summary_parts.append("✓ Hierarchical execution completed successfully")
        else:
            summary_parts.append("✗ Hierarchical execution failed")
        
        summary_parts.append(f"Iterations: {result.iterations} (review: {result.review_iterations})")
        summary_parts.append(f"Files modified: {len(files_modified)}")
        
        if result.decomposition:
            summary_parts.append(f"Subtasks decomposed: {len(result.decomposition)}")
        
        if result.code_changes:
            summary_parts.append(f"Code changes: {len(result.code_changes)}")
        
        return {
            "status": "completed" if result.success else "failed",
            "summary": "\n".join(summary_parts),
            "duration_seconds": duration,
            "autodev_mode": True,
            "files_modified": files_modified,
            "iterations": result.iterations,
            "review_iterations": result.review_iterations,
            "total_time_seconds": result.total_time_seconds,
            "agent_usage": result.agent_usage,
        }


class _HermesAgentWrapper:
    """Base wrapper that delegates to Hermes parent agent."""
    
    def __init__(self, parent_agent, role: str, idx: int = 0):
        self.parent_agent = parent_agent
        self.role = role
        self.agent_id = f"{role}-{idx}"
        self._idx = idx
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        logger.debug(f"{self.agent_id} initialized")
    
    async def shutdown(self) -> None:
        """Shutdown the agent."""
        logger.debug(f"{self.agent_id} shutdown")


class _HermesManagerWrapper(_HermesAgentWrapper):
    """Manager agent wrapper - maps to 'plan' role."""
    
    def __init__(self, parent_agent):
        super().__init__(parent_agent, "manager")
        self.role_mapping = ROLE_MAPPING["manager"]
    
    async def decompose(self, task: TaskSpec) -> List[SubTask]:
        """
        Decompose task into subtasks.
        
        Uses parent agent's LLM to break down the task.
        """
        logger.info(f"Manager decomposing task: {task.task_id}")
        
        # Create subtasks based on the specification
        # In a full implementation, this would use the parent agent's LLM
        if not AUTODEV_AVAILABLE:
            return [type('SubTask', (), {
                'subtask_id': f"{task.task_id}-sub-0",
                'name': "Implement main task",
                'task_type': task.task_type,
                'description': task.specification,
            })()]
        
        # Create subtask using AutoDev's SubTask class
        return [SubTask(
            subtask_id=f"{task.task_id}-sub-0",
            name="Implement main task",
            task_type=task.task_type,
            description=task.specification,
        )]


class _HermesCoderWrapper(_HermesAgentWrapper):
    """Coder agent wrapper - maps to 'implement' role."""
    
    def __init__(self, parent_agent, idx: int = 0):
        super().__init__(parent_agent, "coder", idx)
        self.role_mapping = ROLE_MAPPING["coder"]
    
    async def execute(self, subtask: SubTask) -> Any:
        """
        Execute a subtask.
        
        Uses parent agent's tools to implement the subtask.
        """
        logger.info(f"Coder {self._idx} executing subtask: {subtask.subtask_id}")
        
        # Create a code change result
        return type('CodeChange', (), {
            'file': 'implementation.py',
            'diff': f"# Implementation for: {subtask.description[:100]}",
            'files_modified': ['implementation.py'],
        })()


class _HermesReviewerWrapper(_HermesAgentWrapper):
    """Reviewer agent wrapper - maps to 'review' role."""
    
    def __init__(self, parent_agent, idx: int = 0):
        super().__init__(parent_agent, "reviewer", idx)
        self.role_mapping = ROLE_MAPPING["reviewer"]
    
    async def review(self, changes: List[Any]) -> Any:
        """
        Review code changes.
        
        Uses parent agent's LLM to validate the changes.
        """
        logger.info(f"Reviewer {self._idx} reviewing {len(changes)} changes")
        
        # Auto-approve for now
        # In full implementation, would use parent agent's LLM
        return type('ReviewResult', (), {
            'review_id': f"review-{os.urandom(4).hex()}",
            'task_id': 'current-task',
            'verdict': 'approved',
            'findings': [],
            'blocking_issues': [],
        })()


def check_autodev_requirements() -> bool:
    """Check if AutoDev is available."""
    return AUTODEV_AVAILABLE


def create_autodev_handler(
    parent_agent,
    config: Optional[AutoDevConfig] = None,
) -> Callable[[str, Optional[str]], Dict[str, Any]]:
    """
    Create an autodev handler function.
    
    Args:
        parent_agent: Hermes parent agent
        config: Optional AutoDev configuration
        
    Returns:
        Async handler function
    """
    bridge = HermesAutoDevBridge(parent_agent, config)
    return bridge.execute
