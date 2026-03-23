#!/usr/bin/env python3
"""
Hermes AutoDev Tool - Phase 6 Production Integration

Provides a Hermes tool interface to the AutoDev pipeline, enabling autonomous
coding tasks through the delegate_task architecture. Integrates with MCP servers
for filesystem, git, and terminal operations.

This module bridges:
  - Hermes agent system (tools/registry, delegate_task)
  - AutoDev pipeline (LLM + MCP integration)
  - MCP servers (filesystem, git, terminal)

Usage (as Hermes tool):
    autodev(
        task="Create a Python function that calculates fibonacci numbers",
        workspace="/path/to/project",
        context={"files": ["main.py"], "requirements": "Python 3.11+"}
    )

Architecture:
    Hermes Agent
         │
         ▼
    delegate_task → autodev tool
         │
         ▼
    AutoDevPipeline
         │
         ├── LLM Client (Claude/OpenAI/etc)
         │
         └── MCP Client
              ├── filesystem server
              ├── git server
              └── terminal server
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# AutoDev path configuration
AUTODEV_ROOT = Path(os.getenv("AUTODEV_ROOT", Path.home() / "Projects" / "autodev"))
AUTODEV_SRC = AUTODEV_ROOT / "src"
AUTODEV_CONFIG = AUTODEV_ROOT / "config"

# Add AutoDev to path if available
if AUTODEV_SRC.exists():
    sys.path.insert(0, str(AUTODEV_SRC.parent))

# Try to import AutoDev components
AUTODEV_AVAILABLE = False
AutoDevPipeline = None
CoderPipeline = None
PipelineConfig = None
ExecutionResult = None

try:
    from integration import (
        CoderPipeline,
        PipelineConfig,
        ExecutionResult,
    )
    AUTODEV_AVAILABLE = True
    logger.info("AutoDev integration loaded successfully")
except ImportError as e:
    logger.warning(f"AutoDev not available: {e}. Using fallback mode.")


# =============================================================================
# Configuration
# =============================================================================

DEFAULT_MCP_CONFIG = {
    "servers": [
        {
            "name": "filesystem",
            "command": "mcp-server-filesystem",
            "args": ["--root", "."],
            "env": {},
            "enabled": True,
            "auto_start": True,
            "description": "File system operations for reading and writing code files"
        },
        {
            "name": "git",
            "command": "mcp-server-git",
            "args": [],
            "env": {},
            "enabled": True,
            "auto_start": True,
            "description": "Git version control operations"
        },
        {
            "name": "terminal",
            "command": "mcp-server-terminal",
            "args": [],
            "env": {},
            "enabled": True,
            "auto_start": True,
            "description": "Command execution for running tests, linters, etc."
        }
    ],
    "security": {
        "allowed_paths": ["."],
        "allowed_commands": [
            "pytest", "python", "python3", "black", "mypy", "flake8",
            "pylint", "git", "npm", "yarn", "go", "cargo", "make"
        ],
        "require_confirmation": False
    },
    "connection_settings": {
        "timeout_seconds": 10,
        "retry_attempts": 3,
        "retry_delay_seconds": 1
    }
}


def get_mcp_config_path() -> Path:
    """Get the MCP configuration file path."""
    # Check environment variable first
    env_path = os.getenv("AUTODEV_MCP_CONFIG")
    if env_path:
        return Path(env_path)
    
    # Check standard locations
    candidates = [
        AUTODEV_CONFIG / "mcp_config.json",
        Path.home() / ".config" / "autodev" / "mcp_config.json",
        Path.home() / ".autodev" / "mcp_config.json",
    ]
    
    for candidate in candidates:
        if candidate.exists():
            return candidate
    
    # Return default location (may not exist)
    return candidates[0]


def ensure_mcp_config() -> Path:
    """Ensure MCP configuration exists, creating default if needed."""
    config_path = get_mcp_config_path()
    
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(DEFAULT_MCP_CONFIG, f, indent=2)
        logger.info(f"Created default MCP config at {config_path}")
    
    return config_path


# =============================================================================
# Tool Implementation
# =============================================================================

class AutoDevSession:
    """
    Manages an AutoDev pipeline session.
    
    Provides async context manager for clean resource management.
    """
    
    def __init__(
        self,
        workspace: str = ".",
        api_key: Optional[str] = None,
        max_iterations: int = 20,
        model: str = "claude-sonnet-4-20250514"
    ):
        self.workspace = Path(workspace).resolve()
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.max_iterations = max_iterations
        self.model = model
        self._pipeline: Optional[CoderPipeline] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize the AutoDev pipeline."""
        if not AUTODEV_AVAILABLE:
            raise RuntimeError(
                "AutoDev pipeline not available. "
                "Ensure autodev is installed and src/integration.py is accessible."
            )
        
        if not self.api_key:
            raise RuntimeError(
                "No API key provided. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )
        
        # Ensure workspace exists
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        # Ensure MCP config exists
        mcp_config_path = ensure_mcp_config()
        
        # Create pipeline configuration
        from llm.client import LLMConfig
        
        llm_config = LLMConfig(
            api_key=self.api_key,
            model=self.model
        )
        
        pipeline_config = PipelineConfig(
            llm_config=llm_config,
            mcp_config_path=str(mcp_config_path),
            max_tool_iterations=self.max_iterations,
            workspace_path=str(self.workspace),
            enable_logging=True,
            log_level="INFO"
        )
        
        self._pipeline = CoderPipeline(pipeline_config)
        await self._pipeline.initialize()
        self._initialized = True
        
        logger.info(f"AutoDev session initialized in {self.workspace}")
    
    async def execute(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None
    ) -> ExecutionResult:
        """Execute a coding task."""
        if not self._initialized:
            await self.initialize()
        
        return await self._pipeline.execute_task(
            task=task,
            context=context,
            system_prompt=system_prompt
        )
    
    async def shutdown(self) -> None:
        """Shutdown the pipeline."""
        if self._pipeline:
            await self._pipeline.shutdown()
            self._initialized = False
            logger.info("AutoDev session shut down")
    
    async def __aenter__(self):
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.shutdown()


# Global session cache (for reusing pipelines across calls)
_session_cache: Dict[str, AutoDevSession] = {}


async def get_or_create_session(
    workspace: str,
    api_key: Optional[str] = None,
    max_iterations: int = 20
) -> AutoDevSession:
    """Get or create an AutoDev session for the given workspace."""
    cache_key = f"{workspace}:{max_iterations}"
    
    if cache_key not in _session_cache:
        session = AutoDevSession(
            workspace=workspace,
            api_key=api_key,
            max_iterations=max_iterations
        )
        await session.initialize()
        _session_cache[cache_key] = session
    
    return _session_cache[cache_key]


async def _run_autodev_async(
    task: str,
    workspace: str = ".",
    context: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    max_iterations: int = 20,
    system_prompt: Optional[str] = None,
    **kwargs
) -> str:
    """
    Async implementation of the autodev tool.
    
    Args:
        task: The coding task to execute
        workspace: Working directory for the task
        context: Additional context (files, requirements, constraints)
        api_key: API key (uses env var if not provided)
        max_iterations: Maximum tool calling iterations
        system_prompt: Optional custom system prompt
        **kwargs: Additional parameters (ignored)
    
    Returns:
        JSON string with execution result
    """
    if not AUTODEV_AVAILABLE:
        return json.dumps({
            "success": False,
            "error": "AutoDev pipeline not available",
            "hint": "Ensure autodev is installed at ~/Projects/autodev/ with src/integration.py"
        })
    
    try:
        async with AutoDevSession(
            workspace=workspace,
            api_key=api_key,
            max_iterations=max_iterations
        ) as session:
            result = await session.execute(
                task=task,
                context=context,
                system_prompt=system_prompt
            )
            
            return json.dumps({
                "success": result.success,
                "content": result.content,
                "files_modified": result.files_modified,
                "tools_called": result.tools_called,
                "iterations": result.iterations,
                "tokens_used": result.tokens_used,
                "execution_time_seconds": result.execution_time_seconds,
                "error": result.error,
                "metadata": result.metadata
            }, indent=2)
    
    except Exception as e:
        logger.exception("AutoDev execution failed")
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        })


def autodev(
    task: str,
    workspace: str = ".",
    context: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    max_iterations: int = 20,
    system_prompt: Optional[str] = None,
    **kwargs
) -> str:
    """
    Synchronous wrapper for the autodev tool.
    
    This is the main entry point called by the Hermes tool registry.
    """
    try:
        # Get or create event loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        
        if loop and loop.is_running():
            # We're in an async context, create a new loop in a thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    _run_autodev_async(
                        task=task,
                        workspace=workspace,
                        context=context,
                        api_key=api_key,
                        max_iterations=max_iterations,
                        system_prompt=system_prompt,
                        **kwargs
                    )
                )
                return future.result(timeout=300)  # 5 minute timeout
        else:
            # No running loop, we can use asyncio.run
            return asyncio.run(_run_autodev_async(
                task=task,
                workspace=workspace,
                context=context,
                api_key=api_key,
                max_iterations=max_iterations,
                system_prompt=system_prompt,
                **kwargs
            ))
    except Exception as e:
        logger.exception("autodev tool failed")
        return json.dumps({
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__
        })


# =============================================================================
# Hermes delegate_task Integration
# =============================================================================

def autodev_delegate_handler(
    args: Dict[str, Any],
    parent_agent=None,
    **kwargs
) -> str:
    """
    Handler for delegate_task integration.
    
    When delegate_task spawns a subagent with toolset including 'autodev',
    this handler is called to execute the delegated coding task.
    
    Args:
        args: Tool arguments from delegate_task
        parent_agent: Reference to parent AIAgent (for context)
        **kwargs: Additional context from delegate_task
    
    Returns:
        JSON string with result summary
    """
    # Extract context from parent agent if available
    extra_context = {}
    
    if parent_agent:
        # Get working directory from parent
        if hasattr(parent_agent, 'task_id'):
            # Use parent's task context
            from run_agent import TASK_WORKDIRS
            workdir = TASK_WORKDIRS.get(parent_agent.task_id, os.getcwd())
            extra_context["parent_workspace"] = workdir
        
        # Get any relevant memory
        if hasattr(parent_agent, 'memory_store') and parent_agent.memory_store:
            memory_snapshot = parent_agent.memory_store.get_memory_snapshot()
            if memory_snapshot:
                extra_context["parent_memory"] = memory_snapshot[:500]  # Limit size
    
    # Merge contexts
    context = args.get("context", {})
    if extra_context:
        context.setdefault("parent_context", extra_context)
    
    # Execute the task
    return autodev(
        task=args.get("task", args.get("goal", "")),
        workspace=args.get("workspace", "."),
        context=context,
        max_iterations=args.get("max_iterations", 20),
        system_prompt=args.get("system_prompt"),
        **kwargs
    )


# =============================================================================
# Requirements Check
# =============================================================================

def check_autodev_requirements() -> bool:
    """
    Check if AutoDev is available and properly configured.
    
    Returns True if:
    - AutoDev integration module is importable
    - ANTHROPIC_API_KEY is set (or available via env)
    """
    if not AUTODEV_AVAILABLE:
        return False
    
    # Check for API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.debug("ANTHROPIC_API_KEY not set")
        return False
    
    return True


# =============================================================================
# OpenAI Function-Calling Schema
# =============================================================================

AUTODEV_SCHEMA = {
    "name": "autodev",
    "description": (
        "Execute autonomous coding tasks using the AutoDev pipeline. "
        "This tool provides access to an AI coding agent with file operations, "
        "git integration, and command execution capabilities.\n\n"
        "WHEN TO USE autodev:\n"
        "- Complex coding tasks requiring multiple file modifications\n"
        "- Refactoring operations across a codebase\n"
        "- Implementing new features with tests\n"
        "- Bug fixes requiring code analysis and modification\n"
        "- Code generation with proper project structure\n\n"
        "CAPABILITIES:\n"
        "- Read and write files in the workspace\n"
        "- Execute shell commands (tests, linters, builds)\n"
        "- Git operations (status, diff, commit)\n"
        "- Iterative problem-solving with tool feedback\n\n"
        "PARAMETERS:\n"
        "- task: Clear description of what to implement or fix\n"
        "- workspace: Directory to work in (default: current)\n"
        "- context: Additional context (files, requirements, constraints)\n"
        "- max_iterations: Maximum tool calls (default: 20)\n\n"
        "RETURNS: JSON with success status, content, modified files, and execution stats.\n\n"
        "EXAMPLES:\n"
        "  autodev(task=\"Create a Python module for user authentication\")\n"
        "  autodev(task=\"Fix the bug in main.py\", workspace=\"/path/to/project\")\n"
        "  autodev(task=\"Add unit tests\", context={\"files\": [\"auth.py\"]})"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": (
                    "The coding task to execute. Be specific about requirements, "
                    "file locations, and expected behavior."
                )
            },
            "workspace": {
                "type": "string",
                "description": (
                    "Working directory for the task. Defaults to current directory. "
                    "Use absolute paths for clarity."
                ),
                "default": "."
            },
            "context": {
                "type": "object",
                "description": (
                    "Additional context for the task. Can include:\n"
                    "- files: list of relevant files\n"
                    "- requirements: specific requirements or constraints\n"
                    "- constraints: limitations to respect"
                ),
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of relevant files to consider"
                    },
                    "requirements": {
                        "type": "string",
                        "description": "Specific requirements for the implementation"
                    },
                    "constraints": {
                        "type": "string",
                        "description": "Constraints or limitations to respect"
                    }
                }
            },
            "max_iterations": {
                "type": "integer",
                "description": "Maximum number of tool calling iterations",
                "default": 20,
                "minimum": 1,
                "maximum": 50
            },
            "system_prompt": {
                "type": "string",
                "description": "Optional custom system prompt for the coding agent"
            }
        },
        "required": ["task"]
    }
}


# =============================================================================
# Registry Registration
# =============================================================================

from tools.registry import registry

registry.register(
    name="autodev",
    toolset="autodev",
    schema=AUTODEV_SCHEMA,
    handler=lambda args, **kw: autodev(
        task=args.get("task", ""),
        workspace=args.get("workspace", "."),
        context=args.get("context"),
        max_iterations=args.get("max_iterations", 20),
        system_prompt=args.get("system_prompt"),
        **{k: v for k, v in kw.items() if k not in ['store', 'parent_agent']}
    ),
    check_fn=check_autodev_requirements,
    requires_env=["ANTHROPIC_API_KEY"],
    is_async=False,  # We handle async internally
    description="Autonomous coding agent with file/git/terminal tools",
    emoji="🤖",
)


# =============================================================================
# Toolset Definition for toolsets.py
# =============================================================================

AUTODEV_TOOLSET = {
    "name": "autodev",
    "description": "Autonomous coding agent integration",
    "env_vars": ["ANTHROPIC_API_KEY"],
    "tools": ["autodev"],
    "check_fn": check_autodev_requirements,
    "setup_url": "https://github.com/modelcontextprotocol/servers"
}


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    'autodev',
    'AutoDevSession',
    'autodev_delegate_handler',
    'check_autodev_requirements',
    'AUTODEV_SCHEMA',
    'AUTODEV_TOOLSET',
    'DEFAULT_MCP_CONFIG',
    'ensure_mcp_config',
    'get_mcp_config_path',
]
