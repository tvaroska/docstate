from typing import Dict, List, Optional, Set, Union
from sqlalchemy import JSON, Column, ForeignKey, String, Index, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import backref, DeclarativeBase, relationship


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


class DocumentModel(Base):
    """
    SQLAlchemy model for document storage.
    
    Optimized for high-performance async operations with appropriate indexes
    and relationship configurations.
    """

    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    state = Column(String, nullable=False, index=True)
    content = Column(String, nullable=True)
    media_type = Column(String, default="text/plain", index=True)
    url = Column(String, nullable=True, index=True)
    parent_id = Column(String, ForeignKey("documents.id"), nullable=True, index=True)
    
    # Optimized relationship loading with lazy='selectin' for better performance with large datasets
    children = relationship(
        "DocumentModel",
        backref=backref("parent", remote_side=[id], lazy='selectin'),
        cascade="all, delete-orphan",
        lazy='selectin'  # Use selectin loading for better performance with collections
    )
    
    cmetadata = Column(JSON, nullable=False, default={})
    
    # Composite indexes for common query patterns
    __table_args__ = (
        # Index for queries that filter by state and media_type
        Index('idx_state_media_type', 'state', 'media_type'),
        # Index for queries that filter by parent_id and state
        Index('idx_parent_state', 'parent_id', 'state'),
    )
