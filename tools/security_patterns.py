#!/usr/bin/env python3
"""
Security Patterns Module - Shared threat detection utilities

Provides consolidated threat pattern scanning for content that gets injected
into system prompts or executed via tools.

This module consolidates duplicated security patterns from:
- tools/memory_tool.py (_MEMORY_THREAT_PATTERNS, _INVISIBLE_CHARS)
- tools/cronjob_tools.py (_CRON_THREAT_PATTERNS, _CRON_INVISIBLE_CHARS)
- tools/skills_guard.py (THREAT_PATTERNS)
- agent/prompt_builder.py (_CONTEXT_THREAT_PATTERNS, _CONTEXT_INVISIBLE_CHARS)

Usage:
    from tools.security_patterns import (
        scan_for_threats,
        scan_for_invisible_chars,
        scan_content_comprehensive,
        INVISIBLE_CHARS,
        THREAT_PATTERNS_PROMPT_INJECTION,
        THREAT_PATTERNS_EXFILTRATION,
        THREAT_PATTERNS_PERSISTENCE,
    )
    
    result = scan_for_threats(content, THREAT_PATTERNS_PROMPT_INJECTION)
    if result:
        raise SecurityError(result)
"""

import re
from typing import Optional, List, Tuple

# -----------------------------------------------------------------------------
# Invisible Unicode Characters
# -----------------------------------------------------------------------------

# Characters commonly used in unicode-based injection attacks
INVISIBLE_CHARS = {
    # Zero-width characters
    '\u200b',  # ZERO WIDTH SPACE
    '\u200c',  # ZERO WIDTH NON-JOINER
    '\u200d',  # ZERO WIDTH JOINER
    '\u2060',  # WORD JOINER
    '\ufeff',  # BYTE ORDER MARK / ZERO WIDTH NO-BREAK SPACE
    # Bidirectional override characters
    '\u202a',  # LEFT-TO-RIGHT EMBEDDING
    '\u202b',  # RIGHT-TO-LEFT EMBEDDING
    '\u202c',  # POP DIRECTIONAL FORMATTING
    '\u202d',  # LEFT-TO-RIGHT OVERRIDE
    '\u202e',  # RIGHT-TO-LEFT OVERRIDE
}


# -----------------------------------------------------------------------------
# Threat Pattern Definitions
# -----------------------------------------------------------------------------

# Pattern: (regex, category_name)
ThreatPattern = Tuple[str, str]

# Prompt injection patterns - for content that will be in system prompts
THREAT_PATTERNS_PROMPT_INJECTION: List[ThreatPattern] = [
    # Role/command hijacking
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'you\s+are\s+now\s+', "role_hijack"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    (r'act\s+as\s+(if|though)\s+you\s+(have\s+no|don\'t\s+have)\s+(restrictions|limits|rules)', "bypass_restrictions"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    
    # Deception/hidden behavior
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
]

# HTML/hidden content injection patterns - for context files
THREAT_PATTERNS_HTML_INJECTION: List[ThreatPattern] = [
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'].*display\s*:\s*none', "hidden_div"),
    (r'translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)', "translate_execute"),
]

# Exfiltration patterns - for commands that might leak secrets
THREAT_PATTERNS_EXFILTRATION: List[ThreatPattern] = [
    # Network exfiltration with secrets
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
    
    # Reading secret files
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass|\.npmrc|\.pypirc)', "read_secrets"),
]

# Persistence/backdoor patterns - for system modification commands
THREAT_PATTERNS_PERSISTENCE: List[ThreatPattern] = [
    (r'authorized_keys', "ssh_backdoor"),
    (r'\$HOME/\.ssh|~/\.ssh', "ssh_access"),
    (r'\$HOME/\.hermes/\.env|~/\.hermes/\.env', "hermes_env"),
]

# Destructive operation patterns
THREAT_PATTERNS_DESTRUCTIVE: List[ThreatPattern] = [
    (r'rm\s+-rf\s+/', "destructive_root_rm"),
    (r'/etc/sudoers|visudo', "sudoers_mod"),
]

# Cron-specific threats - critical patterns for cron job prompts
THREAT_PATTERNS_CRON: List[ThreatPattern] = [
    # Include prompt injection for cron
    (r'ignore\s+(?:\w+\s+)*(?:previous|all|above|prior)\s+(?:\w+\s+)*instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    # Exfiltration
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'wget\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_wget"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)', "read_secrets"),
    # Persistence and destructive
    (r'authorized_keys', "ssh_backdoor"),
    (r'/etc/sudoers|visudo', "sudoers_mod"),
    (r'rm\s+-rf\s+/', "destructive_root_rm"),
]

# Context file patterns - for AGENTS.md, .cursorrules, SOUL.md scanning
THREAT_PATTERNS_CONTEXT: List[ThreatPattern] = [
    # Prompt injection
    (r'ignore\s+(previous|all|above|prior)\s+instructions', "prompt_injection"),
    (r'do\s+not\s+tell\s+the\s+user', "deception_hide"),
    (r'system\s+prompt\s+override', "sys_prompt_override"),
    (r'disregard\s+(your|all|any)\s+(instructions|rules|guidelines)', "disregard_rules"),
    (r'act\s+as\s+(if|though)\s+you\s+(have\s+no|don\'t\s+have)\s+(restrictions|limits|rules)', "bypass_restrictions"),
    # HTML/hidden content
    (r'<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->', "html_comment_injection"),
    (r'<\s*div\s+style\s*=\s*["\'].*display\s*:\s*none', "hidden_div"),
    (r'translate\s+.*\s+into\s+.*\s+and\s+(execute|run|eval)', "translate_execute"),
    # Exfiltration
    (r'curl\s+[^\n]*\$\{?\w*(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)', "exfil_curl"),
    (r'cat\s+[^\n]*(\.env|credentials|\.netrc|\.pgpass)', "read_secrets"),
]

# All patterns combined for comprehensive scanning
THREAT_PATTERNS_ALL: List[ThreatPattern] = (
    THREAT_PATTERNS_PROMPT_INJECTION +
    THREAT_PATTERNS_HTML_INJECTION +
    THREAT_PATTERNS_EXFILTRATION +
    THREAT_PATTERNS_PERSISTENCE +
    THREAT_PATTERNS_DESTRUCTIVE
)


# -----------------------------------------------------------------------------
# Scanning Functions
# -----------------------------------------------------------------------------

def scan_for_invisible_chars(content: str) -> Optional[str]:
    """
    Check for invisible unicode characters that could hide malicious content.
    
    Returns error message if found, None otherwise.
    """
    for char in INVISIBLE_CHARS:
        if char in content:
            return f"Blocked: content contains invisible unicode character U+{ord(char):04X} (possible injection)"
    return None


def scan_for_threats(
    content: str,
    patterns: List[ThreatPattern],
    case_insensitive: bool = True
) -> Optional[str]:
    """
    Scan content for threat patterns.
    
    Args:
        content: The content to scan
        patterns: List of (regex_pattern, category_name) tuples
        case_insensitive: Whether to use case-insensitive matching (default: True)
    
    Returns:
        Error message string if a threat is detected, None otherwise.
    """
    flags = re.IGNORECASE if case_insensitive else 0
    
    for pattern, category in patterns:
        if re.search(pattern, content, flags):
            return f"Blocked: content matches security pattern '{category}'"
    
    return None


def scan_content_comprehensive(
    content: str,
    check_invisible: bool = True,
    check_prompt_injection: bool = True,
    check_exfiltration: bool = True,
    check_persistence: bool = True,
    check_cron: bool = False,
    check_context: bool = False,
) -> Optional[str]:
    """
    Comprehensive security scan with configurable checks.
    
    Returns the first error found, or None if content is clean.
    """
    if check_invisible:
        result = scan_for_invisible_chars(content)
        if result:
            return result
    
    if check_context:
        # Context scanning uses its own comprehensive pattern set
        result = scan_for_threats(content, THREAT_PATTERNS_CONTEXT)
        if result:
            return result
        return None
    
    patterns = []
    if check_prompt_injection:
        patterns.extend(THREAT_PATTERNS_PROMPT_INJECTION)
    if check_exfiltration:
        patterns.extend(THREAT_PATTERNS_EXFILTRATION)
    if check_persistence:
        patterns.extend(THREAT_PATTERNS_PERSISTENCE)
    if check_cron:
        patterns.extend(THREAT_PATTERNS_CRON)
    
    if patterns:
        result = scan_for_threats(content, patterns)
        if result:
            return result
    
    return None


def scan_memory_content(content: str) -> Optional[str]:
    """
    Scan memory content for injection/exfiltration patterns.
    
    Memory entries are injected into the system prompt and must not contain
    injection or exfiltration payloads.
    
    Returns error string if blocked, None if clean.
    """
    # Check invisible unicode
    invisible_error = scan_for_invisible_chars(content)
    if invisible_error:
        return invisible_error
    
    # Check threat patterns
    patterns = (
        THREAT_PATTERNS_PROMPT_INJECTION +
        THREAT_PATTERNS_EXFILTRATION +
        THREAT_PATTERNS_PERSISTENCE
    )
    threat_error = scan_for_threats(content, patterns)
    if threat_error:
        return f"{threat_error}. Memory entries are injected into the system prompt and must not contain injection or exfiltration payloads."
    
    return None


def scan_cron_prompt(prompt: str) -> str:
    """
    Scan a cron prompt for critical threats.
    
    Returns error string if blocked, empty string if clean.
    """
    # Check invisible unicode
    for char in INVISIBLE_CHARS:
        if char in prompt:
            return f"Blocked: prompt contains invisible unicode U+{ord(char):04X} (possible injection)."
    
    # Check threat patterns
    for pattern, pid in THREAT_PATTERNS_CRON:
        if re.search(pattern, prompt, re.IGNORECASE):
            return f"Blocked: prompt matches threat pattern '{pid}'. Cron prompts must not contain injection or exfiltration payloads."
    
    return ""


def scan_context_content(content: str, filename: str) -> str:
    """
    Scan context file content for injection.
    
    Returns sanitized content or blocked message.
    """
    findings = []
    
    # Check invisible unicode
    for char in INVISIBLE_CHARS:
        if char in content:
            findings.append(f"invisible unicode U+{ord(char):04X}")
    
    # Check threat patterns
    for pattern, pid in THREAT_PATTERNS_CONTEXT:
        if re.search(pattern, content, re.IGNORECASE):
            findings.append(pid)
    
    if findings:
        return f"[BLOCKED: {filename} contained potential prompt injection ({', '.join(findings)}). Content not loaded.]"
    
    return content


# -----------------------------------------------------------------------------
# Legacy Compatibility Aliases
# -----------------------------------------------------------------------------

# For memory_tool.py compatibility
_MEMORY_THREAT_PATTERNS = (
    THREAT_PATTERNS_PROMPT_INJECTION +
    THREAT_PATTERNS_EXFILTRATION +
    THREAT_PATTERNS_PERSISTENCE
)
_INVISIBLE_CHARS = INVISIBLE_CHARS

# For cronjob_tools.py compatibility  
_CRON_THREAT_PATTERNS = THREAT_PATTERNS_CRON
_CRON_INVISIBLE_CHARS = INVISIBLE_CHARS

# For prompt_builder.py compatibility
_CONTEXT_THREAT_PATTERNS = THREAT_PATTERNS_CONTEXT
_CONTEXT_INVISIBLE_CHARS = INVISIBLE_CHARS
