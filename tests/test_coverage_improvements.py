import pytest
import asyncio
from typing import List

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore


@pytest.fixture
def sqlite_connection_string():
    return "sqlite:///:memory:"


@pytest.fixture
def document_states():
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    error = DocumentState(name="custom_error")
    return link, download, error


@pytest.fixture
def process_func():
    async def simple_process(doc: Document) -> Document:
        return Document(
            content="Processed content",
            state="download",
            metadata={"processed": True}
        )
    return simple_process


@pytest.fixture
def document_type(document_states, process_func):
    link, download, error = document_states
    return DocumentType(
        states=[link, download, error],
        transitions=[
            Transition(from_state=link, to_state=download, process_func=process_func)
        ]
    )


class TestCoverageImprovements:
    """Tests specifically aimed at improving code coverage."""

    def test_context_manager(self, sqlite_connection_string, document_type):
        """Test the context manager for DocStore."""
        with DocStore(connection_string=sqlite_connection_string, document_type=document_type) as docstore:
            # Use the docstore inside the context manager
            doc = Document(content="Test content", state="link")
            docstore.add(doc)
            
            # Verify document was added
            retrieved = docstore.get(id=doc.id)
            assert retrieved is not None
            assert retrieved.content == "Test content"
        
        # The context manager should have disposed of the engine

    def test_add_list_of_documents(self, sqlite_connection_string, document_type):
        """Test adding a list of documents."""
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
        
        # Create documents with explicit and auto-generated IDs
        docs = [
            Document(id="doc1", content="Content 1", state="link"),
            Document(content="Content 2", state="link")  # ID will be auto-generated
        ]
        
        # Add documents as a list
        doc_ids = docstore.add(docs)
        
        # Verify we got back a list of IDs
        assert isinstance(doc_ids, list)
        assert len(doc_ids) == 2
        assert "doc1" in doc_ids
        
        # Verify documents were added
        all_docs = docstore.get()
        assert len(all_docs) == 2
    
    def test_get_all_documents(self, sqlite_connection_string, document_type):
        """Test retrieving all documents when no ID or state is provided."""
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
        
        # Add multiple documents
        docs = [
            Document(id="doc1", content="Content 1", state="link"),
            Document(id="doc2", content="Content 2", state="download")
        ]
        docstore.add(docs)
        
        # Get all documents without specifying ID or state
        all_docs = docstore.get()
        
        # Verify all documents were retrieved
        assert isinstance(all_docs, list)
        assert len(all_docs) == 2
        assert {doc.id for doc in all_docs} == {"doc1", "doc2"}
    
    def test_delete_nonexistent_document(self, sqlite_connection_string, document_type):
        """Test deleting a document that doesn't exist."""
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
        
        # Try to delete a document that doesn't exist
        docstore.delete("nonexistent_id")
        
        # No exception should be raised
    
    @pytest.mark.asyncio
    async def test_next_with_final_state(self, sqlite_connection_string, document_type):
        """Test next() method with a document already in a final state."""
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
        
        # Create a document in a state with no outgoing transitions (final state)
        doc = Document(content="Final content", state="download")
        docstore.add(doc)
        
        # Call next on a document in final state
        results = await docstore.next(doc)
        
        # Should return an empty list (no new documents created)
        assert results == []
    
    @pytest.mark.asyncio
    async def test_next_with_invalid_input(self, sqlite_connection_string, document_type):
        """Test next() method with invalid input in a list."""
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
        
        # Create a valid document
        doc = Document(content="Valid content", state="link")
        
        # Create a list with a valid document and an invalid item
        mixed_input = [doc, "not_a_document"]
        
        # Call next on mixed input (should log a warning but not fail)
        results = await docstore.next(mixed_input)
        
        # Should process the valid document
        assert len(results) == 1
    
    @pytest.mark.asyncio
    async def test_next_with_error(self, sqlite_connection_string, document_states):
        """Test next() method with a processing function that raises an error."""
        link, download, error = document_states
        
        # Create a failing process function
        async def failing_process(doc: Document) -> Document:
            raise ValueError("Simulated error")
        
        # Create document type with failing transition
        doc_type = DocumentType(
            states=[link, download, error],
            transitions=[
                Transition(from_state=link, to_state=download, process_func=failing_process)
            ]
        )
        
        # Create DocStore with custom error state
        docstore = DocStore(
            connection_string=sqlite_connection_string, 
            document_type=doc_type,
            error_state="custom_error"
        )
        
        # Create document
        doc = Document(content="Will fail", state="link")
        docstore.add(doc)
        
        # Process document (should create error document)
        results = await docstore.next(doc)
        
        # Should return error document
        assert len(results) == 1
        assert results[0].state == "custom_error"
        assert "Simulated error" in results[0].metadata["error"]
    
    @pytest.mark.asyncio
    async def test_finish_with_empty_result(self, sqlite_connection_string, document_type):
        """Test finish() method with a scenario that produces no new documents."""
        # Create a modified document type with no transitions
        link, download, _ = document_type.states
        empty_type = DocumentType(
            states=[link, download],
            transitions=[]  # No transitions
        )
        
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=empty_type)
        
        # Create a document
        doc = Document(content="No transitions", state="link")
        
        # Finish should still return documents in final states (which is all states in this case)
        final_docs = await docstore.finish(doc)
        
        # Should contain the original document since it's in a "final" state (has no transitions)
        assert len(final_docs) == 1
        assert final_docs[0].id == doc.id
