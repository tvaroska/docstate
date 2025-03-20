"""
DocState State Manager

This module implements the core state machine functionality for DocState,
including the StateTransition class and StateManager controller.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, TypeVar, cast

from docstate.constants import DEFAULT_ERROR_SUFFIX, END, START
from docstate.models import Document

# Type definitions
DocumentCallable = Callable[[Document], Document]
T = TypeVar("T", bound=Document)


@dataclass
class StateTransition:
    """
    StateTransition represents a transition from one state to another.
    
    Each transition includes:
    - Source state (from_state)
    - Target state (to_state) 
    - Error state in case of transition failure
    - Function to execute during the transition
    - Name of the transition (derived from the function name)
    """
    from_state: str
    to_state: str
    error_state: Optional[str]
    function: DocumentCallable
    name: str
    
    def __post_init__(self) -> None:
        """Validate the transition after initialization."""
        if not callable(self.function):
            raise ValueError(f"Transition function must be callable, got {type(self.function)}")
        
        if not self.name:
            self.name = self.function.__name__


class StateManager:
    """
    StateManager controls the state transition graph and rules.
    
    This class maintains the registry of valid state transitions and 
    provides methods for validating and executing transitions.
    """
    
    def __init__(self) -> None:
        """Initialize the StateManager with an empty transition registry."""
        # Dictionary mapping from_state to a list of possible transitions
        self._transitions: Dict[str, List[StateTransition]] = {}
        # Set of all known states
        self._states: Set[str] = {START, END}
    
    def register_transition(
        self,
        from_state: str,
        to_state: str,
        func: DocumentCallable,
        *,
        error: Optional[str] = None,
        name: Optional[str] = None,
    ) -> None:
        """
        Register a new state transition.
        
        Args:
            from_state: The source state.
            to_state: The target state after successful transition.
            func: The function to execute during the transition.
            error: The error state to transition to if the function raises an exception.
            name: Optional custom name for the transition (defaults to function name).
        """
        # Add states to known states set
        self._states.add(from_state)
        self._states.add(to_state)
        
        # Set default error state if not provided
        if error is None and from_state != END:
            error = f"{from_state}{DEFAULT_ERROR_SUFFIX}"
            # Add error state to known states
            self._states.add(error)
        
        # Create the transition object
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            error_state=error,
            function=func,
            name=name or func.__name__,
        )
        
        # Add to transitions dictionary
        if from_state not in self._transitions:
            self._transitions[from_state] = []
        
        self._transitions[from_state].append(transition)
    
    def get_transitions_from(self, state: str) -> List[StateTransition]:
        """
        Get all transitions available from a given state.
        
        Args:
            state: The source state.
            
        Returns:
            A list of available transitions from the state.
        """
        return self._transitions.get(state, [])
    
    def get_transition_names_from(self, state: str) -> List[str]:
        """
        Get names of all transitions available from a given state.
        
        Args:
            state: The source state.
            
        Returns:
            A list of transition names.
        """
        return [t.name for t in self.get_transitions_from(state)]
    
    def get_transition(self, state: str, transition_name: str) -> Optional[StateTransition]:
        """
        Get a specific transition by name from a given state.
        
        Args:
            state: The source state.
            transition_name: The name of the transition to find.
            
        Returns:
            The transition if found, None otherwise.
        """
        for transition in self.get_transitions_from(state):
            if transition.name == transition_name:
                return transition
        return None
    
    def validate_transition(self, from_state: str, to_state: str) -> bool:
        """
        Validate if a transition from one state to another is possible.
        
        Args:
            from_state: The source state.
            to_state: The target state.
            
        Returns:
            True if the transition is valid, False otherwise.
        """
        for transition in self.get_transitions_from(from_state):
            if transition.to_state == to_state:
                return True
        return False
    
    def execute_transition(
        self, document: Document, transition_name: Optional[str] = None
    ) -> Tuple[Document, str, Optional[Exception]]:
        """
        Execute a transition on a document.
        
        Args:
            document: The document to transform.
            transition_name: Optional name of the transition to execute.
                If not provided, the first available transition will be used.
                
        Returns:
            A tuple containing:
            - The transformed document
            - The new state
            - An exception if one was caught, None otherwise
        """
        current_state = document.state
        transitions = self.get_transitions_from(current_state)
        
        if not transitions:
            return document, current_state, ValueError(f"No transitions available from state '{current_state}'")
        
        # Find the specific transition if a name was provided
        transition = None
        if transition_name:
            transition = self.get_transition(current_state, transition_name)
            if not transition:
                return document, current_state, ValueError(
                    f"No transition named '{transition_name}' available from state '{current_state}'"
                )
        else:
            # Use the first available transition if none specified
            transition = transitions[0]
        
        # Execute the transition
        try:
            result = transition.function(document)
            new_state = transition.to_state
            return result, new_state, None
        except Exception as e:
            # If there's an error, transition to the error state
            if transition.error_state:
                return document, transition.error_state, e
            # If no error state is defined, remain in the current state
            return document, current_state, e
    
    def transition(
        self,
        from_state: str,
        to_state: str,
        *,
        error: Optional[str] = None,
        name: Optional[str] = None,
    ) -> Callable[[DocumentCallable], DocumentCallable]:
        """
        Decorator for registering state transitions.
        
        Args:
            from_state: The source state.
            to_state: The target state after successful transition.
            error: The error state to transition to if the function raises an exception.
            name: Optional custom name for the transition (defaults to function name).
            
        Returns:
            A decorator function that registers the decorated function as a transition.
        """
        def decorator(func: DocumentCallable) -> DocumentCallable:
            # Check if the function signature accepts a Document argument
            sig = inspect.signature(func)
            params = list(sig.parameters.values())
            
            if len(params) < 1:
                raise ValueError(
                    f"Transition function {func.__name__} must accept at least one parameter (Document)"
                )
            
            # Register the transition
            self.register_transition(
                from_state=from_state,
                to_state=to_state,
                func=func,
                error=error,
                name=name,
            )
            
            # Return the original function unchanged
            return func
        
        return decorator
