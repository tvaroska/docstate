import pytest
from uuid import uuid4
from typing import List, Callable, AsyncGenerator
from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore
import os


@pytest.fixture(scope="session")
def document_states():
    """
    Create document states for testing.
    
    Session scope since these are immutable and can be shared across all tests.
    """
    return {
        "link": DocumentState(name="link"),
        "download": DocumentState(name="download"),
        "chunk": DocumentState(name="chunk"),
        "embed": DocumentState(name="embed")
    }


@pytest.fixture(scope="session")
def mock_process_functions():
    """
    Create mock process functions for testing.
    
    Session scope since these are pure functions without side effects.
    """
    async def mock_download(doc):
        return Document(
            content="Downloaded content",
            media_type="text/plain",
            state="download"
        )
    
    async def mock_chunk(doc):
        return [
            Document(content="Chunk 1", media_type="text/plain", state="chunk"),
            Document(content="Chunk 2", media_type="text/plain", state="chunk")
        ]
    
    async def mock_embed(doc):
        return Document(
            content="Embedded vector",
            media_type="application/vector",
            state="embed"
        )
        
    return {
        "download": mock_download,
        "chunk": mock_chunk,
        "embed": mock_embed
    }


@pytest.fixture(scope="session")
def transitions(document_states, mock_process_functions):
    """
    Create transitions for testing.
    
    Session scope since these are created once and reused across all tests.
    They depend on document_states and mock_process_functions.
    """
    return {
        "download": Transition(
            from_state=document_states["link"],
            to_state=document_states["download"],
            process_func=mock_process_functions["download"]
        ),
        "chunk": Transition(
            from_state=document_states["download"],
            to_state=document_states["chunk"],
            process_func=mock_process_functions["chunk"]
        ),
        "embed": Transition(
            from_state=document_states["chunk"],
            to_state=document_states["embed"],
            process_func=mock_process_functions["embed"]
        )
    }


@pytest.fixture(scope="session")
def document_type(document_states, transitions):
    """
    Create a document type for testing.
    
    Session scope since it is constructed from document_states and transitions,
    both of which have session scope.
    """
    return DocumentType(
        states=list(document_states.values()),
        transitions=list(transitions.values())
    )


@pytest.fixture(scope="function")
def document_id():
    """
    Generate a document ID for testing.
    
    Function scope since each test should have a unique ID.
    """
    return str(uuid4())


@pytest.fixture(scope="function")
def root_document():
    """
    Create a root document for testing.
    
    Function scope since tests might modify the document.
    """
    return Document(
        media_type="text/plain",
        state="link"
    )


@pytest.fixture(scope="function")
def child_document(root_document):
    """
    Create a child document for testing.
    
    Function scope since it depends on root_document which has function scope.
    """
    return Document(
        media_type="text/plain",
        state="download",
        parent_id=root_document.id
    )


@pytest.fixture(scope="function")
def document_with_children():
    """
    Create a document with children for testing.
    
    Function scope since tests might modify the document.
    """
    return Document(
        media_type="text/plain",
        state="download",
        children=[str(uuid4()), str(uuid4())]
    )


@pytest.fixture(scope="function")
def document_with_all_fields(document_id):
    """
    Create a document with all fields populated for testing.
    
    Function scope since tests might modify the document.
    """
    return Document(
        id=document_id,
        content="Example content",
        media_type="text/plain",
        state="download",
        parent_id=str(uuid4()),
        children=[str(uuid4()), str(uuid4())],
        metadata={"source": "test", "timestamp": "2025-04-10"}
    )


# DocStore Fixtures

@pytest.fixture(scope="function")
def sqlite_connection_string():
    """
    Provide a connection string for an in-memory SQLite database.
    
    Function scope to ensure each test gets a fresh database.
    """
    return "sqlite:///:memory:"


@pytest.fixture(scope="function")
def docstore(sqlite_connection_string, document_type):
    """
    Create a DocStore instance for testing.
    
    Function scope to ensure each test gets a fresh DocStore with a clean database.
    """
    store = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
    return store


@pytest.fixture(scope="function")
def docstore_with_docs(docstore, root_document, document_with_children):
    """
    Create a DocStore with pre-populated documents for testing.
    
    Function scope since it depends on docstore which has function scope.
    """
    docstore.add(root_document)
    docstore.add(document_with_children)
    return docstore
