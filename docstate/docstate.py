from typing import List, Optional, Dict, Any, Union, Callable
import asyncio
from uuid import uuid4
from sqlalchemy import create_engine, Column, String, JSON, ForeignKey, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import select

from docstate.document import Document, DocumentState, DocumentType, Transition

Base = declarative_base()


class DocumentModel(Base):
    """SQLAlchemy model for document storage."""
    __tablename__ = 'documents'
    
    id = Column(String, primary_key=True)
    state = Column(String, nullable=False)
    content = Column(JSON, nullable=True)
    content_type = Column(String, default='text')
    parent_id = Column(String, ForeignKey('documents.id'), nullable=True)
    children = Column(JSON, nullable=False, default=[])
    cmetadata = Column(JSON, nullable=False, default={})


class DocStore:
    """
    Manages persistence of Document objects and handles state transitions.
    
    The DocStore acts as a repository for Document objects, providing CRUD operations
    and specialized queries. It also manages the execution of state transitions via
    the next() method.
    """
    
    def __init__(self, connection_string: str, document_type: Optional[DocumentType] = None):
        """
        Initialize the DocStore with a database connection and document type.
        
        Args:
            connection_string: SQLAlchemy connection string for the database
            document_type: DocumentType defining the state machine for documents
        """
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.document_type = document_type
        
    def set_document_type(self, document_type: DocumentType) -> None:
        """Set the document type for this DocStore."""
        self.document_type = document_type
        
    def add(self, doc: Document) -> str:
        """
        Add a document to the store and return its ID.
        
        If the document ID is None, a UUID4 will be automatically generated.
        
        Args:
            doc: The Document to add
            
        Returns:
            str: The document ID
        """
        # Generate UUID4 if ID is None
        if doc.id is None:
            doc.id = str(uuid4())
            
        with self.Session() as session:
            db_doc = DocumentModel(
                id=doc.id,
                state=doc.state,
                content=doc.content,
                content_type=doc.content_type,
                parent_id=doc.parent_id,
                children=doc.children,
                cmetadata=doc.metadata
            )
            session.add(db_doc)
            session.commit()
            return doc.id
    
    def get(self, id: Optional[str] = None, state: Optional[str] = None) -> Union[Document, List[Document], None]:
        """
        Retrieve document(s) by ID or state.
        
        Args:
            id: Document ID to retrieve
            state: Document state to filter by
            
        Returns:
            Document, List[Document], or None if no matching documents found
        """
        with self.Session() as session:
            if id:
                result = session.query(DocumentModel).filter_by(id=id).first()
                if result is None:
                    return None
                return Document.model_validate({
                    "id": result.id,
                    "state": result.state,
                    "content": result.content,
                    "content_type": result.content_type,
                    "parent_id": result.parent_id,
                    "children": result.children,
                    "metadata": result.cmetadata
                })
            elif state:
                results = session.query(DocumentModel).filter_by(state=state).all()
                return [Document.model_validate({
                    "id": result.id,
                    "state": result.state,
                    "content": result.content,
                    "content_type": result.content_type,
                    "parent_id": result.parent_id,
                    "children": result.children,
                    "metadata": result.cmetadata
                }) for result in results]
            else:
                # Return all documents if no filters specified
                results = session.query(DocumentModel).all()
                return [Document.model_validate({
                    "id": result.id,
                    "state": result.state,
                    "content": result.content,
                    "content_type": result.content_type,
                    "parent_id": result.parent_id,
                    "children": result.children,
                    "metadata": result.cmetadata
                }) for result in results]
    
    
    def delete(self, id: str) -> None:
        """
        Delete a document from the store.
        
        Args:
            id: ID of the document to delete
        """
        with self.Session() as session:
            doc = session.query(DocumentModel).filter_by(id=id).first()
            if doc:
                session.delete(doc)
                session.commit()
    
    async def next(self, doc: Document) -> Union[Document, List[Document]]:
        """
        Process a document to its next state according to the document type.
        
        Args:
            doc: The Document to process
            
        Returns:
            Document or List[Document]: The processed document(s) in the new state
        """
        if not self.document_type:
            raise ValueError("Document type not set for DocStore")
        
        # Get possible transitions from current state
        transitions = self.document_type.get_transition(doc.state)
        
        if not transitions:
            raise ValueError(f"No valid transitions from state '{doc.state}'")
        
        # Use the first available transition (could be extended to support multiple paths)
        transition = transitions[0]
        
        # Process the document using the transition function
        result = await transition.process_func(doc)
        
        # Handle the result based on whether it's a single document or list
        if isinstance(result, list):
            # When a document is chunked, multiple new documents are created
            for new_doc in result:
                new_doc.parent_id = doc.id
                self.add(new_doc)
                
                # Update parent document with child reference directly in database
                parent = self.get(id=doc.id)
                if parent:
                    parent.add_child(new_doc.id)
                    # Update parent in database directly
                    with self.Session() as session:
                        db_doc = session.query(DocumentModel).filter_by(id=parent.id).first()
                        if db_doc:
                            db_doc.children = parent.children
                            db_doc.cmetadata = parent.metadata
                            session.commit()
            
            return result
        else:
            # Single document transition
            result.parent_id = doc.id
            self.add(result)
            
            # Update parent document with child reference directly in database
            parent = self.get(id=doc.id)
            if parent:
                parent.add_child(result.id)
                # Update parent in database directly
                with self.Session() as session:
                    db_doc = session.query(DocumentModel).filter_by(id=parent.id).first()
                    if db_doc:
                        db_doc.children = parent.children
                        db_doc.cmetadata = parent.metadata
                        session.commit()
            
            return result
