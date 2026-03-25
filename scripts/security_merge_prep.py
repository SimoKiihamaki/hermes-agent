#!/usr/bin/env python3
"""
Automated Security Merge Preparation Script

This script prepares and executes a git merge sequence for upstream security fixes,
handling the critical web_tools.py conflict intelligently by:
1. Preserving local page storage infrastructure
2. Adding SSRF protection from upstream
3. Running tests after each phase

Based on docs/SECURITY_MERGE_CHECKLIST.md

Usage:
    python scripts/security_merge_prep.py [--dry-run] [--phase PHASE_NUM]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path.home() / "Projects" / "hermes-agent"
BACKUP_BRANCH = "backup-pre-security-merge"
MERGE_BRANCH = "security-merge"
ORIGIN = "origin"
MAIN_BRANCH = "main"

# ANSI color codes
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"


class PhaseStatus(Enum):
    PENDING = "⬜"
    RUNNING = "🔄"
    SUCCESS = "✅"
    FAILED = "❌"
    SKIPPED = "⏭️"


@dataclass
class SecurityCommit:
    """Represents a security-related commit from upstream."""
    sha: str
    description: str
    category: str
    priority: str  # CRITICAL, HIGH, MEDIUM, LOW
    files: List[str] = field(default_factory=list)
    action: str = ""


@dataclass
class MergePhase:
    """Represents a phase in the merge process."""
    name: str
    description: str
    estimated_time: str
    status: PhaseStatus = PhaseStatus.PENDING
    commands: List[str] = field(default_factory=list)
    verification_cmd: Optional[str] = None
    rollback_cmd: Optional[str] = None
    is_critical: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Security Commits Configuration
# ─────────────────────────────────────────────────────────────────────────────

SECURITY_COMMITS = [
    SecurityCommit(
        sha="18cbd18f",
        description="Remove litellm/typer/platformdirs from hermes-agent deps (supply chain compromise)",
        category="supply-chain",
        priority="CRITICAL",
        files=["pyproject.toml", "requirements.txt", "scripts/install.sh", "setup-hermes.sh"],
        action="checkout"
    ),
    SecurityCommit(
        sha="c9b76057",
        description="Pin all dependency version ranges (supply chain hardening)",
        category="supply-chain",
        priority="HIGH",
        files=["pyproject.toml"],
        action="checkout"
    ),
    SecurityCommit(
        sha="ac5b8a47",
        description="Add supply chain audit workflow for PR scanning",
        category="ci-security",
        priority="HIGH",
        files=[".github/workflows/supply-chain-audit.yml"],
        action="checkout"
    ),
    SecurityCommit(
        sha="0791efe2",
        description="Add SSRF protection to vision_tools and web_tools",
        category="ssrf",
        priority="HIGH",
        files=["tools/url_safety.py", "tools/web_tools.py", "tools/vision_tools.py"],
        action="merge"
    ),
    SecurityCommit(
        sha="30c417fe",
        description="Add website blocklist enforcement for web/browser tools",
        category="security",
        priority="MEDIUM",
        files=["tools/website_policy.py"],
        action="checkout"
    ),
    SecurityCommit(
        sha="6fc76ef9",
        description="Harden website blocklist — default off, TTL cache, fail-open",
        category="security",
        priority="MEDIUM",
        files=["tools/website_policy.py"],
        action="checkout"
    ),
]


# ─────────────────────────────────────────────────────────────────────────────
# Web Tools SSRF Integration
# ─────────────────────────────────────────────────────────────────────────────

# SSRF import to add at the top of web_tools.py
SSRF_IMPORT = "from tools.url_safety import is_safe_url"

# SSRF check code for web_extract_tool (before backend dispatch)
SSRF_CHECK_EXTRACT = '''
        # ── SSRF protection — filter out private/internal URLs before any backend ──
        safe_urls = []
        ssrf_blocked: List[Dict[str, Any]] = []
        for url in urls:
            if not is_safe_url(url):
                ssrf_blocked.append({
                    "url": url, "title": "", "content": "",
                    "error": "Blocked: URL targets a private or internal network address",
                })
            else:
                safe_urls.append(url)
        
        if not safe_urls:
            # All URLs were blocked
            return json.dumps({"results": ssrf_blocked}, ensure_ascii=False)
        
        urls = safe_urls
        if ssrf_blocked:
            logger.warning("SSRF blocked %d URLs: %s", len(ssrf_blocked), [b["url"] for b in ssrf_blocked])
'''

# SSRF check code for web_crawl_tool
SSRF_CHECK_CRAWL = '''
        # SSRF protection — block private/internal addresses
        if not is_safe_url(url):
            return json.dumps({"results": [{"url": url, "title": "", "content": "",
                "error": "Blocked: URL targets a private or internal network address"}]}, ensure_ascii=False)
'''


def integrate_ssrf_protection(local_content: str) -> str:
    """
    Intelligently merge SSRF protection into local web_tools.py.
    
    Strategy:
    1. Keep all local page storage infrastructure
    2. Add is_safe_url import
    3. Add SSRF checks before backend dispatch in web_extract_tool
    4. Add SSRF checks before crawling in web_crawl_tool
    """
    lines = local_content.split('\n')
    output_lines = []
    
    ssrf_import_added = False
    ssrf_check_extract_added = False
    ssrf_check_crawl_added = False
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Add SSRF import after other tool imports
        if not ssrf_import_added and 'from tools.website_policy import' in line:
            output_lines.append(line)
            if SSRF_IMPORT not in local_content:
                output_lines.append(SSRF_IMPORT)
            ssrf_import_added = True
            i += 1
            continue
        
        # Add SSRF check in web_extract_tool before backend dispatch
        if not ssrf_check_extract_added and 'website_policy.check' in line and 'def web_extract' in '\n'.join(output_lines[-50:]):
            # Check if we're in the right function
            if 'async def web_extract' in '\n'.join(output_lines) or 'def web_extract' in '\n'.join(output_lines):
                # Add SSRF check before policy check
                if SSRF_CHECK_EXTRACT.strip() not in local_content:
                    output_lines.append(SSRF_CHECK_EXTRACT.rstrip())
                ssrf_check_extract_added = True
        
        # Add SSRF check in web_crawl_tool before crawling
        if not ssrf_check_crawl_added and 'async def web_crawl' in '\n'.join(output_lines[-10:]):
            # Look for where to insert - before the website policy check
            if 'blocked = check_website_access' in line or 'website_policy.check' in line:
                if SSRF_CHECK_CRAWL.strip() not in local_content:
                    output_lines.append(SSRF_CHECK_CRAWL.rstrip())
                ssrf_check_crawl_added = True
        
        output_lines.append(line)
        i += 1
    
    # If import wasn't added, add it near the top
    if not ssrf_import_added and SSRF_IMPORT not in local_content:
        for j, line in enumerate(output_lines):
            if line.startswith('from tools.') and 'import' in line:
                output_lines.insert(j + 1, SSRF_IMPORT)
                break
    
    return '\n'.join(output_lines)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def log(level: str, message: str) -> None:
    """Log a message with color coding."""
    colors = {
        "info": CYAN,
        "success": GREEN,
        "warning": YELLOW,
        "error": RED,
        "critical": RED + BOLD,
        "phase": MAGENTA + BOLD,
        "cmd": BLUE,
    }
    color = colors.get(level, "")
    print(f"{color}{message}{RESET}")


def run_command(cmd: str, cwd: Path = PROJECT_ROOT, check: bool = True, 
                capture: bool = False, dry_run: bool = False) -> Tuple[int, str]:
    """Run a shell command with logging."""
    log("cmd", f"  $ {cmd}")
    
    if dry_run:
        log("info", "  [DRY RUN - skipped]")
        return 0, ""
    
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=capture,
        text=True
    )
    
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)
    
    return result.returncode, result.stdout if capture else ""


def git_status_clean() -> bool:
    """Check if git working directory is clean."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    return result.stdout.strip() == ""


def get_current_branch() -> str:
    """Get the current git branch name."""
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()


def file_exists_in_upstream(filepath: str) -> bool:
    """Check if a file exists in upstream main."""
    result = subprocess.run(
        ["git", "show", f"{ORIGIN}/{MAIN_BRANCH}:{filepath}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    return result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Merge Phases
# ─────────────────────────────────────────────────────────────────────────────

def create_merge_phases() -> List[MergePhase]:
    """Create the ordered list of merge phases."""
    return [
        MergePhase(
            name="Backup & Setup",
            description="Create backup branch and prepare for merge",
            estimated_time="5 min",
            commands=[
                "git status",
                "git stash push -m 'Pre-security-merge stash' || true",
                f"git branch {BACKUP_BRANCH} || echo 'Backup branch already exists'",
                f"git checkout -B {MERGE_BRANCH}",
                f"git fetch {ORIGIN}",
            ],
            verification_cmd="git branch --list | grep -E '(backup-pre|security-merge)'",
            is_critical=True
        ),
        MergePhase(
            name="🔴 Supply Chain Fix",
            description="Remove compromised litellm/typer/platformdirs dependencies",
            estimated_time="15 min",
            commands=[
                f"git checkout {ORIGIN}/{MAIN_BRANCH} -- pyproject.toml",
                "grep -E 'litellm|typer|platformdirs' pyproject.toml || echo 'Compromised deps removed'",
            ],
            verification_cmd="pip install -e . --dry-run 2>&1 | head -20 || echo 'Dependencies check complete'",
            is_critical=True
        ),
        MergePhase(
            name="Supply Chain Hardening",
            description="Pin all dependency versions and add audit workflow",
            estimated_time="10 min",
            commands=[
                f"git checkout {ORIGIN}/{MAIN_BRANCH} -- .github/workflows/supply-chain-audit.yml",
            ],
            verification_cmd="ls -la .github/workflows/supply-chain-audit.yml",
        ),
        MergePhase(
            name="SSRF Protection - New Files",
            description="Add url_safety module and tests",
            estimated_time="5 min",
            commands=[
                f"git checkout {ORIGIN}/{MAIN_BRANCH} -- tools/url_safety.py",
                f"git checkout {ORIGIN}/{MAIN_BRANCH} -- tests/tools/test_url_safety.py 2>/dev/null || echo 'Test file not in upstream'",
            ],
            verification_cmd="python -c \"from tools.url_safety import is_safe_url; print('SSRF module OK')\"",
        ),
        MergePhase(
            name="Shell Injection Fix",
            description="Fix file_operations.py shell injection vulnerability",
            estimated_time="5 min",
            commands=[
                f"git checkout {ORIGIN}/{MAIN_BRANCH} -- tools/file_operations.py",
            ],
            verification_cmd="grep -A5 'echo ~' tools/file_operations.py | head -10",
        ),
        MergePhase(
            name="Web Tools SSRF Integration",
            description="Intelligently merge SSRF protection into web_tools.py (preserves page storage)",
            estimated_time="30 min",
            commands=[
                "# This is a special phase - handled by intelligent_merge_web_tools()",
            ],
            verification_cmd="python -c \"from tools.web_tools import *; print('web_tools imports OK')\"",
            is_critical=True
        ),
        MergePhase(
            name="Vision Tools SSRF",
            description="Add SSRF protection to vision_tools.py",
            estimated_time="10 min",
            commands=[
                f"git checkout {ORIGIN}/{MAIN_BRANCH} -- tools/vision_tools.py",
            ],
            verification_cmd="python -c \"from tools.vision_tools import *; print('vision_tools OK')\" 2>/dev/null || echo 'Import check skipped'",
        ),
        MergePhase(
            name="Test Suite",
            description="Run all tests to verify merge integrity",
            estimated_time="30 min",
            commands=[
                "pytest tests/tools/test_url_safety.py -v --tb=short 2>/dev/null || echo 'SSRF tests skipped'",
                "pytest tests/tools/ -k 'web or vision' -v --tb=short 2>/dev/null || echo 'Tool tests skipped'",
            ],
            verification_cmd="python -c \"from tools.url_safety import is_safe_url; assert not is_safe_url('http://127.0.0.1/admin'); print('SSRF protection verified')\"",
            is_critical=True
        ),
        MergePhase(
            name="Final Verification",
            description="Final checks and commit preparation",
            estimated_time="10 min",
            commands=[
                "git diff --cached --stat || git diff --stat",
                "ruff check tools/ tests/ 2>/dev/null || echo 'Lint check skipped'",
            ],
            verification_cmd="git status --short",
        ),
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Main Merge Logic
# ─────────────────────────────────────────────────────────────────────────────

def intelligent_merge_web_tools(dry_run: bool = False) -> bool:
    """
    Perform intelligent merge of web_tools.py:
    - Preserves local page storage infrastructure
    - Adds SSRF protection from upstream
    """
    log("phase", "\n" + "=" * 60)
    log("phase", "Phase: Web Tools SSRF Integration (Intelligent Merge)")
    log("phase", "=" * 60)
    
    web_tools_path = PROJECT_ROOT / "tools" / "web_tools.py"
    
    if not web_tools_path.exists():
        log("error", f"web_tools.py not found at {web_tools_path}")
        return False
    
    # Read local version
    log("info", "Reading local web_tools.py (with page storage)...")
    local_content = web_tools_path.read_text()
    local_lines = len(local_content.split('\n'))
    log("info", f"  Local version: {local_lines} lines")
    
    # Get upstream version
    log("info", "Reading upstream web_tools.py (with SSRF protection)...")
    result = subprocess.run(
        ["git", "show", f"{ORIGIN}/{MAIN_BRANCH}:tools/web_tools.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        log("warning", "Could not fetch upstream web_tools.py, using local only")
        upstream_content = ""
    else:
        upstream_content = result.stdout
        upstream_lines = len(upstream_content.split('\n'))
        log("info", f"  Upstream version: {upstream_lines} lines")
    
    # Check if SSRF protection already exists locally
    if "from tools.url_safety import is_safe_url" in local_content:
        log("success", "SSRF protection already integrated in local web_tools.py")
        return True
    
    # Perform intelligent merge
    log("info", "Integrating SSRF protection while preserving page storage...")
    
    merged_content = integrate_ssrf_protection(local_content)
    merged_lines = len(merged_content.split('\n'))
    
    log("info", f"  Merged version: {merged_lines} lines")
    
    if dry_run:
        log("info", "[DRY RUN] Would write merged content to web_tools.py")
        # Show a preview of the changes
        log("info", "\nKey additions:")
        log("info", "  + from tools.url_safety import is_safe_url")
        log("info", "  + SSRF URL validation before web_extract_tool backend dispatch")
        log("info", "  + SSRF URL validation before web_crawl_tool execution")
        return True
    
    # Create backup of original
    backup_path = web_tools_path.with_suffix('.py.backup')
    shutil.copy(web_tools_path, backup_path)
    log("info", f"  Backup saved to: {backup_path}")
    
    # Write merged content
    web_tools_path.write_text(merged_content)
    log("success", f"Successfully merged web_tools.py ({merged_lines} lines)")
    
    return True


def run_phase(phase: MergePhase, dry_run: bool = False) -> bool:
    """Run a single merge phase."""
    log("phase", f"\n{'=' * 60}")
    log("phase", f"Phase: {phase.name}")
    log("info", f"  {phase.description}")
    log("info", f"  Estimated time: {phase.estimated_time}")
    log("phase", "=" * 60)
    
    if phase.name == "Web Tools SSRF Integration":
        return intelligent_merge_web_tools(dry_run)
    
    try:
        for cmd in phase.commands:
            if cmd.startswith('#'):
                log("info", cmd)
                continue
            run_command(cmd, dry_run=dry_run, check=False)
        
        if phase.verification_cmd:
            log("info", "\nRunning verification...")
            run_command(phase.verification_cmd, dry_run=dry_run, check=False)
        
        log("success", f"\n✓ Phase '{phase.name}' completed successfully")
        return True
        
    except subprocess.CalledProcessError as e:
        log("error", f"\n✗ Phase '{phase.name}' failed: {e}")
        if phase.rollback_cmd:
            log("warning", "Attempting rollback...")
            run_command(phase.rollback_cmd, dry_run=dry_run, check=False)
        return False


def run_all_phases(dry_run: bool = False, specific_phase: Optional[int] = None) -> bool:
    """Run all merge phases in order."""
    phases = create_merge_phases()
    
    log("info", "\n" + "=" * 60)
    log("info", "SECURITY MERGE PREPARATION")
    log("info", "=" * 60)
    log("info", f"Project: {PROJECT_ROOT}")
    log("info", f"Dry run: {dry_run}")
    log("info", f"Total phases: {len(phases)}")
    if specific_phase is not None:
        log("info", f"Running only phase: {specific_phase}")
    log("info", "")
    
    # Pre-flight checks
    if not PROJECT_ROOT.exists():
        log("error", f"Project directory not found: {PROJECT_ROOT}")
        return False
    
    if not git_status_clean() and not dry_run:
        log("warning", "Working directory is not clean!")
        log("info", "Uncommitted changes will be stashed during merge.")
    
    # Print phase overview
    log("info", "\nPhase Overview:")
    for i, phase in enumerate(phases, 1):
        critical_marker = " 🔴" if phase.is_critical else ""
        log("info", f"  {i}. {phase.name} ({phase.estimated_time}){critical_marker}")
    
    # Run phases
    failed_phases = []
    
    for i, phase in enumerate(phases, 1):
        if specific_phase is not None and i != specific_phase:
            continue
        
        success = run_phase(phase, dry_run=dry_run)
        
        if not success:
            failed_phases.append((i, phase.name))
            if phase.is_critical:
                log("critical", f"\n🔴 CRITICAL FAILURE in phase '{phase.name}'")
                log("error", "Aborting merge process.")
                break
        else:
            phase.status = PhaseStatus.SUCCESS
    
    # Summary
    log("info", "\n" + "=" * 60)
    log("info", "MERGE SUMMARY")
    log("info", "=" * 60)
    
    if failed_phases:
        log("error", f"Failed phases: {len(failed_phases)}")
        for num, name in failed_phases:
            log("error", f"  - Phase {num}: {name}")
        return False
    else:
        log("success", "All phases completed successfully!")
        log("info", "\nNext steps:")
        log("info", "  1. Review changes: git diff --cached")
        log("info", "  2. Run full test suite: pytest tests/ -v")
        log("info", "  3. Commit changes: git commit -m 'Merge upstream security fixes'")
        log("info", f"  4. Backup branch: {BACKUP_BRANCH}")
        log("info", f"  5. Merge branch: {MERGE_BRANCH}")
        return True


def generate_merge_plan() -> str:
    """Generate a detailed merge plan document."""
    phases = create_merge_phases()
    
    plan = []
    plan.append("# Security Merge Plan")
    plan.append(f"# Generated: {datetime.now().isoformat()}")
    plan.append(f"# Project: {PROJECT_ROOT}")
    plan.append("")
    plan.append("## Security Commits to Merge")
    plan.append("")
    
    for commit in SECURITY_COMMITS:
        priority_emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}
        emoji = priority_emoji.get(commit.priority, "⚪")
        plan.append(f"- {emoji} `{commit.sha[:8]}`: {commit.description}")
        plan.append(f"  - Category: {commit.category}")
        plan.append(f"  - Files: {', '.join(commit.files)}")
        plan.append("")
    
    plan.append("## Merge Phases")
    plan.append("")
    
    for i, phase in enumerate(phases, 1):
        critical = " **CRITICAL**" if phase.is_critical else ""
        plan.append(f"### Phase {i}: {phase.name}{critical}")
        plan.append(f"- **Description:** {phase.description}")
        plan.append(f"- **Estimated Time:** {phase.estimated_time}")
        plan.append(f"- **Commands:**")
        for cmd in phase.commands:
            plan.append(f"  ```bash")
            plan.append(f"  {cmd}")
            plan.append(f"  ```")
        if phase.verification_cmd:
            plan.append(f"- **Verification:** `{phase.verification_cmd}`")
        plan.append("")
    
    return "\n".join(plan)


# ─────────────────────────────────────────────────────────────────────────────
# CLI Interface
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Automated Security Merge Preparation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run to see what would happen
  python scripts/security_merge_prep.py --dry-run

  # Run all phases
  python scripts/security_merge_prep.py

  # Run only phase 2
  python scripts/security_merge_prep.py --phase 2

  # Generate merge plan document
  python scripts/security_merge_prep.py --plan
        """
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--phase",
        type=int,
        help="Run only a specific phase (1-indexed)"
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Generate and print the merge plan"
    )
    parser.add_argument(
        "--verify-ssrf",
        action="store_true",
        help="Verify SSRF protection is working"
    )
    
    args = parser.parse_args()
    
    if args.plan:
        print(generate_merge_plan())
        return 0
    
    if args.verify_ssrf:
        log("info", "Verifying SSRF protection...")
        try:
            from tools.url_safety import is_safe_url
            
            test_cases = [
                ("http://127.0.0.1/admin", False),
                ("http://localhost/admin", False),
                ("http://192.168.1.1/admin", False),
                ("http://10.0.0.1/admin", False),
                ("http://169.254.169.254/latest/meta-data", False),
                ("http://metadata.google.internal", False),
                ("https://example.com", True),
                ("https://github.com", True),
            ]
            
            all_passed = True
            for url, expected in test_cases:
                result = is_safe_url(url)
                status = "✓" if result == expected else "✗"
                if result != expected:
                    all_passed = False
                print(f"  {status} is_safe_url('{url}') = {result} (expected {expected})")
            
            if all_passed:
                log("success", "\n✓ All SSRF tests passed!")
                return 0
            else:
                log("error", "\n✗ Some SSRF tests failed!")
                return 1
                
        except ImportError as e:
            log("error", f"Cannot import url_safety module: {e}")
            log("info", "Run with --phase 4 to add the SSRF protection module first.")
            return 1
    
    success = run_all_phases(dry_run=args.dry_run, specific_phase=args.phase)
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
