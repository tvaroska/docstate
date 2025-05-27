# DocState-Async

A high-performance asynchronous library for managing documents through various processing states and transitions.

## Overview

DocState-Async is a fully asynchronous implementation of the document processing pipeline library, designed for high-throughput scenarios with improved performance characteristics. The library treats documents as entities with defined states and manages transitions between states via explicit functions, tracking parent-child relationships between original documents and derivatives.

## Key Features

- **100% Async Implementation**: All operations are asynchronous, enabling non-blocking I/O
- **Parallel Processing**: Process multiple documents concurrently with controlled parallelism
- **Connection Pooling**: Optimized database connections for high-throughput scenarios
- **Performance Optimizations**:
  - Cached state machine transitions
  - Batch database operations
  - Optimized query patterns with proper indexing
  - Selective loading of document content for better memory efficiency
- **Streaming Support**: Stream large document content in chunks to handle massive documents
- **Improved Error Handling**: Comprehensive error tracking and recovery mechanisms
- **Type Safety**: Full type annotations for better IDE support and runtime checking

## Architecture

The library follows a state machine architecture with the following key components:

- **Document**: Core entity with properties including ID, state, content, and metadata
- **DocumentState**: Represents a specific state in the document lifecycle
- **Transition**: Connects two DocumentStates with an async processing function
- **DocumentType**: Defines the state machine with states and valid transitions
- **AsyncDocStore**: Manages persistence and processing of documents

## Usage Example

```python
import asyncio
from doc_new.document import Document, DocumentState, DocumentType, Transition
from doc_new.docstate import AsyncDocStore

# Define states
link = DocumentState(name="link")
download = DocumentState(name="download")

# Define async processing function
async def download_document(doc: Document) -> Document:
    # ... implementation that downloads content
    return Document(
        content="downloaded content",
        state="download",
        parent_id=doc.id
    )

# Create state machine
transitions = [
    Transition(from_state=link, to_state=download, process_func=download_document)
]
doc_type = DocumentType(
    states=[link, download],
    transitions=transitions
)

async def main():
    # Create async doc store
    store = AsyncDocStore(
        connection_string="sqlite:///docs.db", 
        document_type=doc_type,
        max_concurrency=5  # Process up to 5 documents in parallel
    )
    
    # Initialize the database
    await store.initialize()
    
    # Create a document
    doc = Document(url="https://example.com", state="link")
    
    # Add to store
    doc_id = await store.add(doc)
    
    # Process through pipeline
    results = await store.next(doc)
    
    # Or process to completion
    final_docs = await store.finish(doc)
    
    # Clean up
    await store.dispose()

if __name__ == "__main__":
    asyncio.run(main())
```

## Performance Optimizations

### Database Optimizations

- **Connection Pooling**: Configurable connection pool for efficient connection reuse
- **Optimized Indexes**: Strategic indexes on commonly queried fields
- **Batch Operations**: Process documents in batches for better throughput
- **Selective Content Loading**: Option to exclude content field for better performance

### Processing Optimizations

- **Concurrent Processing**: Process multiple documents in parallel with configurable concurrency limit
- **Content Streaming**: Stream large document content in chunks
- **Caching**: Cache transition lookups and final state calculations
- **Efficient Parent-Child Updates**: Optimized algorithms for updating document relationships

## Requirements

- Python 3.8+
- SQLAlchemy 2.0+
- Pydantic 2.0+
- aiosqlite (for SQLite async support)
- asyncpg (recommended for PostgreSQL)

## Installation

```bash
pip install docstate-async
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
