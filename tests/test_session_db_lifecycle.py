"""Tests for SessionDB connection lifecycle management.

Tests cover:
- Explicit close() method
- Context manager support (__enter__/__exit__)
- Multiple close() safety
- __del__ warning for unclosed connections
"""

import gc
import sqlite3
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from hermes_state import SessionDB


class TestSessionDBClose:
    """Tests for explicit close() method."""

    def test_close_closes_connection(self, tmp_path: Path):
        """close() should close the underlying SQLite connection."""
        db_path = tmp_path / "test.db"
        db = SessionDB(db_path)
        
        # Verify connection is active
        assert db._conn is not None
        assert not db._closed
        
        db.close()
        
        assert db._closed
        # Connection should be closed - executing should fail
        with pytest.raises(sqlite3.ProgrammingError):
            db._conn.execute("SELECT 1")

    def test_close_is_idempotent(self, tmp_path: Path):
        """Calling close() multiple times should be safe."""
        db_path = tmp_path / "test.db"
        db = SessionDB(db_path)
        
        db.close()
        db.close()  # Should not raise
        db.close()  # Should not raise
        
        assert db._closed

    def test_close_with_lock_contention(self, tmp_path: Path):
        """close() should work even if lock is held elsewhere."""
        db_path = tmp_path / "test.db"
        db = SessionDB(db_path)
        
        # This simulates a scenario where close() is called
        # while another thread might be using the lock
        db.close()
        
        assert db._closed


class TestSessionDBContextManager:
    """Tests for __enter__/__exit__ context manager support."""

    def test_context_manager_closes_on_exit(self, tmp_path: Path):
        """Connection should be closed when exiting context manager."""
        db_path = tmp_path / "test.db"
        
        with SessionDB(db_path) as db:
            assert not db._closed
            # Perform some operation
            db.create_session("test-session", "cli")
        
        # Connection should be closed after exiting
        assert db._closed

    def test_context_manager_closes_on_exception(self, tmp_path: Path):
        """Connection should be closed even if exception is raised."""
        db_path = tmp_path / "test.db"
        
        with pytest.raises(ValueError):
            with SessionDB(db_path) as db:
                db.create_session("test-session", "cli")
                raise ValueError("test error")
        
        # Connection should still be closed
        assert db._closed

    def test_context_manager_returns_self(self, tmp_path: Path):
        """__enter__ should return the SessionDB instance."""
        db_path = tmp_path / "test.db"
        
        with SessionDB(db_path) as db:
            assert isinstance(db, SessionDB)


class TestSessionDBDestructor:
    """Tests for __del__ behavior."""

    def test_del_warns_on_unclosed_connection(self, tmp_path: Path):
        """__del__ should warn if connection was not explicitly closed."""
        db_path = tmp_path / "test.db"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            # Create and immediately discard without closing
            db = SessionDB(db_path)
            db_id = id(db)
            del db
            gc.collect()  # Force garbage collection
            
            # Should have triggered a ResourceWarning
            resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(resource_warnings) == 1
            assert "not explicitly closed" in str(resource_warnings[0].message)

    def test_del_no_warn_on_closed_connection(self, tmp_path: Path):
        """__del__ should NOT warn if connection was properly closed."""
        db_path = tmp_path / "test.db"
        
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            
            db = SessionDB(db_path)
            db.close()
            del db
            gc.collect()
            
            # Should not have any ResourceWarning
            resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
            assert len(resource_warnings) == 0


class TestSessionDBOperationsAfterClose:
    """Tests for behavior when operations are attempted after close."""

    def test_create_session_after_close_raises(self, tmp_path: Path):
        """create_session should fail after close()."""
        db_path = tmp_path / "test.db"
        db = SessionDB(db_path)
        db.close()
        
        with pytest.raises(sqlite3.ProgrammingError):
            db.create_session("test-session", "cli")

    def test_get_session_after_close_raises(self, tmp_path: Path):
        """get_session should fail after close()."""
        db_path = tmp_path / "test.db"
        db = SessionDB(db_path)
        db.close()
        
        with pytest.raises(sqlite3.ProgrammingError):
            db.get_session("test-session")


class TestSessionDBMultipleInstances:
    """Tests for multiple SessionDB instances on same database."""

    def test_multiple_readers_wal_mode(self, tmp_path: Path):
        """Multiple SessionDB instances should work with WAL mode."""
        db_path = tmp_path / "test.db"
        
        # Create first instance and add data
        with SessionDB(db_path) as db1:
            db1.create_session("session-1", "cli")
        
        # Create second instance and read data
        with SessionDB(db_path) as db2:
            session = db2.get_session("session-1")
            assert session is not None
            assert session["id"] == "session-1"

    def test_concurrent_instances(self, tmp_path: Path):
        """Concurrent SessionDB instances should work correctly."""
        db_path = tmp_path / "test.db"
        
        with SessionDB(db_path) as db1:
            with SessionDB(db_path) as db2:
                db1.create_session("session-1", "cli")
                db2.create_session("session-2", "cli")
                
                # Both should be able to read
                assert db1.get_session("session-1") is not None
                assert db2.get_session("session-2") is not None
