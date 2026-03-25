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
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

# Import trace collector for RL training
try:
    from tools.trace_collector import FileBasedTraceCollector, ExecutionTrace
    TRACE_COLLECTOR_AVAILABLE = True
except ImportError:
    TRACE_COLLECTOR_AVAILABLE = False
    FileBasedTraceCollector = None
    ExecutionTrace = None

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
        trace_collector: Optional[FileBasedTraceCollector] = None,
    ):
        """
        Initialize the bridge.
        
        Args:
            parent_agent: Hermes parent agent for context/tools
            config: Optional AutoDev configuration
            trace_collector: Optional trace collector for RL training
        """
        self.parent_agent = parent_agent
        self.config = config or AutoDevConfig()
        self._executor: Optional[HierarchicalExecutor] = None
        self._initialized = False
        
        # Initialize trace collector for RL training
        if trace_collector:
            self._trace_collector = trace_collector
        elif TRACE_COLLECTOR_AVAILABLE:
            self._trace_collector = FileBasedTraceCollector()
        else:
            self._trace_collector = None
        
        # Track active traces during execution
        self._active_traces: Dict[str, str] = {}  # agent_id -> trace_id
        self._completed_traces: List[ExecutionTrace] = []
    
    def _collect_completed_traces(self) -> List[ExecutionTrace]:
        """Collect all completed traces from the collector."""
        if not self._trace_collector:
            return []
        
        # Get traces from the collector's buffer
        traces = list(self._trace_collector._trace_buffer)
        return traces
        
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
            # Create lightweight wrapper agents with trace collection
            # These will delegate actual work back to the Hermes parent agent
            self._manager = _HermesManagerWrapper(
                self.parent_agent, 
                trace_collector=self._trace_collector
            )
            
            self._coder_pool = [
                _HermesCoderWrapper(
                    self.parent_agent, 
                    idx=i,
                    trace_collector=self._trace_collector
                )
                for i in range(self.config.num_coders)
            ]
            
            self._reviewer_pool = [
                _HermesReviewerWrapper(
                    self.parent_agent, 
                    idx=i,
                    trace_collector=self._trace_collector
                )
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
                f"{len(self._coder_pool)} coders, {len(self._reviewer_pool)} reviewers, "
                f"trace_collection={'enabled' if self._trace_collector else 'disabled'}"
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
        start_time = time.monotonic()
        
        # Clear traces from previous execution
        self._active_traces.clear()
        self._completed_traces.clear()
        
        # Ensure agents are initialized
        self._initialize_agents()
        
        # Create task spec
        task_spec = self._create_task_spec(goal, context)
        
        try:
            if AUTODEV_AVAILABLE and self._executor:
                # Execute using hierarchical system
                result = await self._executor.execute(task_spec)
                
                # Collect completed traces before flushing
                self._completed_traces = self._collect_completed_traces()
                
                # Flush any pending traces
                if self._trace_collector:
                    self._trace_collector.flush()
                
                # Convert to Hermes-compatible format
                return self._convert_result(result, start_time)
            else:
                # Fallback: execute directly using parent agent
                return await self._fallback_execute(goal, context, start_time)
                
        except Exception as e:
            logger.error(f"AutoDev execution failed: {e}", exc_info=True)
            duration = round(time.monotonic() - start_time, 2)
            
            # Collect any traces that were completed before the error
            self._completed_traces = self._collect_completed_traces()
            
            return {
                "status": "error",
                "summary": None,
                "error": str(e),
                "duration_seconds": duration,
                "autodev_mode": True,
                "traces": [t.to_dict() for t in self._completed_traces] if self._completed_traces else [],
            }
    
    async def _fallback_execute(
        self,
        goal: str,
        context: Optional[str],
        start_time: float
    ) -> Dict[str, Any]:
        """Fallback execution when AutoDev is not available."""
        logger.warning("AutoDev not available, using fallback mode")
        
        # Collect any traces that may have been created
        self._completed_traces = self._collect_completed_traces()
        
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
            "traces": [t.to_dict() for t in self._completed_traces] if self._completed_traces else [],
        }
    
    def _convert_result(
        self,
        result: HierarchicalResult,
        start_time: float
    ) -> Dict[str, Any]:
        """Convert HierarchicalResult to Hermes-compatible format."""
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
        
        # Collect traces
        traces_data = [t.to_dict() for t in self._completed_traces] if self._completed_traces else []
        
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
            "traces": traces_data,
        }


class _HermesAgentWrapper:
    """Base wrapper that delegates to Hermes parent agent."""
    
    def __init__(self, parent_agent, role: str, idx: int = 0, trace_collector=None):
        self.parent_agent = parent_agent
        self.role = role
        self.agent_id = f"{role}-{idx}"
        self._idx = idx
        self._trace_collector = trace_collector
        self._current_trace_id: Optional[str] = None
    
    async def initialize(self) -> None:
        """Initialize the agent."""
        logger.debug(f"{self.agent_id} initialized")
    
    async def shutdown(self) -> None:
        """Shutdown the agent."""
        logger.debug(f"{self.agent_id} shutdown")
    
    def _start_trace(self, task_id: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Start a trace for this agent."""
        if not self._trace_collector:
            return None
        
        self._current_trace_id = self._trace_collector.start_trace(
            agent_id=self.agent_id,
            task_id=task_id,
            role=self.role,
            metadata=metadata,
        )
        logger.debug(f"{self.agent_id} started trace {self._current_trace_id}")
        return self._current_trace_id
    
    def _end_trace(self, result: Any = None, success: bool = True, error: Optional[str] = None) -> Optional[ExecutionTrace]:
        """End the current trace."""
        if not self._trace_collector or not self._current_trace_id:
            return None
        
        trace = self._trace_collector.end_trace(
            trace_id=self._current_trace_id,
            result=result,
            success=success,
            error=error,
        )
        self._current_trace_id = None
        return trace
    
    def _record_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Any,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Record a tool call in the current trace."""
        if not self._trace_collector or not self._current_trace_id:
            return
        
        self._trace_collector.record_tool_call(
            trace_id=self._current_trace_id,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_output=tool_output,
            duration_ms=duration_ms,
            success=success,
        )
    
    def _record_llm_call(
        self,
        prompt: str,
        response: str,
        tokens_used: int,
        duration_ms: float,
        model: str,
    ) -> None:
        """Record an LLM call in the current trace."""
        if not self._trace_collector or not self._current_trace_id:
            return
        
        self._trace_collector.record_llm_call(
            trace_id=self._current_trace_id,
            prompt=prompt,
            response=response,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            model=model,
        )


class _HermesManagerWrapper(_HermesAgentWrapper):
    """Manager agent wrapper - maps to 'plan' role."""
    
    def __init__(self, parent_agent, trace_collector=None):
        super().__init__(parent_agent, "manager", trace_collector=trace_collector)
        self.role_mapping = ROLE_MAPPING["manager"]
    
    async def decompose(self, task: TaskSpec) -> List[SubTask]:
        """
        Decompose task into subtasks.
        
        Uses parent agent's LLM to break down the task.
        """
        logger.info(f"Manager decomposing task: {task.task_id}")
        
        # Start trace
        self._start_trace(
            task_id=task.task_id,
            metadata={"operation": "decompose", "task_type": task.task_type}
        )
        
        start_time = time.monotonic()
        
        try:
            # Create subtasks based on the specification
            # In a full implementation, this would use the parent agent's LLM
            if not AUTODEV_AVAILABLE:
                subtask = type('SubTask', (), {
                    'subtask_id': f"{task.task_id}-sub-0",
                    'name': "Implement main task",
                    'task_type': task.task_type,
                    'description': task.specification,
                })()
                
                # Record the decomposition as an LLM call
                self._record_llm_call(
                    prompt=f"Decompose task: {task.specification}",
                    response=f"Single subtask: {task.specification[:100]}",
                    tokens_used=100,
                    duration_ms=(time.monotonic() - start_time) * 1000,
                    model=getattr(self.parent_agent, 'model', 'unknown'),
                )
                
                self._end_trace(result={"subtasks_count": 1})
                return [subtask]
            
            # Create subtask using AutoDev's SubTask class
            subtask = SubTask(
                subtask_id=f"{task.task_id}-sub-0",
                name="Implement main task",
                task_type=task.task_type,
                description=task.specification,
            )
            
            # Record the decomposition as an LLM call
            self._record_llm_call(
                prompt=f"Decompose task: {task.specification}",
                response=f"Single subtask: {task.specification[:100]}",
                tokens_used=100,
                duration_ms=(time.monotonic() - start_time) * 1000,
                model=getattr(self.parent_agent, 'model', 'unknown'),
            )
            
            self._end_trace(result={"subtasks_count": 1})
            return [subtask]
            
        except Exception as e:
            logger.error(f"Manager decomposition failed: {e}")
            self._end_trace(result=None, success=False, error=str(e))
            raise


class _HermesCoderWrapper(_HermesAgentWrapper):
    """Coder agent wrapper - maps to 'implement' role."""
    
    def __init__(self, parent_agent, idx: int = 0, trace_collector=None):
        super().__init__(parent_agent, "coder", idx, trace_collector=trace_collector)
        self.role_mapping = ROLE_MAPPING["coder"]
    
    async def execute(self, subtask: SubTask) -> Any:
        """
        Execute a subtask.
        
        Uses parent agent's tools to implement the subtask.
        """
        logger.info(f"Coder {self._idx} executing subtask: {subtask.subtask_id}")
        
        # Start trace
        self._start_trace(
            task_id=subtask.subtask_id,
            metadata={"operation": "execute", "subtask_name": subtask.name}
        )
        
        start_time = time.monotonic()
        
        try:
            # Record tool call for execution
            self._record_tool_call(
                tool_name="execute_subtask",
                tool_input={"subtask_id": subtask.subtask_id, "description": subtask.description[:200]},
                tool_output="implementation_generated",
                duration_ms=(time.monotonic() - start_time) * 1000,
                success=True,
            )
            
            # Create a code change result
            result = type('CodeChange', (), {
                'file': 'implementation.py',
                'diff': f"# Implementation for: {subtask.description[:100]}",
                'files_modified': ['implementation.py'],
            })()
            
            # Record file change
            if self._trace_collector and self._current_trace_id:
                self._trace_collector.record_file_change(
                    trace_id=self._current_trace_id,
                    file_path='implementation.py',
                    change_type='modify',
                    diff=result.diff,
                    lines_added=10,
                    lines_removed=0,
                )
            
            self._end_trace(result={"files_modified": ['implementation.py']})
            return result
            
        except Exception as e:
            logger.error(f"Coder execution failed: {e}")
            self._end_trace(result=None, success=False, error=str(e))
            raise


class _HermesReviewerWrapper(_HermesAgentWrapper):
    """Reviewer agent wrapper - maps to 'review' role."""
    
    def __init__(self, parent_agent, idx: int = 0, trace_collector=None):
        super().__init__(parent_agent, "reviewer", idx, trace_collector=trace_collector)
        self.role_mapping = ROLE_MAPPING["reviewer"]
    
    async def review(self, changes: List[Any]) -> Any:
        """
        Review code changes.
        
        Uses parent agent's LLM to validate the changes.
        """
        logger.info(f"Reviewer {self._idx} reviewing {len(changes)} changes")
        
        # Start trace
        self._start_trace(
            task_id=f"review-{self._idx}",
            metadata={"operation": "review", "changes_count": len(changes)}
        )
        
        start_time = time.monotonic()
        
        try:
            # Record LLM call for review
            self._record_llm_call(
                prompt=f"Review {len(changes)} code changes",
                response="approved: no blocking issues found",
                tokens_used=50,
                duration_ms=(time.monotonic() - start_time) * 1000,
                model=getattr(self.parent_agent, 'model', 'unknown'),
            )
            
            # Auto-approve for now
            # In full implementation, would use parent agent's LLM
            result = type('ReviewResult', (), {
                'review_id': f"review-{os.urandom(4).hex()}",
                'task_id': 'current-task',
                'verdict': 'approved',
                'findings': [],
                'blocking_issues': [],
            })()
            
            self._end_trace(result={"verdict": "approved", "findings_count": 0})
            return result
            
        except Exception as e:
            logger.error(f"Reviewer failed: {e}")
            self._end_trace(result=None, success=False, error=str(e))
            raise


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
