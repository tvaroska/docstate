import pytest
from typing import List
from unittest.mock import AsyncMock, patch

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import Docstore


class TestDocstore:
    @pytest.mark.asyncio
    async def test_init(self, async_sqlite_db_path, document_type):
        """Test Docstore initialization."""
        store = Docstore(
            connection_string=async_sqlite_db_path,
            document_type=document_type
        )
        await store.initialize()
        
        assert store.document_type == document_type
        assert store.error_state == "error"
        assert store.max_concurrency == 10  # Default value
        
        # Test with custom parameters
        custom_store = Docstore(
            connection_string=async_sqlite_db_path,
            document_type=document_type,
            error_state="custom_error",
            max_concurrency=5,
            pool_size=3,
            max_overflow=5,
            echo=True
        )
        await custom_store.initialize()
        
        assert custom_store.error_state == "custom_error"
        assert custom_store.max_concurrency == 5
        
        # Clean up
        await store.dispose()
        await custom_store.dispose()

    @pytest.mark.asyncio
    async def test_set_document_type(self, async_docstore, document_type):
        """Test setting document type."""
        new_document_type = DocumentType(
            states=[DocumentState(name="test")],
            transitions=[]
        )
        async_docstore.set_document_type(new_document_type)
        assert async_docstore.document_type == new_document_type
        
        # Verify that the final state names cache is cleared
        assert async_docstore._final_state_names is None

    @pytest.mark.asyncio
    async def test_final_state_names(self, async_docstore, document_type):
        """Test the final_state_names property."""
        final_names = await async_docstore.final_state_names
        assert "embed" in final_names
        assert "error" in final_names
        
        # Test caching - the property should return the cached value
        assert async_docstore._final_state_names is not None
        cached_names = await async_docstore.final_state_names
        assert cached_names is async_docstore._final_state_names
        
        # Test with a new document type that only has state2 as final state
        new_doctype = DocumentType(
            states=[
                DocumentState(name="state1"),
                DocumentState(name="state2"),
                DocumentState(name="final_state")
            ],
            transitions=[
                Transition(
                    from_state=DocumentState(name="state1"),
                    to_state=DocumentState(name="state2"),
                    process_func=lambda x: x
                )
            ]
        )
        
        async_docstore.set_document_type(new_doctype)
        # Cache should be cleared
        assert async_docstore._final_state_names is None
        
        new_final_names = await async_docstore.final_state_names
        assert "final_state" in new_final_names
        assert "state2" in new_final_names  # Both state2 and final_state are final states
        assert "error" in new_final_names  # Error state is always included

    @pytest.mark.asyncio
    async def test_add_single_document(self, async_docstore, document):
        """Test adding a single document."""
        doc_id = await async_docstore.add(document)
        assert doc_id == document.id

        # Retrieve the document to verify it was added
        retrieved_doc = await async_docstore.get(id=doc_id)
        assert retrieved_doc is not None
        assert retrieved_doc.id == document.id
        assert retrieved_doc.state == document.state
        assert retrieved_doc.content == document.content
        assert retrieved_doc.media_type == document.media_type
        assert retrieved_doc.metadata == document.metadata

    @pytest.mark.asyncio
    async def test_add_multiple_documents(self, async_docstore, documents):
        """Test adding multiple documents."""
        doc_ids = await async_docstore.add(documents)
        assert len(doc_ids) == len(documents)
        
        for i, doc_id in enumerate(doc_ids):
            assert doc_id == documents[i].id
            
            # Retrieve each document to verify it was added
            retrieved_doc = await async_docstore.get(id=doc_id)
            assert retrieved_doc is not None
            assert retrieved_doc.id == documents[i].id
            assert retrieved_doc.state == documents[i].state
            assert retrieved_doc.content == documents[i].content

    @pytest.mark.asyncio
    async def test_get_by_id(self, async_docstore, document):
        """Test getting a document by ID."""
        await async_docstore.add(document)
        retrieved_doc = await async_docstore.get(id=document.id)
        assert retrieved_doc is not None
        assert retrieved_doc.id == document.id

        # Test getting a non-existent document
        non_existent_doc = await async_docstore.get(id="non_existent_id")
        assert non_existent_doc is None
        
        # Test getting document without content
        no_content_doc = await async_docstore.get(id=document.id, include_content=False)
        assert no_content_doc is not None
        assert no_content_doc.id == document.id
        assert no_content_doc.content is None  # Content should be excluded

    @pytest.mark.asyncio
    async def test_get_batch(self, async_docstore, documents):
        """Test getting multiple documents by IDs in batch."""
        await async_docstore.add(documents)
        
        # Get document IDs
        doc_ids = [doc.id for doc in documents]
        
        # Retrieve documents in batch
        retrieved_docs = await async_docstore.get_batch(doc_ids)
        assert len(retrieved_docs) == len(documents)
        
        # Verify all documents were retrieved
        retrieved_ids = [doc.id for doc in retrieved_docs]
        for doc_id in doc_ids:
            assert doc_id in retrieved_ids
            
        # Test with empty list
        empty_result = await async_docstore.get_batch([])
        assert empty_result == []
        
        # Test with mix of existing and non-existing IDs
        mixed_ids = doc_ids + ["non_existent_id"]
        mixed_result = await async_docstore.get_batch(mixed_ids)
        assert len(mixed_result) == len(documents)  # Only existing docs should be returned

    @pytest.mark.asyncio
    async def test_delete(self, async_docstore, document):
        """Test deleting a document."""
        await async_docstore.add(document)
        retrieved_doc = await async_docstore.get(id=document.id)
        assert retrieved_doc is not None

        await async_docstore.delete(document.id)
        deleted_doc = await async_docstore.get(id=document.id)
        assert deleted_doc is None

    @pytest.mark.asyncio
    async def test_update(self, async_docstore, document):
        """Test updating document metadata."""
        await async_docstore.add(document)
        
        # Update with document object
        updated_doc = await async_docstore.update(document, new_field="new_value")
        assert updated_doc.metadata["new_field"] == "new_value"
        assert updated_doc.metadata["test"] == True  # Original metadata preserved
        
        # Update with document ID
        updated_doc = await async_docstore.update(document.id, another_field="another_value")
        assert updated_doc.metadata["another_field"] == "another_value"
        assert updated_doc.metadata["new_field"] == "new_value"
        assert updated_doc.metadata["test"] == True
        
        # Test updating a non-existent document
        with pytest.raises(ValueError):
            await async_docstore.update("non_existent_id", field="value")
        
        # Create a document that doesn't match the one in the database
        different_doc = Document(
            id=document.id,
            state="different_state",
            content="Different content",
            media_type="text/plain"
        )
        with pytest.raises(ValueError):
            await async_docstore.update(different_doc, field="value")

    @pytest.mark.asyncio
    async def test_list(self, async_docstore, document, documents):
        """Test listing documents with filtering."""
        # Add one document with specific metadata
        document.metadata["filter_field"] = "filter_value"
        await async_docstore.add(document)
        
        # Add other documents
        await async_docstore.add(documents)
        
        # List all documents in the 'link' state
        link_docs = await async_docstore.list(state="link")
        assert len(link_docs) == len(documents) + 1
        
        # List documents with specific metadata
        filtered_docs = await async_docstore.list(state="link", filter_field="filter_value")
        assert len(filtered_docs) == 1
        assert filtered_docs[0].id == document.id
        
        # Test leaf parameter
        # First, create a parent-child relationship
        parent_doc = Document(
            state="link",
            content="Parent content",
            media_type="text/plain"
        )
        child_doc = Document(
            state="link",
            content="Child content",
            media_type="text/plain",
            parent_id=parent_doc.id
        )
        await async_docstore.add(parent_doc)
        await async_docstore.add(child_doc)
        
        # Get parent by ID to update its children
        parent = await async_docstore.get(id=parent_doc.id)
        parent.add_child(child_doc.id)
        await async_docstore.update(parent)
        
        # List only leaf nodes (documents without children)
        leaf_docs = await async_docstore.list(state="link", leaf=True)
        parent_ids = [doc.id for doc in leaf_docs]
        assert parent_doc.id not in parent_ids  # Parent should not be included
        assert child_doc.id in parent_ids  # Child should be included
        
        # List including non-leaf nodes
        all_docs = await async_docstore.list(state="link", leaf=False)
        all_ids = [doc.id for doc in all_docs]
        assert parent_doc.id in all_ids  # Parent should be included
        
        # List without content
        no_content_docs = await async_docstore.list(state="link", include_content=False)
        assert all(doc.content is None for doc in no_content_docs)

    @pytest.mark.asyncio
    async def test_next_single_document(self, async_docstore, document):
        """Test processing a single document to the next state."""
        await async_docstore.add(document)
        processed_docs = await async_docstore.next(document)
        
        # Verify the result
        assert len(processed_docs) == 1
        assert processed_docs[0].state == "processed"
        assert processed_docs[0].content == "Processed content"
        assert processed_docs[0].parent_id == document.id
        
        # Verify the parent-child relationship
        parent = await async_docstore.get(id=document.id)
        assert parent.children[0] == processed_docs[0].id

    @pytest.mark.asyncio
    async def test_next_multiple_documents(self, async_docstore, documents):
        """Test processing multiple documents to the next state."""
        await async_docstore.add(documents)
        processed_docs = await async_docstore.next(documents)
        
        # Verify the results
        assert len(processed_docs) == len(documents)
        for i, doc in enumerate(processed_docs):
            assert doc.state == "processed"
            assert doc.parent_id == documents[i].id
            
            # Verify the parent-child relationship
            parent = await async_docstore.get(id=documents[i].id)
            assert parent.children[0] == doc.id

    @pytest.mark.asyncio
    async def test_next_with_document_splits(self, async_docstore, document):
        """Test processing a document that splits into multiple documents."""
        # Create a custom document type with a transition that returns multiple documents
        link = DocumentState(name="link")
        split = DocumentState(name="split")
        
        # Create a mock process function that returns multiple documents
        async def mock_process_with_children(doc: Document) -> List[Document]:
            return [
                Document(
                    state="child1",
                    content="Child 1 content",
                    media_type="text/plain",
                    metadata={"child": 1}
                ),
                Document(
                    state="child2",
                    content="Child 2 content",
                    media_type="text/plain",
                    metadata={"child": 2}
                )
            ]
        
        transitions = [
            Transition(
                from_state=link,
                to_state=split,
                process_func=AsyncMock(side_effect=mock_process_with_children)
            )
        ]
        
        doctype = DocumentType(
            states=[link, split],
            transitions=transitions
        )
        
        async_docstore.set_document_type(doctype)
        
        # Process the document
        await async_docstore.add(document)
        processed_docs = await async_docstore.next(document)
        
        # Verify the results
        assert len(processed_docs) == 2
        assert processed_docs[0].state == "child1"
        assert processed_docs[1].state == "child2"
        assert processed_docs[0].parent_id == document.id
        assert processed_docs[1].parent_id == document.id
        
        # Verify the parent-child relationship
        parent = await async_docstore.get(id=document.id)
        assert len(parent.children) == 2
        assert processed_docs[0].id in parent.children
        assert processed_docs[1].id in parent.children

    @pytest.mark.asyncio
    async def test_next_with_error(self, async_docstore, document):
        """Test processing a document with an error."""
        # Create a custom document type with a transition that raises an error
        link = DocumentState(name="link")
        error = DocumentState(name="error")
        
        # Create a mock process function that raises an error
        async def mock_process_with_error(doc: Document) -> Document:
            raise ValueError("Test process error")
        
        transitions = [
            Transition(
                from_state=link,
                to_state=error,
                process_func=AsyncMock(side_effect=mock_process_with_error)
            )
        ]
        
        doctype = DocumentType(
            states=[link, error],
            transitions=transitions
        )
        
        async_docstore.set_document_type(doctype)
        
        # Process the document
        await async_docstore.add(document)
        processed_docs = await async_docstore.next(document)
        
        # Verify the results - should have an error document
        assert len(processed_docs) == 1
        assert processed_docs[0].state == "error"
        assert processed_docs[0].parent_id == document.id
        assert "Test process error" in processed_docs[0].content
        
        # Verify the parent-child relationship
        parent = await async_docstore.get(id=document.id)
        assert len(parent.children) == 1
        assert processed_docs[0].id in parent.children

    @pytest.mark.asyncio
    async def test_next_with_missing_document_type(self, async_sqlite_db_path, document):
        """Test processing a document without a document type."""
        # Create store without document type
        store = Docstore(connection_string=async_sqlite_db_path)
        await store.initialize()
        
        await store.add(document)
        
        # Attempting to call next() without a document type should raise a ValueError
        with pytest.raises(ValueError, match="Document type not set"):
            await store.next(document)
            
        await store.dispose()

    @pytest.mark.asyncio
    async def test_finish(self, async_docstore, document):
        """Test processing a document through the entire pipeline."""
        # Create a new document type with a well-defined final state
        link = DocumentState(name="link")
        process = DocumentState(name="processed")
        final = DocumentState(name="final")
        
        async def mock_process(doc: Document) -> Document:
            return Document(
                state="processed",
                content="Processed content",
                media_type="text/plain",
                metadata={"processed": True}
            )
        
        async def mock_final(doc: Document) -> Document:
            return Document(
                state="final",
                content="Final content",
                media_type="text/plain",
                metadata={"final": True}
            )
        
        transitions = [
            Transition(
                from_state=link,
                to_state=process,
                process_func=AsyncMock(side_effect=mock_process)
            ),
            Transition(
                from_state=process,
                to_state=final,
                process_func=AsyncMock(side_effect=mock_final)
            )
        ]
        
        doctype = DocumentType(
            states=[link, process, final],
            transitions=transitions
        )
        
        async_docstore.set_document_type(doctype)
        
        # Process the document through the pipeline
        document.state = "link"  # Ensure correct starting state
        await async_docstore.add(document)
        final_docs = await async_docstore.finish(document)
        
        # Should have documents in final state
        assert len(final_docs) > 0
        assert any(doc.state == "final" for doc in final_docs)
        
        # Test with a list of documents
        new_doc = Document(
            state="link",
            content="Another test content",
            media_type="text/plain",
            metadata={"test": True}
        )
        await async_docstore.add(new_doc)
        final_docs = await async_docstore.finish([new_doc])
        assert len(final_docs) > 0
        assert any(doc.state == "final" for doc in final_docs)

    @pytest.mark.asyncio
    async def test_stream_content(self, async_docstore, document):
        """Test streaming document content in chunks."""
        # Create a document with large content
        large_content = "A" * 5000  # 5000 characters
        large_doc = Document(
            state="large",
            content=large_content,
            media_type="text/plain"
        )
        await async_docstore.add(large_doc)
        
        # Stream the content in chunks
        chunks = []
        # Get the async generator object
        stream_gen = async_docstore.stream_content(large_doc.id, chunk_size=1000)
        # Manually iterate through the async generator
        async for chunk in stream_gen:
            chunks.append(chunk)
            
        # Verify all chunks together form the original content
        assert "".join(chunks) == large_content
        assert len(chunks) == 5  # Should be split into 5 chunks of 1000 chars each
        
        # Test with non-existent document
        with pytest.raises(ValueError, match="not found"):
            stream_gen = async_docstore.stream_content("non_existent_id")
            # Need to start iterating to trigger the exception
            async for _ in stream_gen:
                pass
                
        # Test with empty content
        empty_doc = Document(
            state="empty",
            content="",
            media_type="text/plain"
        )
        await async_docstore.add(empty_doc)
        
        empty_chunks = []
        async for chunk in async_docstore.stream_content(empty_doc.id):
            empty_chunks.append(chunk)
            
        assert len(empty_chunks) == 1
        assert empty_chunks[0] == ""

    @pytest.mark.asyncio
    async def test_count(self, async_docstore, documents):
        """Test counting documents with optional state filter."""
        # Add documents
        await async_docstore.add(documents)
        
        # Count all documents
        total_count = await async_docstore.count()
        assert total_count == len(documents)
        
        # Count documents by state
        state_count = await async_docstore.count(state="link")
        assert state_count == len(documents)
        
        # Count documents with non-existent state
        zero_count = await async_docstore.count(state="non_existent")
        assert zero_count == 0
        
        # Add document with different state
        different_doc = Document(
            state="different",
            content="Different content",
            media_type="text/plain"
        )
        await async_docstore.add(different_doc)
        
        # Verify total count increased
        new_total = await async_docstore.count()
        assert new_total == len(documents) + 1
        
        # Verify state count is unchanged
        same_state_count = await async_docstore.count(state="link")
        assert same_state_count == len(documents)
        
        # Verify different state count
        diff_state_count = await async_docstore.count(state="different")
        assert diff_state_count == 1

    @pytest.mark.asyncio
    async def test_context_manager(self, async_sqlite_db_path, document_type):
        """Test using Docstore as an async context manager."""
        async with Docstore(
            connection_string=async_sqlite_db_path,
            document_type=document_type
        ) as store:
            await store.initialize()
            await store.add(Document(state="test", content="test"))
            docs = await store.list(state="test")
            assert len(docs) == 1
            assert docs[0].content == "test"
            
        # The store should be disposed after exiting the context manager
        # We don't have a direct way to test this, but we can verify the context manager works
