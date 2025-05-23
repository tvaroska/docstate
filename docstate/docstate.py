import asyncio
from typing import AsyncGenerator, Generator, List, Optional, Union
from uuid import uuid4

from sqlalchemy import JSON, Column, ForeignKey, String, create_engine, inspect, select as sync_select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncAttrs
from sqlalchemy.future import select
from sqlalchemy.orm import backref, DeclarativeBase, relationship, sessionmaker
from sqlalchemy.orm.session import Session
from sqlalchemy.orm import joinedload

from docstate.document import Document, DocumentType
from docstate.utils import log_document_operation, log_document_processing, log_document_transition

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
        # Create async engine if connection string is SQLite (convert to aiosqlite)
        # or already async compatible
        if connection_string.startswith('sqlite'):
            async_connection_string = connection_string.replace('sqlite', 'sqlite+aiosqlite', 1)
        else:
            # For other databases, user needs to provide proper async driver
            async_connection_string = connection_string
            
        self.async_engine = create_async_engine(async_connection_string)
        self.AsyncSession = sessionmaker(
            bind=self.async_engine, 
            class_=AsyncSession, 
            expire_on_commit=False
        )

        asyncio.run(self.create_db())
        
        self.document_type = document_type
        self.error_state = error_state if error_state is not None else self.ERROR_STATE
        self.max_concurrent_tasks = max_concurrent_tasks

    async def create_db(self):
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)        

    def __enter__(self):
        """Context manager enter method for resource management."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit method to ensure connections are closed."""
        if hasattr(self, "engine"):
            self.engine.dispose()
        if hasattr(self, "async_engine"):
            # We can't await in __exit__, so we'll use run_until_complete
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    loop.run_until_complete(self.async_engine.dispose())
            except (RuntimeError, ValueError):
                # If there's no event loop or it's closed, just log a message
                # In production, proper logging would be used
                print("Warning: Could not properly dispose async engine in __exit__")
    
    async def __aenter__(self):
        """Async context manager enter method."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit method to ensure connections are closed."""
        if hasattr(self, "async_engine"):
            await self.async_engine.dispose()

    def set_document_type(self, document_type: DocumentType) -> None:
        """Set the document type for this DocStore."""
        self.document_type = document_type
    
    async def aadd(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]:
        """
        Async version: Add a document or list of documents to the store and return the ID(s).

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
            
            async with self.AsyncSession() as session:
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
                await session.commit()
                
                # Log document creation
                log_document_operation(operation="create", doc_id=doc.id, details=f"state={doc.state}")
                return doc.id
        
        # Handle list of documents case
        else:
            doc_ids = []
            async with self.AsyncSession() as session:
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

                await session.commit()
                
                # Log each document creation in the batch
                for i, document in enumerate(doc):
                    log_document_operation(
                        operation="create", 
                        doc_id=document.id, 
                        details=f"state={document.state} (batch item {i+1}/{len(doc)})"
                    )
                
                return doc_ids

    def add(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]:
        """
        Add a document or list of documents to the store and return the ID(s).

        If any document ID is None, a UUID4 will be automatically generated.

        Args:
            doc: The Document or List[Document] to add

        Returns:
            Union[str, List[str]]: The document ID or list of document IDs
        """
        return asyncio.run(self.aadd(doc))

    async def aget(
        self, id: str
    ) -> Union[Document, List[Document], None]:
        """
        Async version: Retrieve document(s) by ID or all documents if no ID is provided.

        Args:
            id: Document ID to retrieve

        Returns:
            Document, List[Document], or None if no matching documents found
        """
        async with self.AsyncSession() as session:
            if id:
                # Use SQLAlchemy 2.0 style query with select()
                stmt = select(DocumentModel).filter_by(id=id)
                result = await session.execute(stmt)
                db_doc = result.scalars().first()
                
                if db_doc is None:
                    return None
                
                # Extract child IDs from the relationship
                await session.refresh(db_doc, ['children'])
                child_ids = [child.id for child in db_doc.children]
                return Document.model_validate(
                    {
                        "id": db_doc.id,
                        "state": db_doc.state,
                        "content": db_doc.content,
                        "media_type": db_doc.media_type,
                        "url": db_doc.url,
                        "parent_id": db_doc.parent_id,
                        "children": child_ids,
                        "metadata": db_doc.cmetadata,
                    }
                )
            else:
                # Return all documents if no ID specified
                stmt = select(DocumentModel)
                result = await session.execute(stmt)
                db_docs = result.scalars().all()
                
                return [
                    Document.model_validate(
                        {
                            "id": db_doc.id,
                            "state": db_doc.state,
                            "content": db_doc.content,
                            "media_type": db_doc.media_type,
                            "url": db_doc.url,
                            "parent_id": db_doc.parent_id,
                            "children": [child.id for child in db_doc.children],
                            "metadata": db_doc.cmetadata,
                        }
                    )
                    for db_doc in db_docs
                ]
                
    def get(
        self, id: str
    ) -> Union[Document, List[Document], None]:
        """
        Retrieve document(s) by ID or all documents if no ID is provided.

        Args:
            id: Document ID to retrieve

        Returns:
            Document, List[Document], or None if no matching documents found
        """
        return asyncio.run(self.aget(id))

    async def adelete(self, id: str) -> None:
        """
        Async version: Delete a document from the store.

        Args:
            id: ID of the document to delete
        """
        async with self.AsyncSession() as session:
            # Use SQLAlchemy 2.0 style query
            stmt = select(DocumentModel).filter_by(id=id)
            result = await session.execute(stmt)
            doc = result.scalars().first()
            
            if doc:
                # Get the state before deleting for logging
                state = doc.state
                await session.delete(doc)
                await session.commit()
                
                # Log document deletion
                log_document_operation(operation="delete", doc_id=id, details=f"state={state}")

    def delete(self, id: str) -> None:
        """
        Delete a document from the store.

        Args:
            id: ID of the document to delete
        """
        return asyncio.run(self.adelete(id))

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

        # Log the transition attempt
        log_document_transition(
            from_state=doc.state,
            to_state=transition.to_state.name,
            doc_id=doc.id
        )

        try:
            # Process the document
            log_document_processing(doc_id=doc.id, process_function=transition.process_func.__name__)
            processed_result = await transition.process_func(doc)

            # Collect all results in a list
            results_to_add = []
            if isinstance(processed_result, list):
                results_to_add.extend(processed_result)
            else:
                results_to_add.append(processed_result)

            # Set parent_id for all child documents
            for new_doc in results_to_add:
                new_doc.parent_id = doc.id

            # Add all documents in a single batch operation
            if results_to_add:
                await self.aadd(results_to_add)

            # Update parent-child relationships
            parent = await self.aget(id=doc.id)
            if parent:
                for new_doc in results_to_add:
                    if new_doc.id not in parent.children:
                        parent.add_child(new_doc.id)

            # Return the list of newly created/added documents
            return results_to_add

        except Exception as e:
            # Log the error in transition
            log_document_transition(
                from_state=doc.state,
                to_state=transition.to_state.name,
                doc_id=doc.id,
                success=False,
                error=str(e)
            )
            
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
            await self.aadd(error_doc)

            # Update the parent document's children list
            parent = await self.aget(id=doc.id)
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
                    log_document_transition(
                        from_state=document.state,
                        to_state="unknown", # Can't determine the target state in this case
                        doc_id=document.id,
                        success=False,
                        error=f"ValueError: {str(e)}"
                    )
                    return None
                except Exception as e:
                    # Log error for other exceptions
                    log_document_transition(
                        from_state=document.state,
                        to_state="unknown", # Can't determine the target state in this case
                        doc_id=document.id,
                        success=False,
                        error=f"Exception: {str(e)}"
                    )
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

    async def aupdate(self, doc: Union[Document, str], **kwargs) -> Document:
        """
        Async version: Update only the metadata of a document.

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

        async with self.AsyncSession() as session:
            # Use SQLAlchemy 2.0 style query
            stmt = select(DocumentModel).filter_by(id=doc_id)
            result = await session.execute(stmt)
            db_doc = result.scalars().first()

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
            await session.refresh(db_doc, ['cmetadata'])
            current_metadata = (
                {} if db_doc.cmetadata is None else db_doc.cmetadata.copy()
            )

            # Update the metadata with the new values
            for key, value in kwargs.items():
                current_metadata[key] = value

            # Update the database
            db_doc.cmetadata = current_metadata
            await session.commit()
            
            # Log the metadata update
            updated_fields = ", ".join(kwargs.keys())
            log_document_operation(
                operation="update", 
                doc_id=doc_id, 
                details=f"metadata fields: {updated_fields}"
            )

            # Return the updated document with the updated metadata
            await session.refresh(db_doc, ['children'])
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
        return asyncio.run(self.aupdate(doc, **kwargs))

    async def alist(self, state: str, leaf: bool = True, **kwargs) -> List[Document]:
        """
        Async version: Return a list of documents with the specified state and metadata filters.

        Args:
            state: Document state to filter by (required)
            leaf: If True, only returns documents without children (default: True)
            **kwargs: Optional metadata key/value pairs to filter by

        Returns:
            List[Document]: List of documents matching the specified criteria
        """
        documents = []
        async with self.AsyncSession() as session:
            # Use SQLAlchemy 2.0 style query
            stmt = select(DocumentModel).filter_by(state=state)
            result = await session.execute(stmt)
            results = result.scalars().all()

            # Filter results based on metadata and leaf parameter
            for db_doc in results:
                await session.refresh(db_doc, ['children'])
                await session.refresh(db_doc, ['cmetadata'])
                # Skip if we want leaf nodes only and this document has children
                if leaf and db_doc.children:
                    continue

                # If there are metadata filters, check them
                if kwargs:
                    # Check if document's metadata matches all provided kwargs
                    if db_doc.cmetadata is not None:  # Make sure metadata exists
                        # Check if all conditions match
                        if all(
                            key in db_doc.cmetadata and db_doc.cmetadata[key] == value
                            for key, value in kwargs.items()
                        ):
                            # Build and add document to list
                            documents.append(Document.model_validate(
                                {
                                    "id": db_doc.id,
                                    "state": db_doc.state,
                                    "content": db_doc.content,
                                    "media_type": db_doc.media_type,
                                    "url": db_doc.url,
                                    "parent_id": db_doc.parent_id,
                                    "children": [child.id for child in db_doc.children],
                                    "metadata": db_doc.cmetadata,
                                }
                            ))
                else:
                    # No metadata filters, just add document if it passes leaf check
                    documents.append(Document.model_validate(
                        {
                            "id": db_doc.id,
                            "state": db_doc.state,
                            "content": db_doc.content,
                            "media_type": db_doc.media_type,
                            "url": db_doc.url,
                            "parent_id": db_doc.parent_id,
                            "children": [child.id for child in db_doc.children],
                            "metadata": db_doc.cmetadata,
                        }
                    ))
                    
        return documents

    def list(self, state: str, leaf: bool = True, **kwargs) -> List[Document]:
        """
        Return a list of documents with the specified state and metadata filters.

        Args:
            state: Document state to filter by (required)
            leaf: If True, only returns documents without children (default: True)
            **kwargs: Optional metadata key/value pairs to filter by

        Returns:
            List[Document]: List of documents matching the specified criteria
        """
        return asyncio.run(self.alist(state, leaf, **kwargs))

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
            existing_doc = await self.aget(id=doc.id)
            if not existing_doc:
                await self.aadd(doc)

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

        # Collect all documents in final states by querying directly
        async with self.AsyncSession() as session:
            final_documents = []
            for state_name in final_state_names:
                # Use SQLAlchemy 2.0 style query for each final state
                stmt = select(DocumentModel).filter_by(state=state_name)
                result = await session.execute(stmt)
                db_docs = result.scalars().all()
                
                # Convert DB models to Document objects
                for db_doc in db_docs:
                    await session.refresh(db_doc, ['children'])
                    doc = Document.model_validate(
                        {
                            "id": db_doc.id,
                            "state": db_doc.state,
                            "content": db_doc.content,
                            "media_type": db_doc.media_type,
                            "url": db_doc.url,
                            "parent_id": db_doc.parent_id,
                            "children": [child.id for child in db_doc.children],
                            "metadata": db_doc.cmetadata,
                        }
                    )
                    final_documents.append(doc)

        return final_documents
