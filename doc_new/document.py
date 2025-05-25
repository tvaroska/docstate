from typing import Any, Dict, List, Optional, Union, Set
from uuid import uuid4
from functools import lru_cache

from pydantic import BaseModel, Field, model_validator


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
    
    # Cache string representation for better performance
    @lru_cache(maxsize=128)
    def __str__(self) -> str:
        return self.name


class Transition(BaseModel):
    """Represents a transition between document states."""

    from_state: DocumentState
    to_state: DocumentState
    process_func: Any  # This will be an async function

    model_config = {"arbitrary_types_allowed": True}
    
    @model_validator(mode='after')
    def validate_process_func(self) -> 'Transition':
        """Validate that process_func is a callable."""
        if not callable(self.process_func):
            raise ValueError("process_func must be a callable")
        return self


class DocumentType(BaseModel):
    """Defines the state machine for a document type."""

    states: List[DocumentState]
    transitions: List[Transition]
    
    # Cache for faster access to transitions
    _transition_cache: Dict[str, List[Transition]] = Field(default_factory=dict, exclude=True)
    _final_states_cache: Optional[List[DocumentState]] = Field(default=None, exclude=True)

    @property
    def final(self) -> List[DocumentState]:
        """Return list of final states (states with no outgoing transitions)"""
        # Use cached result if available
        if self._final_states_cache is not None:
            return self._final_states_cache
            
        # A final state is one that has no outgoing transitions
        states_with_transitions = {t.from_state for t in self.transitions}
        final_states = [state for state in self.states if state not in states_with_transitions]
        
        # Cache the result
        self._final_states_cache = final_states
        return final_states

    def get_transition(self, from_state: Union[DocumentState, str]) -> List[Transition]:
        """
        Get all possible transitions from a given state.
        
        Uses an internal cache for improved performance.
        """
        # Convert string to DocumentState if needed
        state_name = from_state if isinstance(from_state, str) else from_state.name
        
        # Check cache first
        if state_name in self._transition_cache:
            return self._transition_cache[state_name]
        
        # Convert from_state to DocumentState if it's a string
        if isinstance(from_state, str):
            from_state = DocumentState(name=from_state)

        # Find matching transitions
        matching_transitions = [t for t in self.transitions if t.from_state == from_state]
        
        # Cache the result
        self._transition_cache[state_name] = matching_transitions
        
        return matching_transitions

    @model_validator(mode='after')
    def validate_states_and_transitions(self) -> 'DocumentType':
        """Validate that all states referenced in transitions exist in the states list."""
        state_names = {state.name for state in self.states}
        for transition in self.transitions:
            if transition.from_state.name not in state_names:
                raise ValueError(f"Transition references unknown from_state: {transition.from_state.name}")
            if transition.to_state.name not in state_names:
                raise ValueError(f"Transition references unknown to_state: {transition.to_state.name}")
        return self

    model_config = {"arbitrary_types_allowed": True}


class Document(BaseModel):
    """
    Represents a document in the processing pipeline.

    A document has a unique ID, a state, content, and relationships
    to parent and child documents. The document follows a state machine
    defined by its DocumentType.
    
    This implementation is optimized for performance with proper caching
    and minimal memory usage.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    content: Optional[str] = None
    media_type: str = Field(
        default="text/plain",
        description="Media type of the content (e.g., text/plain, application/pdf)",
    )
    url: Optional[str] = None
    state: str
    parent_id: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}

    @property
    def is_root(self) -> bool:
        """Check if this document is a root document (has no parent)."""
        return self.parent_id is None

    @property
    def has_children(self) -> bool:
        """Check if this document has child documents."""
        return bool(self.children)

    def add_child(self, child_id: str) -> None:
        """Add a child document ID to this document."""
        if child_id not in self.children:
            self.children.append(child_id)
            
    def add_children(self, child_ids: List[str]) -> None:
        """
        Add multiple child document IDs to this document.
        More efficient than calling add_child multiple times.
        """
        current_children = set(self.children)
        # Add only new children that don't already exist
        new_children = [id for id in child_ids if id not in current_children]
        if new_children:
            self.children.extend(new_children)
