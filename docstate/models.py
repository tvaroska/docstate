"""
DocState SQLAlchemy Models.

This module defines the SQLAlchemy ORM models that represent the database schema
for DocState. The core models are Document and TransitionHistory.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Document(Base):
    """
    Document entity representing a document in the system.
    
    A document moves through different states as defined by the state machine.
    Each document has a unique ID, content, metadata, and other properties.
    """
    
    __tablename__ = "documents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    state = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=False, default=dict)
    uri = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    version = Column(Integer, default=1, nullable=False)
    
    # Relationship with transition history
    transitions = relationship("TransitionHistory", back_populates="document", cascade="all, delete-orphan")
    
    def __init__(
        self, 
        state: str = "START", 
        content: Optional[str] = None, 
        metadata: Optional[Dict[str, Any]] = None,
        uri: Optional[str] = None,
    ):
        """
        Initialize a new Document instance.
        
        Args:
            state: The initial state of the document. Defaults to "START".
            content: The document's content. Defaults to None.
            metadata: Document metadata as a dictionary. Defaults to an empty dict.
            uri: URI reference for the document. Defaults to None.
        """
        self.state = state
        self.content = content
        self.metadata = metadata or {}
        self.uri = uri
    
    def get_available_transitions(self) -> list[str]:
        """
        Get the list of available transitions from the current state.
        
        This is a placeholder method that would be implemented by the DocState controller
        which has access to the state transition registry.
        
        Returns:
            A list of transition names that can be executed from the current state.
        """
        return []
    
    def next_step(self) -> Document:
        """
        Execute the next available transition for this document.
        
        This is a placeholder method that would be implemented by the DocState controller
        which handles the actual transition execution.
        
        Returns:
            The updated document after the transition.
        """
        return self


class TransitionHistory(Base):
    """
    TransitionHistory tracks all state transitions for a document.
    
    Each record represents a single transition from one state to another,
    including metadata such as timing, success/failure, and error messages.
    """
    
    __tablename__ = "transition_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True)
    from_state = Column(String, nullable=False)
    to_state = Column(String, nullable=False)
    transition_name = Column(String, nullable=False)
    executed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration_ms = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    error_message = Column(Text, nullable=True)
    
    # Relationship with document
    document = relationship("Document", back_populates="transitions")
    
    def __init__(
        self,
        document_id: uuid.UUID,
        from_state: str,
        to_state: str,
        transition_name: str,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ):
        """
        Initialize a new TransitionHistory instance.
        
        Args:
            document_id: The ID of the document that was transitioned.
            from_state: The state the document was in before the transition.
            to_state: The state the document is in after the transition.
            transition_name: The name of the transition function.
            duration_ms: The duration of the transition in milliseconds.
            success: Whether the transition was successful.
            error_message: Error message if the transition failed.
        """
        self.document_id = document_id
        self.from_state = from_state
        self.to_state = to_state
        self.transition_name = transition_name
        self.duration_ms = duration_ms
        self.success = success
        self.error_message = error_message
