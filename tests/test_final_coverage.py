import asyncio
from typing import List, Optional

import pytest

from docstate.docstate import DocStore
from docstate.document import Document, DocumentState, DocumentType, Transition


@pytest.fixture
def sqlite_connection_string():
    return "sqlite:///:memory:"


@pytest.fixture
def document_states():
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    error = DocumentState(name="error")
    return link, download, error


@pytest.fixture
def process_func():
    async def simple_process(doc: Document) -> Document:
        return Document(
            content="Processed content", state="download", metadata={"processed": True}
        )

    return simple_process


@pytest.fixture
def document_type(document_states, process_func):
    link, download, error = document_states
    return DocumentType(
        states=[link, download, error],
        transitions=[
            Transition(from_state=link, to_state=download, process_func=process_func)
        ],
    )


class TestFinalCoverage:
    """Final tests to achieve 100% coverage."""

    def test_add_with_default_id(self, sqlite_connection_string, document_type):
        """Test add() with a document using the default auto-generated ID."""
        docstore = DocStore(
            connection_string=sqlite_connection_string, document_type=document_type
        )

        # Create document without specifying an ID (will use the default)
        doc = Document(content="Test content", state="link")

        # Add document, which should auto-generate an ID
        doc_id = docstore.add(doc)

        # Verify document was added with a generated ID
        assert doc_id is not None
        assert len(doc_id) > 0

        # Retrieve the document and verify content
        retrieved = docstore.get(id=doc_id)
        assert retrieved is not None
        assert retrieved.content == "Test content"

    def test_add_list_with_default_ids(self, sqlite_connection_string, document_type):
        """Test add() with a list of documents using default auto-generated IDs."""
        docstore = DocStore(
            connection_string=sqlite_connection_string, document_type=document_type
        )

        # Create documents without specifying IDs (will use the defaults)
        docs = [
            Document(content="Content 1", state="link"),
            Document(content="Content 2", state="link"),
        ]

        # Add documents as a list, which should auto-generate IDs
        doc_ids = docstore.add(docs)

        # Verify we got back a list of generated IDs
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == 2
        assert all(id is not None and len(id) > 0 for id in doc_ids)

        # Retrieve the documents and verify content
        for i, doc_id in enumerate(doc_ids):
            retrieved = docstore.get(id=doc_id)
            assert retrieved is not None
            assert retrieved.content == f"Content {i+1}"

    def test_get_by_nonexistent_state(self, sqlite_connection_string, document_type):
        """Test get() with a state that has no documents."""
        docstore = DocStore(
            connection_string=sqlite_connection_string, document_type=document_type
        )

        # Add a document in a known state
        doc = Document(content="Test content", state="link")
        docstore.add(doc)

        # Get by a state that doesn't exist in the database
        results = docstore.get(state="nonexistent_state")

        # Should return an empty list
        assert isinstance(results, list)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_process_single_document_with_list_result(
        self, sqlite_connection_string, document_states
    ):
        """Test _process_single_document with a process function that returns a list."""
        link, download, _ = document_states

        # Define a process function that returns a list of documents
        async def list_process(doc: Document) -> List[Document]:
            return [
                Document(content="Result 1", state="download"),
                Document(content="Result 2", state="download"),
            ]

        # Create document type with list-returning transition
        doc_type = DocumentType(
            states=[link, download],
            transitions=[
                Transition(
                    from_state=link, to_state=download, process_func=list_process
                )
            ],
        )

        docstore = DocStore(
            connection_string=sqlite_connection_string, document_type=doc_type
        )

        # Create document
        doc = Document(content="Test content", state="link")
        docstore.add(doc)

        # Call next, which should create multiple child documents
        results = await docstore.next(doc)

        # Verify multiple documents were created
        assert len(results) == 2
        assert all(doc.state == "download" for doc in results)
        assert "Result 1" in [doc.content for doc in results]
        assert "Result 2" in [doc.content for doc in results]

        # Verify the parent-child relationships
        parent = docstore.get(id=doc.id)
        assert parent.has_children
        assert len(parent.children) == 2
