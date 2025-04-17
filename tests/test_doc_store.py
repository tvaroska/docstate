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
        assert retrieved_doc.media_type == root_document.media_type

    def test_add_document_generates_id(self, docstore):
        """Test that add generates an ID if document doesn't have one."""
        # Create document without explicitly providing an ID
        # The pydantic model will auto-generate an ID with the default_factory
        doc = Document(media_type="text/plain", state="link")
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
        assert doc.media_type == root_document.media_type
        
        # Get non-existent document
        non_existent_doc = docstore_with_docs.get(id=str(uuid4()))
        assert non_existent_doc is None

    def test_get_documents_by_state(self, docstore_with_docs, root_document):
        """Test retrieving documents by state."""
        # Add another document with same state for testing multiple retrieval
        same_state_doc = Document(media_type="text/plain", state=root_document.state)
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
        next_docs_list = await docstore.next(root_document) # next now returns a list

        # Verify next document list
        assert isinstance(next_docs_list, list)
        assert len(next_docs_list) == 1 # Should contain one new document
        next_doc = next_docs_list[0] # Get the single document from the list

        assert next_doc is not None
        assert next_doc.state == "download"  # Based on mock_process_functions in conftest.py
        assert next_doc.parent_id == root_document.id

        # Verify parent updated
        parent = docstore.get(id=root_document.id)
        assert parent is not None
        assert next_doc.id in parent.children, f"Child ID {next_doc.id} not found in parent children {parent.children}"

    @pytest.mark.asyncio
    async def test_next_multiple_documents(self, docstore, document_type):
        """Test processing a document to its next state - multiple documents case (chunking)."""
        # Create and add download document
        download_doc = Document(media_type="text/plain", state="download", content="Test content")
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
        doc = Document(media_type="text/plain", state="link")
        docstore.add(doc)
        
        # Attempt to process without document type
        with pytest.raises(ValueError, match="Document type not set for DocStore"):
            await docstore.next(doc)

    @pytest.mark.asyncio
    async def test_next_no_valid_transitions(self, docstore, document_type):
        """Test that next raises an error when there are no valid transitions."""
        # Create document in a final state
        final_state = document_type.final[0]
        doc = Document(media_type="text/plain", state=final_state.name)
        docstore.add(doc)
        
        # Attempt to process from final state - should return an empty list now
        result_docs = await docstore.next(doc)
        assert isinstance(result_docs, list)
        assert len(result_docs) == 0

    @pytest.mark.asyncio
    async def test_next_with_list_input(self, docstore, document_type):
        """Test processing a list of documents using the next method."""
        # Create documents
        doc1 = Document(media_type="application/uri", state="link", content="http://example.com/1")
        doc2 = Document(media_type="application/uri", state="link", content="http://example.com/2")
        doc3 = Document(media_type="text/plain", state="download", content="Already downloaded") # This will transition differently
        docstore.add(doc1)
        docstore.add(doc2)
        docstore.add(doc3)

        # Process list of documents
        input_docs = [doc1, doc2, doc3]
        processed_docs = await docstore.next(input_docs)

        # Verify results - expecting 2 'download' and 2 'chunk' docs (based on mock funcs)
        assert isinstance(processed_docs, list)
        assert len(processed_docs) == 4 # 2 from doc1/doc2 (link->download) + 2 from doc3 (download->chunk)

        download_docs = [d for d in processed_docs if d.state == "download"]
        chunk_docs = [d for d in processed_docs if d.state == "chunk"]

        assert len(download_docs) == 2
        assert len(chunk_docs) == 2

        # Verify parentage for download docs
        assert all(d.parent_id == doc1.id or d.parent_id == doc2.id for d in download_docs)
        # Verify parentage for chunk docs
        assert all(d.parent_id == doc3.id for d in chunk_docs)

        # Verify parents were updated
        parent1 = docstore.get(id=doc1.id)
        parent2 = docstore.get(id=doc2.id)
        parent3 = docstore.get(id=doc3.id)
        assert parent1 and len(parent1.children) == 1 # One download child
        assert parent2 and len(parent2.children) == 1 # One download child
        assert parent3 and len(parent3.children) == 2 # Two chunk children


    def test_metadata_persistence(self, docstore):
        """Test that document metadata is properly persisted and retrieved."""
        # Create document with metadata
        metadata = {"key1": "value1", "key2": 123, "key3": {"nested": "value"}}
        doc = Document(media_type="text/plain", state="link", metadata=metadata)
        
        # Add document
        doc_id = docstore.add(doc)
        
        # Retrieve document
        retrieved_doc = docstore.get(id=doc_id)
        
        # Verify metadata
        assert retrieved_doc.metadata == metadata
        assert retrieved_doc.metadata["key1"] == "value1"
        assert retrieved_doc.metadata["key2"] == 123
        assert retrieved_doc.metadata["key3"]["nested"] == "value"

    def test_update_with_document_object(self, docstore):
        """Test updating document metadata using a Document object."""
        # Create and add a document with initial metadata
        initial_metadata = {"key1": "value1", "key2": 123}
        doc = Document(media_type="text/plain", state="link", metadata=initial_metadata)
        doc_id = docstore.add(doc)
        
        # Retrieve document to ensure it's in the database with expected values
        retrieved_doc = docstore.get(id=doc_id)
        assert retrieved_doc.metadata == initial_metadata
        
        # Update metadata
        updated_doc = docstore.update(retrieved_doc, key1="updated_value", key3="new_value")
        
        # Verify document was updated correctly
        assert updated_doc.id == doc_id
        assert updated_doc.state == "link"  # State should remain unchanged
        assert updated_doc.media_type == "text/plain"  # Media type should remain unchanged
        assert updated_doc.metadata["key1"] == "updated_value"  # Updated existing key
        assert updated_doc.metadata["key2"] == 123  # Existing key not in kwargs should remain unchanged
        assert updated_doc.metadata["key3"] == "new_value"  # New key should be added
        
        # Verify changes persist when retrieved again
        re_retrieved_doc = docstore.get(id=doc_id)
        assert re_retrieved_doc.metadata["key1"] == "updated_value"
        assert re_retrieved_doc.metadata["key2"] == 123
        assert re_retrieved_doc.metadata["key3"] == "new_value"

    def test_update_with_document_id(self, docstore):
        """Test updating document metadata using a document ID."""
        # Create and add a document with initial metadata
        initial_metadata = {"key1": "value1", "key2": 123}
        doc = Document(media_type="text/plain", state="link", metadata=initial_metadata)
        doc_id = docstore.add(doc)
        
        # Update metadata using just the ID
        updated_doc = docstore.update(doc_id, key1="updated_value", key3="new_value")
        
        # Verify document was updated correctly
        assert updated_doc.id == doc_id
        assert updated_doc.state == "link"
        assert updated_doc.media_type == "text/plain"
        assert updated_doc.metadata["key1"] == "updated_value"
        assert updated_doc.metadata["key2"] == 123
        assert updated_doc.metadata["key3"] == "new_value"
        
        # Verify changes persist when retrieved again
        re_retrieved_doc = docstore.get(id=doc_id)
        assert re_retrieved_doc.metadata["key1"] == "updated_value"
        assert re_retrieved_doc.metadata["key2"] == 123
        assert re_retrieved_doc.metadata["key3"] == "new_value"

    def test_update_nonexistent_document(self, docstore):
        """Test that updating a non-existent document raises an error."""
        non_existent_id = str(uuid4())
        
        # Attempt to update non-existent document
        with pytest.raises(ValueError, match=f"Document with ID {non_existent_id} not found in the database"):
            docstore.update(non_existent_id, key1="value1")

    def test_update_mismatched_document(self, docstore):
        """Test that updating a document with mismatched properties raises an error."""
        # Create and add a document
        doc = Document(media_type="text/plain", state="link", content="original content")
        doc_id = docstore.add(doc)
        
        # Create a modified version of the document with different state/content
        modified_doc = Document(
            id=doc_id,
            media_type="text/plain",
            state="download",  # Different state
            content="modified content"  # Different content
        )
        
        # Attempt to update with mismatched document
        with pytest.raises(ValueError, match="Provided document does not match the document in the database"):
            docstore.update(modified_doc, key1="value1")


if __name__ == "__main__":
    pytest.main()
