import os
import pytest
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import Base, DocStore, DocumentModel


@pytest.fixture
def document_state():
    """Return a simple document state."""
    return DocumentState(name="test_state")


@pytest.fixture
def document_states():
    """Return a list of document states for the state machine."""
    return [
        DocumentState(name="link"),
        DocumentState(name="download"),
        DocumentState(name="chunk"),
        DocumentState(name="embed"),
        DocumentState(name="error")
    ]


@pytest.fixture
def mock_process_func():
    """Return a mock async processing function."""
    async def process_mock(doc: Document) -> Document:
        return Document(
            state="processed",
            content="Processed content",
            media_type="text/plain",
            metadata={"processed": True}
        )
    return AsyncMock(side_effect=process_mock)


@pytest.fixture
def mock_process_func_with_children():
    """Return a mock async processing function that returns multiple documents."""
    async def process_mock(doc: Document) -> List[Document]:
        return [
            Document(
                state="child1",
                content="Child 1 content",
                media_type="text/plain",
                metadata={"child": 1}
            ),
            Document(
                state="child2",
                content="Child 2 content",
                media_type="text/plain",
                metadata={"child": 2}
            )
        ]
    return AsyncMock(side_effect=process_mock)


@pytest.fixture
def mock_process_func_with_error():
    """Return a mock async processing function that raises an error."""
    async def process_mock(doc: Document) -> Document:
        raise ValueError("Test process error")
    return AsyncMock(side_effect=process_mock)


@pytest.fixture
def transition(document_states, mock_process_func):
    """Return a simple transition between states."""
    return Transition(
        from_state=document_states[0],
        to_state=document_states[1],
        process_func=mock_process_func
    )


@pytest.fixture
def transitions(document_states, mock_process_func, mock_process_func_with_children):
    """Return a list of transitions for the state machine."""
    return [
        Transition(
            from_state=document_states[0],  # link
            to_state=document_states[1],    # download
            process_func=mock_process_func
        ),
        Transition(
            from_state=document_states[1],  # download
            to_state=document_states[2],    # chunk
            process_func=mock_process_func_with_children
        ),
        Transition(
            from_state=document_states[2],  # chunk
            to_state=document_states[3],    # embed
            process_func=mock_process_func
        )
    ]


@pytest.fixture
def document_type(document_states, transitions):
    """Return a document type with states and transitions."""
    # Explicitly ensure 'embed' is a final state by not having transitions from it
    return DocumentType(
        states=document_states,
        transitions=transitions
    )


@pytest.fixture
def document():
    """Return a simple document."""
    return Document(
        state="link",
        content="Test content",
        media_type="text/plain",
        url="https://example.com/test",
        metadata={"test": True}
    )


@pytest.fixture
def documents():
    """Return a list of documents."""
    return [
        Document(
            state="link",
            content="Test content 1",
            media_type="text/plain",
            url="https://example.com/test1",
            metadata={"test": 1}
        ),
        Document(
            state="link",
            content="Test content 2",
            media_type="text/plain",
            url="https://example.com/test2",
            metadata={"test": 2}
        )
    ]


@pytest.fixture
def document_with_children():
    """Return a document with children."""
    doc = Document(
        state="download",
        content="Parent content",
        media_type="text/plain",
        metadata={"parent": True}
    )
    child1 = Document(
        state="chunk",
        content="Child 1 content",
        media_type="text/plain",
        parent_id=doc.id,
        metadata={"child": 1}
    )
    child2 = Document(
        state="chunk",
        content="Child 2 content",
        media_type="text/plain",
        parent_id=doc.id,
        metadata={"child": 2}
    )
    doc.add_child(child1.id)
    doc.add_child(child2.id)
    return doc, [child1, child2]


@pytest.fixture
def sqlite_db_path(request):
    """Return a path to an in-memory SQLite database."""
    # Use in-memory SQLite database for tests
    db_path = "sqlite:///:memory:"
    
    yield db_path
    
    # No cleanup required for in-memory databases


@pytest.fixture
def docstore(sqlite_db_path, document_type):
    """Return a DocStore with SQLite database."""
    # Ensure the database exists and tables are created
    engine = create_engine(sqlite_db_path)
    Base.metadata.create_all(engine)
    
    # Create DocStore instance
    store = DocStore(connection_string=sqlite_db_path, document_type=document_type)

    yield store
    
    # Clean up
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def mock_httpx_client():
    """Return a mock httpx client for testing download_document."""
    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.text = "Downloaded content"
        mock_response.raise_for_status = MagicMock()
        
        mock_client_instance = AsyncMock()
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.get.return_value = mock_response
        
        mock_client.return_value = mock_client_instance
        yield mock_client


@pytest.fixture
def mock_splitter():
    """Return a mock RecursiveCharacterTextSplitter for testing chunk_document."""
    with patch("langchain_text_splitters.RecursiveCharacterTextSplitter") as mock_splitter:
        mock_splitter_instance = MagicMock()
        mock_splitter_instance.split_text.return_value = ["Chunk 1", "Chunk 2"]
        mock_splitter.return_value = mock_splitter_instance
        yield mock_splitter


@pytest.fixture
def mock_vectorstore():
    """Return a mock vector store for testing embed_document."""
    # Patch FAISS instead of PGVector for SQLite compatibility
    with patch("langchain_community.vectorstores.faiss.FAISS") as mock_vectorstore:
        mock_vectorstore_instance = MagicMock()
        mock_vectorstore_instance.add_texts.return_value = ["embedding_id"]
        mock_vectorstore.from_texts.return_value = mock_vectorstore_instance
        yield mock_vectorstore
