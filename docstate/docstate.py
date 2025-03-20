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
            self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        
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
            
    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """
        Transaction context manager for database operations.
        
        This context manager creates a transaction scope that will be
        committed when the context is exited without an exception, or
        rolled back if an exception occurs.
        
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
        data: Optional[Dict[str, Any]] = None,
        uri: Optional[str] = None,
        initial_state: str = START,
    ) -> Document:
        """
        Create a new document in the database.
        
        Args:
            content: The document's content.
            data: Document data as a dictionary.
            uri: URI reference for the document.
            initial_state: The initial state of the document. Defaults to START.
            
        Returns:
            The created document with method bindings.
        """
        document = Document(
            state=initial_state,
            content=content,
            data=data,
            uri=uri,
        )
        
        # Create in a transaction
        with self.transaction() as session:
            session.add(document)
            session.flush()  # Flush to generate the ID
            document_id = document.id  # Store ID to re-fetch after commit
            
            # Create initial transition history entry for document creation
            transition_history = TransitionHistory(
                document_id=document_id,
                from_state="",  # No prior state
                to_state=initial_state,
                transition_name="document_created",
                success=True,
            )
            session.add(transition_history)
        
        # Re-fetch the document to ensure we have a clean instance
        document = self.get_document(document_id, inject_methods=False)
        
        # Inject document methods
        self._inject_document_methods(document)
        
        return document
    
    def get_document(self, document_id: uuid.UUID, inject_methods: bool = True) -> Document:
        """
        Get a document by ID.
        
        Args:
            document_id: The UUID of the document to retrieve.
            inject_methods: Whether to inject document methods for direct access.
            
        Returns:
            The document if found, with optional method bindings.
            
        Raises:
            ValueError: If the document is not found.
        """
        with self.session() as session:
            document = session.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise ValueError(f"Document with ID {document_id} not found")
                
            if inject_methods:
                self._inject_document_methods(document)
                
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
        old_state = None
        
        # Use a transaction for atomicity
        with self.transaction() as session:
            # Get a fresh instance of the document
            db_document = session.query(Document).filter(Document.id == document.id).first()
            if not db_document:
                raise ValueError(f"Document with ID {document.id} not found")
            
            # Store the old state for transition recording
            old_state = db_document.state
            
            # Update the document
            if new_state and new_state != old_state:
                db_document.state = new_state
            
            db_document.content = document.content
            db_document.data = document.data
            db_document.uri = document.uri
            db_document.version += 1
            
            session.flush()  # Flush to ensure changes are applied
            document_id = db_document.id  # Store ID to re-fetch after commit
            
            # Record the state change if new_state was provided and different
            if new_state and new_state != old_state:
                transition_history = TransitionHistory(
                    document_id=document_id,
                    from_state=old_state,
                    to_state=new_state,
                    transition_name="manual_update",
                    success=True,
                )
                session.add(transition_history)
        
        # Re-fetch the document to ensure we have a clean instance
        document = self.get_document(document_id)
        
        # Inject document methods
        self._inject_document_methods(document)
        
        return document
    
    def record_transition(
        self,
        document_id: uuid.UUID,
        from_state: str,
        to_state: str,
        transition_name: str,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> TransitionHistory:
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
            
        Returns:
            The created TransitionHistory record.
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
        
        with self.transaction() as session:
            session.add(transition_history)
            session.flush()
            history_id = transition_history.id
            
        # Return the committed record
        with self.session() as session:
            return session.query(TransitionHistory).filter(TransitionHistory.id == history_id).one()
    
    def execute_transition(
        self, document: Document, transition_name: Optional[str] = None
    ) -> Document:
        """
        Execute a transition on a document.
        
        This method runs a state transition in a transaction, ensuring that
        all database changes (document updates and transition history) are
        committed atomically.
        
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
        document_id = None
        error_to_raise = None
        
        # Execute everything in a single transaction for atomicity
        with self.transaction() as session:
            # Re-fetch the document within this session to ensure it's attached
            db_document = session.query(Document).filter(Document.id == document.id).first()
            if not db_document:
                raise ValueError(f"Document with ID {document.id} not found")
            
            # Execute the transition via the state manager
            result, new_state, error = self.state_manager.execute_transition(
                db_document, transition_name
            )
            
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)
            
            # If there was an error, record it and prepare to raise
            if error:
                # Create transition history record within this session
                transition_history = TransitionHistory(
                    document_id=document.id,
                    from_state=from_state,
                    to_state=new_state,
                    transition_name=transition_name or "unknown",
                    duration_ms=duration_ms,
                    success=False,
                    error_message=str(error),
                )
                session.add(transition_history)
                
                # Update document state to error state
                db_document.state = new_state
                db_document.version += 1
                
                # Flush changes before raising the error
                session.flush()
                document_id = db_document.id
                
                # We'll re-fetch the document after the session is closed and raise the error
                error_to_raise = error
            else:
                # Create transition history record for successful transition
                transition_history = TransitionHistory(
                    document_id=document.id,
                    from_state=from_state,
                    to_state=new_state,
                    transition_name=transition_name or (
                        result.__class__.__name__ if hasattr(result, "__class__") else "unknown"
                    ),
                    duration_ms=duration_ms,
                    success=True,
                )
                session.add(transition_history)
                
                # Update the document state and content
                db_document.state = new_state
                db_document.content = result.content
                db_document.data = result.data
                db_document.uri = result.uri
                db_document.version += 1
                
                session.flush()
                document_id = db_document.id
        
        # Re-fetch the document to ensure we have a clean instance
        updated_document = self.get_document(document_id)
        
        # If there was an error, raise it now that we have a clean document instance
        if error_to_raise:
            if isinstance(error_to_raise, ValueError):
                raise error_to_raise
            raise ValueError(f"Transition failed: {error_to_raise}")
            
        return updated_document
    
    def get_document_history(
        self, document_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[TransitionHistory]:
        """
        Get the transition history for a document.
        
        Args:
            document_id: The UUID of the document to retrieve history for.
            limit: Maximum number of history records to return.
            offset: Number of records to skip (for pagination).
            
        Returns:
            A list of TransitionHistory records for the document, ordered by most recent first.
        """
        with self.session() as session:
            history = (
                session.query(TransitionHistory)
                .filter(TransitionHistory.document_id == document_id)
                .order_by(TransitionHistory.executed_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            return history
    
    def get_state_history(
        self, document_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> List[str]:
        """
        Get the sequence of states that a document has been in.
        
        Args:
            document_id: The UUID of the document to retrieve state history for.
            limit: Maximum number of states to return.
            offset: Number of records to skip (for pagination).
            
        Returns:
            A list of state names, from most recent to earliest.
        """
        with self.session() as session:
            # Query transitions and order by executed_at descending to get most recent first
            transitions = (
                session.query(TransitionHistory)
                .filter(TransitionHistory.document_id == document_id)
                .order_by(TransitionHistory.executed_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )
            
            # Start with the current state
            states = []
            if transitions:
                states.append(transitions[0].to_state)
                # Add each previous state
                for transition in transitions:
                    # Don't add duplicate consecutive states
                    if not states or states[-1] != transition.from_state:
                        states.append(transition.from_state)
            else:
                # If no transitions, get the document to find its current state
                document = session.query(Document).filter(Document.id == document_id).first()
                if document:
                    states.append(document.state)
                    
            return states
    
    def get_transition_stats(
        self, document_id: uuid.UUID, include_errors: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get statistics about transitions for a document.
        
        Args:
            document_id: The UUID of the document to retrieve statistics for.
            include_errors: Whether to include error transitions in the statistics.
            
        Returns:
            A dictionary mapping transition names to statistics dictionaries with keys:
            - count: Number of times the transition was executed
            - avg_duration: Average duration in milliseconds
            - success_rate: Percentage of successful transitions
            - error_count: Number of failed transitions
            - last_executed: Timestamp of last execution
        """
        with self.session() as session:
            # Query all transitions for the document
            query = session.query(TransitionHistory).filter(
                TransitionHistory.document_id == document_id
            )
            
            if not include_errors:
                query = query.filter(TransitionHistory.success == True)
                
            transitions = query.all()
            
            # Calculate statistics for each transition
            stats: Dict[str, Dict[str, Any]] = {}
            
            for transition in transitions:
                name = transition.transition_name
                
                if name not in stats:
                    stats[name] = {
                        "count": 0,
                        "durations": [],
                        "success_count": 0,
                        "error_count": 0,
                        "last_executed": transition.executed_at,
                    }
                
                stats[name]["count"] += 1
                
                if transition.duration_ms is not None:
                    stats[name]["durations"].append(transition.duration_ms)
                    
                if transition.success:
                    stats[name]["success_count"] += 1
                else:
                    stats[name]["error_count"] += 1
                    
                if transition.executed_at > stats[name]["last_executed"]:
                    stats[name]["last_executed"] = transition.executed_at
            
            # Calculate averages and rates
            for name, data in stats.items():
                durations = data.pop("durations", [])
                data["avg_duration"] = sum(durations) / len(durations) if durations else None
                data["success_rate"] = (
                    (data["success_count"] / data["count"]) * 100 if data["count"] > 0 else 0
                )
                
            return stats
    
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
        data: Optional[Dict[str, Any]] = None,
        uri: Optional[str] = None,
        initial_state: str = START,
    ) -> Document:
        ...
    
    def _inject_document_methods(self, document: Document) -> None:
        """
        Inject methods into a Document instance.
        
        This method binds DocState methods to the Document instance, allowing
        the methods to be called directly on the Document object.
        
        Args:
            document: The Document instance to enhance with methods.
        """
        # Bind the get_history method
        document.get_history = lambda limit=100, offset=0: self.get_document_history(
            document.id, limit, offset
        )
        
        # Bind the get_state_history method
        document.get_state_history = lambda limit=100, offset=0: self.get_state_history(
            document.id, limit, offset
        )
        
        # Bind the get_transition_stats method
        document.get_transition_stats = lambda include_errors=True: self.get_transition_stats(
            document.id, include_errors
        )
        
        # Bind the get_available_transitions method
        document.get_available_transitions = lambda: self.get_available_transitions(document)
        
        # Bind the next_step method
        document.next_step = lambda transition_name=None: self.execute_transition(
            document, transition_name
        )
    
    def __call__(
        self,
        document_id: Optional[uuid.UUID] = None,
        *,
        content: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
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
            data: Data for a new document.
            uri: URI for a new document.
            initial_state: Initial state for a new document.
            
        Returns:
            Either an existing document or a newly created one.
        """
        if document_id is not None:
            document = self.get_document(document_id)
        else:
            document = self.create_document(
                content=content,
                data=data,
                uri=uri,
                initial_state=initial_state,
            )
        
        # Inject document methods
        self._inject_document_methods(document)
        
        return document
