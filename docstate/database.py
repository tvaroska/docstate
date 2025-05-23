from sqlalchemy import JSON, Column, ForeignKey, String
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import backref, DeclarativeBase, relationship


class Base(AsyncAttrs, DeclarativeBase):
    pass


class DocumentModel(Base):
    """SQLAlchemy model for document storage."""

    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    state = Column(String, nullable=False)
    content = Column(String, nullable=True)
    media_type = Column(String, default="text/plain")
    url = Column(String, nullable=True)
    parent_id = Column(String, ForeignKey("documents.id"), nullable=True)
    children = relationship(
        "DocumentModel",
        backref=backref("parent", remote_side=[id]),
        cascade="all, delete-orphan"
    )
    cmetadata = Column(JSON, nullable=False, default={})
