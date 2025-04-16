from typing import List

import asyncio
import httpx
from docstate.document import Document
from docstate.docstate import DocStore, DocumentType, DocumentState, Transition

DB = 'postgresql://postgres:postgres@localhost/postgres'

async def download_document(doc: Document) -> Document:
    """Download content of url."""
    if not doc.url:
        raise ValueError(f"Expected url, got '{doc.media_type}'")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(doc.url)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            content = response.text
        except httpx.RequestError as exc:
            raise RuntimeError(f"An error occurred while requesting {exc.request.url!r}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Error response {exc.response.status_code} while requesting {exc.request.url!r}: {exc.response.text}") from exc

    return Document(
        content=content,
        media_type="text/plain",  # Assuming downloaded content is text
        state="download",
        metadata={"source_url": doc.content}
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
            metadata={
                **doc.metadata,
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
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
        media_type="vector",
        state="embed",
        metadata={
            **doc.metadata,
            "vector_dimensions": 1,
            "embedding_method": "test_hash"
        }
    )

async def main():

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

    doctype = DocumentType(
        states=[link, download, chunk, embed],
        transitions=transitions
    )

    docstore = DocStore(connection_string=DB, document_type=doctype)

    doc = Document(
        url='https://docs.pydantic.dev/latest/llms.txt',
        state='link'
    )

    docstore.add(doc)
    doc2 = await docstore.next(doc)
    doc3 = await docstore.next(doc2)
    doc4 = await docstore.next(doc3)
    doc5 = await docstore.next(doc4)

    error_doc = Document(
        url='htt://docs.pydantic.dev/latest/llms.txt',
        state='link'
    )
    
    docstore.add(error_doc)
    error_doc2 = await docstore.next(error_doc)

    pass

if __name__ == '__main__':
    asyncio.run(main())
