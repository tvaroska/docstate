# Tech Context: Document Processing Pipeline

## Technologies Used

### Core Technologies
- **Python 3.8+**: Primary implementation language
- **SQLAlchemy**: ORM for database interactions with SQLite and PostgreSQL backends
- **Async IO**: Python's asynchronous programming framework for non-blocking operations
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
  - `docstate/` - Core library code (document.py, docstate.py)
  - `examples/` - Example implementations like RAG
  - `tests/` - Comprehensive test suite

## Technical Constraints
1. **Async Compatibility**: All processing functions are implemented as async functions
2. **State Flow Integrity**: Documents must follow the defined state transitions in the DocumentType
3. **Database Compatibility**: Supports both SQLite and PostgreSQL backends via SQLAlchemy
4. **Memory Efficiency**: The chunking approach allows processing large documents in smaller pieces
5. **Vector Database Integration**: Using PGVector and VertexAI for embeddings
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
    def __init__(self, connection_string: str, document_type: Optional[DocumentType] = None, error_state: Optional[str] = None): ...
    
    def set_document_type(self, document_type: DocumentType) -> None: ...
    
    def add(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]: ...
    
    def get(self, id: Optional[str] = None, state: Optional[str] = None) -> Union[Document, List[Document], None]: ...
    
    def delete(self, id: str) -> None: ...
    
    def update(self, doc: Union[Document, str], **kwargs) -> Document: ...
    
    def list(self, state: str, leaf: bool = True, **kwargs) -> Document: ...
    
    async def next(self, docs: Union[Document, List[Document]]) -> List[Document]: ...
    
    async def finish(self, docs: Union[Document, List[Document]]) -> List[Document]: ...
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

### Processing Functions in RAG Example

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
    
    id = vectorstore.add_texts([doc.content])
    id = [0]

    return Document(
        content=str(id[0]),  # Store embedding as string
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

### RAG Example Usage
```python
# Import the necessary components
from typing import List
import asyncio
import httpx
from docstate.document import Document
from docstate.docstate import DocStore, DocumentType, DocumentState, Transition

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_postgres import PGVector
from langchain_google_vertexai import VertexAIEmbeddings

# Database connection string
DB = 'postgresql://postgres:postgres@localhost/postgres'

# Initialize embeddings and vector store
embeddings = VertexAIEmbeddings(model="text-embedding-004")
vectorstore = PGVector(
    connection=DB,
    embeddings=embeddings
)

# Define document states and transitions
link = DocumentState(name="link")
download = DocumentState(name="download")
chunk = DocumentState(name="chunk")
embed = DocumentState(name="embed")

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

# Process a document through the entire pipeline with error handling
doc = Document(
    url='https://docs.pydantic.dev/latest/llms.txt',
    state='link'
)

await docstore.finish(doc)

# Process a document with an invalid URL to demonstrate error handling
error_doc = Document(
    url='htt://docs.pydantic.dev/latest/llms.txt',
    state='link'
)

await docstore.finish(error_doc)

# Examples of using the list method
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
```
