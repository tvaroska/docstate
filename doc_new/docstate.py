import asyncio
from datetime import datetime
from functools import lru_cache
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple, Type, Union, cast
from uuid import uuid4

from sqlalchemy import select, func, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.pool import AsyncAdaptedQueuePool

from doc_new.database import Base, DocumentModel
from doc_new.document import Document, DocumentType
from doc_new.utils import (
    log_document_operation, 
    log_document_processing, 
    log_document_transition,
    async_timed,
    gather_with_concurrency
)


class AsyncDocStore:
    """
    Fully asynchronous document store for managing documents through state transitions.
    
    This implementation is optimized for high performance with:
    - Connection pooling
    - Batch operations
    - Parallel processing
    - Query optimization
    - Caching
    - Streaming support for large documents
    """

    # Default error state name
    ERROR_STATE = "error"

    def __init__(
        self,
        connection_string: str,
        document_type: Optional[DocumentType] = None,
        error_state: Optional[str] = None,
        max_concurrency: int = 10,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
        pool_recycle: int = 1800,
        echo: bool = False,
    ):
        """
        Initialize the AsyncDocStore with a database connection and document type.

        Args:
            connection_string: SQLAlchemy connection string for the database
            document_type: DocumentType defining the state machine for documents
            error_state: Optional custom name for the error state. Defaults to ERROR_STATE.
            max_concurrency: Maximum number of concurrent document processing tasks
            pool_size: The size of the connection pool
            max_overflow: The maximum overflow size of the pool
            pool_timeout: Seconds to wait before timing out on getting a connection
            pool_recycle: Seconds after which a connection is recycled
            echo: Whether to echo SQL to the logs
        """
        # Convert connection string to async format if needed
        if connection_string.startswith('sqlite'):
            async_connection_string = connection_string.replace('sqlite', 'sqlite+aiosqlite', 1)
        else:
            # For other databases, user needs to provide proper async driver
            async_connection_string = connection_string
            
        # Create engine with optimized connection pooling
        self.engine = create_async_engine(
            async_connection_string,
            echo=echo,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            poolclass=AsyncAdaptedQueuePool,
        )
        
        # Create sessionmaker with expire_on_commit=False for better performance
        self.async_session = async_sessionmaker(
            bind=self.engine, 
            class_=AsyncSession, 
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        self.document_type = document_type
        self.error_state = error_state if error_state is not None else self.ERROR_STATE
        self.max_concurrency = max_concurrency
        
        # Cache for final state names
        self._final_state_names: Optional[List[str]] = None
        
    async def initialize(self):
        """
        Initialize the database by creating all tables if they don't exist.
        
        This method should be called after creating the AsyncDocStore instance.
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
    async def __aenter__(self):
        """Async context manager enter method."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit method to ensure connections are closed."""
        await self.dispose()
            
    async def dispose(self):
        """Close all connections in the connection pool."""
        if hasattr(self, "engine"):
            await self.engine.dispose()
    
    def set_document_type(self, document_type: DocumentType) -> None:
        """Set the document type for this AsyncDocStore."""
        self.document_type = document_type
        # Clear the final state names cache when setting a new document type
        self._final_state_names = None
    
    @property
    async def final_state_names(self) -> List[str]:
        """
        Get the names of all final states.
        
        This property caches the result for better performance.
        """
        if self._final_state_names is not None:
            return self._final_state_names
            
        if not self.document_type:
            return [self.error_state]
            
        final_states = self.document_type.final
        state_names = [state.name for state in final_states]
        
        # Add error state if it's not already in the list
        if self.error_state not in state_names:
            state_names.append(self.error_state)
            
        # Cache the result
        self._final_state_names = state_names
        return state_names
    
    async def _convert_model_to_document(self, db_doc: DocumentModel) -> Document:
        """
        Convert a DocumentModel to a Document.
        
        Args:
            db_doc: The DocumentModel to convert.
            
        Returns:
            The converted Document.
        """
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
                "metadata": db_doc.cmetadata or {},
            }
        )
    
    @async_timed()
    async def add(self, doc: Union[Document, List[Document]]) -> Union[str, List[str]]:
        """
        Add a document or list of documents to the store and return the ID(s).

        If any document ID is None, a UUID4 will be automatically generated.
        This method optimizes batch inserts for better performance.

        Args:
            doc: The Document or List[Document] to add

        Returns:
            Union[str, List[str]]: The document ID or list of document IDs
        """
        # Handle single document case
        if not isinstance(doc, list):
            docs = [doc]
        else:
            docs = doc

        # Prepare all documents before creating the session
        db_docs = []
        doc_ids = []
        
        for document in docs:
            # Generate UUID4 if ID is None
            if document.id is None:
                document.id = str(uuid4())
                
            doc_ids.append(document.id)
            
            db_docs.append(DocumentModel(
                id=document.id,
                state=document.state,
                content=document.content,
                media_type=document.media_type,
                url=document.url,
                parent_id=document.parent_id,
                cmetadata=document.metadata,
            ))

        # Add all documents in a single transaction
        async with self.async_session() as session:
            async with session.begin():
                for db_doc in db_docs:
                    session.add(db_doc)
            
        # Log document creation operations
        for i, document in enumerate(docs):
            log_document_operation(
                operation="create", 
                doc_id=document.id, 
                details=f"state={document.state} {f'(batch item {i+1}/{len(docs)})' if len(docs) > 1 else ''}"
            )
        
        # Return single ID or list based on input type
        return doc_ids[0] if not isinstance(doc, list) else doc_ids

    @async_timed()
    async def get(
        self, id: Optional[str] = None, state: Optional[str] = None, include_content: bool = True
    ) -> Union[Document, List[Document], None]:
        """
        Retrieve document(s) by ID, state, or all documents if no filters provided.

        Args:
            id: Document ID to retrieve
            state: Document state to filter by
            include_content: Whether to include the content field (can improve performance for large documents)

        Returns:
            Document, List[Document], or None if no matching documents found
        """
        async with self.async_session() as session:
            # Build query based on provided filters
            if id:
                stmt = select(DocumentModel).filter_by(id=id).options(selectinload(DocumentModel.children))
                result = await session.execute(stmt)
                db_doc = result.scalars().first()
                
                if db_doc is None:
                    return None
                
                return await self._convert_model_to_document(db_doc)
            else:
                # Apply state filter if provided
                stmt = select(DocumentModel).options(selectinload(DocumentModel.children))
                if state:
                    stmt = stmt.filter_by(state=state)
                    
                # Optimize query if content is not needed
                if not include_content:
                    # This optimization requires SQLAlchemy 1.4+
                    stmt = stmt.with_only_columns([c for c in DocumentModel.__table__.c if c.name != 'content'])
                    
                result = await session.execute(stmt)
                db_docs = result.scalars().all()
                
                # Convert all models to Documents
                documents = []
                for db_doc in db_docs:
                    doc = await self._convert_model_to_document(db_doc)
                    documents.append(doc)
                
                return documents

    @async_timed()
    async def get_batch(self, ids: List[str]) -> List[Document]:
        """
        Efficiently retrieve multiple documents by their IDs in a single query.
        
        Args:
            ids: List of document IDs to retrieve
            
        Returns:
            List of Document objects. Missing documents are not included.
        """
        if not ids:
            return []
            
        async with self.async_session() as session:
            stmt = select(DocumentModel).where(
                DocumentModel.id.in_(ids)
            ).options(selectinload(DocumentModel.children))
            
            result = await session.execute(stmt)
            db_docs = result.scalars().all()
            
            # Convert all models to Documents
            documents = []
            for db_doc in db_docs:
                doc = await self._convert_model_to_document(db_doc)
                documents.append(doc)
            
            return documents

    @async_timed()
    async def delete(self, id: str) -> None:
        """
        Delete a document from the store.

        Args:
            id: ID of the document to delete
        """
        async with self.async_session() as session:
            async with session.begin():
                stmt = select(DocumentModel).filter_by(id=id)
                result = await session.execute(stmt)
                doc = result.scalars().first()
                
                if doc:
                    # Get the state before deleting for logging
                    state = doc.state
                    await session.delete(doc)
                    
                    # Log document deletion
                    log_document_operation(operation="delete", doc_id=id, details=f"state={state}")

    @async_timed()
    async def update(self, doc: Union[Document, str], **kwargs) -> Document:
        """
        Update the metadata of a document.

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

        async with self.async_session() as session:
            async with session.begin():
                stmt = select(DocumentModel).filter_by(id=doc_id).options(
                    selectinload(DocumentModel.children)
                )
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
                current_metadata = (
                    {} if db_doc.cmetadata is None else db_doc.cmetadata.copy()
                )

                # Update the metadata with the new values
                for key, value in kwargs.items():
                    current_metadata[key] = value

                # Update the database
                db_doc.cmetadata = current_metadata
                
                # Log the metadata update
                updated_fields = ", ".join(kwargs.keys())
                log_document_operation(
                    operation="update", 
                    doc_id=doc_id, 
                    details=f"metadata fields: {updated_fields}"
                )

            # Return the updated document with the updated metadata
            return await self._convert_model_to_document(db_doc)

    async def _process_single_document(
        self, doc: Document, session: AsyncSession
    ) -> List[Document]:
        """
        Process a single document transition.
        
        Args:
            doc: The document to process
            session: SQLAlchemy async session to use for database operations
            
        Returns:
            List of resulting documents after the transition
        """
        if not self.document_type:
            raise ValueError("Document type not set for AsyncDocStore")

        transitions = self.document_type.get_transition(doc.state)
        if not transitions:
            # If no transition, return an empty list (no new documents created)
            return []

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
            start_time = datetime.now()
            log_document_processing(doc_id=doc.id, process_function=transition.process_func.__name__, start_time=start_time)
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

            # Add all documents to the database
            if results_to_add:
                # Create DocumentModel instances
                db_docs = []
                for result_doc in results_to_add:
                    db_doc = DocumentModel(
                        id=result_doc.id if result_doc.id else str(uuid4()),
                        state=result_doc.state,
                        content=result_doc.content,
                        media_type=result_doc.media_type,
                        url=result_doc.url,
                        parent_id=result_doc.parent_id,
                        cmetadata=result_doc.metadata,
                    )
                    db_docs.append(db_doc)
                    # Update the document ID if it was generated
                    if not result_doc.id:
                        result_doc.id = db_doc.id
                
                # Add all documents to the session
                for db_doc in db_docs:
                    session.add(db_doc)

            # Get the parent document to update its children list
            stmt = select(DocumentModel).filter_by(id=doc.id).options(
                selectinload(DocumentModel.children)
            )
            result = await session.execute(stmt)
            parent_db_doc = result.scalars().first()
            
            if parent_db_doc:
                # Update the parent's children in the Document object
                parent_doc = await self._convert_model_to_document(parent_db_doc)
                
                # Add new children to the parent document
                new_child_ids = [doc.id for doc in results_to_add]
                parent_doc.add_children(new_child_ids)
                
                # Update the parent document's children list in the database
                parent_db_doc.children.extend([
                    db_doc for db_doc in db_docs 
                    if db_doc.id not in [child.id for child in parent_db_doc.children]
                ])

            # Return the list of newly created documents
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
                    "timestamp": datetime.now().isoformat(),
                    "process_function": transition.process_func.__name__,
                },
            )

            # Add the error document to the database
            db_error_doc = DocumentModel(
                id=error_doc.id,
                state=error_doc.state,
                content=error_doc.content,
                media_type=error_doc.media_type,
                url=error_doc.url,
                parent_id=error_doc.parent_id,
                cmetadata=error_doc.metadata,
            )
            session.add(db_error_doc)

            # Update the parent document's children list
            stmt = select(DocumentModel).filter_by(id=doc.id).options(
                selectinload(DocumentModel.children)
            )
            result = await session.execute(stmt)
            parent_db_doc = result.scalars().first()
            
            if parent_db_doc and error_doc.id not in [child.id for child in parent_db_doc.children]:
                parent_db_doc.children.append(db_error_doc)

            # Return the error document
            return [error_doc]

    @async_timed()
    async def next(self, docs: Union[Document, List[Document]]) -> List[Document]:
        """
        Process document(s) to their next state according to the document type.
        
        This implementation uses asyncio.gather with concurrency control for
        parallel processing with optimal performance.

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
        
        # Process documents in a single transaction for better performance
        async with self.async_session() as session:
            async with session.begin():
                # Define the processing function for each document
                async def process_doc(document: Document) -> List[Document]:
                    try:
                        return await self._process_single_document(document, session)
                    except Exception as e:
                        log_document_transition(
                            from_state=document.state,
                            to_state="unknown",
                            doc_id=document.id,
                            success=False,
                            error=f"Exception: {str(e)}"
                        )
                        return []
                
                # Process documents in parallel with concurrency control
                tasks = [process_doc(doc) for doc in valid_docs]
                results = await gather_with_concurrency(self.max_concurrency, *tasks)
                
                # Flatten results
                for result_list in results:
                    all_results.extend(result_list)
        
        return all_results

    @async_timed()
    async def list(
        self, 
        state: str, 
        leaf: bool = True, 
        include_content: bool = True,
        **kwargs
    ) -> List[Document]:
        """
        Return a list of documents with the specified state and metadata filters.

        Args:
            state: Document state to filter by (required)
            leaf: If True, only returns documents without children (default: True)
            include_content: Whether to include the content field (default: True)
            **kwargs: Optional metadata key/value pairs to filter by

        Returns:
            List[Document]: List of documents matching the specified criteria
        """
        async with self.async_session() as session:
            # Start with a base query for documents in the specified state
            stmt = select(DocumentModel).filter_by(state=state).options(
                selectinload(DocumentModel.children)
            )
            
            # Optimize query if content is not needed
            if not include_content:
                stmt = stmt.with_only_columns([c for c in DocumentModel.__table__.c if c.name != 'content'])
            
            result = await session.execute(stmt)
            results = result.scalars().all()

            # Filter results based on metadata and leaf parameter
            documents = []
            for db_doc in results:
                # Skip if we want leaf nodes only and this document has children
                if leaf and db_doc.children:
                    continue

                # Check metadata filters if provided
                if kwargs:
                    # Make sure metadata exists and matches all filters
                    if db_doc.cmetadata is not None and all(
                        key in db_doc.cmetadata and db_doc.cmetadata[key] == value
                        for key, value in kwargs.items()
                    ):
                        documents.append(await self._convert_model_to_document(db_doc))
                else:
                    # No metadata filters, just add document if it passes leaf check
                    documents.append(await self._convert_model_to_document(db_doc))
                    
            return documents

    @async_timed()
    async def finish(self, docs: Union[Document, List[Document]]) -> List[Document]:
        """
        Process document(s) through the entire pipeline until all reach a final state.
        
        This implementation uses optimized database operations and parallel processing
        for maximum performance.

        Args:
            docs: The Document or List[Document] to process to completion

        Returns:
            List[Document]: A list of all documents that reached a final state
        """
        if not self.document_type:
            raise ValueError("Document type not set for AsyncDocStore")

        # Convert single document to list for consistent handling
        if not isinstance(docs, list):
            docs_to_process = [docs]
        else:
            docs_to_process = docs

        # Add documents to database if they don't exist already
        for doc in docs_to_process:
            # Check if document exists in database
            existing_doc = await self.get(id=doc.id)
            if not existing_doc:
                await self.add(doc)

        # Get final states
        final_state_names = await self.final_state_names

        # Process documents until all are in final states
        documents_to_process = docs_to_process.copy()
        
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
        final_documents = []
        
        # Optimize by querying all final states in a single query
        async with self.async_session() as session:
            stmt = select(DocumentModel).filter(
                DocumentModel.state.in_(final_state_names)
            ).options(selectinload(DocumentModel.children))
            
            result = await session.execute(stmt)
            db_docs = result.scalars().all()
            
            # Convert DB models to Document objects
            for db_doc in db_docs:
                doc = await self._convert_model_to_document(db_doc)
                final_documents.append(doc)

        return final_documents
        
    @async_timed()
    async def stream_content(self, doc_id: str, chunk_size: int = 1024) -> AsyncGenerator[str, None]:
        """
        Stream the content of a document in chunks to handle large documents efficiently.
        
        Args:
            doc_id: The ID of the document to stream
            chunk_size: The size of each chunk in characters
            
        Yields:
            Chunks of the document content
            
        Raises:
            ValueError: If the document is not found
        """
        async with self.async_session() as session:
            # First get the document without content to check if it exists
            stmt = select(DocumentModel.id).filter_by(id=doc_id)
            result = await session.execute(stmt)
            doc_exists = result.scalar_one_or_none()
            
            if not doc_exists:
                raise ValueError(f"Document with ID {doc_id} not found")
            
            # Now get just the content column
            stmt = select(DocumentModel.content).filter_by(id=doc_id)
            result = await session.execute(stmt)
            content = result.scalar_one()
            
            if not content:
                # If content is None or empty, yield empty string and finish
                yield ""
                return
                
            # Stream the content in chunks
            for i in range(0, len(content), chunk_size):
                yield content[i:i + chunk_size]

    @async_timed()
    async def count(self, state: Optional[str] = None) -> int:
        """
        Count documents, optionally filtered by state.
        
        Args:
            state: Optional state to filter by
            
        Returns:
            Number of matching documents
        """
        async with self.async_session() as session:
            stmt = select(func.count(DocumentModel.id))
            if state:
                stmt = stmt.filter_by(state=state)
                
            result = await session.execute(stmt)
            return result.scalar_one()
