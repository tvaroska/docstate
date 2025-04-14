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
- SQLite database for development and testing
- Type checking with mypy is supported through type annotations
- Project structure:
  - `a2/` - Core library code (document.py, doc_store.py)
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
    content_type: str = Field(description="Type of content - text, uri, ...")
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
    
    async def next(self, doc: Document) -> Union[Document, List[Document]]: ...
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
    """
    Download content from the URL in the document.
    
    Args:
        doc: A Document in the 'link' state with a URL in the content field
        
    Returns:
        A new Document in the 'download' state with the downloaded content
    """
    if doc.content_type != "uri":
        raise ValueError(f"Expected content_type 'uri', got '{doc.content_type}'")
    
    try:
        # In a real implementation, we would use proper error handling,
        # timeouts, retries, etc.
        async with httpx.AsyncClient() as client:
            # Use a timeout to prevent hanging on slow requests
            response = await client.get(doc.content, timeout=10.0)
            response.raise_for_status()
            content = response.text
            
            # For this example, we'll limit content length to prevent huge documents
            if len(content) > 10000:
                content = content[:10000] + "...[truncated]"
                
    except httpx.RequestError as e:
        # Return a document with error information
        return Document(
            content=f"Error downloading content: {str(e)}",
            content_type="text",
            state="download",
            metadata={
                "source_url": doc.content,
                "error": str(e),
                "success": False
            }
        )
    
    # Return a new document with the downloaded content
    return Document(
        content=content,
        content_type="text",
        state="download",
        metadata={
            "source_url": doc.content,
            "content_length": len(content),
            "success": True
        }
    )

async def chunk_document(doc: Document) -> List[Document]:
    """
    Split a document into smaller chunks.
    
    Args:
        doc: A Document in the 'download' state with text content
        
    Returns:
        A list of new Documents in the 'chunk' state, each containing a chunk of the original content
    """
    if doc.content_type != "text":
        raise ValueError(f"Expected content_type 'text', got '{doc.content_type}'")
    
    # Check if document has an error
    if doc.metadata.get("success") is False:
        return [Document(
            content=doc.content,
            content_type="text",
            state="chunk",
            metadata={
                **doc.metadata,
                "chunk_index": 0,
                "total_chunks": 1
            }
        )]
    
    # Simple paragraph-based chunking strategy
    paragraphs = [p for p in doc.content.split("\n\n") if p.strip()]
    
    # Ensure paragraphs aren't too long by splitting further if needed
    chunks = []
    max_chunk_length = 1000  # Character limit for chunks
    
    for paragraph in paragraphs:
        # If paragraph is short enough, add it directly
        if len(paragraph) <= max_chunk_length:
            chunks.append(paragraph)
        else:
            # Otherwise, split into sentences and group them
            sentences = [s.strip() + "." for s in paragraph.split(".") if s.strip()]
            current_chunk = []
            current_length = 0
            
            for sentence in sentences:
                if current_length + len(sentence) > max_chunk_length and current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                
                current_chunk.append(sentence)
                current_length += len(sentence) + 1  # +1 for the space
            
            # Add the final chunk if it's not empty
            if current_chunk:
                chunks.append(" ".join(current_chunk))
    
    # If no chunks were created (e.g., empty document), create at least one
    if not chunks:
        chunks = [""]
    
    # Create Document objects for each chunk
    return [
        Document(
            content=chunk,
            content_type="text",
            state="chunk",
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
    Create a vector embedding for a document chunk.
    
    Args:
        doc: A Document in the 'chunk' state with text content
        
    Returns:
        A new Document in the 'embed' state with the embedding vector as content
    """
    if doc.content_type != "text":
        raise ValueError(f"Expected content_type 'text', got '{doc.content_type}'")
    
    # Check if document has an error
    if doc.metadata.get("success") is False:
        # Return a simple placeholder embedding
        return Document(
            content="[0.0]",  # Placeholder embedding
            content_type="vector",
            state="embed",
            metadata={
                **doc.metadata,
                "vector_dimensions": 1,
                "embedding_method": "error_placeholder",
                "embedding_success": False
            }
        )
    
    # In a real implementation, we would use a proper embedding model
    # For this example, we'll use a simple character frequency approach
    text = doc.content.lower()  # Normalize text
    
    # Create a simple embedding based on character frequencies
    char_freq = {}
    for char in text:
        if char.isalnum():
            char_freq[char] = char_freq.get(char, 0) + 1
    
    # Normalize by text length
    text_length = max(1, len(text))
    vector = [char_freq.get(chr(i), 0) / text_length for i in range(97, 123)]  # a-z frequencies
    
    # Return a new document with the embedding vector
    return Document(
        content=str(vector),  # Store embedding as string
        content_type="vector",
        state="embed",
        metadata={
            **doc.metadata,
            "vector_dimensions": len(vector),
            "embedding_method": "char_frequency",
            "embedding_success": True
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
    content_type = Column(String, default='text')
    parent_id = Column(String, ForeignKey('documents.id'), nullable=True)
    children = Column(JSON, nullable=False, default=[])
    cmetadata = Column(JSON, nullable=False, default={})  # Note: Inconsistency with Document.metadata
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

# Create a DocStore with SQLite backend
docstore = DocStore(connection_string="sqlite:///")
doc = Document(content_type="uri", content="http://www.example.com", state="link")
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
