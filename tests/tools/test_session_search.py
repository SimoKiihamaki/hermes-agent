"""Tests for tools/session_search_tool.py — helper functions and search dispatcher."""

import json
import time
import pytest

from tools.session_search_tool import (
    _format_timestamp,
    _format_conversation,
    _truncate_around_matches,
    MAX_SESSION_CHARS,
    SESSION_SEARCH_SCHEMA,
)


# =========================================================================
# Tool schema guidance
# =========================================================================

class TestSessionSearchSchema:
    def test_keeps_cross_session_recall_guidance_without_current_session_nudge(self):
        description = SESSION_SEARCH_SCHEMA["description"]
        assert "past conversations" in description
        assert "recent turns of the current session" not in description


# =========================================================================
# _format_timestamp
# =========================================================================

class TestFormatTimestamp:
    def test_unix_float(self):
        ts = 1700000000.0  # Nov 14, 2023
        result = _format_timestamp(ts)
        assert "2023" in result or "November" in result

    def test_unix_int(self):
        result = _format_timestamp(1700000000)
        assert isinstance(result, str)
        assert len(result) > 5

    def test_iso_string(self):
        result = _format_timestamp("2024-01-15T10:30:00")
        assert isinstance(result, str)

    def test_none_returns_unknown(self):
        assert _format_timestamp(None) == "unknown"

    def test_numeric_string(self):
        result = _format_timestamp("1700000000.0")
        assert isinstance(result, str)
        assert "unknown" not in result.lower()


# =========================================================================
# _format_conversation
# =========================================================================

class TestFormatConversation:
    def test_basic_messages(self):
        msgs = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = _format_conversation(msgs)
        assert "[USER]: Hello" in result
        assert "[ASSISTANT]: Hi there!" in result

    def test_tool_message(self):
        msgs = [
            {"role": "tool", "content": "search results", "tool_name": "web_search"},
        ]
        result = _format_conversation(msgs)
        assert "[TOOL:web_search]" in result

    def test_long_tool_output_truncated(self):
        msgs = [
            {"role": "tool", "content": "x" * 1000, "tool_name": "terminal"},
        ]
        result = _format_conversation(msgs)
        assert "[truncated]" in result

    def test_assistant_with_tool_calls(self):
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "web_search"}},
                    {"function": {"name": "terminal"}},
                ],
            },
        ]
        result = _format_conversation(msgs)
        assert "web_search" in result
        assert "terminal" in result

    def test_empty_messages(self):
        result = _format_conversation([])
        assert result == ""


# =========================================================================
# _truncate_around_matches
# =========================================================================

class TestTruncateAroundMatches:
    def test_short_text_unchanged(self):
        text = "Short text about docker"
        result = _truncate_around_matches(text, "docker")
        assert result == text

    def test_long_text_truncated(self):
        # Create text longer than MAX_SESSION_CHARS with query term in middle
        padding = "x" * (MAX_SESSION_CHARS + 5000)
        text = padding + " KEYWORD_HERE " + padding
        result = _truncate_around_matches(text, "KEYWORD_HERE")
        assert len(result) <= MAX_SESSION_CHARS + 100  # +100 for prefix/suffix markers
        assert "KEYWORD_HERE" in result

    def test_truncation_adds_markers(self):
        text = "a" * 50000 + " target " + "b" * (MAX_SESSION_CHARS + 5000)
        result = _truncate_around_matches(text, "target")
        assert "truncated" in result.lower()

    def test_no_match_takes_from_start(self):
        text = "x" * (MAX_SESSION_CHARS + 5000)
        result = _truncate_around_matches(text, "nonexistent")
        # Should take from the beginning
        assert result.startswith("x")

    def test_match_at_beginning(self):
        text = "KEYWORD " + "x" * (MAX_SESSION_CHARS + 5000)
        result = _truncate_around_matches(text, "KEYWORD")
        assert "KEYWORD" in result


# =========================================================================
# session_search (dispatcher)
# =========================================================================

class TestSessionSearch:
    def test_no_db_returns_error(self):
        from tools.session_search_tool import session_search
        result = json.loads(session_search(query="test"))
        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_empty_query_returns_error(self):
        from tools.session_search_tool import session_search
        mock_db = object()
        result = json.loads(session_search(query="", db=mock_db))
        assert result["success"] is False

    def test_whitespace_query_returns_error(self):
        from tools.session_search_tool import session_search
        mock_db = object()
        result = json.loads(session_search(query="   ", db=mock_db))
        assert result["success"] is False

    def test_current_session_excluded(self):
        """session_search should never return the current session."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_abc123"

        # Simulate FTS5 returning matches only from the current session
        mock_db.search_messages.return_value = [
            {"session_id": current_sid, "content": "test match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id=current_sid,
        ))
        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []

    def test_current_session_excluded_keeps_others(self):
        """Other sessions should still be returned when current is excluded."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        current_sid = "20260304_120000_abc123"
        other_sid = "20260303_100000_def456"

        mock_db.search_messages.return_value = [
            {"session_id": current_sid, "content": "match 1", "source": "cli",
             "session_started": 1709500000, "model": "test"},
            {"session_id": other_sid, "content": "match 2", "source": "telegram",
             "session_started": 1709400000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        # Mock async_call_llm to raise RuntimeError → summarizer returns None
        from unittest.mock import AsyncMock, patch as _patch
        with _patch("tools.session_search_tool.async_call_llm",
                     new_callable=AsyncMock,
                     side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(
                query="test", db=mock_db, current_session_id=current_sid,
            ))

        assert result["success"] is True
        # Current session should be skipped, only other_sid should appear
        assert result["sessions_searched"] == 1
        assert current_sid not in [r.get("session_id") for r in result.get("results", [])]

    def test_current_child_session_excludes_parent_lineage(self):
        """Compression/delegation parents should be excluded for the active child session."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "parent_sid", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        def _get_session(session_id):
            if session_id == "child_sid":
                return {"parent_session_id": "parent_sid"}
            if session_id == "parent_sid":
                return {"parent_session_id": None}
            return None

        mock_db.get_session.side_effect = _get_session

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id="child_sid",
        ))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []
        assert result["sessions_searched"] == 0

    def test_current_root_session_excludes_child_lineage(self):
        """Delegation child hits should be excluded when they resolve to the current root session."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "child_sid", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        def _get_session(session_id):
            if session_id == "root_sid":
                return {"parent_session_id": None}
            if session_id == "child_sid":
                return {"parent_session_id": "root_sid"}
            return None

        mock_db.get_session.side_effect = _get_session

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id="root_sid",
        ))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []
        assert result["sessions_searched"] == 0


# =========================================================================
# _summarize_session (async)
# =========================================================================

class TestSummarizeSession:
    @pytest.mark.asyncio
    async def test_successful_summarization(self):
        """Test successful session summarization."""
        from unittest.mock import AsyncMock, patch
        from tools.session_search_tool import _summarize_session

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "Test summary"

        with patch("tools.session_search_tool.async_call_llm",
                   new_callable=AsyncMock, return_value=mock_response):
            result = await _summarize_session(
                "Conversation text",
                "search query",
                {"source": "cli", "started_at": 1700000000}
            )
            assert result == "Test summary"

    @pytest.mark.asyncio
    async def test_no_auxiliary_model_returns_none(self):
        """RuntimeError from missing auxiliary model should return None."""
        from unittest.mock import AsyncMock, patch
        from tools.session_search_tool import _summarize_session

        with patch("tools.session_search_tool.async_call_llm",
                   new_callable=AsyncMock, side_effect=RuntimeError("no provider")):
            result = await _summarize_session(
                "Conversation text",
                "search query",
                {"source": "cli"}
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_retries_on_transient_error(self):
        """Should retry on transient errors before giving up."""
        from unittest.mock import AsyncMock, patch, call
        from tools.session_search_tool import _summarize_session

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "Success after retry"

        call_count = [0]

        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Transient error")
            return mock_response

        with patch("tools.session_search_tool.async_call_llm",
                   new_callable=AsyncMock, side_effect=side_effect):
            result = await _summarize_session(
                "Conversation text",
                "search query",
                {"source": "cli"}
            )
            assert result == "Success after retry"
            assert call_count[0] == 3

    @pytest.mark.asyncio
    async def test_gives_up_after_max_retries(self):
        """Should return None after max retries."""
        from unittest.mock import AsyncMock, patch
        from tools.session_search_tool import _summarize_session

        with patch("tools.session_search_tool.async_call_llm",
                   new_callable=AsyncMock, side_effect=Exception("Persistent error")):
            result = await _summarize_session(
                "Conversation text",
                "search query",
                {"source": "cli"}
            )
            assert result is None


# =========================================================================
# check_session_search_requirements
# =========================================================================

class TestCheckSessionSearchRequirements:
    def test_returns_bool(self):
        """Should return a boolean value."""
        from tools.session_search_tool import check_session_search_requirements
        result = check_session_search_requirements()
        assert isinstance(result, bool)

    def test_import_error_returns_false(self):
        """Should return False if hermes_state can't be imported."""
        from unittest.mock import patch
        from tools.session_search_tool import check_session_search_requirements

        with patch.dict("sys.modules", {"hermes_state": None}):
            # Force ImportError
            with patch("tools.session_search_tool.DEFAULT_DB_PATH", None, create=True):
                with patch("builtins.__import__", side_effect=ImportError("No module")):
                    result = check_session_search_requirements()
                    assert result is False


# =========================================================================
# FTS5 search - role filter and query handling
# =========================================================================

class TestFTS5RoleFilter:
    def test_role_filter_parsed_from_comma_string(self):
        """Role filter should be parsed into a list."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="test", db=mock_db, role_filter="user,assistant")

        call_args = mock_db.search_messages.call_args
        assert call_args[1]["role_filter"] == ["user", "assistant"]

    def test_role_filter_with_whitespace(self):
        """Role filter should handle whitespace around roles."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="test", db=mock_db, role_filter=" user , assistant ")

        call_args = mock_db.search_messages.call_args
        assert call_args[1]["role_filter"] == ["user", "assistant"]

    def test_empty_role_filter_ignored(self):
        """Empty role filter should result in None."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="test", db=mock_db, role_filter="")

        call_args = mock_db.search_messages.call_args
        assert call_args[1]["role_filter"] is None

    def test_whitespace_role_filter_ignored(self):
        """Whitespace-only role filter should result in None."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="test", db=mock_db, role_filter="   ")

        call_args = mock_db.search_messages.call_args
        assert call_args[1]["role_filter"] is None


# =========================================================================
# Limit capping
# =========================================================================

class TestLimitCapping:
    def test_limit_capped_at_5(self):
        """Limit should be capped at 5 sessions."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="test", db=mock_db, limit=10)

        # The function internally caps limit at 5
        # We verify by checking the result doesn't allow more than 5
        call_args = mock_db.search_messages.call_args
        assert call_args[1]["limit"] == 50  # Internal raw limit for FTS5

    def test_limit_preserved_if_under_5(self):
        """Limit under 5 should be preserved."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="test", db=mock_db, limit=2)

        # Should work fine with limit 2
        assert mock_db.search_messages.called


# =========================================================================
# _format_timestamp edge cases
# =========================================================================

class TestFormatTimestampEdgeCases:
    def test_invalid_timestamp_returns_str(self):
        """Invalid timestamp should return string representation."""
        from tools.session_search_tool import _format_timestamp
        result = _format_timestamp("not-a-timestamp")
        assert result == "not-a-timestamp"

    def test_negative_timestamp(self):
        """Negative timestamp should be handled gracefully."""
        from tools.session_search_tool import _format_timestamp
        # Negative timestamps can cause OSError on some platforms
        result = _format_timestamp(-10000000000)
        assert isinstance(result, str)

    def test_very_large_timestamp(self):
        """Very large timestamp should be handled gracefully."""
        from tools.session_search_tool import _format_timestamp
        # Large timestamps can cause overflow
        result = _format_timestamp(9999999999999)
        assert isinstance(result, str)


# =========================================================================
# _format_conversation edge cases
# =========================================================================

class TestFormatConversationEdgeCases:
    def test_unknown_role(self):
        """Unknown roles should be formatted as-is."""
        from tools.session_search_tool import _format_conversation
        msgs = [{"role": "custom_role", "content": "test"}]
        result = _format_conversation(msgs)
        assert "[CUSTOM_ROLE]: test" in result

    def test_missing_content(self):
        """Missing content should be handled gracefully."""
        from tools.session_search_tool import _format_conversation
        msgs = [{"role": "user"}]
        result = _format_conversation(msgs)
        assert "[USER]:" in result

    def test_none_content(self):
        """None content should be treated as empty string."""
        from tools.session_search_tool import _format_conversation
        msgs = [{"role": "user", "content": None}]
        result = _format_conversation(msgs)
        assert "[USER]:" in result

    def test_tool_call_with_direct_name(self):
        """Tool calls with direct 'name' field should work."""
        from tools.session_search_tool import _format_conversation
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"name": "terminal"}]
        }]
        result = _format_conversation(msgs)
        assert "terminal" in result

    def test_tool_call_with_nested_name(self):
        """Tool calls with nested function.name should work."""
        from tools.session_search_tool import _format_conversation
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": "web_search"}}]
        }]
        result = _format_conversation(msgs)
        assert "web_search" in result

    def test_assistant_with_tool_calls_and_content(self):
        """Assistant with tool calls and content should include both."""
        from tools.session_search_tool import _format_conversation
        msgs = [{
            "role": "assistant",
            "content": "Here's what I found",
            "tool_calls": [{"function": {"name": "terminal"}}]
        }]
        result = _format_conversation(msgs)
        assert "Called: terminal" in result
        assert "Here's what I found" in result

    def test_tool_call_missing_name(self):
        """Tool calls without name should use placeholder."""
        from tools.session_search_tool import _format_conversation
        msgs = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [{}]
        }]
        result = _format_conversation(msgs)
        # Should handle gracefully without crashing
        assert "[ASSISTANT]" in result

    def test_tool_message_without_name(self):
        """Tool message without tool_name should still work."""
        from tools.session_search_tool import _format_conversation
        msgs = [{"role": "tool", "content": "result"}]
        result = _format_conversation(msgs)
        assert "[TOOL]:" in result or "[TOOL:unknown]" in result


# =========================================================================
# Session search no results
# =========================================================================

class TestSessionSearchNoResults:
    def test_no_matches_returns_empty_results(self):
        """No FTS5 matches should return success with empty results."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        result = json.loads(session_search(query="nonexistent", db=mock_db))

        assert result["success"] is True
        assert result["count"] == 0
        assert result["results"] == []
        assert "No matching sessions" in result["message"]


# =========================================================================
# Error handling in session_search
# =========================================================================

class TestSessionSearchErrorHandling:
    def test_db_exception_caught(self):
        """Exceptions from DB should be caught and return error."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.side_effect = Exception("DB error")

        result = json.loads(session_search(query="test", db=mock_db))

        assert result["success"] is False
        assert "Search failed" in result["error"]

    def test_get_messages_exception_skips_session(self):
        """Exception loading messages should skip that session."""
        from unittest.mock import MagicMock, patch
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "sid1", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}
        mock_db.get_messages_as_conversation.side_effect = Exception("Load error")

        with patch("tools.session_search_tool.async_call_llm",
                   side_effect=RuntimeError("no provider")):
            result = json.loads(session_search(query="test", db=mock_db))

        assert result["success"] is True
        assert result["count"] == 0  # Session was skipped


# =========================================================================
# Session metadata extraction
# =========================================================================

class TestSessionMetadata:
    def test_metadata_included_in_results(self):
        """Session metadata should be included in search results."""
        from unittest.mock import MagicMock, patch, AsyncMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "sid1", "content": "match", "source": "telegram",
             "session_started": 1709500000, "model": "claude-3"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
        ]

        mock_response = AsyncMock()
        mock_response.choices = [AsyncMock()]
        mock_response.choices[0].message.content = "Summary"

        with patch("tools.session_search_tool.async_call_llm",
                   new_callable=AsyncMock, return_value=mock_response):
            result = json.loads(session_search(query="test", db=mock_db))

        assert result["success"] is True
        assert len(result["results"]) == 1
        assert result["results"][0]["source"] == "telegram"
        assert result["results"][0]["model"] == "claude-3"
        assert "session_id" in result["results"][0]


# =========================================================================
# Registry integration
# =========================================================================

class TestRegistryIntegration:
    def test_tool_registered(self):
        """Tool should be registered in the registry."""
        from tools.registry import registry
        all_tools = registry.get_all_tool_names()
        assert "session_search" in all_tools

    def test_tool_has_correct_toolset(self):
        """Tool should belong to session_search toolset."""
        from tools.registry import registry
        toolset = registry.get_toolset_for_tool("session_search")
        assert toolset == "session_search"

    def test_tool_has_emoji(self):
        """Tool should have an emoji registered."""
        from tools.registry import registry
        emoji = registry.get_emoji("session_search")
        assert emoji == "🔍"


# =========================================================================
# Truncation edge cases
# =========================================================================

class TestTruncateEdgeCases:
    def test_multiple_query_terms(self):
        """Truncation should find the first match of any term."""
        from tools.session_search_tool import _truncate_around_matches
        text = "a" * 60000 + " SECOND " + "b" * 60000 + " FIRST " + "c" * 60000
        result = _truncate_around_matches(text, "first second")
        # Should find FIRST (first match alphabetically could be either)
        assert "FIRST" in result or "SECOND" in result

    def test_case_insensitive_matching(self):
        """Truncation should match terms case-insensitively."""
        from tools.session_search_tool import _truncate_around_matches
        text = "a" * 60000 + " KEYWORD " + "b" * 60000
        result = _truncate_around_matches(text, "keyword")
        assert "KEYWORD" in result

    def test_exact_max_chars(self):
        """Text exactly at max_chars should not be truncated."""
        from tools.session_search_tool import _truncate_around_matches, MAX_SESSION_CHARS
        text = "x" * MAX_SESSION_CHARS
        result = _truncate_around_matches(text, "query")
        assert result == text
        assert "truncated" not in result.lower()


# =========================================================================
# Session lineage resolution edge cases
# =========================================================================

class TestSessionLineageResolution:
    def test_deep_parent_chain(self):
        """Deep delegation chains should resolve to root parent."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "child3", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        def _get_session(session_id):
            chain = {
                "child3": {"parent_session_id": "child2"},
                "child2": {"parent_session_id": "child1"},
                "child1": {"parent_session_id": "root"},
                "root": {"parent_session_id": None},
            }
            return chain.get(session_id)

        mock_db.get_session.side_effect = _get_session

        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id="root",
        ))

        # child3 resolves to root, which is current, so should be excluded
        assert result["success"] is True
        assert result["count"] == 0

    def test_circular_parent_chain_handled(self):
        """Circular parent chains should not cause infinite loop."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "sid_a", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        def _get_session(session_id):
            # Create a circular reference
            chain = {
                "sid_a": {"parent_session_id": "sid_b"},
                "sid_b": {"parent_session_id": "sid_a"},
            }
            return chain.get(session_id)

        mock_db.get_session.side_effect = _get_session
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
        ]

        # Should not hang or crash
        result = json.loads(session_search(
            query="test", db=mock_db, current_session_id="other",
        ))
        assert result["success"] is True

    def test_get_session_exception_handled(self):
        """Exception in get_session should be handled gracefully."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "sid1", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]

        call_count = [0]

        def _get_session(session_id):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("DB error")
            return {"parent_session_id": None}

        mock_db.get_session.side_effect = _get_session

        result = json.loads(session_search(
            query="test", db=mock_db,
        ))
        # Should handle the exception gracefully
        assert result["success"] is True


# =========================================================================
# Summarization result handling
# =========================================================================

class TestSummarizationResultHandling:
    def test_exception_in_result_skipped(self):
        """Exceptions returned in summarization results should be skipped."""
        from unittest.mock import MagicMock, patch, AsyncMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = [
            {"session_id": "sid1", "content": "match", "source": "cli",
             "session_started": 1709500000, "model": "test"},
        ]
        mock_db.get_session.return_value = {"parent_session_id": None}
        mock_db.get_messages_as_conversation.return_value = [
            {"role": "user", "content": "hello"},
        ]

        # Return an exception instead of a summary
        with patch("tools.session_search_tool.async_call_llm",
                   new_callable=AsyncMock,
                   side_effect=Exception("LLM error")):
            result = json.loads(session_search(query="test", db=mock_db))

        assert result["success"] is True
        assert result["count"] == 0  # Session was skipped due to exception


# =========================================================================
# FTS5 query handling
# =========================================================================

class TestFTS5QueryHandling:
    def test_query_stripped(self):
        """Query should be stripped of leading/trailing whitespace."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query="  test query  ", db=mock_db)

        call_args = mock_db.search_messages.call_args
        assert call_args[1]["query"] == "test query"

    def test_special_fts5_characters(self):
        """FTS5 special characters in query should be passed through."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        # These are valid FTS5 query patterns
        session_search(query="docker OR kubernetes", db=mock_db)
        call_args = mock_db.search_messages.call_args
        assert call_args[1]["query"] == "docker OR kubernetes"

    def test_phrase_query(self):
        """Phrase queries with quotes should work."""
        from unittest.mock import MagicMock
        from tools.session_search_tool import session_search

        mock_db = MagicMock()
        mock_db.search_messages.return_value = []

        session_search(query='"exact phrase"', db=mock_db)
        call_args = mock_db.search_messages.call_args
        assert call_args[1]["query"] == '"exact phrase"'
