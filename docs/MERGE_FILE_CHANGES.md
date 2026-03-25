# Test File Changes for Security Update Merge
## Hermes-Agent Upstream (94 commits ahead)

**Generated:** March 24, 2026  
**Command:** `git diff --name-status main..origin/main -- tests/`

---

## Summary Statistics
- **Total test files changed:** 48 files
- **Insertions:** +4,080 lines
- **Deletions:** -7,885 lines
- **Net change:** -3,805 lines (consolidation/refactoring)

---

## NEW TEST FILES (13 files)

### Gateway Tests (6 new files)
1. **test_api_server_jobs.py** - Jobs API hardening (input limits, field whitelist, startup checks)
2. **test_discord_document_handling.py** - Document caching and text-file injection
3. **test_discord_system_messages.py** - System message filtering in Discord handler
4. **test_flush_memory_stale_guard.py** - Memory management and stale session handling
5. **test_platform_reconnect.py** - Platform reconnection logic and resilience
6. **test_queue_consumption.py** - Message queue consumption patterns
7. **test_session_reset_notify.py** - User notification on session auto-reset

### CLI Tests (1 new file)
8. **test_mcp_config.py** - MCP server management CLI + OAuth 2.1 PKCE auth

### Core Tests (1 new file)
9. **test_config_env_expansion.py** - Environment variable substitution in config.yaml

### Tools Tests (3 new files)
10. **test_ansi_strip.py** - ANSI stripping functionality
11. **test_browser_homebrew_paths.py** - macOS Homebrew PATH resolution
12. **test_mcp_oauth.py** - MCP OAuth security (port mismatch, path traversal, handler state)
13. **test_url_safety.py** - SSRF protection and URL safety checks

---

## MODIFIED TEST FILES (29 files)

### Agent Module (3 files)
- `test_auxiliary_client.py`
- `test_prompt_builder.py`
- `test_redact.py`

### Core/Cross-cutting (7 files)
- `conftest.py` - Test configuration updates
- `test_api_key_providers.py`
- `test_cli_preloaded_skills.py`
- `test_context_references.py`
- `test_context_token_tracking.py`
- `test_plugins.py`
- `test_runtime_provider_resolution.py`

### Cron/Scheduling (2 files)
- `test_jobs.py`
- `test_scheduler.py`

### Gateway Module (6 files)
- `test_api_server.py`
- `test_discord_slash_commands.py`
- `test_mattermost.py`
- `test_runner_fatal_adapter.py`
- `test_session_hygiene.py`
- `test_signal.py`

### Hermes CLI (2 files)
- `test_gateway_service.py`
- `test_tools_config.py`

### Tools Module (9 files)
- `test_approval.py`
- `test_delegate.py`
- `test_file_tools.py`
- `test_local_env_blocklist.py`
- `test_session_search.py`
- `test_skills_guard.py` - Updated for dangerous skills handling
- `test_transcription.py`
- `test_vision_tools.py` - SSRF redirect guard additions
- `test_website_policy.py`

---

## DELETED TEST FILES (6 files)

All deletions appear to be consolidations or security-related removals:

1. **test_autodev_bridge.py** - Removed (consolidated/deprecated)
2. **test_browser_tool.py** - Removed (security: browser access restrictions)
3. **test_code_execution_tool.py** - Removed (security: code execution concerns)
4. **test_terminal_tool.py** - Removed (security: terminal access restrictions)
5. **test_tts_tool.py** - Removed (consolidated/deprecated)
6. **test_web_tools.py** - Removed (security: SSRF protection refactoring)

**Note:** These deletions align with security fixes blocking untrusted browser access and hardening tool execution.

---

## Security-Relevant Test Additions

### High Priority for Security Merge:
1. ✅ **test_mcp_oauth.py** - Tests for OAuth vulnerabilities (port mismatch, path traversal, shared handler state)
2. ✅ **test_url_safety.py** - SSRF protection tests
3. ✅ **test_browser_homebrew_paths.py** - Path resolution security
4. ✅ **test_api_server_jobs.py** - API hardening tests

### Medium Priority:
5. **test_flush_memory_stale_guard.py** - Memory/session security
6. **test_session_reset_notify.py** - Session management security
7. **test_config_env_expansion.py** - Configuration security (env var injection)

---

## Key Security Commits Referenced

From `git log main..origin/main`:

- `0791efe2` - fix(security): add SSRF protection to vision_tools and web_tools (hardened)
- `e109a8b5` - fix(security): block untrusted browser access to api server
- `73a88a02` - fix(security): prevent shell injection in _expand_path via ~user path suffix
- `ed805f57` - fix(mcp-oauth): port mismatch, path traversal, and shared handler state
- `c0c13e4e` - fix(api-server): harden jobs API — input limits, field whitelist, startup check, tests

---

## Merge Recommendations

### Must Merge (Security Critical):
- All 13 NEW test files (especially OAuth, SSRF, and API hardening tests)
- Modified security-related tests: `test_vision_tools.py`, `test_skills_guard.py`, `test_approval.py`

### Should Merge (Functionality):
- Discord and gateway test updates
- Session management tests
- Config and environment expansion tests

### Review Before Merge:
- Deleted tool tests (verify tools are intentionally removed/consolidated)
- Conftest changes (may affect test infrastructure)

---

## Next Steps

1. ✅ Test file inventory complete
2. ⬜ Merge test files with conflict resolution
3. ⬜ Run test suite to validate security fixes
4. ⬜ Update merge checklist with test coverage notes
5. ⬜ Document any test infrastructure changes needed
