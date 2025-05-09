from typing import List

import asyncio
import httpx
from docstate.document import Document, DocumentState, Transition, DocumentType
from docstate.docstate import DocStore

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector
from langchain_google_vertexai import VertexAIEmbeddings

DB = 'postgresql://postgres:postgres@localhost/postgres'

embeddings = VertexAIEmbeddings(model="text-embedding-004")
vectorstore = PGVector(
    connection=DB,
    embeddings=embeddings
)

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

    # Import inside the function to allow test mocking
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_text(doc.content)
    
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
    
    ids = vectorstore.add_texts([doc.content])

    return Document(
        content=str(ids[0]),  # Store embedding as string
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

    await docstore.finish(doc)

    error_doc = Document(
        url='htt://docs.pydantic.dev/latest/llms.txt',
        state='link'
    )

    await docstore.finish(error_doc)
    
    # Examples of using the list method
    
    # List all documents in 'embed' state (only leaf nodes - default)
    print("\nListing embed documents (leaf nodes only):")
    embed_docs = list(docstore.list(state="embed"))
    for doc in embed_docs:
        print(f"ID: {doc.id}, State: {doc.state}, Children: {len(doc.children)}")
    
    # List all documents in 'download' state (including non-leaf nodes)
    print("\nListing download documents (including non-leaf nodes):")
    download_docs = list(docstore.list(state="download", leaf=False))
    for doc in download_docs:
        print(f"ID: {doc.id}, State: {doc.state}, Children: {len(doc.children)}")
    
    # List documents with metadata filtering
    print("\nListing documents with metadata filtering:")
    filtered_docs = list(docstore.list(state="chunk", total_chunks=2))
    for doc in filtered_docs:
        print(f"ID: {doc.id}, State: {doc.state}, Chunk index: {doc.metadata.get('chunk_index')}")

if __name__ == '__main__':
    asyncio.run(main())
