"""
Global pytest configuration for the docstate test suite.

This file contains common pytest configuration and hooks used across all test files.
"""

import os
import pytest

# Import all fixtures to make them available for tests
from tests.fixtures import (
    document_state, document_states, mock_process_func, mock_process_func_with_children, 
    mock_process_func_with_error, transition, transitions, document_type, document, 
    documents, document_with_children, async_sqlite_db_path, async_docstore, mock_httpx_client, 
    mock_splitter, mock_vectorstore
)


def pytest_configure(config):
    """Configure pytest for the test suite."""
    # Register marks
    config.addinivalue_line("markers", "asyncio: mark test as requiring asyncio")


def pytest_collection_modifyitems(items):
    """Add asyncio mark to all async test functions."""
    for item in items:
        if item.name.startswith("test_") and "async" in item.function.__code__.co_names:
            item.add_marker(pytest.mark.asyncio)
