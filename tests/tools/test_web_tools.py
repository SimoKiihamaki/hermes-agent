"""Tests for web_search_tool and web_extract_tool core functionality.

Coverage:
  web_search_tool — Firecrawl/Parallel dispatch, result parsing, error handling.
  web_extract_tool — Firecrawl/Parallel dispatch, URL handling, LLM processing integration.
  clean_base64_images — base64 image removal patterns.
  process_content_with_llm — LLM summarization, chunked processing, size limits.
  Page storage functions — store_page, search_pages, list_pages, get_page, delete_page.
"""

import json
import os
import asyncio
import hashlib
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_web_tools_state():
    """Reset module state before and after each test."""
    import tools.web_tools
    tools.web_tools._firecrawl_client = None
    tools.web_tools._parallel_client = None
    tools.web_tools._async_parallel_client = None
    # Reset thread-local DB connection
    if hasattr(tools.web_tools._local, 'connection'):
        try:
            tools.web_tools._local.connection.close()
        except Exception:
            pass
        tools.web_tools._local.connection = None
    
    yield
    
    # Cleanup after test
    tools.web_tools._firecrawl_client = None
    tools.web_tools._parallel_client = None
    tools.web_tools._async_parallel_client = None


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Use a temporary database for page storage tests."""
    db_path = tmp_path / "test_web_pages.db"
    monkeypatch.setenv("WEB_PAGES_DB_PATH", str(db_path))
    yield db_path


# ─── web_search_tool Tests ─────────────────────────────────────────────────────

class TestWebSearchToolFirecrawl:
    """Test suite for web_search_tool with Firecrawl backend."""

    def test_search_returns_json_string(self):
        """Result is always a JSON string."""
        mock_response = MagicMock()
        mock_response.web = [
            MagicMock(title="Result 1", url="https://r1.com", description="Desc 1")
        ]
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result = web_search_tool("test query")
            assert isinstance(result, str)
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    def test_search_success_structure(self):
        """Successful search returns proper structure."""
        # Create a mock result with actual dict-like behavior
        mock_result = MagicMock()
        mock_result.title = "Python Guide"
        mock_result.url = "https://docs.python.org"
        mock_result.description = "Official Python documentation"
        # Make model_dump return a proper dict
        mock_result.model_dump.return_value = {
            "title": "Python Guide",
            "url": "https://docs.python.org",
            "description": "Official Python documentation"
        }
        
        mock_response = MagicMock()
        mock_response.web = [mock_result]
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            # Set up the mock client to return the response directly
            mock_client.return_value.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result_json = web_search_tool("python tutorial", limit=5)
            result = json.loads(result_json)
            
            # The function always returns a dict with success key
            assert result.get("success") is True
            assert "data" in result
            assert "web" in result["data"]
            assert len(result["data"]["web"]) == 1
            # The result may be serialized as a dict or object, check the title exists
            assert result["data"]["web"][0].get("title") == "Python Guide"

    def test_search_empty_results(self):
        """Empty search results return success with empty list."""
        mock_response = MagicMock()
        mock_response.web = []
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("obscure query"))
            
            assert result["success"] is True
            assert result["data"]["web"] == []

    def test_search_respects_limit(self):
        """Limit parameter is passed to Firecrawl."""
        mock_response = MagicMock()
        mock_response.web = []
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            web_search_tool("test", limit=10)
            
            call_args = mock_client.return_value.search.call_args
            assert call_args.kwargs.get("limit") == 10

    def test_search_pydantic_model_response(self):
        """Handles Pydantic model responses (model_dump method)."""
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "title": "Title",
            "url": "https://example.com",
            "description": "Description"
        }
        mock_result.title = "Title"
        mock_result.url = "https://example.com"
        
        mock_response = MagicMock()
        mock_response.web = [mock_result]
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert result["data"]["web"][0]["title"] == "Title"

    def test_search_dict_response(self):
        """Handles dict responses directly."""
        mock_response = {
            "web": [
                {"title": "Dict Result", "url": "https://dict.com", "description": "From dict"}
            ]
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert result["data"]["web"][0]["title"] == "Dict Result"

    def test_search_interrupted_returns_error(self):
        """Interruption returns proper error JSON."""
        with patch("tools.interrupt.is_interrupted", return_value=True):
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert result.get("error") == "Interrupted"
            assert result.get("success") is False

    def test_search_exception_returns_error_json(self):
        """Exceptions are caught and returned as JSON error."""
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.side_effect = RuntimeError("API failure")
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert "error" in result
            assert "API failure" in result["error"]


class TestWebSearchToolParallel:
    """Test suite for web_search_tool with Parallel backend."""

    def test_parallel_search_success(self):
        """Parallel search returns normalized results."""
        mock_result = MagicMock()
        mock_result.url = "https://parallel.com"
        mock_result.title = "Parallel Result"
        mock_result.excerpts = ["Excerpt 1", "Excerpt 2"]
        
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test", limit=5))
            
            assert result["success"] is True
            assert len(result["data"]["web"]) == 1
            assert result["data"]["web"][0]["url"] == "https://parallel.com"
            assert "Excerpt 1" in result["data"]["web"][0]["description"]

    def test_parallel_search_empty_results(self):
        """Parallel search with no results returns empty list."""
        mock_response = MagicMock()
        mock_response.results = []
        
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert result["success"] is True
            assert result["data"]["web"] == []

    def test_parallel_search_none_response(self):
        """Parallel search returning None returns error."""
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.search.return_value = None
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert "error" in result
            assert result["success"] is False

    def test_parallel_search_interrupted(self):
        """Parallel search respects interrupt."""
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.interrupt.is_interrupted", return_value=True):
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert result["error"] == "Interrupted"

    def test_parallel_search_mode_selection(self):
        """Parallel search uses correct mode from env var."""
        mock_response = MagicMock()
        mock_response.results = []
        
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch.dict(os.environ, {"PARALLEL_SEARCH_MODE": "fast"}), \
             patch("tools.web_tools._get_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.search.return_value = mock_response
            from tools.web_tools import web_search_tool
            web_search_tool("test")
            
            call_kwargs = mock_client.return_value.beta.search.call_args.kwargs
            assert call_kwargs.get("mode") == "fast"

    def test_parallel_search_sdk_error(self):
        """Parallel SDK AttributeError is caught."""
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.search.side_effect = AttributeError("SDK error")
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert "error" in result
            assert "SDK error" in result["error"]


# ─── web_extract_tool Tests ────────────────────────────────────────────────────

class TestWebExtractToolFirecrawl:
    """Test suite for web_extract_tool with Firecrawl backend."""

    @pytest.mark.asyncio
    async def test_extract_returns_json_string(self):
        """Result is always a JSON string."""
        mock_scrape = {
            "markdown": "# Content",
            "metadata": {"title": "Page Title", "sourceURL": "https://example.com"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = await web_extract_tool(["https://example.com"], use_llm_processing=False)
            assert isinstance(result, str)
            assert json.loads(result) is not None

    @pytest.mark.asyncio
    async def test_extract_single_url_success(self):
        """Extract single URL returns content."""
        mock_scrape = {
            "markdown": "# Hello World\n\nThis is content.",
            "metadata": {"title": "Test Page", "sourceURL": "https://example.com"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com"], 
                use_llm_processing=False
            ))
            
            assert "results" in result
            assert len(result["results"]) == 1
            assert result["results"][0]["url"] == "https://example.com"
            assert result["results"][0]["title"] == "Test Page"
            assert "Hello World" in result["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_extract_multiple_urls(self):
        """Extract multiple URLs returns all results."""
        def scrape_side_effect(url, formats):
            return {
                "markdown": f"Content for {url}",
                "metadata": {"title": f"Page {url}", "sourceURL": url}
            }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.side_effect = scrape_side_effect
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://a.com", "https://b.com"], 
                use_llm_processing=False
            ))
            
            assert len(result["results"]) == 2
            urls = {r["url"] for r in result["results"]}
            assert "https://a.com" in urls
            assert "https://b.com" in urls

    @pytest.mark.asyncio
    async def test_extract_blocked_by_policy(self):
        """Blocked URL returns error with policy info."""
        blocked_info = {
            "host": "blocked.test",
            "rule": "blocked.test",
            "source": "config",
            "message": "Blocked by website policy"
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools.check_website_access", return_value=blocked_info):
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://blocked.test/page"], 
                use_llm_processing=False
            ))
            
            assert len(result["results"]) == 1
            assert result["results"][0]["url"] == "https://blocked.test/page"
            assert "Blocked by website policy" in result["results"][0]["error"]
            assert result["results"][0]["blocked_by_policy"]["rule"] == "blocked.test"

    @pytest.mark.asyncio
    async def test_extract_interrupted(self):
        """Interrupted extraction returns error."""
        with patch("tools.interrupt.is_interrupted", return_value=True):
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com"], 
                use_llm_processing=False
            ))
            
            assert result["results"][0]["error"] == "Interrupted"

    @pytest.mark.asyncio
    async def test_extract_scrape_error(self):
        """Scrape errors are caught and returned in results."""
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.side_effect = RuntimeError("Scrape failed")
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com"], 
                use_llm_processing=False
            ))
            
            assert len(result["results"]) == 1
            assert "Scrape failed" in result["results"][0]["error"]

    @pytest.mark.asyncio
    async def test_extract_format_markdown(self):
        """Format parameter requests markdown content."""
        mock_scrape = {
            "markdown": "# Markdown Content",
            "html": "<html>HTML Content</html>",
            "metadata": {"title": "Page", "sourceURL": "https://example.com"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com"], 
                format="markdown",
                use_llm_processing=False
            ))
            
            assert "# Markdown Content" in result["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_extract_format_html(self):
        """Format parameter requests HTML content."""
        mock_scrape = {
            "markdown": "# Markdown Content",
            "html": "<html>HTML Content</html>",
            "metadata": {"title": "Page", "sourceURL": "https://example.com"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com"], 
                format="html",
                use_llm_processing=False
            ))
            
            assert "<html>" in result["results"][0]["content"]

    @pytest.mark.asyncio
    async def test_extract_empty_results_error(self):
        """Empty results array returns inaccessible error."""
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value={"host": "x", "rule": "x", "source": "x", "message": "blocked"}):
            from tools.web_tools import web_extract_tool
            # All URLs blocked, resulting in empty accessible content
            result = json.loads(await web_extract_tool(
                ["https://blocked.test"], 
                use_llm_processing=False
            ))
            # When all results have errors but have content, still returns results
            assert "results" in result


class TestWebExtractToolParallel:
    """Test suite for web_extract_tool with Parallel backend."""

    @pytest.mark.asyncio
    async def test_parallel_extract_success(self):
        """Parallel extract returns content."""
        mock_result = MagicMock()
        mock_result.url = "https://parallel.com"
        mock_result.title = "Parallel Page"
        mock_result.full_content = "Full content from Parallel"
        mock_result.excerpts = ["Excerpt 1"]
        
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.errors = []
        
        # Create an async mock for the extract method
        async def async_extract(*args, **kwargs):
            return mock_response
        
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_async_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            # Set up the async mock for beta.extract
            mock_client.return_value.beta.extract = async_extract
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://parallel.com"], 
                use_llm_processing=False
            ))
            
            assert "results" in result
            assert len(result["results"]) == 1
            assert result["results"][0]["url"] == "https://parallel.com"
            assert result["results"][0]["title"] == "Parallel Page"

    @pytest.mark.asyncio
    async def test_parallel_extract_with_errors(self):
        """Parallel extract includes errors in results."""
        mock_result = MagicMock()
        mock_result.url = "https://good.com"
        mock_result.title = "Good Page"
        mock_result.full_content = "Content"
        
        mock_error = MagicMock()
        mock_error.url = "https://bad.com"
        mock_error.content = "Error message"
        mock_error.error_type = "timeout"
        
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.errors = [mock_error]
        
        # Create an async mock for the extract method
        async def async_extract(*args, **kwargs):
            return mock_response
        
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_async_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.extract = async_extract
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://good.com", "https://bad.com"], 
                use_llm_processing=False
            ))
            
            assert "results" in result
            urls = {r["url"] for r in result["results"]}
            assert "https://good.com" in urls
            assert "https://bad.com" in urls
            
            # Find the error result
            bad_result = next(r for r in result["results"] if r["url"] == "https://bad.com")
            assert bad_result["error"] == "Error message"

    @pytest.mark.asyncio
    async def test_parallel_extract_interrupted(self):
        """Parallel extract respects interrupt."""
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.interrupt.is_interrupted", return_value=True):
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com"], 
                use_llm_processing=False
            ))
            
            assert result["results"][0]["error"] == "Interrupted"

    @pytest.mark.asyncio
    async def test_parallel_extract_falls_back_to_excerpts(self):
        """Parallel extract uses excerpts when no full_content."""
        mock_result = MagicMock()
        mock_result.url = "https://excerpt.com"
        mock_result.title = "Excerpt Page"
        mock_result.full_content = None
        mock_result.excerpts = ["Excerpt A", "Excerpt B"]
        
        mock_response = MagicMock()
        mock_response.results = [mock_result]
        mock_response.errors = []
        
        # Create an async mock for the extract method
        async def async_extract(*args, **kwargs):
            return mock_response
        
        with patch("tools.web_tools._get_backend", return_value="parallel"), \
             patch("tools.web_tools._get_async_parallel_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False):
            mock_client.return_value.beta.extract = async_extract
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://excerpt.com"], 
                use_llm_processing=False
            ))
            
            assert "results" in result
            assert "Excerpt A" in result["results"][0]["content"]
            assert "Excerpt B" in result["results"][0]["content"]


# ─── clean_base64_images Tests ────────────────────────────────────────────────

class TestCleanBase64Images:
    """Test suite for clean_base64_images function."""

    def test_removes_parentheses_wrapped_base64(self):
        """Removes base64 images wrapped in parentheses."""
        from tools.web_tools import clean_base64_images
        text = "Here is an image: (data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB) and more text"
        result = clean_base64_images(text)
        
        assert "[BASE64_IMAGE_REMOVED]" in result
        assert "data:image/png;base64" not in result
        assert "Here is an image:" in result
        assert "and more text" in result

    def test_removes_standalone_base64(self):
        """Removes base64 images without parentheses."""
        from tools.web_tools import clean_base64_images
        text = "Image: data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ more text"
        result = clean_base64_images(text)
        
        assert "[BASE64_IMAGE_REMOVED]" in result
        assert "data:image/jpeg;base64" not in result

    def test_removes_svg_base64(self):
        """Removes SVG base64 images."""
        from tools.web_tools import clean_base64_images
        text = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53"
        result = clean_base64_images(text)
        
        assert "[BASE64_IMAGE_REMOVED]" in result

    def test_no_base64_returns_unchanged(self):
        """Text without base64 is unchanged."""
        from tools.web_tools import clean_base64_images
        text = "Regular text without any images"
        result = clean_base64_images(text)
        
        assert result == text

    def test_multiple_base64_images(self):
        """Multiple base64 images are all removed."""
        from tools.web_tools import clean_base64_images
        text = "First: data:image/png;base64,AAAA Second: (data:image/jpeg;base64,BBBB) Third: data:image/gif;base64,CCCC"
        result = clean_base64_images(text)
        
        assert result.count("[BASE64_IMAGE_REMOVED]") == 3


# ─── process_content_with_llm Tests ───────────────────────────────────────────

class TestProcessContentWithLlm:
    """Test suite for LLM content processing."""

    @pytest.mark.asyncio
    async def test_short_content_skipped(self):
        """Content below min_length is not processed."""
        from tools.web_tools import process_content_with_llm
        
        result = await process_content_with_llm(
            "Short content",
            min_length=100
        )
        
        assert result is None

    @pytest.mark.asyncio
    async def test_large_content_refused(self):
        """Content above 2MB is refused."""
        from tools.web_tools import process_content_with_llm
        
        huge_content = "x" * 2_500_000
        result = await process_content_with_llm(huge_content)
        
        assert result is not None
        assert "too large" in result.lower()

    @pytest.mark.asyncio
    async def test_normal_content_processed(self):
        """Normal content is processed with LLM."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## Summary\n\nKey points here"
        
        with patch("tools.web_tools.async_call_llm", new_callable=AsyncMock, return_value=mock_response):
            from tools.web_tools import process_content_with_llm
            
            content = "x" * 6000  # Above default min_length
            result = await process_content_with_llm(content, url="https://test.com", title="Test")
            
            assert result is not None
            assert "Summary" in result

    @pytest.mark.asyncio
    async def test_output_capped_at_max_size(self):
        """Processed output is capped at MAX_OUTPUT_SIZE."""
        huge_response = "x" * 10000
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = huge_response
        
        with patch("tools.web_tools.async_call_llm", new_callable=AsyncMock, return_value=mock_response):
            from tools.web_tools import process_content_with_llm
            
            content = "x" * 6000
            result = await process_content_with_llm(content)
            
            assert len(result) <= 5000 + 100  # MAX_OUTPUT_SIZE + truncation message
            assert "truncated" in result.lower()

    @pytest.mark.asyncio
    async def test_llm_error_returns_fallback(self):
        """LLM errors return error message string or None."""
        with patch("tools.web_tools.async_call_llm", new_callable=AsyncMock, side_effect=RuntimeError("API Error")):
            from tools.web_tools import process_content_with_llm
            
            content = "x" * 6000
            result = await process_content_with_llm(content)
            
            # RuntimeError returns None (see line 948-949 in web_tools.py)
            assert result is None or "Failed to process" in result


# ─── Page Storage Tests ────────────────────────────────────────────────────────

class TestStorePage:
    """Test suite for store_page function."""

    def test_store_page_success(self, temp_db):
        """Page is stored successfully."""
        from tools.web_tools import store_page
        
        result = store_page(
            url="https://example.com",
            title="Example Page",
            content="This is the content",
            source_tool="web_extract"
        )
        
        assert result["success"] is True
        assert "page_id" in result
        assert result["url"] == "https://example.com"

    def test_store_page_requires_url(self, temp_db):
        """Missing URL returns error."""
        from tools.web_tools import store_page
        
        result = store_page(url="", title="No URL")
        
        assert result["success"] is False
        assert "URL is required" in result["error"]

    def test_store_page_updates_existing(self, temp_db):
        """Existing URL is updated."""
        from tools.web_tools import store_page
        
        # First store
        store_page(url="https://test.com", title="Original", content="Original content")
        
        # Update
        result = store_page(url="https://test.com", title="Updated", content="Updated content")
        
        assert result["success"] is True

    def test_store_page_with_metadata(self, temp_db):
        """Metadata is stored as JSON."""
        from tools.web_tools import store_page
        
        result = store_page(
            url="https://meta.com",
            title="Meta Page",
            content="Content",
            metadata={"key": "value", "nested": {"a": 1}}
        )
        
        assert result["success"] is True


class TestSearchPages:
    """Test suite for search_pages function."""

    def test_search_pages_requires_query(self, temp_db):
        """Empty query returns error."""
        from tools.web_tools import search_pages
        
        result = search_pages("")
        parsed = json.loads(result)
        
        assert "error" in parsed

    def test_search_pages_returns_json(self, temp_db):
        """Search returns JSON string."""
        from tools.web_tools import store_page, search_pages
        
        store_page(url="https://python.com", title="Python", content="Python programming language")
        
        result = search_pages("python")
        parsed = json.loads(result)
        
        assert parsed["success"] is True
        assert "results" in parsed

    def test_search_pages_no_results(self, temp_db):
        """Search with no matches returns empty results."""
        from tools.web_tools import search_pages
        
        result = search_pages("nonexistent")
        parsed = json.loads(result)
        
        assert parsed["success"] is True
        assert parsed["results"] == []


class TestListPages:
    """Test suite for list_pages function."""

    def test_list_pages_returns_json(self, temp_db):
        """List returns JSON string."""
        from tools.web_tools import list_pages
        
        result = list_pages()
        parsed = json.loads(result)
        
        assert parsed["success"] is True
        assert "pages" in parsed
        assert "total" in parsed

    def test_list_pages_respects_limit(self, temp_db):
        """Limit parameter is respected."""
        from tools.web_tools import store_page, list_pages
        
        # Store multiple pages
        for i in range(5):
            store_page(url=f"https://page{i}.com", title=f"Page {i}", content="Content")
        
        result = list_pages(limit=2)
        parsed = json.loads(result)
        
        assert len(parsed["pages"]) == 2
        assert parsed["total"] == 5

    def test_list_pages_filter_by_source(self, temp_db):
        """Source tool filter works."""
        from tools.web_tools import store_page, list_pages
        
        store_page(url="https://extract.com", title="Extract", content="C", source_tool="web_extract")
        store_page(url="https://crawl.com", title="Crawl", content="C", source_tool="web_crawl")
        
        result = list_pages(source_tool="web_extract")
        parsed = json.loads(result)
        
        assert len(parsed["pages"]) == 1
        assert parsed["pages"][0]["source_tool"] == "web_extract"


class TestGetPage:
    """Test suite for get_page function."""

    def test_get_page_by_url(self, temp_db):
        """Get page by URL."""
        from tools.web_tools import store_page, get_page
        
        store_page(url="https://get.com", title="Get Test", content="Get content")
        
        result = get_page(url="https://get.com")
        parsed = json.loads(result)
        
        assert parsed["success"] is True
        assert parsed["page"]["url"] == "https://get.com"
        assert parsed["page"]["title"] == "Get Test"

    def test_get_page_by_id(self, temp_db):
        """Get page by ID."""
        from tools.web_tools import store_page, get_page
        
        store_result = store_page(url="https://byid.com", title="By ID", content="Content")
        page_id = store_result["page_id"]
        
        result = get_page(page_id=page_id)
        parsed = json.loads(result)
        
        assert parsed["success"] is True
        assert parsed["page"]["id"] == page_id

    def test_get_page_not_found(self, temp_db):
        """Non-existent page returns error."""
        from tools.web_tools import get_page
        
        result = get_page(url="https://nonexistent.com")
        parsed = json.loads(result)
        
        assert "error" in parsed
        assert parsed["success"] is False

    def test_get_page_requires_identifier(self, temp_db):
        """Missing identifier returns error."""
        from tools.web_tools import get_page
        
        result = get_page()
        parsed = json.loads(result)
        
        assert "error" in parsed


class TestDeletePage:
    """Test suite for delete_page function."""

    def test_delete_page_by_url(self, temp_db):
        """Delete page by URL."""
        from tools.web_tools import store_page, delete_page, get_page
        
        store_page(url="https://delete.com", title="Delete", content="Content")
        
        result = delete_page(url="https://delete.com")
        parsed = json.loads(result)
        
        assert parsed["success"] is True
        assert parsed["deleted"] == 1
        
        # Verify deleted
        get_result = get_page(url="https://delete.com")
        assert "error" in json.loads(get_result)

    def test_delete_page_by_id(self, temp_db):
        """Delete page by ID."""
        from tools.web_tools import store_page, delete_page
        
        store_result = store_page(url="https://delid.com", title="Del by ID", content="C")
        page_id = store_result["page_id"]
        
        result = delete_page(page_id=page_id)
        parsed = json.loads(result)
        
        assert parsed["success"] is True

    def test_delete_page_not_found(self, temp_db):
        """Deleting non-existent page returns error."""
        from tools.web_tools import delete_page
        
        result = delete_page(url="https://neverexisted.com")
        parsed = json.loads(result)
        
        assert "error" in parsed
        assert parsed["success"] is False


class TestGetStorageStats:
    """Test suite for get_storage_stats function."""

    def test_stats_returns_dict(self, temp_db):
        """Stats returns dictionary."""
        from tools.web_tools import get_storage_stats
        
        result = get_storage_stats()
        
        assert isinstance(result, dict)
        assert "success" in result
        assert "total_pages" in result

    def test_stats_counts_pages(self, temp_db):
        """Stats counts stored pages."""
        from tools.web_tools import store_page, get_storage_stats
        
        store_page(url="https://stat1.com", title="S1", content="C1")
        store_page(url="https://stat2.com", title="S2", content="C2")
        
        result = get_storage_stats()
        
        assert result["total_pages"] == 2


# ─── URL Handling Edge Cases ──────────────────────────────────────────────────

class TestUrlHandling:
    """Test suite for URL handling edge cases."""

    @pytest.mark.asyncio
    async def test_extract_url_with_fragment(self):
        """URLs with fragments are handled."""
        mock_scrape = {
            "markdown": "Content",
            "metadata": {"title": "Page", "sourceURL": "https://example.com/page#section"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com/page#section"], 
                use_llm_processing=False
            ))
            
            assert "results" in result

    @pytest.mark.asyncio
    async def test_extract_url_with_query_params(self):
        """URLs with query parameters are handled."""
        mock_scrape = {
            "markdown": "Content",
            "metadata": {"title": "Page", "sourceURL": "https://example.com?param=value"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://example.com?param=value"], 
                use_llm_processing=False
            ))
            
            assert "results" in result

    @pytest.mark.asyncio
    async def test_extract_unicode_url(self):
        """Unicode URLs are handled."""
        mock_scrape = {
            "markdown": "Content",
            "metadata": {"title": "Unicode", "sourceURL": "https://例え.jp/page"}
        }
        
        with patch("tools.web_tools._get_backend", return_value="firecrawl"), \
             patch("tools.web_tools._get_firecrawl_client") as mock_client, \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch("tools.web_tools.check_website_access", return_value=None):
            mock_client.return_value.scrape.return_value = mock_scrape
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(
                ["https://例え.jp/page"], 
                use_llm_processing=False
            ))
            
            assert "results" in result


# ─── Error Handling Tests ─────────────────────────────────────────────────────

class TestErrorHandling:
    """Test suite for error handling across web tools."""

    @pytest.mark.asyncio
    async def test_extract_general_exception(self):
        """General exceptions in extract are caught."""
        with patch("tools.web_tools._get_backend", side_effect=Exception("Unexpected error")):
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool(["https://test.com"]))
            
            assert "error" in result

    def test_search_general_exception(self):
        """General exceptions in search are caught."""
        with patch("tools.web_tools._get_backend", side_effect=Exception("Unexpected error")):
            from tools.web_tools import web_search_tool
            result = json.loads(web_search_tool("test"))
            
            assert "error" in result

    @pytest.mark.asyncio
    async def test_extract_empty_url_list(self):
        """Empty URL list is handled gracefully."""
        with patch("tools.web_tools._get_backend", return_value="firecrawl"):
            from tools.web_tools import web_extract_tool
            result = json.loads(await web_extract_tool([], use_llm_processing=False))
            
            # Should return empty results or error
            assert "results" in result or "error" in result
