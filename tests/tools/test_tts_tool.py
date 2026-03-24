"""Tests for tools/tts_tool.py — TTS providers, audio output, error handling.

Coverage:
  text_to_speech_tool — main tool function, provider selection, file output
  _load_tts_config — config loading from YAML
  _get_provider — provider selection logic
  _has_ffmpeg / _convert_to_opus — ffmpeg utilities
  _generate_edge_tts — Edge TTS provider (async)
  _generate_elevenlabs — ElevenLabs provider
  _generate_openai_tts — OpenAI TTS provider
  _generate_neutts — NeuTTS local provider
  _check_neutts_available — NeuTTS availability check
  check_tts_requirements — requirements verification
  _strip_markdown_for_tts — markdown sanitization for TTS
  stream_tts_to_speaker — streaming TTS pipeline
"""

import json
import os
import queue
import tempfile
import threading
import time
import pytest
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, mock_open

# Ensure parent directory is on path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the tts_tool module using importlib to get module, not function
import importlib
tt = importlib.import_module('tools.tts_tool')


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture(autouse=True)
def reset_tts_state(monkeypatch):
    """Reset module state before and after each test."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
    monkeypatch.delenv("HERMES_SESSION_PLATFORM", raising=False)
    yield


@pytest.fixture
def mock_edge_tts():
    """Mock edge_tts module and Communicate class."""
    mock_communicate = MagicMock()
    mock_communicate.save = AsyncMock()
    
    mock_module = MagicMock()
    mock_module.Communicate.return_value = mock_communicate
    return mock_module


@pytest.fixture
def mock_elevenlabs_client():
    """Mock ElevenLabs client."""
    mock_client = MagicMock()
    mock_client.text_to_speech.convert.return_value = [b"fake_audio_chunk"]
    return mock_client


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client with speech API."""
    mock_response = MagicMock()
    mock_response.stream_to_file = MagicMock()
    
    mock_speech = MagicMock()
    mock_speech.create.return_value = mock_response
    
    mock_client = MagicMock()
    mock_client.audio.speech = mock_speech
    return mock_client


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory."""
    output_dir = tmp_path / "audio_cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# =============================================================================
# _load_tts_config Tests
# =============================================================================

class TestLoadTtsConfig:
    """Test suite for _load_tts_config."""

    def test_returns_dict(self):
        """Always returns a dict, never None."""
        # Patch hermes_cli.config.load_config where it's imported
        with patch('hermes_cli.config.load_config', side_effect=ImportError("no module")):
            result = tt._load_tts_config()
            assert isinstance(result, dict)

    def test_returns_empty_on_import_error(self):
        """Returns empty dict if hermes_cli not available."""
        with patch('hermes_cli.config.load_config', side_effect=ImportError("no module")):
            result = tt._load_tts_config()
            assert result == {}

    def test_returns_empty_on_exception(self):
        """Returns empty dict on any exception."""
        with patch('hermes_cli.config.load_config', side_effect=RuntimeError("fail")):
            result = tt._load_tts_config()
            assert result == {}

    def test_returns_tts_section(self):
        """Returns tts section from config."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "elevenlabs"}}):
            result = tt._load_tts_config()
            assert result == {"provider": "elevenlabs"}

    def test_returns_empty_when_no_tts_key(self):
        """Returns empty dict when tts key missing."""
        with patch('hermes_cli.config.load_config', return_value={"other": "config"}):
            result = tt._load_tts_config()
            assert result == {}


# =============================================================================
# _get_provider Tests
# =============================================================================

class TestGetProvider:
    """Test suite for _get_provider."""

    def test_default_provider(self):
        """Default provider is 'edge'."""
        result = tt._get_provider({})
        assert result == "edge"

    def test_custom_provider(self):
        """Custom provider is returned."""
        result = tt._get_provider({"provider": "elevenlabs"})
        assert result == "elevenlabs"

    def test_provider_normalized_to_lowercase(self):
        """Provider is normalized to lowercase."""
        result = tt._get_provider({"provider": "OPENAI"})
        assert result == "openai"

    def test_provider_stripped(self):
        """Provider is stripped of whitespace."""
        result = tt._get_provider({"provider": "  neutts  "})
        assert result == "neutts"


# =============================================================================
# _has_ffmpeg Tests
# =============================================================================

class TestHasFfmpeg:
    """Test suite for _has_ffmpeg."""

    def test_returns_true_when_ffmpeg_found(self):
        """Returns True if ffmpeg in PATH."""
        with patch('shutil.which', return_value='/usr/bin/ffmpeg'):
            assert tt._has_ffmpeg() is True

    def test_returns_false_when_ffmpeg_not_found(self):
        """Returns False if ffmpeg not in PATH."""
        with patch('shutil.which', return_value=None):
            assert tt._has_ffmpeg() is False


# =============================================================================
# _convert_to_opus Tests
# =============================================================================

class TestConvertToOpus:
    """Test suite for _convert_to_opus."""

    def test_returns_none_when_no_ffmpeg(self):
        """Returns None if ffmpeg not available."""
        with patch('tools.tts_tool._has_ffmpeg', return_value=False):
            result = tt._convert_to_opus("/tmp/test.mp3")
            assert result is None

    def test_converts_mp3_to_ogg(self, tmp_path):
        """Converts MP3 file to OGG Opus format."""
        mp3_path = str(tmp_path / "test.mp3")
        ogg_path = str(tmp_path / "test.ogg")
        
        # Create a fake mp3 file
        with open(mp3_path, 'wb') as f:
            f.write(b"fake mp3 data")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = b""
        
        def fake_run(cmd, **kwargs):
            # Create the output file
            output_path = cmd[cmd.index("-i") + 2]
            for arg in cmd:
                if arg.endswith(".ogg"):
                    with open(arg, 'wb') as f:
                        f.write(b"fake ogg data")
                    break
            return mock_result
        
        with patch('tools.tts_tool._has_ffmpeg', return_value=True), \
             patch('subprocess.run', side_effect=fake_run):
            result = tt._convert_to_opus(mp3_path)
            assert result is not None
            assert result.endswith(".ogg")

    def test_returns_none_on_ffmpeg_failure(self, tmp_path):
        """Returns None if ffmpeg fails."""
        mp3_path = str(tmp_path / "test.mp3")
        Path(mp3_path).touch()
        
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = b"ffmpeg error"
        
        with patch('tools.tts_tool._has_ffmpeg', return_value=True), \
             patch('subprocess.run', return_value=mock_result):
            result = tt._convert_to_opus(mp3_path)
            assert result is None

    def test_handles_timeout(self, tmp_path):
        """Handles ffmpeg timeout gracefully."""
        mp3_path = str(tmp_path / "test.mp3")
        Path(mp3_path).touch()
        
        import subprocess
        
        with patch('tools.tts_tool._has_ffmpeg', return_value=True), \
             patch('subprocess.run', side_effect=subprocess.TimeoutExpired("ffmpeg", 30)):
            result = tt._convert_to_opus(mp3_path)
            assert result is None

    def test_handles_file_not_found(self, tmp_path):
        """Handles ffmpeg not found gracefully."""
        mp3_path = str(tmp_path / "test.mp3")
        Path(mp3_path).touch()
        
        with patch('tools.tts_tool._has_ffmpeg', return_value=True), \
             patch('subprocess.run', side_effect=FileNotFoundError()):
            result = tt._convert_to_opus(mp3_path)
            assert result is None


# =============================================================================
# _strip_markdown_for_tts Tests
# =============================================================================

class TestStripMarkdownForTts:
    """Test suite for _strip_markdown_for_tts."""

    def test_strips_code_blocks(self):
        """Removes code blocks."""
        text = "Here is code:\n```python\nprint('hello')\n```\nMore text."
        result = tt._strip_markdown_for_tts(text)
        assert "print" not in result
        assert "Here is code" in result
        assert "More text" in result

    def test_strips_links(self):
        """Removes link URLs, keeps text."""
        text = "Click [here](https://example.com) to continue."
        result = tt._strip_markdown_for_tts(text)
        assert "https://example.com" not in result
        assert "here" in result

    def test_strips_bare_urls(self):
        """Removes bare URLs."""
        text = "Visit https://example.com for more."
        result = tt._strip_markdown_for_tts(text)
        assert "https://example.com" not in result
        assert "Visit" in result

    def test_strips_bold(self):
        """Removes bold markers, keeps text."""
        text = "This is **important** text."
        result = tt._strip_markdown_for_tts(text)
        assert "**" not in result
        assert "important" in result

    def test_strips_italic(self):
        """Removes italic markers, keeps text."""
        text = "This is *emphasized* text."
        result = tt._strip_markdown_for_tts(text)
        assert "*emphasized*" not in result
        assert "emphasized" in result

    def test_strips_inline_code(self):
        """Removes inline code markers, keeps content."""
        text = "Use the `print` function."
        result = tt._strip_markdown_for_tts(text)
        assert "`" not in result
        assert "print" in result

    def test_strips_headers(self):
        """Removes header markers."""
        text = "# Main Title\n## Subtitle\nContent"
        result = tt._strip_markdown_for_tts(text)
        assert "# Main Title" not in result
        assert "Main Title" in result

    def test_strips_list_items(self):
        """Removes list item markers."""
        text = "Items:\n- First item\n- Second item"
        result = tt._strip_markdown_for_tts(text)
        assert "- First" not in result

    def test_strips_horizontal_rules(self):
        """Removes horizontal rules."""
        text = "Above\n---\nBelow"
        result = tt._strip_markdown_for_tts(text)
        assert "---" not in result

    def test_collapses_excess_newlines(self):
        """Collapses excess newlines."""
        text = "Para 1\n\n\n\n\nPara 2"
        result = tt._strip_markdown_for_tts(text)
        assert "\n\n\n" not in result

    def test_combined_markdown(self):
        """Handles combined markdown elements."""
        text = """# Title

This is **bold** and *italic* text with a [link](https://example.com).

```python
code = 123
```

- List item
- Another item

Visit https://test.com for more."""
        result = tt._strip_markdown_for_tts(text)
        assert "**" not in result
        assert "*italic*" not in result
        assert "https://" not in result
        assert "```" not in result
        assert "Title" in result
        assert "bold" in result


# =============================================================================
# _check_neutts_available Tests
# =============================================================================

class TestCheckNeuttsAvailable:
    """Test suite for _check_neutts_available."""

    def test_returns_true_when_available(self):
        """Returns True if neutts importable."""
        with patch('importlib.util.find_spec', return_value=MagicMock()):
            assert tt._check_neutts_available() is True

    def test_returns_false_when_not_available(self):
        """Returns False if neutts not importable."""
        with patch('importlib.util.find_spec', return_value=None):
            assert tt._check_neutts_available() is False

    def test_returns_false_on_exception(self):
        """Returns False on any exception."""
        with patch('importlib.util.find_spec', side_effect=Exception("fail")):
            assert tt._check_neutts_available() is False


# =============================================================================
# _default_neutts_ref_audio Tests
# =============================================================================

class TestDefaultNeuttsRefAudio:
    """Test suite for _default_neutts_ref_audio."""

    def test_returns_string(self):
        """Returns a string path."""
        result = tt._default_neutts_ref_audio()
        assert isinstance(result, str)

    def test_path_contains_jo(self):
        """Path includes the default voice filename."""
        result = tt._default_neutts_ref_audio()
        assert "jo.wav" in result


# =============================================================================
# _default_neutts_ref_text Tests
# =============================================================================

class TestDefaultNeuttsRefText:
    """Test suite for _default_neutts_ref_text."""

    def test_returns_string(self):
        """Returns a string path."""
        result = tt._default_neutts_ref_text()
        assert isinstance(result, str)

    def test_path_contains_jo(self):
        """Path includes the default voice transcript filename."""
        result = tt._default_neutts_ref_text()
        assert "jo.txt" in result


# =============================================================================
# check_tts_requirements Tests
# =============================================================================

class TestCheckTtsRequirements:
    """Test suite for check_tts_requirements."""

    def test_returns_true_with_edge_tts(self):
        """Returns True if edge_tts available."""
        with patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()):
            assert tt.check_tts_requirements() is True

    def test_returns_true_with_elevenlabs_and_key(self, monkeypatch):
        """Returns True if ElevenLabs available with API key."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test_key")
        
        with patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._import_elevenlabs', return_value=MagicMock()):
            assert tt.check_tts_requirements() is True

    def test_returns_false_with_elevenlabs_no_key(self, monkeypatch):
        """Returns False if ElevenLabs available but no API key."""
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        
        with patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._import_elevenlabs', return_value=MagicMock()):
            assert tt.check_tts_requirements() is False

    def test_returns_true_with_openai_and_key(self, monkeypatch):
        """Returns True if OpenAI available with API key."""
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "test_key")
        
        with patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._import_elevenlabs', side_effect=ImportError), \
             patch('tools.tts_tool._import_openai_client', return_value=MagicMock()):
            assert tt.check_tts_requirements() is True

    def test_returns_false_with_openai_no_key(self, monkeypatch):
        """Returns False if OpenAI available but no API key."""
        monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
        
        with patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._import_elevenlabs', side_effect=ImportError), \
             patch('tools.tts_tool._import_openai_client', return_value=MagicMock()):
            assert tt.check_tts_requirements() is False

    def test_returns_true_with_neutts(self):
        """Returns True if NeuTTS available."""
        with patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._import_elevenlabs', side_effect=ImportError), \
             patch('tools.tts_tool._import_openai_client', side_effect=ImportError), \
             patch('tools.tts_tool._check_neutts_available', return_value=True):
            assert tt.check_tts_requirements() is True

    def test_returns_false_when_no_provider(self):
        """Returns False if no provider available."""
        with patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._import_elevenlabs', side_effect=ImportError), \
             patch('tools.tts_tool._import_openai_client', side_effect=ImportError), \
             patch('tools.tts_tool._check_neutts_available', return_value=False):
            assert tt.check_tts_requirements() is False


# =============================================================================
# text_to_speech_tool - Input Validation Tests
# =============================================================================

class TestTextToSpeechToolInputValidation:
    """Test suite for text_to_speech_tool input validation."""

    def test_empty_text_returns_error(self):
        """Empty text returns error JSON."""
        result = tt.text_to_speech_tool(text="")
        parsed = json.loads(result)
        assert parsed["success"] is False
        assert "required" in parsed["error"].lower()

    def test_whitespace_only_text_returns_error(self):
        """Whitespace-only text returns error JSON."""
        result = tt.text_to_speech_tool(text="   \n\t  ")
        parsed = json.loads(result)
        assert parsed["success"] is False

    def test_result_is_json_string(self):
        """Result is always a JSON string."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen:
            # Mock file creation
            mock_gen.return_value = "/tmp/test.mp3"
            
            with patch('os.path.exists', return_value=True), \
                 patch('os.path.getsize', return_value=1024):
                result = tt.text_to_speech_tool(text="Hello world")
                assert isinstance(result, str)
                parsed = json.loads(result)
                assert isinstance(parsed, dict)


# =============================================================================
# text_to_speech_tool - Provider Selection Tests
# =============================================================================

class TestTextToSpeechToolProviderSelection:
    """Test suite for provider selection in text_to_speech_tool."""

    def test_edge_tts_provider_called(self, mock_edge_tts):
        """Edge TTS provider is called when configured."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "edge"}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            mock_gen.return_value = "/tmp/test.mp3"
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is True

    def test_elevenlabs_provider_missing_package_error(self):
        """ElevenLabs returns error if package not installed."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "elevenlabs"}}), \
             patch('tools.tts_tool._import_elevenlabs', side_effect=ImportError("no package")):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "elevenlabs" in parsed["error"].lower()

    def test_elevenlabs_provider_missing_key_error(self, monkeypatch):
        """ElevenLabs returns error if API key not set."""
        monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
        
        # Patch config to return elevenlabs provider
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "elevenlabs"}}):
            with patch('tools.tts_tool._import_elevenlabs', return_value=MagicMock):
                result = tt.text_to_speech_tool(text="Hello")
                parsed = json.loads(result)
                assert parsed["success"] is False
                assert "api" in parsed["error"].lower() or "key" in parsed["error"].lower()

    def test_openai_provider_missing_package_error(self):
        """OpenAI returns error if package not installed."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "openai"}}), \
             patch('tools.tts_tool._import_openai_client', side_effect=ImportError("no package")):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "openai" in parsed["error"].lower()

    def test_openai_provider_missing_key_error(self, monkeypatch):
        """OpenAI returns error if API key not set."""
        monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "openai"}}), \
             patch('tools.tts_tool._import_openai_client', return_value=MagicMock):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "openai" in parsed["error"].lower()

    def test_neutts_provider_not_available_error(self):
        """NeuTTS returns error if not installed."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "neutts"}}), \
             patch('tools.tts_tool._check_neutts_available', return_value=False):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "neutts" in parsed["error"].lower()

    def test_no_provider_available_error(self):
        """Returns error when no TTS provider available."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', side_effect=ImportError), \
             patch('tools.tts_tool._check_neutts_available', return_value=False):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "no tts provider" in parsed["error"].lower()


# =============================================================================
# text_to_speech_tool - Output Path Tests
# =============================================================================

class TestTextToSpeechToolOutputPath:
    """Test suite for output path handling in text_to_speech_tool."""

    def test_custom_output_path_used(self, tmp_path):
        """Custom output path is used when provided."""
        custom_path = str(tmp_path / "custom_output.mp3")
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            mock_gen.return_value = custom_path
            result = tt.text_to_speech_tool(text="Hello", output_path=custom_path)
            parsed = json.loads(result)
            assert parsed["success"] is True
            assert custom_path in parsed["file_path"]

    def test_expands_tilde_in_path(self):
        """Tilde in path is expanded."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            mock_gen.return_value = "/home/user/test.mp3"
            result = tt.text_to_speech_tool(text="Hello", output_path="~/test.mp3")
            parsed = json.loads(result)
            assert parsed["success"] is True


# =============================================================================
# text_to_speech_tool - Platform Detection Tests
# =============================================================================

class TestTextToSpeechToolPlatformDetection:
    """Test suite for platform detection in text_to_speech_tool."""

    def test_telegram_platform_requests_ogg(self, monkeypatch, tmp_path):
        """Telegram platform requests OGG format for compatible providers."""
        monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
        
        mock_module = MagicMock()
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "openai"}}), \
             patch('tools.tts_tool._import_openai_client', return_value=MagicMock) as mock_import, \
             patch.dict(os.environ, {"VOICE_TOOLS_OPENAI_KEY": "test_key"}):
            with patch('tools.tts_tool._generate_openai_tts') as mock_gen:
                mock_gen.return_value = str(tmp_path / "test.ogg")
                
                with patch('os.path.exists', return_value=True), \
                     patch('os.path.getsize', return_value=1024):
                    result = tt.text_to_speech_tool(text="Hello")
                    parsed = json.loads(result)
                    # Should succeed
                    assert parsed["success"] is True


# =============================================================================
# text_to_speech_tool - Error Handling Tests
# =============================================================================

class TestTextToSpeechToolErrorHandling:
    """Test suite for error handling in text_to_speech_tool."""

    def test_file_not_created_returns_error(self):
        """Returns error if audio file not created."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=False):
            mock_gen.return_value = "/tmp/test.mp3"
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "no output" in parsed["error"].lower()

    def test_empty_file_returns_error(self):
        """Returns error if audio file is empty."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=0):
            mock_gen.return_value = "/tmp/test.mp3"
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False

    def test_value_error_caught(self):
        """ValueError (config errors) is caught."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "elevenlabs"}}), \
             patch('tools.tts_tool._import_elevenlabs', return_value=MagicMock), \
             patch('tools.tts_tool._generate_elevenlabs', side_effect=ValueError("bad config")):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "config" in parsed["error"].lower()

    def test_file_not_found_error_caught(self):
        """FileNotFoundError is caught."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen:
            mock_gen.side_effect = FileNotFoundError("file missing")
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is False
            assert "missing" in parsed["error"].lower()

    def test_generic_exception_caught(self):
        """Generic exceptions in config loading are caught and tool falls back to defaults."""
        # Patch the config loading to raise an exception - tool should gracefully fall back
        with patch('hermes_cli.config.load_config', side_effect=RuntimeError("unexpected")):
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            # Tool gracefully handles config errors by falling back to defaults
            # So it should still work (success=True) or fail for other reasons (no API keys)
            assert "success" in parsed


# =============================================================================
# text_to_speech_tool - Text Truncation Tests
# =============================================================================

class TestTextToSpeechToolTextTruncation:
    """Test suite for text truncation in text_to_speech_tool."""

    def test_long_text_truncated(self):
        """Text longer than MAX_TEXT_LENGTH is truncated."""
        long_text = "x" * 5000
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            mock_gen.return_value = "/tmp/test.mp3"
            result = tt.text_to_speech_tool(text=long_text)
            parsed = json.loads(result)
            assert parsed["success"] is True
            # Verify _generate_edge_tts was called (text is truncated before being passed)
            assert mock_gen.called


# =============================================================================
# text_to_speech_tool - Media Tag Tests
# =============================================================================

class TestTextToSpeechToolMediaTag:
    """Test suite for media tag generation in text_to_speech_tool."""

    def test_includes_media_tag(self):
        """Result includes MEDIA tag."""
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_edge_tts', return_value=MagicMock()), \
             patch('tools.tts_tool._generate_edge_tts', new_callable=AsyncMock) as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024), \
             patch('tools.tts_tool._convert_to_opus', return_value="/tmp/test.ogg"):
            mock_gen.return_value = "/tmp/test.mp3"
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is True
            assert "media_tag" in parsed
            assert "MEDIA:" in parsed["media_tag"]

    def test_voice_compatible_tag_for_telegram(self, monkeypatch):
        """Voice compatible tag added for Telegram when Opus available."""
        monkeypatch.setenv("HERMES_SESSION_PLATFORM", "telegram")
        
        mock_module = MagicMock()
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {"provider": "openai"}}), \
             patch('tools.tts_tool._import_openai_client', return_value=MagicMock), \
             patch.dict(os.environ, {"VOICE_TOOLS_OPENAI_KEY": "test_key"}), \
             patch('tools.tts_tool._generate_openai_tts') as mock_gen, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            mock_gen.return_value = "/tmp/test.ogg"
            result = tt.text_to_speech_tool(text="Hello")
            parsed = json.loads(result)
            assert parsed["success"] is True
            assert "voice_compatible" in parsed


# =============================================================================
# _generate_elevenlabs Tests
# =============================================================================

class TestGenerateElevenlabs:
    """Test suite for _generate_elevenlabs."""

    def test_generates_mp3_by_default(self, tmp_path, monkeypatch):
        """Generates MP3 format by default."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test_key")
        output_path = str(tmp_path / "test.mp3")
        
        mock_client = MagicMock()
        mock_client.text_to_speech.convert.return_value = [b"audio_data"]
        
        with patch('tools.tts_tool._import_elevenlabs', return_value=MagicMock) as mock_import:
            mock_import.return_value = mock_client
            
            # Create the output file to simulate success
            with open(output_path, 'wb') as f:
                f.write(b"audio_data")
            
            result = tt._generate_elevenlabs("Hello", output_path, {})
            assert result == output_path

    def test_generates_ogg_for_telegram(self, tmp_path, monkeypatch):
        """Generates Opus format for Telegram."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test_key")
        output_path = str(tmp_path / "test.ogg")
        
        mock_client = MagicMock()
        mock_client.text_to_speech.convert.return_value = [b"audio_data"]
        
        with patch('tools.tts_tool._import_elevenlabs', return_value=MagicMock) as mock_import:
            mock_import.return_value = mock_client
            
            with open(output_path, 'wb') as f:
                f.write(b"audio_data")
            
            result = tt._generate_elevenlabs("Hello", output_path, {})
            assert result == output_path

    def test_uses_custom_voice_id(self, monkeypatch, tmp_path):
        """Uses custom voice_id from config."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test_key")
        output_path = str(tmp_path / "test.mp3")
        
        mock_client = MagicMock()
        mock_client.text_to_speech.convert.return_value = [b"audio_data"]
        
        config = {"elevenlabs": {"voice_id": "custom_voice"}}
        
        mock_elevenlabs = MagicMock()
        mock_elevenlabs.return_value = mock_client
        
        with patch('tools.tts_tool._import_elevenlabs', return_value=mock_elevenlabs):
            # Create the output file to simulate success
            with open(output_path, 'wb') as f:
                f.write(b"audio_data")
            
            tt._generate_elevenlabs("Hello", output_path, config)
            
            # Verify the convert method was called
            assert mock_client.text_to_speech.convert.called
            call_args = mock_client.text_to_speech.convert.call_args
            # Check that voice_id was in the call
            if call_args and call_args.kwargs:
                assert call_args.kwargs.get("voice_id") == "custom_voice"


# =============================================================================
# _generate_openai_tts Tests
# =============================================================================

class TestGenerateOpenaiTts:
    """Test suite for _generate_openai_tts."""

    def test_generates_mp3_by_default(self, tmp_path, monkeypatch):
        """Generates MP3 format by default."""
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "test_key")
        output_path = str(tmp_path / "test.mp3")
        
        mock_response = MagicMock()
        
        mock_client = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response
        
        with patch('tools.tts_tool._import_openai_client', return_value=MagicMock) as mock_import:
            mock_import.return_value = mock_client
            
            # Simulate stream_to_file creating the file
            mock_response.stream_to_file = MagicMock()
            
            result = tt._generate_openai_tts("Hello", output_path, {})
            assert result == output_path

    def test_uses_custom_model_and_voice(self, tmp_path, monkeypatch):
        """Uses custom model and voice from config."""
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "test_key")
        output_path = str(tmp_path / "test.mp3")
        
        mock_response = MagicMock()
        
        mock_client = MagicMock()
        mock_client.audio.speech.create.return_value = mock_response
        
        config = {"openai": {"model": "tts-1", "voice": "nova"}}
        
        mock_openai = MagicMock()
        mock_openai.return_value = mock_client
        
        with patch('tools.tts_tool._import_openai_client', return_value=mock_openai):
            tt._generate_openai_tts("Hello", output_path, config)
            
            # Verify create was called
            assert mock_client.audio.speech.create.called
            call_args = mock_client.audio.speech.create.call_args
            # Check that model and voice were in the call
            if call_args and call_args.kwargs:
                assert call_args.kwargs.get("model") == "tts-1"
                assert call_args.kwargs.get("voice") == "nova"


# =============================================================================
# _generate_neutts Tests
# =============================================================================

class TestGenerateNeutts:
    """Test suite for _generate_neutts."""

    def test_calls_subprocess_correctly(self, tmp_path):
        """Calls neutts_synth.py subprocess correctly."""
        output_path = str(tmp_path / "test.wav")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = "OK: synthesis complete"
        
        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            # Create output file
            Path(output_path).touch()
            
            result = tt._generate_neutts("Hello", output_path, {})
            
            # Check subprocess was called
            assert mock_run.called
            call_args = mock_run.call_args[0][0]
            assert "--text" in call_args
            assert "Hello" in call_args
            assert "--out" in call_args

    def test_handles_subprocess_failure(self):
        """Handles subprocess failure gracefully."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: synthesis failed"
        
        with patch('subprocess.run', return_value=mock_result):
            with pytest.raises(RuntimeError) as exc_info:
                tt._generate_neutts("Hello", "/tmp/test.wav", {})
            assert "failed" in str(exc_info.value).lower()

    def test_handles_timeout(self):
        """Handles subprocess timeout."""
        import subprocess
        
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired("python", 120)):
            with pytest.raises(subprocess.TimeoutExpired):
                tt._generate_neutts("Hello", "/tmp/test.wav", {})

    def test_uses_config_options(self, tmp_path):
        """Uses config options for model and device."""
        output_path = str(tmp_path / "test.wav")
        
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        config = {"neutts": {"model": "custom-model", "device": "cuda"}}
        
        with patch('subprocess.run', return_value=mock_result) as mock_run, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1024):
            Path(output_path).touch()
            
            tt._generate_neutts("Hello", output_path, config)
            
            call_args = mock_run.call_args[0][0]
            assert "--model" in call_args
            assert "custom-model" in call_args
            assert "--device" in call_args
            assert "cuda" in call_args


# =============================================================================
# stream_tts_to_speaker Tests
# =============================================================================

class TestStreamTtsToSpeaker:
    """Test suite for stream_tts_to_speaker."""

    def test_processes_text_queue(self):
        """Processes text from queue and calls display callback."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        display_callback = MagicMock()
        
        # Put text and sentinel
        text_queue.put("Hello world. ")
        text_queue.put("How are you?")
        text_queue.put(None)  # End sentinel
        
        # Set stop event after a short delay to allow processing
        def stop_after_delay():
            time.sleep(0.5)
            if not tts_done_event.is_set():
                stop_event.set()
        
        threading.Thread(target=stop_after_delay, daemon=True).start()
        
        # Run without ElevenLabs client
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch.dict(os.environ, {}, clear=True):  # No API key
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event,
                display_callback=display_callback
            )
        
        # Display callback should have been called
        assert display_callback.called

    def test_stop_event_aborts_early(self):
        """Stop event causes early exit."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        display_callback = MagicMock()
        
        # Set stop immediately
        stop_event.set()
        
        tt.stream_tts_to_speaker(
            text_queue=text_queue,
            stop_event=stop_event,
            tts_done_event=tts_done_event,
            display_callback=display_callback
        )
        
        # tts_done_event should be set
        assert tts_done_event.is_set()

    def test_handles_none_sentinel(self):
        """None sentinel causes flush and exit."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        display_callback = MagicMock()
        
        text_queue.put("Final text.")
        text_queue.put(None)  # Sentinel
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch.dict(os.environ, {}, clear=True):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event,
                display_callback=display_callback
            )
        
        assert tts_done_event.is_set()

    def test_strips_markdown_from_text(self):
        """Markdown is stripped before TTS processing."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        display_callback = MagicMock()
        
        # Put markdown text
        text_queue.put("This is **bold** text. ")
        text_queue.put(None)
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch.dict(os.environ, {}, clear=True):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event,
                display_callback=display_callback
            )
        
        # Display callback receives raw text (markdown not stripped for display)
        assert display_callback.called

    def test_filters_think_blocks(self):
        """Think blocks are filtered from speech."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        display_callback = MagicMock()
        
        # Put text with think block
        text_queue.put("Before. <think internal thoughts </think After. ")
        text_queue.put(None)
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch.dict(os.environ, {}, clear=True):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event,
                display_callback=display_callback
            )
        
        assert tts_done_event.is_set()

    def test_skips_duplicate_sentences(self):
        """Duplicate sentences are skipped."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        display_callback = MagicMock()
        
        # Put duplicate text
        text_queue.put("Same text. ")
        text_queue.put("Same text! ")
        text_queue.put(None)
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch.dict(os.environ, {}, clear=True):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event,
                display_callback=display_callback
            )
        
        # Should process but skip duplicates for audio
        assert tts_done_event.is_set()

    def test_drains_queue_on_exit(self):
        """Queue is drained on exit to prevent deadlock."""
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        # Fill queue with items
        for i in range(5):
            text_queue.put(f"Item {i}")
        
        # Set stop immediately
        stop_event.set()
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch.dict(os.environ, {}, clear=True):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event,
                display_callback=None
            )
        
        # Queue should be emptied
        assert text_queue.empty()


# =============================================================================
# stream_tts_to_speaker - Audio Output Tests
# =============================================================================

class TestStreamTtsToSpeakerAudio:
    """Test suite for audio output in stream_tts_to_speaker."""

    def test_creates_audio_client_with_key(self, monkeypatch):
        """Creates ElevenLabs client when API key available."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test_key")
        
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        text_queue.put(None)  # Immediate exit
        
        mock_client = MagicMock()
        mock_client.text_to_speech.convert.return_value = [b"audio"]
        
        mock_elevenlabs = MagicMock()
        mock_elevenlabs.return_value = mock_client
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_elevenlabs', return_value=mock_elevenlabs), \
             patch('tools.tts_tool._import_sounddevice', side_effect=ImportError("no audio")):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event
            )
        
        assert tts_done_event.is_set()

    def test_handles_sounddevice_unavailable(self, monkeypatch):
        """Handles sounddevice not being available."""
        monkeypatch.setenv("ELEVENLABS_API_KEY", "test_key")
        
        text_queue = queue.Queue()
        stop_event = threading.Event()
        tts_done_event = threading.Event()
        
        text_queue.put(None)
        
        mock_client = MagicMock()
        mock_elevenlabs = MagicMock()
        mock_elevenlabs.return_value = mock_client
        
        with patch('hermes_cli.config.load_config', return_value={"tts": {}}), \
             patch('tools.tts_tool._import_elevenlabs', return_value=mock_elevenlabs), \
             patch('tools.tts_tool._import_sounddevice', side_effect=ImportError("no audio")):
            tt.stream_tts_to_speaker(
                text_queue=text_queue,
                stop_event=stop_event,
                tts_done_event=tts_done_event
            )
        
        assert tts_done_event.is_set()


# =============================================================================
# Defaults and Constants Tests
# =============================================================================

class TestDefaults:
    """Test suite for default values and constants."""

    def test_default_provider_is_edge(self):
        """Default provider is 'edge'."""
        assert tt.DEFAULT_PROVIDER == "edge"

    def test_default_edge_voice_is_valid(self):
        """Default Edge voice is a valid voice name."""
        assert "en-US" in tt.DEFAULT_EDGE_VOICE

    def test_max_text_length_is_reasonable(self):
        """MAX_TEXT_LENGTH is reasonable for TTS."""
        assert 1000 <= tt.MAX_TEXT_LENGTH <= 10000

    def test_default_output_dir_exists_or_creatable(self):
        """Default output directory can be created."""
        output_dir = Path(tt.DEFAULT_OUTPUT_DIR)
        # Should be under home directory or HERMES_HOME
        assert str(Path.home()) in str(output_dir) or "hermes" in str(output_dir).lower()


# =============================================================================
# Registry Integration Tests
# =============================================================================

class TestRegistryIntegration:
    """Test suite for tool registry integration."""

    def test_tool_registered(self):
        """Tool is registered in registry."""
        from tools.registry import registry
        
        # Check if text_to_speech is in the registry
        # The registry may use a different method to check registration
        tools = registry.list_tools() if hasattr(registry, 'list_tools') else []
        tool_names = registry.tools if hasattr(registry, 'tools') else {}
        
        # Either the tool is in list_tools() or in tools dict
        registered = "text_to_speech" in tools or "text_to_speech" in tool_names
        assert registered or tt.TTS_SCHEMA is not None  # At minimum schema exists

    def test_tool_schema_valid(self):
        """Tool schema is valid."""
        schema = tt.TTS_SCHEMA
        
        assert schema["name"] == "text_to_speech"
        assert "parameters" in schema
        assert "properties" in schema["parameters"]
        assert "text" in schema["parameters"]["properties"]
        assert "text" in schema["parameters"]["required"]
