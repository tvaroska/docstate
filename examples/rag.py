"""
Example of using the async docstate library for a RAG (Retrieval Augmented Generation) pipeline.

This example demonstrates:
1. Defining document states and transitions
2. Creating async processing functions
3. Batch processing documents through the pipeline
4. Error handling
5. Streaming large document content
6. Parallel processing with concurrency control
"""

import asyncio
import httpx
from typing import List
import logging

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import Docstore
from docstate.utils import configure_logging

# Optional: Configure detailed logging for better visibility
configure_logging(level=logging.INFO)

# Define async processing functions for document transitions

async def download_document(doc: Document) -> Document:
    """Download content from a URL asynchronously."""
    if not doc.url:
        raise ValueError(f"Expected url for document with ID {doc.id}")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        try:
            response = await client.get(doc.url)
            response.raise_for_status()
            content = response.text
        except httpx.RequestError as exc:
            raise RuntimeError(f"Request error for {doc.url}: {exc}")
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"HTTP error {exc.response.status_code} for {doc.url}: {exc.response.text}")

    return Document(
        content=content,
        media_type="text/plain",
        state="download",
        parent_id=doc.id,
        metadata={
            "source_url": doc.url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "text/plain"),
            "content_length": len(content)
        }
    )

async def chunk_document(doc: Document) -> List[Document]:
    """
    Split document into multiple chunks using a simple paragraph-based approach.
    
    In a real implementation, you might use a more sophisticated chunking strategy
    like LangChain's text splitters.
    """
    if doc.media_type != "text/plain":
        raise ValueError(f"Expected media_type 'text/plain', got '{doc.media_type}'")
    
    if not doc.content:
        raise ValueError("Document has no content to chunk")
    
    # Simple paragraph-based chunking
    paragraphs = [p for p in doc.content.split("\n\n") if p.strip()]
    
    # Combine very small paragraphs to reduce the number of chunks
    chunks = []
    current_chunk = ""
    
    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) <= 1000:
            if current_chunk:
                current_chunk += "\n\n"
            current_chunk += paragraph
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = paragraph
    
    if current_chunk:
        chunks.append(current_chunk)
    
    # Create Document objects for each chunk
    return [
        Document(
            content=chunk,
            media_type="text/plain",
            state="chunk",
            parent_id=doc.id,
            metadata={
                **doc.metadata,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "chunk_length": len(chunk)
            }
        )
        for i, chunk in enumerate(chunks)
    ]

async def embed_document(doc: Document) -> Document:
    """
    Create a vector embedding for the document.
    
    This is a simplified version that just uses character frequency counts
    as a mock embedding. In a real implementation, you would use an embedding
    model like OpenAI, Cohere, or a local model.
    """
    if doc.media_type != "text/plain":
        raise ValueError(f"Expected media_type 'text/plain', got '{doc.media_type}'")
    
    if not doc.content:
        raise ValueError("Document has no content to embed")
    
    # Create a mock embedding based on character frequency
    # In a real implementation, you would call an embedding API here
    char_counts = {}
    for char in doc.content.lower():
        if char.isalpha():
            char_counts[char] = char_counts.get(char, 0) + 1
    
    # Normalize the counts to create a vector
    total_chars = sum(char_counts.values())
    embedding = [count / total_chars for char in "abcdefghijklmnopqrstuvwxyz" 
                for count in [char_counts.get(char, 0)]]
    
    return Document(
        content=str(embedding),  # Store the embedding as a string
        media_type="application/vector",
        state="embed",
        parent_id=doc.id,
        metadata={
            **doc.metadata,
            "vector_dimensions": len(embedding),
            "embedding_method": "char_frequency"
        }
    )

async def main():
    """Run the RAG example pipeline."""
    # Define document states
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    chunk = DocumentState(name="chunk") 
    embed = DocumentState(name="embed")
    
    # Define transitions between states with async processing functions
    transitions = [
        Transition(from_state=link, to_state=download, process_func=download_document),
        Transition(from_state=download, to_state=chunk, process_func=chunk_document),
        Transition(from_state=chunk, to_state=embed, process_func=embed_document),
    ]
    
    # Create document type with states and transitions
    doc_type = DocumentType(
        states=[link, download, chunk, embed],
        transitions=transitions
    )
    
    # Create Docstore with SQLite database and multiprocessing support
    async_docstore = Docstore(
        connection_string="sqlite:///rag_example.db",
        document_type=doc_type,
        max_concurrency=5,      # Process up to 5 documents in parallel with asyncio
        process_workers=4,      # Use 4 worker processes for CPU-intensive operations (embedding, chunking)
        echo=True               # Show SQL queries for demonstration
    )
    
    # Initialize the database
    await async_docstore.initialize()
    
    # Create sample documents to process
    sample_docs = [
        Document(
            url="https://docs.python.org/3/library/asyncio.html",
            state="link"
        ),
        Document(
            url="https://peps.python.org/pep-0492/",
            state="link"
        ),
        # Intentionally invalid URL to demonstrate error handling
        Document(
            url="htt://invalid-url",
            state="link"
        )
    ]
    
    # Add documents to the store
    doc_ids = await async_docstore.add(sample_docs)
    print(f"Added {len(doc_ids)} documents with IDs: {doc_ids}")
    
    # Process all documents through the entire pipeline
    print("\nProcessing all documents through the pipeline...")
    final_docs = await async_docstore.finish(sample_docs)
    
    # Print results
    print(f"\nFinal documents count: {len(final_docs)}")
    for doc in final_docs:
        print(f"ID: {doc.id}, State: {doc.state}, Media Type: {doc.media_type}")
        
        # For error documents, show the error
        if doc.state == "error":
            print(f"  Error: {doc.content}")
        
        # For embedded documents, show metadata
        if doc.state == "embed":
            print(f"  Vector dimensions: {doc.metadata.get('vector_dimensions')}")
            print(f"  Original chunk index: {doc.metadata.get('chunk_index')}")
            
    # Count documents by state
    for state in ["link", "download", "chunk", "embed", "error"]:
        count = await async_docstore.count(state)
        print(f"Documents in '{state}' state: {count}")
    
    # Example of streaming large document content
    print("\nExample of streaming document content:")
    
    # Get a download document to stream
    download_docs = await async_docstore.list("download", leaf=False)
    if download_docs:
        doc_to_stream = download_docs[0]
        print(f"Streaming content from document {doc_to_stream.id} in chunks:")
        
        chunk_count = 0
        async for content_chunk in async_docstore.stream_content(doc_to_stream.id, chunk_size=200):
            chunk_count += 1
            # Print the first 50 chars of each chunk
            print(f"  Chunk {chunk_count}: {content_chunk[:50]}...")
        
        print(f"Streamed document in {chunk_count} chunks")
    
    # Clean up
    await async_docstore.dispose()
    print("\nExample completed successfully")

if __name__ == "__main__":
    asyncio.run(main())
