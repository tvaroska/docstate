# Tech Context: Document Processing Pipeline

## Technologies Used

### Core Technologies
- **Python 3.8+**: Primary implementation language
- **SQLAlchemy with Async Support**: ORM for database interactions with SQLite and PostgreSQL backends
- **Asyncio**: Python's asynchronous programming framework for non-blocking operations
- **Pydantic**: Provides BaseModel for data validation, serialization, and type safety
- **Type Hints**: Extensive use of Python type annotations for better code quality
- **httpx**: Asynchronous HTTP client for document downloading
- **UUID**: For generating unique document identifiers
- **LangChain**: For text splitters and vector database integrations
- **PGVector**: PostgreSQL vector storage extension
- **VertexAI**: Google's AI platform for embeddings

## Development Setup
- Python virtual environment management with uv
- Testing with pytest - tests run with `uv run pytest`
- SQLite and PostgreSQL databases for development and testing
- Type checking with mypy is supported through type annotations
- Project structure:
  - `docstate/` - Core library code
    - `document.py` - Document, DocumentState, DocumentType, and Transition classes
    - `docstate.py` - AsyncDocStore implementation
    - `database.py` - SQLAlchemy models
    - `utils.py` - Utility functions and decorators
  - `examples/` - Example implementations like RAG
  - `tests/` - Comprehensive test suite

## Technical Constraints
1. **Async Compatibility**: All processing functions are implemented as async functions
2. **State Flow Integrity**: Documents must follow the defined state transitions in the DocumentType
3. **Database Compatibility**: Supports both SQLite and PostgreSQL backends via SQLAlchemy
4. **Memory Efficiency**: Streaming support for handling large documents
5. **Vector Database Integration**: Using PGVector and VertexAI for embeddings
6. **Parent-Child Relationships**: Must maintain document lineage throughout transformations
7. **Performance Considerations**: Optimized for high-volume document processing

## Technical Interfaces

### Document Class
```python
class Document(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    content: Optional[str] = None
    media_type: str = Field(default="text/plain", description="Media type of the content (e.g., text/plain, application/pdf)")
    url: Optional[str] = None
    state: str
    parent_id: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "arbitrary_types_allowed": True
    }
    
    @property
    def is_root(self) -> bool: ...
    
    @property
    def has_children(self) -> bool: ...
    
    def add_child(self, child_id: str) -> None: ...
    
    def add_children(self, child_ids: List[str]) -> None: ...
```

### AsyncDocStore Interface
```python
class AsyncDocStore:
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
    ): ...
    
    async def initialize(self): ...
    
    async def dispose(self): ...
    
    def set_document_type(self, document_type: DocumentType) -> None: ...
    
    @property
    async def final_state_names(self) -> List[str]: ...
    
    async def add(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]: ...
    
    async def get(
        self, id: Optional[str] = None, state: Optional[str] = None, include_content: bool = True
    ) -> Union[Document, List[Document], None]: ...
    
    async def get_batch(self, ids: List[str]) -> List[Document]: ...
    
    async def delete(self, id: str) -> None: ...
    
    async def update(self, doc: Union[Document, str], **kwargs) -> Document: ...
    
    async def next(self, docs: Union[Document, List[Document]]) -> List[Document]: ...
    
    async def list(
        self, 
        state: str, 
        leaf: bool = True, 
        include_content: bool = True,
        **kwargs
    ) -> List[Document]: ...
    
    async def finish(self, docs: Union[Document, List[Document]]) -> List[Document]: ...
    
    async def stream_content(self, doc_id: str, chunk_size: int = 1024) -> AsyncGenerator[str, None]: ...
    
    async def count(self, state: Optional[str] = None) -> int: ...
```

### State Machine Components
```python
class DocumentState(BaseModel):
    name: str
    
    def __eq__(self, other): ...
    
    def __hash__(self): ...
    
    @lru_cache(maxsize=128)
    def __str__(self) -> str: ...

class Transition(BaseModel):
    from_state: DocumentState
    to_state: DocumentState
    process_func: Any  # Async function
    
    model_config = {
        "arbitrary_types_allowed": True
    }
    
    @model_validator(mode='after')
    def validate_process_func(self) -> 'Transition': ...

class DocumentType(BaseModel):
    states: List[DocumentState]
    transitions: List[Transition]
    transition_cache: Dict[str, List[Transition]] = Field(default_factory=dict, exclude=True)
    final_states_cache: Optional[List[DocumentState]] = Field(default=None, exclude=True)
    
    @property
    def final(self) -> List[DocumentState]: ...
    
    def get_transition(self, from_state: Union[DocumentState, str]) -> List[Transition]: ...
    
    @model_validator(mode='after')
    def validate_states_and_transitions(self) -> 'DocumentType': ...
    
    model_config = {
        "arbitrary_types_allowed": True
    }
```

### Processing Functions Pattern

```python
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
    """Split document into multiple chunks."""
    # Implementation logic for chunking
    chunks = []  # Chunking logic here
    
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
    """Create a vector embedding for the document."""
    # Implementation for embedding
    
    return Document(
        content=str(embedding),  # Store embedding as string
        media_type="application/vector",
        state="embed",
        parent_id=doc.id,
        metadata={
            **doc.metadata,
            "vector_dimensions": len(embedding),
            "embedding_method": "method_name"
        }
    )
```

### SQLAlchemy Model
```python
class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass

class DocumentModel(Base):
    """SQLAlchemy model for document storage."""
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    state = Column(String, nullable=False, index=True)
    content = Column(String, nullable=True)
    media_type = Column(String, default="text/plain", index=True)
    url = Column(String, nullable=True, index=True)
    parent_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    
    children = relationship(
        "DocumentModel",
        backref=backref("parent", remote_side=[id], lazy='selectin'),
        cascade="all, delete-orphan",
        lazy='selectin'
    )
    
    cmetadata = Column(JSON, nullable=False, default={})
    
    __table_args__ = (
        Index('idx_state_media_type', 'state', 'media_type'),
        Index('idx_parent_state', 'parent_id', 'state'),
    )
```

### Utility Functions
```python
@async_timed()
def timed_function(): ...

async def gather_with_concurrency(n, *tasks): ...

def configure_logging(level=logging.INFO, enable_stdout=True, log_file=None): ...

def log_document_transition(from_state, to_state, doc_id, success=True, error=None): ...

def log_document_processing(doc_id, process_function, start_time=None): ...

def log_document_operation(operation, doc_id, details=None): ...
```

### RAG Example Usage
```python
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

# Create AsyncDocStore with SQLite database
async_docstore = AsyncDocStore(
    connection_string="sqlite:///rag_example.db",
    document_type=doc_type,
    max_concurrency=5  # Process up to 5 documents in parallel
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
    )
]

# Add documents to the store
doc_ids = await async_docstore.add(sample_docs)

# Process all documents through the entire pipeline
final_docs = await async_docstore.finish(sample_docs)

# Stream content from a large document
async for content_chunk in async_docstore.stream_content(doc_id, chunk_size=200):
    # Process each chunk
    pass
