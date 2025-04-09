from typing import Optional, List, Dict, Any, Callable
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID

class DocumentVersion(BaseModel):
    """Represents a specific version of a document."""
    version_id: UUID = Field(..., description="Unique identifier for this version.")
    created_at: datetime = Field(..., description="Timestamp when this version was created.")
    reason: str = Field(..., description="Description of why this version was created.")
    content: Any = Field(..., description="The actual content of this version.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about this version.")

class DocumentState(BaseModel):
    """Represents a specific state within a document's lifecycle."""
    name: str = Field(..., description="The unique name of the state (e.g., 'downloaded', 'chunked').")
    description: Optional[str] = Field(None, description="An optional description of the state.")
    allows_multiple_outputs: bool = Field(default=False, description="Whether transitions from this state can produce multiple outputs.")

    def __eq__(self, other):
        pass

    def __hash__(self):
        pass

    def __repr__(self):
        pass

class DocumentType(BaseModel):
    """Defines a type of document and its associated state machine."""
    name: str = Field(..., description="The unique name for this document type.")
    states: List[DocumentState] = Field(..., description="An ordered list of possible states.")
    initial_state: DocumentState = Field(..., description="The starting state for new documents.")

    def __repr__(self):
        pass

class DocumentLineage(BaseModel):
    """Tracks relationships between document versions."""
    source_id: UUID = Field(..., description="ID of the source document version.")
    target_id: UUID = Field(..., description="ID of the target document version.")
    relationship_type: str = Field(..., description="Type of relationship (e.g., 'version', 'branch', 'output').")
    created_at: datetime = Field(..., description="When this relationship was created.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata about the relationship.")

class DocumentInstance(BaseModel):
    """Represents an instance of a document being managed."""
    doc_id: UUID = Field(..., description="The unique identifier for the document instance.")
    doc_type: DocumentType = Field(..., description="The type of the document.")
    current_state: DocumentState = Field(..., description="The current state of this instance.")
    current_version: UUID = Field(..., description="ID of the current version of this document.")
    branch_id: Optional[UUID] = Field(None, description="Unique ID for this branch.")
    parent_branch_id: Optional[UUID] = Field(None, description="ID of the parent branch.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata.")

    def __repr__(self):
        pass

# Type alias for Transition Functions
TransitionFunction = Callable[[DocumentInstance, Any], List[DocumentInstance]]  # Can return multiple instances

class StateTransition(BaseModel):
    """Defines a valid transition between states."""
    doc_type: DocumentType = Field(..., description="The document type this applies to.")
    from_state: DocumentState = Field(..., description="Starting state.")
    to_state: DocumentState = Field(..., description="Ending state.")
    transition_func: TransitionFunction = Field(..., description="Function to execute.")
    creates_new_version: bool = Field(default=True, description="Whether to create a new version.")
    can_produce_multiple: bool = Field(default=False, description="Can produce multiple outputs.")

    def __repr__(self):
        pass
