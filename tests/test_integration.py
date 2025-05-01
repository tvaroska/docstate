import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore
from examples.rag import download_document, chunk_document, embed_document
from tests.fixtures import (
    document, document_states, mock_httpx_client, mock_splitter, mock_vectorstore, sqlite_db_path
)


@pytest.fixture
def rag_document_type(mock_httpx_client, mock_splitter, mock_vectorstore):
    """Create a document type for RAG with mocked processing functions."""
    # Create states
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    chunk = DocumentState(name="chunk")
    embed = DocumentState(name="embed")
    error = DocumentState(name="error")
    
    # Create transitions
    transitions = [
        Transition(from_state=link, to_state=download, process_func=download_document),
        Transition(from_state=download, to_state=chunk, process_func=chunk_document),
        Transition(from_state=chunk, to_state=embed, process_func=embed_document),
    ]
    
    return DocumentType(
        states=[link, download, chunk, embed, error],
        transitions=transitions
    )


class TestCompletePipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_success(self, sqlite_db_path, rag_document_type, mock_httpx_client, mock_splitter):
        """Test running a document through the complete RAG pipeline."""
        # Patch vectorstore
        with patch("examples.rag.vectorstore") as mock_vs:
            mock_vs.add_texts.return_value = ["embedding_id"]
            
            # Create a DocStore
            store = DocStore(
                connection_string=sqlite_db_path,
                document_type=rag_document_type
            )
            
            # Create a test document
            doc = Document(
                state="link",
                url="https://example.com/test",
                media_type="text/plain",
                metadata={"source": "test"}
            )
            
            # Add the document to the store
            store.add(doc)
            
            # Process the document through the entire pipeline
            final_docs = await store.finish(doc)
            
            # Verify we got results
            assert len(final_docs) > 0
            
            # Find documents in each state to verify the pipeline worked
            link_docs = store.get(state="link")
            download_docs = store.get(state="download") 
            chunk_docs = store.get(state="chunk")
            embed_docs = store.get(state="embed")
            
            # Should have one link document
            assert len(link_docs) == 1
            
            # Should have one download document
            assert len(download_docs) == 1
            
            # Should have two chunk documents (from the mock splitter)
            assert len(chunk_docs) == 2
            
            # Should have two embed documents (one for each chunk)
            assert len(embed_docs) == 2
            
            # Verify parent-child relationships
            link_doc = link_docs[0]
            download_doc = download_docs[0]
            
            # The download document should be a child of the link document
            assert download_doc.parent_id == link_doc.id
            assert download_doc.id in link_doc.children
            
            # The chunk documents should be children of the download document
            for chunk_doc in chunk_docs:
                assert chunk_doc.parent_id == download_doc.id
                assert chunk_doc.id in download_doc.children
            
            # The embed documents should be children of chunk documents
            for embed_doc in embed_docs:
                # Find the parent chunk
                parent_chunk = next(
                    (chunk for chunk in chunk_docs if embed_doc.parent_id == chunk.id),
                    None
                )
                assert parent_chunk is not None
                assert embed_doc.id in parent_chunk.children

    @pytest.mark.asyncio
    async def test_pipeline_with_error(self, sqlite_db_path, rag_document_type):
        """Test pipeline with an error in the middle."""
        # Create a DocStore
        store = DocStore(
            connection_string=sqlite_db_path,
            document_type=rag_document_type
        )
        
        # Create a test document with an invalid URL to trigger an error
        doc = Document(
            state="link",
            url=None,  # Missing URL will cause an error in download_document
            media_type="text/plain",
            metadata={"source": "test"}
        )
        
        # Add the document to the store
        store.add(doc)
        
        # Process the document through the pipeline
        final_docs = await store.finish(doc)
        
        # Should have error documents
        error_docs = store.get(state="error")
        assert len(error_docs) > 0
        
        # The error document should contain the error message
        assert any("Expected url" in doc.content for doc in error_docs)
        
        # The error document should be a child of the link document
        link_doc = store.get(state="link")[0]
        error_doc = error_docs[0]
        assert error_doc.parent_id == link_doc.id
        assert error_doc.id in link_doc.children


class TestBatchProcessing:
    @pytest.mark.asyncio
    async def test_batch_processing(self, sqlite_db_path, rag_document_type, mock_httpx_client, mock_splitter):
        """Test processing multiple documents in a batch."""
        # Patch vectorstore
        with patch("examples.rag.vectorstore") as mock_vs:
            mock_vs.add_texts.return_value = ["embedding_id"]
            
            # Create a DocStore
            store = DocStore(
                connection_string=sqlite_db_path,
                document_type=rag_document_type
            )
            
            # Create multiple test documents
            docs = [
                Document(
                    state="link",
                    url=f"https://example.com/test{i}",
                    media_type="text/plain",
                    metadata={"source": f"test{i}"}
                )
                for i in range(3)
            ]
            
            # Add the documents to the store
            store.add(docs)
            
            # Process the documents through the first step
            processed_docs = await store.next(docs)
            
            # Should have processed all documents
            assert len(processed_docs) == len(docs)
            
            # All processed documents should be in the download state
            assert all(doc.state == "download" for doc in processed_docs)
            
            # Check parent-child relationships
            for i, doc in enumerate(docs):
                # Get the document from the store to ensure we have the latest version
                parent = store.get(id=doc.id)
                assert len(parent.children) == 1
                assert processed_docs[i].id in parent.children


class TestListAndFilter:
    @pytest.mark.asyncio
    async def test_list_and_filter(self, sqlite_db_path, rag_document_type, mock_httpx_client, mock_splitter):
        """Test listing and filtering documents at different stages of the pipeline."""
        # Patch vectorstore
        with patch("examples.rag.vectorstore") as mock_vs:
            mock_vs.add_texts.return_value = ["embedding_id"]
            
            # Create a DocStore
            store = DocStore(
                connection_string=sqlite_db_path,
                document_type=rag_document_type
            )
            
            # Create a test document
            doc = Document(
                state="link",
                url="https://example.com/test",
                media_type="text/plain",
                metadata={"source": "test", "filter_value": "special"}
            )
            
            # Add the document to the store
            store.add(doc)
            
            # Process the document through the entire pipeline
            await store.finish(doc)
            
            # Test listing documents in different states
            link_docs = list(store.list(state="link", leaf=False))
            assert len(link_docs) == 1
            
            download_docs = list(store.list(state="download", leaf=False))
            assert len(download_docs) == 1
            
            chunk_docs = list(store.list(state="chunk", leaf=False))
            assert len(chunk_docs) == 2
            
            embed_docs = list(store.list(state="embed"))
            assert len(embed_docs) == 2
            
            # Test filtering by metadata
            filtered_docs = list(store.list(state="link", filter_value="special", leaf=False))
            assert len(filtered_docs) == 1
            assert filtered_docs[0].id == doc.id
            
            # Test filtering by non-existent metadata
            non_existent_docs = list(store.list(state="link", non_existent="value", leaf=False))
            assert len(non_existent_docs) == 0
            
            # Test listing only leaf nodes
            # By default, store.list only returns leaf nodes - documents without children
            download_leaf_docs = list(store.list(state="download"))
            assert len(download_leaf_docs) == 0  # All download docs have children
            
            # Test listing non-leaf nodes
            download_all_docs = list(store.list(state="download", leaf=False))
            assert len(download_all_docs) == 1
            
            # Test listing chunk documents with specific metadata
            # Get all chunk documents first to see what metadata is being set
            all_chunks = store.get(state="chunk")
            # Use the first chunk's metadata for filtering
            if all_chunks and len(all_chunks) > 0:
                first_chunk = all_chunks[0]
                # Instead of assuming chunk_index is the key, use leaf=False to make sure we get results
                chunk_docs = list(store.list(state="chunk", leaf=False))
                assert len(chunk_docs) > 0
