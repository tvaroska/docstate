# Tech Context: Document Processing Pipeline

## Technologies Used

### Core Technologies
- **Python 3.8+**: Primary implementation language
- **SQLAlchemy**: ORM for database interactions with SQLite backend
- **Async IO**: Python's asynchronous programming framework for non-blocking operations
- **Pydantic**: Provides BaseModel for data validation, serialization, and type safety
- **Type Hints**: Extensive use of Python type annotations for better code quality
- **httpx**: Asynchronous HTTP client for document downloading
- **UUID**: For generating unique document identifiers

## Development Setup
- Python virtual environment management with uv
- Testing with pytest - tests run with `uv run pytest`
- SQLite and Postgresql databases for development and testing
- Type checking with mypy is supported through type annotations
- Project structure:
  - `docstate/` - Core library code (document.py, doc_store.py)
  - `processing.py` - Processing functions implementation
  - `example.py` - Demonstration of the API

## Technical Constraints
1. **Async Compatibility**: All processing functions are implemented as async functions
2. **State Flow Integrity**: Documents must follow the defined state transitions in the DocumentType
3. **Database Compatibility**: Currently SQLite-based, but SQLAlchemy allows for other backends
4. **Memory Efficiency**: The chunking approach allows processing large documents in smaller pieces
5. **Vector Database Integration**: Currently simulated with content hashing, will need real integration
6. **Parent-Child Relationships**: Must maintain document lineage throughout transformations

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
```

### DocStore Interface
```python
class DocStore:
    def __init__(self, connection_string: str, document_type: Optional[DocumentType] = None): ...
    
    def set_document_type(self, document_type: DocumentType) -> None: ...
    
    def add(self, doc: Document) -> str: ...
    
    def get(self, id: Optional[str] = None, state: Optional[str] = None) -> Union[Document, List[Document], None]: ...
    
    def delete(self, id: str) -> None: ...
    
    async def next(self, docs: Union[Document, List[Document]]) -> List[Document]: ...
```

### State Machine Components
```python
class DocumentState(BaseModel):
    name: str
    
    def __eq__(self, other): ...
    
    def __hash__(self): ...

class Transition(BaseModel):
    from_state: DocumentState
    to_state: DocumentState
    process_func: Any  # Async function
    
    model_config = {
        "arbitrary_types_allowed": True
    }

class DocumentType(BaseModel):
    states: List[DocumentState]
    transitions: List[Transition]
    
    @property
    def final(self) -> List[DocumentState]:
        """Return list of final states (states with no outgoing transitions)"""
        # A final state is one that has no outgoing transitions
        states_with_transitions = {t.from_state for t in self.transitions}
        return [state for state in self.states if state not in states_with_transitions]
    
    def get_transition(self, from_state: Union[DocumentState, str]) -> List[Transition]: ...
    
    model_config = {
        "arbitrary_types_allowed": True
    }
```

### Processing Functions

```python
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
```

### SQLAlchemy Model
```python
class DocumentModel(Base):
    """SQLAlchemy model for document storage."""
    __tablename__ = 'documents'
    
    id = Column(String, primary_key=True)
    state = Column(String, nullable=False)
    content = Column(JSON, nullable=True)
    media_type = Column(String, default='text/plain')
    url = Column(String, nullable=True)
    parent_id = Column(String, ForeignKey('documents.id'), nullable=True)
    children = relationship("DocumentModel", backref=backref("parent", remote_side=[id]), cascade="all, delete-orphan")
    cmetadata = Column(JSON, nullable=False, default={})
```

### Example Usage
```python
# Define document states
link = DocumentState(name="link")
download = DocumentState(name="download")
chunk = DocumentState(name="chunk") 
embed = DocumentState(name="embed")

# Define document type with state transitions
document_type = DocumentType(
    states=[link, download, chunk, embed],
    transitions=[
        Transition(from_state=link, to_state=download, process_func=download_document),
        Transition(from_state=download, to_state=chunk, process_func=chunk_document),
        Transition(from_state=chunk, to_state=embed, process_func=embed_document),
    ]
)

# Create a DocStore with PostgreSQL backend in RAG example
docstore = DocStore(connection_string="postgresql://postgres:postgres@localhost/postgres")
doc = Document(
    url="https://docs.pydantic.dev/latest/llms.txt",
    state="link"
)
docstore.add(doc)

# Sample file contains the following flow (with syntax errors)
# id = docstore.add(doc)
# doc2 = docstore.next(doc)
# assert doc2.parent_id == id
# assert doc2.state == 'download'
# 
# old_doc = docstore.get(id=id)
# assert doc2.id in old_doc.children
# 
# doc3 = docstore.next(doc)
# assert doc3.parent_id == id
# 
# all_downloads = docstore.get(state='download')
