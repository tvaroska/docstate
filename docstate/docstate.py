import asyncio
from typing import Generator, List, Optional, Union
from uuid import uuid4

from sqlalchemy import JSON, Column, ForeignKey, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import backref, declarative_base, relationship, sessionmaker
from sqlalchemy.sql import select

from docstate.document import Document, DocumentType

Base = declarative_base()


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
        cascade="all, delete-orphan",
    )
    cmetadata = Column(JSON, nullable=False, default={})


class DocStore:
    """
    Manages persistence of Document objects and handles state transitions.

    The DocStore acts as a repository for Document objects, providing CRUD operations
    and specialized queries. It also manages the execution of state transitions via
    the next() method.
    """

    # Default error state name
    ERROR_STATE = "error"

    def __init__(
        self,
        connection_string: str,
        document_type: Optional[DocumentType] = None,
        error_state: Optional[str] = None,
        max_concurrent_tasks: int = 5,
    ):
        """
        Initialize the DocStore with a database connection and document type.

        Args:
            connection_string: SQLAlchemy connection string for the database
            document_type: DocumentType defining the state machine for documents
            error_state: Optional custom name for the error state. Defaults to DocStore.ERROR_STATE.
            max_concurrent_tasks: Maximum number of concurrent document processing tasks. Defaults to 5.
        """
        self.engine = create_engine(connection_string)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.document_type = document_type
        self.error_state = error_state if error_state is not None else self.ERROR_STATE
        self.max_concurrent_tasks = max_concurrent_tasks

    def __enter__(self):
        """Context manager enter method for resource management."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit method to ensure connections are closed."""
        if hasattr(self, "engine"):
            self.engine.dispose()

    def set_document_type(self, document_type: DocumentType) -> None:
        """Set the document type for this DocStore."""
        self.document_type = document_type

    def add(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]:
        """
        Add a document or list of documents to the store and return the ID(s).

        If any document ID is None, a UUID4 will be automatically generated.

        Args:
            doc: The Document or List[Document] to add

        Returns:
            Union[str, List[str]]: The document ID or list of document IDs
        """
        # Handle single document case
        if not isinstance(doc, list):
            # Generate UUID4 if ID is None
            if doc.id is None:
                doc.id = str(uuid4())

            with self.Session() as session:
                db_doc = DocumentModel(
                    id=doc.id,
                    state=doc.state,
                    content=doc.content,
                    media_type=doc.media_type,
                    url=doc.url,
                    parent_id=doc.parent_id,
                    cmetadata=doc.metadata,
                )
                # Children will be managed separately through relationships
                session.add(db_doc)
                session.commit()
                return doc.id

        # Handle list of documents case
        else:
            doc_ids = []
            with self.Session() as session:
                for document in doc:
                    # Generate UUID4 if ID is None
                    if document.id is None:
                        document.id = str(uuid4())

                    db_doc = DocumentModel(
                        id=document.id,
                        state=document.state,
                        content=document.content,
                        media_type=document.media_type,
                        url=document.url,
                        parent_id=document.parent_id,
                        cmetadata=document.metadata,
                    )
                    # Children will be managed separately through relationships
                    session.add(db_doc)
                    doc_ids.append(document.id)

                session.commit()
                return doc_ids

    def get(
        self, id: Optional[str] = None, state: Optional[str] = None
    ) -> Union[Document, List[Document], None]:
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
                # Extract child IDs from the relationship
                child_ids = [child.id for child in result.children]
                return Document.model_validate(
                    {
                        "id": result.id,
                        "state": result.state,
                        "content": result.content,
                        "media_type": result.media_type,
                        "url": result.url,
                        "parent_id": result.parent_id,
                        "children": child_ids,
                        "metadata": result.cmetadata,
                    }
                )
            elif state:
                results = session.query(DocumentModel).filter_by(state=state).all()
                return [
                    Document.model_validate(
                        {
                            "id": result.id,
                            "state": result.state,
                            "content": result.content,
                            "media_type": result.media_type,
                            "url": result.url,
                            "parent_id": result.parent_id,
                            "children": [child.id for child in result.children],
                            "metadata": result.cmetadata,
                        }
                    )
                    for result in results
                ]
            else:
                # Return all documents if no filters specified
                results = session.query(DocumentModel).all()
                return [
                    Document.model_validate(
                        {
                            "id": result.id,
                            "state": result.state,
                            "content": result.content,
                            "media_type": result.media_type,
                            "url": result.url,
                            "parent_id": result.parent_id,
                            "children": [child.id for child in result.children],
                            "metadata": result.cmetadata,
                        }
                    )
                    for result in results
                ]

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

    async def _process_single_document(
        self, doc: Document
    ) -> Union[Document, List[Document]]:
        """Helper function to process a single document transition."""
        if not self.document_type:
            raise ValueError("Document type not set for DocStore")

        transitions = self.document_type.get_transition(doc.state)
        if not transitions:
            # If no transition, return the original document (or handle as error/final state)
            # For now, let's consider it might be a final state or no-op
            # raise ValueError(f"No valid transitions from state '{doc.state}'") # Option 1: Raise error
            return doc  # Option 2: Return original if no transition (e.g., final state)

        # Use the first available transition
        transition = transitions[0]

        try:
            # Process the document
            processed_result = await transition.process_func(doc)

            results_to_add = []
            if isinstance(processed_result, list):
                results_to_add.extend(processed_result)
            else:
                results_to_add.append(processed_result)

            added_docs = []
            for new_doc in results_to_add:
                new_doc.parent_id = doc.id
                self.add(new_doc)
                added_docs.append(new_doc)

                # The parent-child relationship in the database is handled automatically
                # through the parent_id foreign key. We just need to update the
                # Pydantic Document's children list for the current session
                parent = self.get(id=doc.id)
                if parent and new_doc.id not in parent.children:
                    parent.add_child(new_doc.id)

                    # Note: We don't need to update the database model's children list
                    # because the relationship is automatically managed by SQLAlchemy
                    # through the parent_id foreign key on each child document

            # Return the list of newly created/added documents
            return added_docs

        except Exception as e:
            # Create an error document
            error_doc = Document(
                state=self.error_state,
                media_type="application/json",
                content=str(e),
                parent_id=doc.id,
                metadata={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "transition_from": doc.state,
                    "transition_to": transition.to_state.name,
                    "original_media_type": doc.media_type,
                    "timestamp": transition.process_func.__name__,
                },
            )

            # Add the error document to the store
            self.add(error_doc)

            # Update the parent document's children list
            parent = self.get(id=doc.id)
            if parent and error_doc.id not in parent.children:
                parent.add_child(error_doc.id)

            # Return the error document
            return [error_doc]

    async def next(self, docs: Union[Document, List[Document]]) -> List[Document]:
        """
        Process document(s) to their next state according to the document type.
        Accepts either a single Document or a list of Documents.
        
        Documents are processed concurrently using asyncio.gather with a configurable
        limit on the maximum number of concurrent tasks.

        Args:
            docs: The Document or List[Document] to process

        Returns:
            List[Document]: A flattened list of the processed document(s) in the new state(s).
                           Returns an empty list if no documents were processed or resulted in new states.
        """
        if not isinstance(docs, list):
            docs_to_process = [docs]
        else:
            docs_to_process = docs

        # Filter out invalid document types
        valid_docs = []
        for doc in docs_to_process:
            if not isinstance(doc, Document):
                print(f"Warning: Skipping invalid input type in list: {type(doc)}")
                continue
            valid_docs.append(doc)

        if not valid_docs:
            return []

        all_results = []
        
        # Process documents in batches to control concurrency
        for i in range(0, len(valid_docs), self.max_concurrent_tasks):
            batch = valid_docs[i:i + self.max_concurrent_tasks]
            
            # Create async tasks for each document in the batch
            tasks = []
            
            # Define the error handling function outside the loop
            # to avoid closure issues
            async def process_with_error_handling(document):
                try:
                    return await self._process_single_document(document)
                except ValueError as e:
                    # Re-raise ValueError exceptions like "Document type not set"
                    if "Document type not set" in str(e):
                        raise
                    # Log error for other ValueError cases
                    print(f"ValueError processing document {document.id}: {e}")
                    return None
                except Exception as e:
                    # Log error for other exceptions
                    print(f"Error processing document {document.id}: {e}")
                    return None
            
            # Create tasks for each document
            for doc in batch:
                tasks.append(process_with_error_handling(doc))
            
            # Process the batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=False)
            
            # Collect and flatten results
            for result in batch_results:
                if result is None:
                    continue
                if isinstance(result, list):
                    all_results.extend(result)
                elif isinstance(result, Document):
                    # If the original document is returned (e.g., final state), 
                    # we don't include it by default.
                    # Uncomment below if you want to include final state docs:
                    # all_results.append(result)
                    pass

        return all_results

    def update(self, doc: Union[Document, str], **kwargs) -> Document:
        """
        Update only the metadata of a document.

        Args:
            doc: Either a Document object or a document ID (str)
            **kwargs: Keyword arguments representing metadata fields to update

        Returns:
            Document: The updated document

        Raises:
            ValueError: If the document is not found in the database
            ValueError: If a Document object is provided but doesn't match the one in the database
        """
        doc_id = doc.id if isinstance(doc, Document) else doc

        with self.Session() as session:
            db_doc = session.query(DocumentModel).filter_by(id=doc_id).first()

            if not db_doc:
                raise ValueError(f"Document with ID {doc_id} not found in the database")

            # If a Document object was provided, verify it matches what's in the database
            if isinstance(doc, Document):
                if (
                    doc.state != db_doc.state
                    or doc.content != db_doc.content
                    or doc.media_type != db_doc.media_type
                ):
                    raise ValueError(
                        "Provided document does not match the document in the database"
                    )

            # Get the current metadata (initialize to empty dict if None)
            current_metadata = (
                {} if db_doc.cmetadata is None else db_doc.cmetadata.copy()
            )

            # Update the metadata with the new values
            for key, value in kwargs.items():
                current_metadata[key] = value

            # Update the database
            db_doc.cmetadata = current_metadata
            session.commit()

            # Return the updated document with the updated metadata
            return Document.model_validate(
                {
                    "id": db_doc.id,
                    "state": db_doc.state,
                    "content": db_doc.content,
                    "media_type": db_doc.media_type,
                    "url": db_doc.url,
                    "parent_id": db_doc.parent_id,
                    "children": [child.id for child in db_doc.children],
                    "metadata": current_metadata,  # Use the locally updated metadata to ensure it's correct
                }
            )

    def list(self, state: str, leaf: bool = True, **kwargs) -> Generator[Document, None, None]:
        """
        Generate documents with the specified state and metadata filters.

        Args:
            state: Document state to filter by (required)
            leaf: If True, only returns documents without children (default: True)
            **kwargs: Optional metadata key/value pairs to filter by

        Yields:
            Document: Documents matching the specified criteria
        """
        with self.Session() as session:
            # Start with a query for the specified state
            query = session.query(DocumentModel).filter_by(state=state)

            # Get all documents with the specified state first
            results = query.all()

            # Filter results based on metadata and leaf parameter
            for result in results:
                # Skip if we want leaf nodes only and this document has children
                if leaf and result.children:
                    continue

                # If there are metadata filters, check them
                if kwargs:
                    # Check if document's metadata matches all provided kwargs
                    if result.cmetadata is not None:  # Make sure metadata exists
                        # Check if all conditions match
                        if all(
                            key in result.cmetadata and result.cmetadata[key] == value
                            for key, value in kwargs.items()
                        ):
                            # Build and yield document
                            yield Document.model_validate(
                                {
                                    "id": result.id,
                                    "state": result.state,
                                    "content": result.content,
                                    "media_type": result.media_type,
                                    "url": result.url,
                                    "parent_id": result.parent_id,
                                    "children": [child.id for child in result.children],
                                    "metadata": result.cmetadata,
                                }
                            )
                else:
                    # No metadata filters, just yield document if it passes leaf check
                    yield Document.model_validate(
                        {
                            "id": result.id,
                            "state": result.state,
                            "content": result.content,
                            "media_type": result.media_type,
                            "url": result.url,
                            "parent_id": result.parent_id,
                            "children": [child.id for child in result.children],
                            "metadata": result.cmetadata,
                        }
                    )

    async def finish(self, docs: Union[Document, List[Document]]) -> List[Document]:
        """
        Process document(s) through the entire pipeline until all reach a final state.
        A final state is defined as a state with no outgoing transitions.

        This method will:
        1. Add document(s) to the database if they don't exist yet
        2. Repeatedly call next() until all documents are in final states
        3. Return all documents that are in final states

        Args:
            docs: The Document or List[Document] to process to completion

        Returns:
            List[Document]: A list of all documents that reached a final state
        """
        if not self.document_type:
            raise ValueError("Document type not set for DocStore")

        # Convert single document to list for consistent handling
        if not isinstance(docs, list):
            docs_to_process = [docs]
        else:
            docs_to_process = docs

        # Add documents to database if they don't exist already
        for doc in docs_to_process:
            # Check if document exists in database
            existing_doc = self.get(id=doc.id)
            if not existing_doc:
                self.add(doc)

        # Get final states from document type
        final_states = self.document_type.final
        final_state_names = [state.name for state in final_states]

        # Add error state to final states list (documents in error state shouldn't be processed further)
        if self.error_state not in final_state_names:
            final_state_names.append(self.error_state)

        # Process documents until all are in final states
        documents_to_process = docs_to_process.copy()
        final_documents = []

        while documents_to_process:
            # Filter out documents that are already in final states
            documents_to_process = [
                doc
                for doc in documents_to_process
                if doc.state not in final_state_names
            ]

            if not documents_to_process:
                break

            # Process the next state for each document
            next_documents = await self.next(documents_to_process)

            if not next_documents:
                # If no new documents were created, we're done
                break

            # Update documents to process with the new documents
            documents_to_process = next_documents

        # Collect all documents in final states
        for state_name in final_state_names:
            docs_in_state = self.get(state=state_name)
            if docs_in_state:
                if isinstance(docs_in_state, list):
                    final_documents.extend(docs_in_state)
                else:
                    final_documents.append(docs_in_state)

        return final_documents
