import pytest
import asyncio
from typing import List

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore

# Import the existing test process functions
from tests.test_document_pipeline import (
    download_document,
    chunk_document, 
    embed_document,
    pipeline_document_type,
    pipeline_docstore
)


class TestFinishMethod:
    """Tests for the finish method that processes documents to completion."""
    
    @pytest.mark.asyncio
    async def test_finish_single_document(self, pipeline_docstore):
        """Test processing a single document to completion."""
        # Create a document in the 'link' state
        doc = Document(
            content="http://example.com/finish-test",
            media_type="application/uri",
            state="link",
            metadata={"test_id": "finish_test_single"}
        )
        
        # Process the document to completion
        final_docs = await pipeline_docstore.finish(doc)
        
        # Verify we got documents in the final state
        assert isinstance(final_docs, list)
        assert len(final_docs) > 0  # Should have at least one document
        
        # Check that all returned documents are in final states
        document_type = pipeline_docstore.document_type
        final_state_names = [state.name for state in document_type.final]
        assert all(doc.state in final_state_names for doc in final_docs)
        
        # Verify there are embedding documents (should be the final state)
        embed_docs = [doc for doc in final_docs if doc.state == "embed"]
        assert len(embed_docs) > 0
        
        # Verify the content and metadata of embedding documents
        for embed_doc in embed_docs:
            assert embed_doc.media_type == "application/vector"
            assert embed_doc.metadata["vector_dimensions"] == 1
            assert embed_doc.metadata["embedding_method"] == "test_hash"
            
        # Check the document lineage by tracing back from embed to link
        for embed_doc in embed_docs:
            # Get the chunk document (parent of embed)
            chunk_doc = pipeline_docstore.get(id=embed_doc.parent_id)
            assert chunk_doc.state == "chunk"
            
            # Get the download document (parent of chunk)
            download_doc = pipeline_docstore.get(id=chunk_doc.parent_id)
            assert download_doc.state == "download"
            
            # Get the original link document (parent of download)
            link_doc = pipeline_docstore.get(id=download_doc.parent_id)
            assert link_doc.state == "link"
            assert link_doc.id == doc.id
    
    @pytest.mark.asyncio
    async def test_finish_multiple_documents(self, pipeline_docstore):
        """Test processing multiple documents to completion."""
        # Create multiple documents in the 'link' state
        docs = [
            Document(
                content=f"http://example.com/finish-test-{i}",
                media_type="application/uri",
                state="link",
                metadata={"test_id": f"finish_test_multiple_{i}"}
            )
            for i in range(3)
        ]
        
        # Process the documents to completion
        final_docs = await pipeline_docstore.finish(docs)
        
        # Verify we got documents in the final state
        assert isinstance(final_docs, list)
        assert len(final_docs) > 0
        
        # Check that all returned documents are in final states
        document_type = pipeline_docstore.document_type
        final_state_names = [state.name for state in document_type.final]
        assert all(doc.state in final_state_names for doc in final_docs)
        
        # We should have multiple embed documents
        embed_docs = [doc for doc in final_docs if doc.state == "embed"]
        assert len(embed_docs) >= 3  # At least one embed doc per original document
        
        # Check that the original documents are still in the database
        for original_doc in docs:
            stored_doc = pipeline_docstore.get(id=original_doc.id)
            assert stored_doc is not None
            assert stored_doc.state == "link"
            assert len(stored_doc.children) > 0  # Should have children documents
    
    @pytest.mark.asyncio
    async def test_finish_with_documents_in_different_states(self, pipeline_docstore):
        """Test processing documents that start in different states."""
        # Create documents in different states
        link_doc = Document(
            content="http://example.com/link-doc",
            media_type="application/uri",
            state="link",
            metadata={"test_id": "finish_test_mixed_link"}
        )
        
        download_doc = Document(
            content="Downloaded content from http://example.com/download-doc",
            media_type="text/plain",
            state="download",
            metadata={"test_id": "finish_test_mixed_download"}
        )
        
        chunk_doc = Document(
            content="A chunk of content for testing",
            media_type="text/plain",
            state="chunk",
            metadata={"test_id": "finish_test_mixed_chunk"}
        )
        
        # Add documents to start with
        pipeline_docstore.add(link_doc)
        pipeline_docstore.add(download_doc)
        pipeline_docstore.add(chunk_doc)
        
        # Process the documents to completion
        mixed_docs = [link_doc, download_doc, chunk_doc]
        final_docs = await pipeline_docstore.finish(mixed_docs)
        
        # Verify we got documents in the final state
        assert isinstance(final_docs, list)
        assert len(final_docs) > 0
        
        # Check that all returned documents are in final states
        document_type = pipeline_docstore.document_type
        final_state_names = [state.name for state in document_type.final]
        assert all(doc.state in final_state_names for doc in final_docs)
        
        # Verify that all original documents have been processed
        for original_doc in mixed_docs:
            if original_doc.state == "link":
                # Link document should have download children
                stored_doc = pipeline_docstore.get(id=original_doc.id)
                assert stored_doc.has_children
                # Get the download child
                download_children = [
                    pipeline_docstore.get(id=child_id) for child_id in stored_doc.children
                ]
                assert any(child.state == "download" for child in download_children)
            
            elif original_doc.state == "download":
                # Download document should have chunk children
                stored_doc = pipeline_docstore.get(id=original_doc.id)
                assert stored_doc.has_children
                # Get the chunk children
                chunk_children = [
                    pipeline_docstore.get(id=child_id) for child_id in stored_doc.children
                ]
                assert any(child.state == "chunk" for child in chunk_children)
            
            elif original_doc.state == "chunk":
                # Chunk document should have embed children
                stored_doc = pipeline_docstore.get(id=original_doc.id)
                assert stored_doc.has_children
                # Get the embed children
                embed_children = [
                    pipeline_docstore.get(id=child_id) for child_id in stored_doc.children
                ]
                assert any(child.state == "embed" for child in embed_children)
    
    @pytest.mark.asyncio
    async def test_finish_with_error_handling(self, sqlite_connection_string, pipeline_document_type):
        """Test that finish handles errors properly."""
        # Create a custom document type with a failing transition
        link = DocumentState(name="link")
        download = DocumentState(name="download")
        error = DocumentState(name="error")
        
        # Define a failing processing function
        async def failing_process_func(doc: Document) -> Document:
            if "fail" in doc.content:
                raise ValueError("Simulated process failure")
            return Document(
                content=f"Processed: {doc.content}",
                media_type="text/plain",
                state="download"
            )
        
        # Create document type with conditional failing transition
        doc_type = DocumentType(
            states=[link, download, error],
            transitions=[
                Transition(
                    from_state=link, 
                    to_state=download, 
                    process_func=failing_process_func
                )
            ]
        )
        
        # Create DocStore with this document type
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=doc_type)
        
        # Create mixed documents - one will succeed, one will fail
        doc1 = Document(
            content="http://example.com/success",
            media_type="application/uri",
            state="link",
            metadata={"test_id": "finish_test_error_success"}
        )
        
        doc2 = Document(
            content="http://example.com/fail",
            media_type="application/uri",
            state="link",
            metadata={"test_id": "finish_test_error_fail"}
        )
        
        # Process the documents to completion
        final_docs = await docstore.finish([doc1, doc2])
        
        # Verify we got documents in the final states
        assert isinstance(final_docs, list)
        
        # We should have both error and download documents
        error_docs = [doc for doc in final_docs if doc.state == "error"]
        download_docs = [doc for doc in final_docs if doc.state == "download"]
        
        # Should have at least one of each
        assert len(error_docs) > 0
        assert len(download_docs) > 0
        
        # Verify error document
        error_doc = error_docs[0]
        assert error_doc.state == "error"
        assert "Simulated process failure" in error_doc.metadata["error"]
        
        # Verify download document
        download_doc = download_docs[0]
        assert download_doc.state == "download"
        assert "Processed" in download_doc.content
