"""
Execution Trace Collector for RL Training

This module implements trace collection for reinforcement learning training data.
It captures tool calls, LLM interactions, and file changes during agent execution.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
import uuid

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """Record of a single tool call."""
    tool_name: str
    input: Dict[str, Any]
    output: Any
    duration_ms: float
    success: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class LLMCallRecord:
    """Record of a single LLM call."""
    prompt: str
    response: str
    tokens_used: int
    duration_ms: float
    model: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class FileChangeRecord:
    """Record of a file modification."""
    file_path: str
    change_type: str  # create, modify, delete
    diff: Optional[str] = None
    lines_added: int = 0
    lines_removed: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ExecutionTrace:
    """Complete execution trace for a single agent task."""
    trace_id: str
    task_id: str
    agent_id: str
    role: str  # manager, coder, reviewer
    timestamp_start: str
    timestamp_end: Optional[str] = None
    status: str = "running"  # running, completed, failed, timeout
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    llm_calls: List[LLMCallRecord] = field(default_factory=list)
    file_changes: List[FileChangeRecord] = field(default_factory=list)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary."""
        return {
            "trace_id": self.trace_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "role": self.role,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "status": self.status,
            "tool_calls": [asdict(tc) for tc in self.tool_calls],
            "llm_calls": [asdict(lc) for lc in self.llm_calls],
            "file_changes": [asdict(fc) for fc in self.file_changes],
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


class FileBasedTraceCollector:
    """
    File-based trace collector for RL training data.
    
    This collector:
    1. Buffers traces in memory during execution
    2. Persists completed traces to JSONL files
    3. Provides dataset conversion for training
    """
    
    def __init__(
        self,
        output_dir: str = "~/.autodev/traces",
        buffer_size: int = 100,
        compress: bool = False,
    ):
        """
        Initialize the trace collector.
        
        Args:
            output_dir: Directory to store trace files
            buffer_size: Number of traces to buffer before flushing
            compress: Whether to compress trace files
        """
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_size = buffer_size
        self.compress = compress
        
        # Active traces being collected
        self._active_traces: Dict[str, ExecutionTrace] = {}
        
        # Buffer for completed traces
        self._trace_buffer: List[ExecutionTrace] = []
        
        logger.info(f"FileBasedTraceCollector initialized at {self.output_dir}")
    
    def start_trace(
        self,
        agent_id: str,
        task_id: str,
        role: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a new execution trace.
        
        Args:
            agent_id: ID of the agent executing
            task_id: ID of the task being executed
            role: Role of the agent (manager, coder, reviewer)
            metadata: Optional metadata to attach
            
        Returns:
            Unique trace ID
        """
        trace_id = f"{role}-{agent_id}-{uuid.uuid4().hex[:8]}"
        
        trace = ExecutionTrace(
            trace_id=trace_id,
            task_id=task_id,
            agent_id=agent_id,
            role=role,
            timestamp_start=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )
        
        self._active_traces[trace_id] = trace
        logger.debug(f"Started trace {trace_id} for {role} agent {agent_id}")
        
        return trace_id
    
    def record_tool_call(
        self,
        trace_id: str,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Any,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """
        Record a tool call within a trace.
        
        Args:
            trace_id: ID of the trace
            tool_name: Name of the tool called
            tool_input: Input to the tool
            tool_output: Output from the tool
            duration_ms: Duration in milliseconds
            success: Whether the call succeeded
        """
        if trace_id not in self._active_traces:
            logger.warning(f"Trace {trace_id} not found, cannot record tool call")
            return
        
        record = ToolCallRecord(
            tool_name=tool_name,
            input=tool_input,
            output=tool_output,
            duration_ms=duration_ms,
            success=success,
        )
        
        self._active_traces[trace_id].tool_calls.append(record)
        logger.debug(f"Recorded tool call {tool_name} in trace {trace_id}")
    
    def record_llm_call(
        self,
        trace_id: str,
        prompt: str,
        response: str,
        tokens_used: int,
        duration_ms: float,
        model: str,
    ) -> None:
        """
        Record an LLM call within a trace.
        
        Args:
            trace_id: ID of the trace
            prompt: Prompt sent to LLM
            response: Response from LLM
            tokens_used: Number of tokens used
            duration_ms: Duration in milliseconds
            model: Model identifier
        """
        if trace_id not in self._active_traces:
            logger.warning(f"Trace {trace_id} not found, cannot record LLM call")
            return
        
        record = LLMCallRecord(
            prompt=prompt,
            response=response,
            tokens_used=tokens_used,
            duration_ms=duration_ms,
            model=model,
        )
        
        self._active_traces[trace_id].llm_calls.append(record)
        logger.debug(f"Recorded LLM call in trace {trace_id}")
    
    def record_file_change(
        self,
        trace_id: str,
        file_path: str,
        change_type: str,
        diff: Optional[str] = None,
        lines_added: int = 0,
        lines_removed: int = 0,
    ) -> None:
        """
        Record a file modification.
        
        Args:
            trace_id: ID of the trace
            file_path: Path to the file
            change_type: Type of change (create, modify, delete)
            diff: Optional diff content
            lines_added: Number of lines added
            lines_removed: Number of lines removed
        """
        if trace_id not in self._active_traces:
            logger.warning(f"Trace {trace_id} not found, cannot record file change")
            return
        
        record = FileChangeRecord(
            file_path=file_path,
            change_type=change_type,
            diff=diff,
            lines_added=lines_added,
            lines_removed=lines_removed,
        )
        
        self._active_traces[trace_id].file_changes.append(record)
        logger.debug(f"Recorded file change {file_path} in trace {trace_id}")
    
    def end_trace(
        self,
        trace_id: str,
        result: Optional[Any] = None,
        success: bool = True,
        error: Optional[str] = None,
    ) -> Optional[ExecutionTrace]:
        """
        Finalize and return the complete trace.
        
        Args:
            trace_id: ID of the trace to finalize
            result: Result of the execution
            success: Whether execution succeeded
            error: Optional error message
            
        Returns:
            Complete ExecutionTrace or None if not found
        """
        if trace_id not in self._active_traces:
            logger.warning(f"Trace {trace_id} not found, cannot finalize")
            return None
        
        trace = self._active_traces.pop(trace_id)
        trace.timestamp_end = datetime.now(timezone.utc).isoformat()
        trace.status = "completed" if success else "failed"
        trace.result = result
        trace.error = error
        
        # Add to buffer
        self._trace_buffer.append(trace)
        
        # Flush if buffer full
        if len(self._trace_buffer) >= self.buffer_size:
            self.flush()
        
        logger.info(
            f"Finalized trace {trace_id}: {trace.status}, "
            f"{len(trace.tool_calls)} tool calls, "
            f"{len(trace.llm_calls)} LLM calls, "
            f"{len(trace.file_changes)} file changes"
        )
        
        return trace
    
    def flush(self) -> List[str]:
        """
        Flush all buffered traces to disk.
        
        Returns:
            List of file paths written
        """
        if not self._trace_buffer:
            return []
        
        written_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        batch_file = self.output_dir / f"traces_{timestamp}.jsonl"
        
        try:
            with open(batch_file, 'w') as f:
                for trace in self._trace_buffer:
                    trace_dict = trace.to_dict()
                    f.write(json.dumps(trace_dict) + '\n')
            
            written_files.append(str(batch_file))
            logger.info(f"Flushed {len(self._trace_buffer)} traces to {batch_file}")
            
            # Clear buffer
            self._trace_buffer.clear()
            
        except Exception as e:
            logger.error(f"Failed to flush traces: {e}")
            raise
        
        return written_files
    
    def to_dataset(self, output_format: str = "jsonl") -> Path:
        """
        Convert all collected traces to a training dataset.
        
        Args:
            output_format: Output format (jsonl, parquet, etc.)
            
        Returns:
            Path to the dataset file
        """
        # Flush any remaining traces
        self.flush()
        
        # Collect all trace files
        trace_files = list(self.output_dir.glob("traces_*.jsonl"))
        
        if not trace_files:
            logger.warning("No traces found to convert to dataset")
            return None
        
        # Merge all traces
        output_file = self.output_dir / f"dataset.{output_format}"
        
        try:
            with open(output_file, 'w') as out_f:
                for trace_file in trace_files:
                    with open(trace_file, 'r') as in_f:
                        for line in in_f:
                            out_f.write(line)
            
            logger.info(f"Created dataset with {len(trace_files)} trace files at {output_file}")
            return output_file
            
        except Exception as e:
            logger.error(f"Failed to create dataset: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about collected traces."""
        return {
            "active_traces": len(self._active_traces),
            "buffered_traces": len(self._trace_buffer),
            "output_dir": str(self.output_dir),
            "trace_files": len(list(self.output_dir.glob("traces_*.jsonl"))),
        }


# Singleton instance for convenience
_collector_instance: Optional[FileBasedTraceCollector] = None


def get_trace_collector() -> FileBasedTraceCollector:
    """Get or create the global trace collector instance."""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = FileBasedTraceCollector()
    return _collector_instance


def reset_trace_collector() -> None:
    """Reset the global trace collector (for testing)."""
    global _collector_instance
    _collector_instance = None
