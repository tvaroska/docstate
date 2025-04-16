from typing import List, Optional, Any, Dict, Union
from uuid import uuid4
from pydantic import BaseModel, Field


class DocumentState(BaseModel):
    """Represents a possible state in the document lifecycle."""
    name: str

    def __eq__(self, other):
        if isinstance(other, DocumentState):
            return self.name == other.name
        elif isinstance(other, str):
            return self.name == other
        return False
    
    def __hash__(self):
        return hash(self.name)


class Transition(BaseModel):
    """Represents a transition between document states."""
    from_state: DocumentState
    to_state: DocumentState
    process_func: Any  # This will be an async function

    model_config = {
        "arbitrary_types_allowed": True
    }


class DocumentType(BaseModel):
    """Defines the state machine for a document type."""
    states: List[DocumentState]
    transitions: List[Transition]

    @property
    def final(self) -> List[DocumentState]:
        """Return list of final states (states with no outgoing transitions)"""
        # A final state is one that has no outgoing transitions
        states_with_transitions = {t.from_state for t in self.transitions}
        return [state for state in self.states if state not in states_with_transitions]

    def get_transition(self, from_state: Union[DocumentState, str]) -> List[Transition]:
        """Get all possible transitions from a given state."""
        if isinstance(from_state, str):
            from_state = DocumentState(name=from_state)
            
        return [t for t in self.transitions if t.from_state == from_state]
    
    model_config = {
        "arbitrary_types_allowed": True
    }


class Document(BaseModel):
    """
    Represents a document in the processing pipeline.
    
    A document has a unique ID, a state, content, and relationships
    to parent and child documents. The document follows a state machine
    defined by its DocumentType.
    """
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
    def is_root(self) -> bool:
        """Check if this document is a root document (has no parent)."""
        return self.parent_id is None
    
    @property
    def has_children(self) -> bool:
        """Check if this document has child documents."""
        return len(self.children) > 0
    
    def add_child(self, child_id: str) -> None:
        """Add a child document ID to this document."""
        if child_id not in self.children:
            self.children.append(child_id)
