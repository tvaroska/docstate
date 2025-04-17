# DocState

DocState is a document processing pipeline library that manages documents through various processing states using a state machine architecture. It provides a clean, structured way to process documents through defined state transitions with full parent-child relationship tracking and database persistence.

## Features

- **State Machine Architecture**: Documents progress through well-defined states with explicit transitions
- **Parent-Child Relationship Tracking**: Maintain document lineage throughout transformations
- **Database Persistence**: Store documents with SQLAlchemy (SQLite and PostgreSQL support)
- **Async Processing**: All document processing steps are implemented as async functions
- **Flexible Querying**: Query documents by state, relationships, and metadata
- **Error Handling**: Robust error handling with custom error states
- **Batch Processing**: Process multiple documents concurrently

## Installation

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/docstate/docstate.git
cd docstate

# Create a virtual environment
uv venv

# Activate the virtual environment
source .venv/bin/activate

# Install in development mode
uv pip install -e .
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/docstate/docstate.git
cd docstate

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Install in development mode
pip install -e .
```

## Basic Usage

```python
from typing import List
import asyncio
import httpx
from docstate.document import Document
from docstate.docstate import DocStore, DocumentType, DocumentState, Transition

# Define document states
link = DocumentState(name="link")
download = DocumentState(name="download")
chunk = DocumentState(name="chunk")
embed = DocumentState(name="embed")

# Define processing functions
async def download_document(doc: Document) -> Document:
    """Download content from URL."""
    if not doc.url:
        raise ValueError(f"Expected url, got '{doc.media_type}'")

    async with httpx.AsyncClient() as client:
        response = await client.get(doc.url)
        response.raise_for_status()
        content = response.text

    return Document(
        content=content,
        media_type="text/plain",
        state="download",
        metadata={"source_url": doc.url}
    )

async def chunk_document(doc: Document) -> List[Document]:
    """Split document into multiple chunks."""
    # Implement chunking logic
    chunks = [doc.content[i:i+1000] for i in range(0, len(doc.content), 1000)]
    
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
    # Implement embedding logic (simplified example)
    embedding = hash(doc.content) % 1000  # Placeholder for real embedding
    
    return Document(
        content=str(embedding),
        media_type="vector",
        state="embed",
        metadata={
            **doc.metadata,
            "vector_dimensions": 1,
            "embedding_method": "simple_hash"
        }
    )

# Define transitions
transitions = [
    Transition(from_state=link, to_state=download, process_func=download_document),
    Transition(from_state=download, to_state=chunk, process_func=chunk_document),
    Transition(from_state=chunk, to_state=embed, process_func=embed_document),
]

# Create document type
doctype = DocumentType(
    states=[link, download, chunk, embed],
    transitions=transitions
)

# Initialize docstore
docstore = DocStore(connection_string="sqlite:///documents.db", document_type=doctype)

# Create a document
doc = Document(
    url='https://example.com',
    state='link'
)

# Add document to store
doc_id = docstore.add(doc)

# Process document
async def process_document():
    # Process document through a single transition
    result_docs = await docstore.next(doc)
    
    # Or process through entire pipeline
    final_docs = await docstore.finish(doc)
    
    # Query documents by state
    embed_docs = list(docstore.list(state="embed"))
    
    # Query with metadata filters
    filtered_docs = list(docstore.list(state="chunk", total_chunks=2))

# Run the async process
asyncio.run(process_document())
```

## RAG Example Integration

The library includes a fully-functional RAG (Retrieval Augmented Generation) example that demonstrates integration with:

- VertexAI for embeddings
- PGVector for vector storage
- LangChain text splitters for document chunking

See `examples/rag.py` for the complete implementation.

## Current Status

The project has implemented all core components:
- ✅ Document, DocumentState, DocumentType, and Transition classes
- ✅ DocStore with SQLAlchemy for document persistence
- ✅ Parent-child relationship tracking
- ✅ Processing functions (download, chunk, embed)
- ✅ Error handling with custom error states
- ✅ Batch processing with mixed success/failure handling
- ✅ Vector embedding integration with VertexAI
- ✅ Comprehensive test suite

In progress features:
- 🔄 Streaming support for large document handling
- 🔄 Performance optimization for larger document sets
- 🔄 Additional document format support (PDF, DOCX, HTML)
- 🔄 Concurrency improvements with asyncio.gather

## Development

```bash
# Run tests
uv run pytest

# Type checking
mypy docstate
```

## Requirements

- Python 3.8+
- SQLAlchemy
- Pydantic
- httpx
- langchain (for text splitters)
- pgvector (for PostgreSQL vector storage)
- google-cloud-aiplatform (for VertexAI embeddings)

## License

MIT License
