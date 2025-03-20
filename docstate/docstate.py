"""
DocState Controller

This module implements the DocState controller, which is the main interface
for interacting with documents and state transitions.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Type, TypeVar, Union, cast, overload

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from docstate.constants import START, END
from docstate.models import Base, Document, TransitionHistory
from docstate.state_manager import DocumentCallable, StateManager, StateTransition

# Type definitions
T = TypeVar("T", bound=Document)
SessionFactory = Callable[[], Session]


class DocState:
    """
    DocState is the main controller for managing document state transitions.
    
    It provides:
    - Factory method for creating new documents
    - Methods for retrieving and updating documents
    - Decorator for defining state transitions
    - Methods for executing state transitions with transaction management
    """
    
    def __init__(
        self,
        connection_string: str,
        *,
        echo: bool = False,
        create_tables: bool = False,
        custom_session_factory: Optional[SessionFactory] = None,
    ):
        """
        Initialize the DocState controller.
        
        Args:
            connection_string: SQLAlchemy connection string for the database.
            echo: Whether to echo SQL statements (for debugging).
            create_tables: Whether to create tables in the database if they don't exist.
            custom_session_factory: Optional custom session factory for SQLAlchemy.
        """
        self.engine: Engine = create_engine(connection_string, echo=echo)
        
        if create_tables:
            Base.metadata.create_all(self.engine)
        
        if custom_session_factory:
            self.session_factory = custom_session_factory
        else:
            self.session_factory = sessionmaker(bind=self.engine)
        
        # Initialize the state manager
        self.state_manager = StateManager()
    
    @contextmanager
    def session(self) -> Iterator[Session]:
        """
        Context manager for database sessions.
        
        Yields:
            An SQLAlchemy session.
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_document(
        self,
        *,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        uri: Optional[str] = None,
        initial_state: str = START,
    ) -> Document:
        """
        Create a new document in the database.
        
        Args:
            content: The document's content.
            metadata: Document metadata as a dictionary.
            uri: URI reference for the document.
            initial_state: The initial state of the document. Defaults to START.
            
        Returns:
            The created document.
        """
        document = Document(
            state=initial_state,
            content=content,
            metadata=metadata,
            uri=uri,
        )
        
        with self.session() as session:
            session.add(document)
            session.flush()  # Flush to generate the ID
            document_id = document.id  # Store ID to re-fetch after commit
        
        # Re-fetch the document to ensure we have a clean instance
        return self.get_document(document_id)
    
    def get_document(self, document_id: uuid.UUID) -> Document:
        """
        Get a document by ID.
        
        Args:
            document_id: The UUID of the document to retrieve.
            
        Returns:
            The document if found.
            
        Raises:
            ValueError: If the document is not found.
        """
        with self.session() as session:
            document = session.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise ValueError(f"Document with ID {document_id} not found")
            return document
    
    def update_document(
        self, document: Document, new_state: Optional[str] = None
    ) -> Document:
        """
        Update a document in the database.
        
        Args:
            document: The document to update.
            new_state: Optional new state for the document.
            
        Returns:
            The updated document.
        """
        with self.session() as session:
            # Get a fresh instance of the document
            db_document = session.query(Document).filter(Document.id == document.id).first()
            if not db_document:
                raise ValueError(f"Document with ID {document.id} not found")
            
            # Update the document
            if new_state:
                db_document.state = new_state
            
            db_document.content = document.content
            db_document.metadata = document.metadata
            db_document.uri = document.uri
            db_document.version += 1
            
            session.flush()  # Flush to ensure changes are applied
            document_id = db_document.id  # Store ID to re-fetch after commit
        
        # Re-fetch the document to ensure we have a clean instance
        return self.get_document(document_id)
    
    def record_transition(
        self,
        document_id: uuid.UUID,
        from_state: str,
        to_state: str,
        transition_name: str,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Record a transition in the transition history.
        
        Args:
            document_id: The ID of the document that was transitioned.
            from_state: The state the document was in before the transition.
            to_state: The state the document is in after the transition.
            transition_name: The name of the transition function.
            duration_ms: The duration of the transition in milliseconds.
            success: Whether the transition was successful.
            error_message: Error message if the transition failed.
        """
        transition_history = TransitionHistory(
            document_id=document_id,
            from_state=from_state,
            to_state=to_state,
            transition_name=transition_name,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message,
        )
        
        with self.session() as session:
            session.add(transition_history)
    
    def execute_transition(
        self, document: Document, transition_name: Optional[str] = None
    ) -> Document:
        """
        Execute a transition on a document.
        
        Args:
            document: The document to transform.
            transition_name: Optional name of the transition to execute.
                If not provided, the first available transition will be used.
                
        Returns:
            The transformed document with updated state.
            
        Raises:
            ValueError: If no valid transition is found or if the transition fails.
        """
        # Ensure we have the latest document state
        document = self.get_document(document.id)
        from_state = document.state
        
        # Record start time for performance tracking
        start_time = time.time()
        
        # Execute the transition via the state manager
        result, new_state, error = self.state_manager.execute_transition(
            document, transition_name
        )
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # If there was an error, record it and raise
        if error:
            self.record_transition(
                document_id=document.id,
                from_state=from_state,
                to_state=new_state,
                transition_name=transition_name or "unknown",
                duration_ms=duration_ms,
                success=False,
                error_message=str(error),
            )
            
            # Update document state to error state
            document = self.update_document(document, new_state)
            
            # Raise the error for the caller to handle
            if isinstance(error, ValueError):
                raise error
            raise ValueError(f"Transition failed: {error}")
        
        # Record successful transition
        self.record_transition(
            document_id=document.id,
            from_state=from_state,
            to_state=new_state,
            transition_name=transition_name or result.__class__.__name__,
            duration_ms=duration_ms,
            success=True,
        )
        
        # Update the document state and content
        result.state = new_state
        return self.update_document(result, new_state)
    
    def get_available_transitions(self, document: Document) -> List[str]:
        """
        Get the list of available transitions from the document's current state.
        
        Args:
            document: The document to check.
            
        Returns:
            A list of transition names that can be executed from the current state.
        """
        return self.state_manager.get_transition_names_from(document.state)
    
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
        
        This delegates to the state manager's transition decorator.
        
        Args:
            from_state: The source state.
            to_state: The target state after successful transition.
            error: The error state to transition to if the function raises an exception.
            name: Optional custom name for the transition (defaults to function name).
            
        Returns:
            A decorator function that registers the decorated function as a transition.
        """
        return self.state_manager.transition(
            from_state=from_state,
            to_state=to_state,
            error=error,
            name=name,
        )
    
    @overload
    def __call__(
        self,
        document_id: uuid.UUID,
    ) -> Document:
        ...
    
    @overload
    def __call__(
        self,
        *,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        uri: Optional[str] = None,
        initial_state: str = START,
    ) -> Document:
        ...
    
    def __call__(
        self,
        document_id: Optional[uuid.UUID] = None,
        *,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        uri: Optional[str] = None,
        initial_state: str = START,
    ) -> Document:
        """
        Factory method for getting existing or creating new documents.
        
        This method can be used in two ways:
        1. With a document_id to retrieve an existing document
        2. With document properties to create a new document
        
        Args:
            document_id: The UUID of an existing document to retrieve.
            content: The content for a new document.
            metadata: Metadata for a new document.
            uri: URI for a new document.
            initial_state: Initial state for a new document.
            
        Returns:
            Either an existing document or a newly created one.
        """
        if document_id is not None:
            return self.get_document(document_id)
        
        return self.create_document(
            content=content,
            metadata=metadata,
            uri=uri,
            initial_state=initial_state,
        )
