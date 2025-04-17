import asyncio
from typing import Any, Dict, List
from uuid import uuid4

import httpx
import pytest

from docstate.docstate import DocStore
from docstate.document import Document, DocumentState, DocumentType, Transition


# Define simple processing functions for the pipeline
async def download_document(doc: Document) -> Document:
    """Download content of url."""
    if doc.media_type != "application/uri":
        raise ValueError(
            f"Expected media_type 'application/uri', got '{doc.media_type}'"
        )

    # Simulate downloading content from a URL
    # In a real implementation, this would use httpx to fetch the content
    content = f"Downloaded content from {doc.content}"

    return Document(
        content=content,
        media_type="text/plain",
        state="download",
        metadata={"source_url": doc.content},
    )


async def chunk_document(doc: Document) -> List[Document]:
    """Split document into multiple chunks."""
    if doc.media_type != "text/plain":
        raise ValueError(f"Expected media_type 'text/plain', got '{doc.media_type}'")

    # Simple chunking strategy - split by newlines and ensure chunks aren't too long
    lines = doc.content.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0
    max_chunk_length = 100  # Simple character limit

    for line in lines:
        # If adding this line would exceed max length, finalize current chunk
        if current_length + len(line) > max_chunk_length and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        # Add line to current chunk
        current_chunk.append(line)
        current_length += len(line)

    # Add the final chunk if it's not empty
    if current_chunk:
        chunks.append("\n".join(current_chunk))

    # If no chunks were created (e.g., empty document), create at least one
    if not chunks:
        chunks = [""]

    # Create Document objects for each chunk
    return [
        Document(
            content=chunk,
            media_type="text/plain",
            state="chunk",
            metadata={**doc.metadata, "chunk_index": i, "total_chunks": len(chunks)},
        )
        for i, chunk in enumerate(chunks)
    ]


async def embed_document(doc: Document) -> Document:
    """Create a vector embedding for the document."""
    if doc.media_type != "text/plain":
        raise ValueError(f"Expected media_type 'text/plain', got '{doc.media_type}'")

    # Simple hash-based embedding for testing
    # In a real implementation, this would use a proper embedding model
    hash_vector = hash(doc.content) % 1000000
    vector = [hash_vector / 1000000]  # Fake 1D embedding

    return Document(
        content=str(vector),  # Store embedding as string
        media_type="application/vector",
        state="embed",
        metadata={
            **doc.metadata,
            "vector_dimensions": 1,
            "embedding_method": "test_hash",
        },
    )


@pytest.fixture(scope="function")
def pipeline_document_type():
    """Create a document type with the pipeline processing functions."""
    # Define states
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    chunk = DocumentState(name="chunk")
    embed = DocumentState(name="embed")

    # Define transitions
    transitions = [
        Transition(from_state=link, to_state=download, process_func=download_document),
        Transition(from_state=download, to_state=chunk, process_func=chunk_document),
        Transition(from_state=chunk, to_state=embed, process_func=embed_document),
    ]

    return DocumentType(states=[link, download, chunk, embed], transitions=transitions)


@pytest.fixture(scope="function")
def pipeline_docstore(sqlite_connection_string, pipeline_document_type):
    """Create a DocStore with the pipeline document type."""
    return DocStore(
        connection_string=sqlite_connection_string, document_type=pipeline_document_type
    )


class TestDocumentPipeline:
    """Integration tests for the document processing pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_execution(self, pipeline_docstore):
        """Test the full document processing pipeline."""
        # Create a document in the 'link' state
        doc = Document(
            content="http://example.com",
            media_type="application/uri",
            state="link",
            metadata={"test_id": "pipeline_test"},
        )

        # Add document to the store
        doc_id = pipeline_docstore.add(doc)
        assert doc_id is not None

        # Process to 'download' state
        download_docs = await pipeline_docstore.next(doc)
        assert isinstance(download_docs, list)
        assert (
            len(download_docs) == 1
        )  # Expect one document for link->download transition
        download_doc = download_docs[0]  # Get the first document from the list
        assert download_doc.state == "download"
        assert download_doc.media_type == "text/plain"
        assert "Downloaded content from" in download_doc.content
        assert download_doc.parent_id == doc_id

        # Verify parent-child relationship
        parent_doc = pipeline_docstore.get(id=doc_id)
        assert download_doc.id in parent_doc.children

        # Process to 'chunk' state
        chunk_docs = await pipeline_docstore.next(download_doc)
        assert isinstance(chunk_docs, list)
        assert len(chunk_docs) > 0
        assert all(d.state == "chunk" for d in chunk_docs)
        assert all(d.parent_id == download_doc.id for d in chunk_docs)

        # Verify parent-child relationship
        parent_doc = pipeline_docstore.get(id=download_doc.id)
        for chunk_doc in chunk_docs:
            assert chunk_doc.id in parent_doc.children
            assert chunk_doc.metadata["chunk_index"] is not None
            assert chunk_doc.metadata["total_chunks"] == len(chunk_docs)

        # Process chunks to 'embed' state
        all_embed_docs = []
        for chunk_doc in chunk_docs:
            chunk_embed_docs = await pipeline_docstore.next(chunk_doc)
            assert isinstance(chunk_embed_docs, list)
            assert len(chunk_embed_docs) == 1  # Each chunk should produce one embedding
            all_embed_docs.extend(chunk_embed_docs)

        # Verify embeddings
        assert len(all_embed_docs) == len(chunk_docs)
        for i, embed_doc in enumerate(all_embed_docs):
            assert embed_doc.state == "embed"
            assert embed_doc.media_type == "application/vector"
            assert embed_doc.metadata["vector_dimensions"] == 1
            assert embed_doc.metadata["embedding_method"] == "test_hash"
            assert embed_doc.parent_id == chunk_docs[i].id

            # Verify parent-child relationship
            parent_doc = pipeline_docstore.get(id=chunk_docs[i].id)
            assert embed_doc.id in parent_doc.children

    @pytest.mark.asyncio
    async def test_pipeline_document_queries(self, pipeline_docstore):
        """Test querying documents by state in the pipeline."""
        # Setup - create documents in various states
        original_doc = Document(
            content="http://example.com/page",
            media_type="application/uri",
            state="link",
            metadata={"test_id": "query_test"},
        )

        # Add original document
        doc_id = pipeline_docstore.add(original_doc)

        # Process through pipeline
        download_docs = await pipeline_docstore.next(original_doc)
        download_doc = download_docs[0]  # Get the first document from the list
        chunk_docs = await pipeline_docstore.next(download_doc)

        # Only process first chunk to embed
        embed_docs = await pipeline_docstore.next(chunk_docs[0])
        embed_doc = embed_docs[0]  # Get the first document from the list

        # Create another link document
        another_link_doc = Document(
            content="http://example.com/another",
            media_type="application/uri",
            state="link",
        )
        pipeline_docstore.add(another_link_doc)

        # Now query by state
        link_docs = pipeline_docstore.get(state="link")
        download_docs = pipeline_docstore.get(state="download")
        chunk_docs_query = pipeline_docstore.get(state="chunk")
        embed_docs = pipeline_docstore.get(state="embed")

        # Verify query results
        assert len(link_docs) == 2
        assert len(download_docs) == 1
        assert len(chunk_docs_query) == len(chunk_docs)
        assert len(embed_docs) == 1

        # Verify document content
        assert any(d.content == "http://example.com/page" for d in link_docs)
        assert any(d.content == "http://example.com/another" for d in link_docs)
        assert download_docs[0].media_type == "text/plain"
        assert embed_docs[0].media_type == "application/vector"


if __name__ == "__main__":
    pytest.main()
