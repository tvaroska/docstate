# DocState Library Documentation

## Overview

DocState is a fully asynchronous library for managing documents through various processing states and transitions using a state machine architecture. It provides a clean, structured way to process documents with parent-child relationship tracking and database persistence.

The library is designed for high-performance document processing workflows, enabling vector embedding of document content for AI/ML applications, supporting document chunking, and maintaining document lineage throughout transformations.

### Key Features

- **State Machine Architecture**: Documents progress through well-defined states with explicit transitions
- **Parent-Child Relationship Tracking**: Maintain relationships between original documents and their derivatives
- **Fully Asynchronous Processing**: All operations implemented as async functions for improved performance
- **Database Persistence**: Store documents with SQLAlchemy ORM supporting both SQLite and PostgreSQL
- **Streaming Support**: Handle large document content efficiently
- **Concurrency Control**: Process multiple documents in parallel with configurable limits
- **Batch Processing**: Optimize operations for handling multiple documents at once
- **Connection Pooling**: Configurable database connection management for performance
- **Optimized Query Patterns**: Efficient database access with caching strategies

## Installation

```bash
pip install docstate
```

## Core Concepts

DocState is built around a state machine architecture with the following key components:

### Document

A `Document` is the core entity representing content to be processed. Each document has:
- A unique ID
- Content or URL
- A state (representing its position in the processing pipeline)
- Media type
- Parent-child relationships
- Custom metadata

Documents maintain lineage through parent-child relationships, allowing you to track a document's full processing history.

### DocumentState

A `DocumentState` represents a specific state in the document lifecycle, such as:
- `link`: Initial state with a URL to be fetched
- `download`: Content has been downloaded
- `chunk`: Document has been split into chunks
- `embed`: Document has been embedded into vector representation

States are immutable value objects identified by name.

### Transition

A `Transition` connects two DocumentStates and defines how to transform a document from one state to another. Each transition has:
- A from_state
- A to_state
- A process_func (async function that transforms documents)

### DocumentType

A `DocumentType` defines the state machine for a type of document, containing:
- All possible states
- Valid transitions between states
- Methods to retrieve possible transitions and identify final states

### Docstore

The `Docstore` manages persistence and processing of documents:
- Stores documents in a database
- Executes state transitions
- Maintains document relationships
- Provides query capabilities for document retrieval
- Supports streaming for large document content
- Implements concurrency controls for parallel processing

## API Reference

### Document

```python
class Document(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    content: Optional[str] = None
    media_type: str = Field(default="text/plain")
    url: Optional[str] = None
    state: str
    parent_id: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Properties
    @property
    def is_root(self) -> bool:
        """Check if this document is a root document (has no parent)."""
        
    @property
    def has_children(self) -> bool:
        """Check if this document has child documents."""
        
    # Methods
    def add_child(self, child_id: str) -> None:
        """Add a child document ID to this document."""
        
    def add_children(self, child_ids: List[str]) -> None:
        """Add multiple child document IDs to this document."""
```

### DocumentState

```python
class DocumentState(BaseModel):
    name: str
    
    def __eq__(self, other):
        """Equality comparison with DocumentState objects or strings."""
        
    def __hash__(self):
        """Hash implementation for use in collections."""
        
    @lru_cache(maxsize=128)
    def __str__(self) -> str:
        """String representation with caching for performance."""
```

### Transition

```python
class Transition(BaseModel):
    from_state: DocumentState
    to_state: DocumentState
    process_func: Any  # Async function
    
    @model_validator(mode='after')
    def validate_process_func(self) -> 'Transition':
        """Validate that process_func is a callable."""
```

### DocumentType

```python
class DocumentType(BaseModel):
    states: List[DocumentState]
    transitions: List[Transition]
    transition_cache: Dict[str, List[Transition]] = Field(default_factory=dict, exclude=True)
    final_states_cache: Optional[List[DocumentState]] = Field(default=None, exclude=True)
    
    @property
    def final(self) -> List[DocumentState]:
        """Return list of final states (states with no outgoing transitions)"""
        
    def get_transition(self, from_state: Union[DocumentState, str]) -> List[Transition]:
        """Get all possible transitions from a given state."""
        
    @model_validator(mode='after')
    def validate_states_and_transitions(self) -> 'DocumentType':
        """Validate that all states referenced in transitions exist in the states list."""
```

### Docstore

```python
class Docstore:
    def __init__(
        self,
        connection_string: str,
        document_type: Optional[DocumentType] = None,
        error_state: Optional[str] = None,
        max_concurrency: int = 10,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
        echo: bool = False,
    ):
        """Initialize the Docstore with a database connection and document type."""
        
    async def initialize(self):
        """Initialize the database by creating all tables if they don't exist."""
        
    async def dispose(self):
        """Close all connections in the connection pool."""
        
    def set_document_type(self, document_type: DocumentType) -> None:
        """Set the document type for this Docstore."""
        
    @property
    async def final_state_names(self) -> List[str]:
        """Get the names of all final states."""
        
    async def add(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]:
        """Add a document or list of documents to the store and return the ID(s)."""
        
    async def get(
        self, id: Optional[str] = None, state: Optional[str] = None, include_content: bool = True
    ) -> Union[Document, List[Document], None]:
        """Retrieve document(s) by ID, state, or all documents if no filters provided."""
        
    async def get_batch(self, ids: List[str]) -> List[Document]:
        """Efficiently retrieve multiple documents by their IDs in a single query."""
        
    async def delete(self, id: str) -> None:
        """Delete a document from the store."""
        
    async def update(self, doc: Union[Document, str], **kwargs) -> Document:
        """Update the metadata of a document."""
        
    async def next(self, docs: Union[Document, List[Document]]) -> List[Document]:
        """Process document(s) to their next state according to the document type."""
        
    async def list(
        self, 
        state: str, 
        leaf: bool = True, 
        include_content: bool = True,
        **kwargs
    ) -> List[Document]:
        """Return a list of documents with the specified state and metadata filters."""
        
    async def finish(self, docs: Union[Document, List[Document]]) -> List[Document]:
        """Process document(s) through the entire pipeline until all reach a final state."""
        
    async def stream_content(self, doc_id: str, chunk_size: int = 1024) -> AsyncGenerator[str, None]:
        """Stream the content of a document in chunks to handle large documents efficiently."""
        
    async def count(self, state: Optional[str] = None) -> int:
        """Count documents, optionally filtered by state."""
```

### Utility Functions

```python
def configure_logging(level=logging.INFO, enable_stdout=True, log_file=None):
    """Configure the docstate logger with a standardized format and handlers."""
    
def log_document_transition(from_state, to_state, doc_id, success=True, error=None):
    """Log a document state transition with relevant details."""
    
def log_document_processing(doc_id, process_function, start_time=None):
    """Log document processing information, optionally including duration."""
    
def log_document_operation(operation, doc_id, details=None):
    """Log general document operations like creation, deletion, updates."""
    
def async_timed():
    """Decorator for timing async functions and logging their execution time."""
    
async def gather_with_concurrency(n, *tasks):
    """Run tasks concurrently with a limit on the number of concurrent tasks."""
```

## Examples

### Example 1: "Hello World" - Simple Document Processing

This basic example demonstrates creating and processing a document through a simple state machine:

```python
import asyncio
from docstate import Document, DocumentState, DocumentType, Transition, Docstore

# Define a simple async processing function
async def hello_world_processor(doc: Document) -> Document:
    """Transform content to uppercase and add greeting."""
    content = f"Hello, World! Original content: {doc.content.upper()}"
    return Document(
        content=content,
        state="processed",
        parent_id=doc.id,
        metadata={"source": doc.metadata, "transformation": "uppercase"}
    )

async def main():
    # Define document states
    initial = DocumentState(name="initial")
    processed = DocumentState(name="processed")
    
    # Define a transition between states
    transition = Transition(
        from_state=initial,
        to_state=processed,
        process_func=hello_world_processor
    )
    
    # Create a document type with states and transitions
    doc_type = DocumentType(
        states=[initial, processed],
        transitions=[transition]
    )
    
    # Create Docstore with in-memory SQLite database
    async_docstore = Docstore(
        connection_string="sqlite+aiosqlite:///:memory:",
        document_type=doc_type
    )
    
    # Initialize the database
    await async_docstore.initialize()
    
    # Create a sample document
    sample_doc = Document(
        content="sample text",
        state="initial",
        metadata={"source": "example"}
    )
    
    # Add document to the store
    doc_id = await async_docstore.add(sample_doc)
    print(f"Added document with ID: {doc_id}")
    
    # Process the document to its next state
    processed_docs = await async_docstore.next(sample_doc)
    
    # Print the processed document
    for doc in processed_docs:
        print(f"Processed document content: {doc.content}")
        print(f"Metadata: {doc.metadata}")
    
    # Clean up
    await async_docstore.dispose()

if __name__ == "__main__":
    asyncio.run(main())
```

### Example 2: Complete RAG (Retrieval Augmented Generation) Workflow

This example demonstrates a more complex document processing pipeline for RAG applications, including downloading web content, chunking, and embedding:

```python
import asyncio
import httpx
from docstate import Document, DocumentState, DocumentType, Transition, Docstore

# Define processing functions
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

async def chunk_document(doc: Document) -> list[Document]:
    """Split document into multiple chunks based on paragraphs."""
    if not doc.content:
        raise ValueError(f"Expected content for document with ID {doc.id}")
    
    # Simple chunking by paragraphs (double newlines)
    chunks = [chunk for chunk in doc.content.split("\n\n") if chunk.strip()]
    
    # If no chunks were found or only one small chunk, keep as a single chunk
    if len(chunks) <= 1 and len(doc.content) < 1000:
        chunks = [doc.content]
    
    return [
        Document(
            content=chunk,
            media_type="text/plain",
            state="chunk",
            parent_id=doc.id,
            metadata={
                **doc.metadata,
                "chunk_index": i,
                "total_chunks": len(chunks)
            }
        )
        for i, chunk in enumerate(chunks)
    ]

async def embed_document(doc: Document) -> Document:
    """Create a simple vector embedding for the document based on character frequency."""
    if not doc.content:
        raise ValueError(f"Expected content for document with ID {doc.id}")
    
    # Simple embedding based on character frequency (for demonstration only)
    # In a real application, you would use a proper embedding model
    content = doc.content.lower()
    
    # Count character frequencies for a-z and create a simple 26-dim vector
    embedding = [0] * 26
    for char in content:
        if 'a' <= char <= 'z':
            embedding[ord(char) - ord('a')] += 1
    
    # Normalize the embedding if it's not all zeros
    total = sum(embedding)
    if total > 0:
        embedding = [val/total for val in embedding]
    
    return Document(
        content=str(embedding),  # Store embedding as string
        media_type="application/vector",
        state="embed",
        parent_id=doc.id,
        metadata={
            **doc.metadata,
            "vector_dimensions": len(embedding),
            "embedding_method": "character_frequency"
        }
    )

async def summarize_document(doc: Document) -> Document:
    """Create a simple summary of the document."""
    if not doc.content:
        raise ValueError(f"Expected content for document with ID {doc.id}")
    
    # Simple summarization by taking the first 100 characters
    summary = doc.content[:100] + "..." if len(doc.content) > 100 else doc.content
    
    return Document(
        content=summary,
        media_type="text/plain",
        state="summary",
        parent_id=doc.id,
        metadata={
            **doc.metadata,
            "summary_method": "first_100_chars",
            "original_length": len(doc.content)
        }
    )

async def extract_topics(doc: Document) -> Document:
    """Extract simple topics from document based on word frequency."""
    if not doc.content:
        raise ValueError(f"Expected content for document with ID {doc.id}")
    
    # Simple topic extraction by finding most common words
    content = doc.content.lower()
    # Remove punctuation
    for char in ",.?!;:()[]{}\"'":
        content = content.replace(char, " ")
    
    # Count word frequencies
    words = content.split()
    word_count = {}
    for word in words:
        if len(word) > 3:  # Skip short words
            word_count[word] = word_count.get(word, 0) + 1
    
    # Get top 5 words as topics
    topics = sorted(word_count.items(), key=lambda x: x[1], reverse=True)[:5]
    topic_list = [word for word, count in topics]
    
    return Document(
        content=str(topic_list),
        media_type="application/json",
        state="topics",
        parent_id=doc.id,
        metadata={
            **doc.metadata,
            "topic_count": len(topic_list),
            "extraction_method": "word_frequency"
        }
    )

async def main():
    # Define document states
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    chunk = DocumentState(name="chunk")
    embed = DocumentState(name="embed")
    summary = DocumentState(name="summary")
    topics = DocumentState(name="topics")

    # Define transitions between states
    transitions = [
        Transition(from_state=link, to_state=download, process_func=download_document),
        Transition(from_state=download, to_state=chunk, process_func=chunk_document),
        Transition(from_state=chunk, to_state=embed, process_func=embed_document),
        Transition(from_state=download, to_state=summary, process_func=summarize_document),
        Transition(from_state=download, to_state=topics, process_func=extract_topics),
    ]

    # Create document type with states and transitions
    doc_type = DocumentType(
        states=[link, download, chunk, embed, summary, topics],
        transitions=transitions
    )

    # Create Docstore with SQLite database
    async_docstore = Docstore(
        connection_string="sqlite+aiosqlite:///rag_example.db",
        document_type=doc_type,
        max_concurrency=5  # Process up to 5 documents in parallel
    )

    # Initialize the database
    await async_docstore.initialize()

    # Create sample documents to process
    sample_docs = [
        Document(
            url="https://www.python.org/about/",
            state="link",
            metadata={"source": "example", "topic": "python"}
        )
    ]

    # Add documents to the store
    doc_ids = await async_docstore.add(sample_docs)
    print(f"Added {len(doc_ids)} documents")

    # First, download the documents
    downloaded_docs = await async_docstore.next(sample_docs)
    print(f"Downloaded {len(downloaded_docs)} documents")
    
    # Create summary and extract topics from the downloaded document
    for doc in downloaded_docs:
        # Create summary
        summary_docs = await async_docstore.next(doc)
        print(f"Created summary: {summary_docs[0].content if summary_docs else 'None'}")
        
        # Extract topics
        topics_docs = await async_docstore.next(doc)
        print(f"Extracted topics: {topics_docs[0].content if topics_docs else 'None'}")
        
        # Chunk the document
        chunk_docs = await async_docstore.next(doc)
        print(f"Created {len(chunk_docs)} chunks")
        
        # Embed all chunks
        all_embeddings = []
        for chunk_doc in chunk_docs:
            embed_docs = await async_docstore.next(chunk_doc)
            all_embeddings.extend(embed_docs)
        
        print(f"Created {len(all_embeddings)} embeddings")
    
    # Count documents in each state
    for state in ["link", "download", "chunk", "embed", "summary", "topics"]:
        count = await async_docstore.count(state)
        print(f"Documents in state '{state}': {count}")

    # Clean up
    await async_docstore.dispose()

if __name__ == "__main__":
    asyncio.run(main())
```

## Advanced Usage

### Stream Large Document Content

For large documents, you can use streaming to process content in chunks:

```python
async def process_large_document(doc_id, async_docstore):
    """Process a large document by streaming its content in chunks."""
    async for content_chunk in async_docstore.stream_content(doc_id, chunk_size=1024):
        # Process each chunk of content
        print(f"Processing chunk of size {len(content_chunk)}")
```

### Concurrency Control

Control the number of documents processed in parallel:

```python
# Create Docstore with specific concurrency limit
async_docstore = Docstore(
    connection_string="sqlite+aiosqlite:///example.db",
    document_type=doc_type,
    max_concurrency=10  # Process up to 10 documents in parallel
)
```

### Custom Error Handling

Define a custom error state and handle document processing errors:

```python
# Create Docstore with custom error state
async_docstore = Docstore(
    connection_string="sqlite+aiosqlite:///example.db",
    document_type=doc_type,
    error_state="failed_processing"  # Custom error state name
)

# Process documents and handle errors
processed_docs = await async_docstore.next(docs)
error_docs = await async_docstore.list(state="failed_processing")

# Analyze errors
for doc in error_docs:
    print(f"Error processing document {doc.parent_id}: {doc.metadata.get('error')}")
```

### Custom Logging

Configure custom logging for document operations:

```python
from docstate.utils import configure_logging
import logging

# Configure logging with custom settings
configure_logging(
    level=logging.DEBUG,
    enable_stdout=True,
    log_file="docstate.log"
)
