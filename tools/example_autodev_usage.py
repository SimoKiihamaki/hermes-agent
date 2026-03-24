#!/usr/bin/env python3
"""
Example: Using AutoDev hierarchical execution with delegate_task

This demonstrates the complete flow:
1. Standard delegation (default)
2. AutoDev hierarchical execution
3. Result comparison
"""

import sys
import os

# Setup paths
sys.path.insert(0, os.path.expanduser("~/Projects/hermes-agent"))

import json
from typing import Any, Dict


class ExampleAgent:
    """Example parent agent for demonstration."""
    
    def __init__(self):
        self.working_dir = "/tmp/example"
        self.model = "example-model"
        self.base_url = "https://api.example.com"
        self.api_key = "example-key"


def example_standard_delegation():
    """Example: Standard delegation (spawns child AIAgent)."""
    print("=" * 60)
    print("Example 1: Standard Delegation")
    print("=" * 60)
    
    from tools.delegate_tool import delegate_task
    
    agent = ExampleAgent()
    
    result = delegate_task(
        goal="Fix the authentication bug",
        context="Error in login.py line 42",
        parent_agent=agent
    )
    
    result_dict = json.loads(result)
    print("\nResult:")
    print(json.dumps(result_dict, indent=2))
    
    return result_dict


def example_autodev_delegation():
    """Example: AutoDev hierarchical execution."""
    print("\n" + "=" * 60)
    print("Example 2: AutoDev Hierarchical Execution")
    print("=" * 60)
    
    from tools.delegate_tool import delegate_task
    
    agent = ExampleAgent()
    
    result = delegate_task(
        goal="Implement user authentication system",
        context="Requirements: JWT-based, support refresh tokens, integrate with existing user model",
        task_type="autodev",
        parent_agent=agent
    )
    
    result_dict = json.loads(result)
    print("\nResult:")
    print(json.dumps(result_dict, indent=2))
    
    return result_dict


def example_comparison():
    """Compare standard vs AutoDev delegation."""
    print("\n" + "=" * 60)
    print("Example 3: Comparison")
    print("=" * 60)
    
    print("\nStandard Delegation:")
    print("  - Spawns isolated child agent")
    print("  - Single execution path")
    print("  - Best for: focused tasks, debugging, research")
    
    print("\nAutoDev Hierarchical:")
    print("  - Manager→Coder→Reviewer flow")
    print("  - Iterative refinement")
    print("  - Best for: complex development tasks, feature implementation")
    
    print("\nKey Differences:")
    print("  - Standard: fast, isolated, single-shot")
    print("  - AutoDev: thorough, iterative, validated")


def show_usage_patterns():
    """Show common usage patterns."""
    print("\n" + "=" * 60)
    print("Common Usage Patterns")
    print("=" * 60)
    
    patterns = [
        {
            "name": "Quick Bug Fix",
            "type": "default",
            "goal": "Fix null pointer exception in UserService.java",
            "context": "Stack trace shows error at line 145",
            "recommended": "default",
            "reason": "Single focused task, no planning needed"
        },
        {
            "name": "Feature Implementation",
            "type": "autodev",
            "goal": "Implement REST API endpoints for user management",
            "context": "CRUD operations needed, integrate with existing auth system",
            "recommended": "autodev",
            "reason": "Complex task requiring decomposition, implementation, and review"
        },
        {
            "name": "Code Refactoring",
            "type": "autodev",
            "goal": "Refactor payment processing module",
            "context": "Improve error handling, add logging, maintain backward compatibility",
            "recommended": "autodev",
            "reason": "Requires careful planning and validation to preserve functionality"
        },
        {
            "name": "Research Task",
            "type": "default",
            "goal": "Investate performance bottleneck in database queries",
            "context": "Users reporting slow load times on dashboard",
            "recommended": "default",
            "reason": "Investigation/exploration task, single-shot execution"
        }
    ]
    
    for pattern in patterns:
        print(f"\n{pattern['name']}:")
        print(f"  Type: {pattern['type']}")
        print(f"  Goal: {pattern['goal']}")
        print(f"  Recommended: {pattern['recommended']} - {pattern['reason']}")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("AutoDev Integration Examples")
    print("=" * 60)
    
    # Show patterns
    show_usage_patterns()
    
    # Run examples (may fail if AutoDev not available)
    print("\n" + "=" * 60)
    print("Running Live Examples")
    print("=" * 60)
    
    try:
        example_standard_delegation()
    except Exception as e:
        print(f"\nStandard delegation example failed: {e}")
    
    try:
        example_autodev_delegation()
    except Exception as e:
        print(f"\nAutoDev delegation example failed: {e}")
        print("This is expected if AutoDev components are not available.")
    
    # Show comparison
    example_comparison()
    
    print("\n" + "=" * 60)
    print("Examples Complete")
    print("=" * 60)


if __name__ == "__main__":
    main()
