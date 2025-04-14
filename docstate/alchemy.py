from typing import Optional, List, Dict, Any
from uuid import UUID
import uuid
from datetime import datetime
import json

from sqlalchemy import create_engine, Column, String, DateTime, Boolean, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.orm import declarative_base

# For SQLite support
import json
from sqlalchemy.types import TypeDecorator, TEXT
from sqlalchemy_utils import UUIDType

from docstate.persistence import PersistenceInterface
from docstate.core import DocumentInstance, DocumentVersion, DocumentLineage, DocumentState, DocumentType


class JSONEncodedDict(TypeDecorator):
    """Represents a JSON structure as a text-based column for SQLite."""
    impl = TEXT

    def process_bind_param(self, value, dialect):
        if value is not None:
            value = json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            value = json.loads(value)
        return value

# Define the SQLAlchemy base
Base = declarative_base()

# SQLAlchemy models - with SQLite compatibility
class DocumentInstanceModel(Base):
    """SQLAlchemy model for DocumentInstance."""
    __tablename__ = 'document_instances'
    
    # Composite primary key of doc_id and branch_id
    doc_id = Column(UUIDType(binary=False), primary_key=True)
    branch_id = Column(UUIDType(binary=False), primary_key=True, nullable=True)
    
    # Fields that match the Pydantic model
    parent_branch_id = Column(UUIDType(binary=False), nullable=True)
    current_version = Column(UUIDType(binary=False), nullable=False)
    
    # JSON fields for complex objects - SQLite compatible
    doc_type = Column(JSONEncodedDict, nullable=False)
    current_state = Column(JSONEncodedDict, nullable=False)
    db_metadata = Column(JSONEncodedDict, nullable=False, default={})


class DocumentVersionModel(Base):
    """SQLAlchemy model for DocumentVersion."""
    __tablename__ = 'document_versions'
    
    version_id = Column(UUIDType(binary=False), primary_key=True)
    created_at = Column(DateTime, nullable=False)
    reason = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    mime_type = Column(String, nullable=False)
    
    # Store content as JSON encoded text for SQLite compatibility
    content = Column(JSONEncodedDict, nullable=False)
    db_metadata = Column(JSONEncodedDict, nullable=False, default={})


class DocumentLineageModel(Base):
    """SQLAlchemy model for DocumentLineage."""
    __tablename__ = 'document_lineage'
    
    id = Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUIDType(binary=False), nullable=False, index=True)
    target_id = Column(UUIDType(binary=False), nullable=False, index=True)
    relationship_type = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)
    db_metadata = Column(JSONEncodedDict, nullable=False, default={})


class SQLAlchemyPersistence(PersistenceInterface):
    """An SQLAlchemy based implementation of the PersistenceInterface."""
    
    def __init__(self, connection_string: str, echo: bool = False):
        """
        Initialize the SQLAlchemy persistence layer.
        
        Args:
            connection_string: SQLAlchemy connection string (e.g., 'postgresql://user:pass@localhost/dbname')
            echo: If True, SQLAlchemy will log all SQL statements
        """
        self.engine = create_engine(connection_string, echo=echo)
        self.Session = sessionmaker(bind=self.engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(self.engine)
    
    def save_document_instance(self, instance: DocumentInstance) -> None:
        """Saves or updates the state of a document instance/branch in persistent storage."""
        with self.Session() as session:
            # Convert pydantic model to dict for JSON fields
            doc_type_dict = instance.doc_type.dict()
            current_state_dict = instance.current_state.dict()
            
            # Check if instance already exists
            existing = session.query(DocumentInstanceModel).filter_by(
                doc_id=instance.doc_id, 
                branch_id=instance.branch_id
            ).first()
            
            if existing:
                # Update existing instance
                existing.current_version = instance.current_version
                existing.doc_type = doc_type_dict
                existing.current_state = current_state_dict
                existing.db_metadata = instance.metadata
                existing.parent_branch_id = instance.parent_branch_id
            else:
                # Create new instance
                model = DocumentInstanceModel(
                    doc_id=instance.doc_id,
                    branch_id=instance.branch_id,
                    parent_branch_id=instance.parent_branch_id,
                    current_version=instance.current_version,
                    doc_type=doc_type_dict,
                    current_state=current_state_dict,
                    db_metadata=instance.metadata
                )
                session.add(model)
            
            session.commit()
    
    def save_document_version(self, version: DocumentVersion) -> None:
        """Saves a new document version."""
        with self.Session() as session:
            # Handle non-JSON serializable content
            if isinstance(version.content, (dict, list)):
                content = version.content
            else:
                # Convert non-JSON content to string
                content = str(version.content)
            
            model = DocumentVersionModel(
                version_id=version.version_id,
                created_at=version.created_at,
                reason=version.reason,
                content_type=version.content_type,
                mime_type=version.mime_type,
                content=content,
                db_metadata=version.metadata
            )
            session.add(model)
            session.commit()
    
    def save_document_lineage(self, lineage: DocumentLineage) -> None:
        """Saves a document lineage relationship."""
        with self.Session() as session:
            model = DocumentLineageModel(
                id=uuid.uuid4(),
                source_id=lineage.source_id,
                target_id=lineage.target_id,
                relationship_type=lineage.relationship_type,
                created_at=lineage.created_at,
                db_metadata=lineage.metadata
            )
            session.add(model)
            session.commit()
    
    def load_document_instance(self, doc_id: UUID, branch_id: Optional[UUID] = None) -> Optional[DocumentInstance]:
        """Loads a specific document instance/branch."""
        with self.Session() as session:
            model = session.query(DocumentInstanceModel).filter_by(
                doc_id=doc_id,
                branch_id=branch_id
            ).first()
            
            if model:
                # Convert JSON fields back to Pydantic models
                doc_type = DocumentType(**model.doc_type)
                current_state = DocumentState(**model.current_state)
                
                return DocumentInstance(
                    doc_id=model.doc_id,
                    branch_id=model.branch_id,
                    parent_branch_id=model.parent_branch_id,
                    current_version=model.current_version,
                    doc_type=doc_type,
                    current_state=current_state,
                    metadata=model.db_metadata
                )
            return None
    
    def load_document_version(self, version_id: UUID) -> Optional[DocumentVersion]:
        """Loads a specific document version."""
        with self.Session() as session:
            model = session.query(DocumentVersionModel).filter_by(version_id=version_id).first()
            
            if model:
                # Handle content based on content_type
                content = model.content
                
                return DocumentVersion(
                    version_id=model.version_id,
                    created_at=model.created_at,
                    reason=model.reason,
                    content_type=model.content_type,
                    mime_type=model.mime_type,
                    content=content,
                    metadata=model.db_metadata
                )
            return None
    
    def load_document_versions(self, doc_id: UUID) -> List[DocumentVersion]:
        """Loads all versions for a document."""
        with self.Session() as session:
            # Find all lineage entries for the document ID as source
            lineage_models = session.query(DocumentLineageModel).filter_by(source_id=doc_id).all()
            
            versions = []
            for lineage in lineage_models:
                # Get the target version for each lineage
                version_model = session.query(DocumentVersionModel).filter_by(
                    version_id=lineage.target_id
                ).first()
                
                if version_model:
                    versions.append(DocumentVersion(
                        version_id=version_model.version_id,
                        created_at=version_model.created_at,
                        reason=version_model.reason,
                        content_type=version_model.content_type,
                        mime_type=version_model.mime_type,
                        content=version_model.content,
                        metadata=version_model.db_metadata
                    ))
            
            return versions
    
    def load_document_lineage(self, doc_id: UUID) -> List[DocumentLineage]:
        """Loads all lineage relationships for a document."""
        with self.Session() as session:
            lineage_models = session.query(DocumentLineageModel).filter_by(source_id=doc_id).all()
            
            return [
                DocumentLineage(
                    source_id=model.source_id,
                    target_id=model.target_id,
                    relationship_type=model.relationship_type,
                    created_at=model.created_at,
                    metadata=model.db_metadata
                )
                for model in lineage_models
            ]
    
    def load_document_branches(self, doc_id: UUID) -> List[DocumentInstance]:
        """Loads all branches for a document."""
        with self.Session() as session:
            branch_models = session.query(DocumentInstanceModel).filter_by(doc_id=doc_id).all()
            
            branches = []
            for model in branch_models:
                # Convert JSON fields back to Pydantic models
                doc_type = DocumentType(**model.doc_type)
                current_state = DocumentState(**model.current_state)
                
                branches.append(DocumentInstance(
                    doc_id=model.doc_id,
                    branch_id=model.branch_id,
                    parent_branch_id=model.parent_branch_id,
                    current_version=model.current_version,
                    doc_type=doc_type,
                    current_state=current_state,
                    metadata=model.db_metadata
                ))
            
            return branches
    
    def get_next_branch_id(self, doc_id: UUID) -> UUID:
        """Generates a unique branch ID for a document."""
        # Simply generate a new UUID - collision chance is astronomically small
        new_branch_id = uuid.uuid4()
        return new_branch_id
    
    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(self.engine)
    
    def drop_db(self) -> None:
        """Drop all tables - use with caution!"""
        Base.metadata.drop_all(self.engine)
