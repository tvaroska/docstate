import pytest
import asyncio
from uuid import uuid4
from typing import List, Optional, Dict, Any, Union
from sqlalchemy.exc import SQLAlchemyError

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore, DocumentModel

class TestDocStore:
    """Unit tests for the DocStore class."""

    def test_init(self, sqlite_connection_string, document_type):
        """Test DocStore initialization."""
        # Test with document type
        store1 = DocStore(connection_string=sqlite_connection_string, document_type=document_type)
        assert store1.document_type == document_type

        # Test without document type
        store2 = DocStore(connection_string=sqlite_connection_string)
        assert store2.document_type is None

        # Test setting document type later
        store2.set_document_type(document_type)
        assert store2.document_type == document_type

    def test_add_document(self, docstore, root_document):
        """Test adding a document to the store."""
        # Add document
        doc_id = docstore.add(root_document)
        
        # Verify that the ID was returned
        assert doc_id is not None
        assert doc_id == root_document.id
        
        # Retrieve and verify document
        retrieved_doc = docstore.get(id=doc_id)
        assert retrieved_doc is not None
        assert retrieved_doc.id == doc_id
        assert retrieved_doc.state == root_document.state
        assert retrieved_doc.content_type == root_document.content_type

    def test_add_document_generates_id(self, docstore):
        """Test that add generates an ID if document doesn't have one."""
        # Create document without explicitly providing an ID
        # The pydantic model will auto-generate an ID with the default_factory
        doc = Document(content_type="text", state="link")
        original_id = doc.id
        
        # Add document to store - the DocStore should use the auto-generated ID
        doc_id = docstore.add(doc)
        
        # Verify that an ID was generated
        assert doc_id is not None
        assert len(doc_id) > 0
        
        # Verify document was saved with that ID
        retrieved_doc = docstore.get(id=doc_id)
        assert retrieved_doc is not None
        assert retrieved_doc.id == doc_id

    def test_get_document_by_id(self, docstore_with_docs, root_document):
        """Test retrieving a document by ID."""
        # Get document
        doc = docstore_with_docs.get(id=root_document.id)
        
        # Verify document
        assert doc is not None
        assert doc.id == root_document.id
        assert doc.state == root_document.state
        assert doc.content_type == root_document.content_type
        
        # Get non-existent document
        non_existent_doc = docstore_with_docs.get(id=str(uuid4()))
        assert non_existent_doc is None

    def test_get_documents_by_state(self, docstore_with_docs, root_document):
        """Test retrieving documents by state."""
        # Add another document with same state for testing multiple retrieval
        same_state_doc = Document(content_type="text", state=root_document.state)
        docstore_with_docs.add(same_state_doc)
        
        # Get documents by state
        docs = docstore_with_docs.get(state=root_document.state)
        
        # Verify documents
        assert isinstance(docs, list)
        assert len(docs) == 2
        assert any(d.id == root_document.id for d in docs)
        assert any(d.id == same_state_doc.id for d in docs)
        
        # Get documents by non-existent state
        non_existent_docs = docstore_with_docs.get(state="non-existent")
        assert isinstance(non_existent_docs, list)
        assert len(non_existent_docs) == 0

    def test_get_all_documents(self, docstore_with_docs, root_document, document_with_children):
        """Test retrieving all documents."""
        # Get all documents
        docs = docstore_with_docs.get()
        
        # Verify documents
        assert isinstance(docs, list)
        assert len(docs) == 2
        assert any(d.id == root_document.id for d in docs)
        assert any(d.id == document_with_children.id for d in docs)

    def test_delete_document(self, docstore_with_docs, root_document):
        """Test deleting a document."""
        # Verify document exists
        doc = docstore_with_docs.get(id=root_document.id)
        assert doc is not None
        
        # Delete document
        docstore_with_docs.delete(root_document.id)
        
        # Verify document no longer exists
        deleted_doc = docstore_with_docs.get(id=root_document.id)
        assert deleted_doc is None
        
        # Deleting non-existent document should not raise error
        docstore_with_docs.delete(str(uuid4()))

    @pytest.mark.asyncio
    async def test_next_single_document(self, docstore, document_type, root_document):
        """Test processing a document to its next state - single document case."""
        # Add document
        docstore.add(root_document)
        
        # Process to next state
        next_doc = await docstore.next(root_document)
        
        # Verify next document
        assert next_doc is not None
        assert next_doc.state == "download"  # Based on mock_process_functions
        assert next_doc.parent_id == root_document.id
        
        # Verify parent updated
        parent = docstore.get(id=root_document.id)
        assert parent is not None
        assert next_doc.id in parent.children

    @pytest.mark.asyncio
    async def test_next_multiple_documents(self, docstore, document_type):
        """Test processing a document to its next state - multiple documents case (chunking)."""
        # Create and add download document
        download_doc = Document(content_type="text", state="download", content="Test content")
        docstore.add(download_doc)
        
        # Process to next state (chunk) - should return multiple documents
        next_docs = await docstore.next(download_doc)
        
        # Verify next documents
        assert isinstance(next_docs, list)
        assert len(next_docs) == 2  # Based on mock_process_functions
        assert all(d.state == "chunk" for d in next_docs)
        assert all(d.parent_id == download_doc.id for d in next_docs)
        
        # Verify parent updated
        parent = docstore.get(id=download_doc.id)
        assert parent is not None
        for doc in next_docs:
            assert doc.id in parent.children

    @pytest.mark.asyncio
    async def test_next_no_document_type(self, sqlite_connection_string):
        """Test that next raises an error when document_type is not set."""
        # Create docstore without document type
        docstore = DocStore(connection_string=sqlite_connection_string)
        
        # Create document
        doc = Document(content_type="text", state="link")
        docstore.add(doc)
        
        # Attempt to process without document type
        with pytest.raises(ValueError, match="Document type not set for DocStore"):
            await docstore.next(doc)

    @pytest.mark.asyncio
    async def test_next_no_valid_transitions(self, docstore, document_type):
        """Test that next raises an error when there are no valid transitions."""
        # Create document in a final state
        final_state = document_type.final[0]
        doc = Document(content_type="text", state=final_state.name)
        docstore.add(doc)
        
        # Attempt to process from final state
        with pytest.raises(ValueError, match=f"No valid transitions from state '{final_state.name}'"):
            await docstore.next(doc)

    def test_metadata_persistence(self, docstore):
        """Test that document metadata is properly persisted and retrieved."""
        # Create document with metadata
        metadata = {"key1": "value1", "key2": 123, "key3": {"nested": "value"}}
        doc = Document(content_type="text", state="link", metadata=metadata)
        
        # Add document
        doc_id = docstore.add(doc)
        
        # Retrieve document
        retrieved_doc = docstore.get(id=doc_id)
        
        # Verify metadata
        assert retrieved_doc.metadata == metadata
        assert retrieved_doc.metadata["key1"] == "value1"
        assert retrieved_doc.metadata["key2"] == 123
        assert retrieved_doc.metadata["key3"]["nested"] == "value"


if __name__ == "__main__":
    pytest.main()
