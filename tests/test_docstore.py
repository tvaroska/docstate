import pytest
from typing import List
from unittest.mock import AsyncMock

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore


class TestDocStore:
    def test_init(self, sqlite_db_path, document_type):
        """Test DocStore initialization."""
        store = DocStore(
            connection_string=sqlite_db_path,
            document_type=document_type
        )
        assert store.document_type == document_type
        assert store.error_state == "error"

        # Test with custom error state
        custom_error_state = "custom_error"
        store = DocStore(
            connection_string=sqlite_db_path,
            document_type=document_type,
            error_state=custom_error_state
        )
        assert store.error_state == custom_error_state

    def test_set_document_type(self, docstore, document_type):
        """Test setting document type."""
        new_document_type = DocumentType(
            states=[DocumentState(name="test")],
            transitions=[]
        )
        docstore.set_document_type(new_document_type)
        assert docstore.document_type == new_document_type

    def test_add_single_document(self, docstore, document):
        """Test adding a single document."""
        doc_id = docstore.add(document)
        assert doc_id == document.id

        # Retrieve the document to verify it was added
        retrieved_doc = docstore.get(id=doc_id)
        assert retrieved_doc is not None
        assert retrieved_doc.id == document.id
        assert retrieved_doc.state == document.state
        assert retrieved_doc.content == document.content
        assert retrieved_doc.media_type == document.media_type
        assert retrieved_doc.metadata == document.metadata

    def test_add_multiple_documents(self, docstore, documents):
        """Test adding multiple documents."""
        doc_ids = docstore.add(documents)
        assert len(doc_ids) == len(documents)
        
        for i, doc_id in enumerate(doc_ids):
            assert doc_id == documents[i].id
            
            # Retrieve each document to verify it was added
            retrieved_doc = docstore.get(id=doc_id)
            assert retrieved_doc is not None
            assert retrieved_doc.id == documents[i].id
            assert retrieved_doc.state == documents[i].state
            assert retrieved_doc.content == documents[i].content

    def test_get_by_id(self, docstore, document):
        """Test getting a document by ID."""
        docstore.add(document)
        retrieved_doc = docstore.get(id=document.id)
        assert retrieved_doc is not None
        assert retrieved_doc.id == document.id

        # Test getting a non-existent document
        non_existent_doc = docstore.get(id="non_existent_id")
        assert non_existent_doc is None

    def test_delete(self, docstore, document):
        """Test deleting a document."""
        docstore.add(document)
        retrieved_doc = docstore.get(id=document.id)
        assert retrieved_doc is not None

        docstore.delete(document.id)
        deleted_doc = docstore.get(id=document.id)
        assert deleted_doc is None

    def test_update(self, docstore, document):
        """Test updating document metadata."""
        docstore.add(document)
        
        # Update with document object
        updated_doc = docstore.update(document, new_field="new_value")
        assert updated_doc.metadata["new_field"] == "new_value"
        assert updated_doc.metadata["test"] == True  # Original metadata preserved
        
        # Update with document ID
        updated_doc = docstore.update(document.id, another_field="another_value")
        assert updated_doc.metadata["another_field"] == "another_value"
        assert updated_doc.metadata["new_field"] == "new_value"
        assert updated_doc.metadata["test"] == True
        
        # Test updating a non-existent document
        with pytest.raises(ValueError):
            docstore.update("non_existent_id", field="value")
        
        # Create a document that doesn't match the one in the database
        different_doc = Document(
            id=document.id,
            state="different_state",
            content="Different content",
            media_type="text/plain"
        )
        with pytest.raises(ValueError):
            docstore.update(different_doc, field="value")

    def test_list(self, docstore, document, documents):
        """Test listing documents with filtering."""
        # Add one document with specific metadata
        document.metadata["filter_field"] = "filter_value"
        docstore.add(document)
        
        # Add other documents
        docstore.add(documents)
        
        # List all documents in the 'link' state
        link_docs = docstore.list(state="link")
        assert len(link_docs) == len(documents) + 1
        
        # List documents with specific metadata
        filtered_docs = docstore.list(state="link", filter_field="filter_value")
        assert len(filtered_docs) == 1
        assert filtered_docs[0].id == document.id
        
        # List documents with non-existent metadata
        non_existent_docs = docstore.list(state="link", non_existent="value")
        assert len(non_existent_docs) == 0

    @pytest.mark.asyncio
    async def test_next_single_document(self, docstore, document):
        """Test processing a single document to the next state."""
        await docstore.aadd(document)
        processed_docs = await docstore.next(document)
        
        # Verify the result
        assert len(processed_docs) == 1
        assert processed_docs[0].state == "processed"
        assert processed_docs[0].content == "Processed content"
        assert processed_docs[0].parent_id == document.id
        
        # Verify the parent-child relationship
        parent = await docstore.aget(id=document.id)
        assert parent.children[0] == processed_docs[0].id

    @pytest.mark.asyncio
    async def test_next_multiple_documents(self, docstore, documents):
        """Test processing multiple documents to the next state."""
        await docstore.aadd(documents)
        processed_docs = await docstore.next(documents)
        
        # Verify the results
        assert len(processed_docs) == len(documents)
        for i, doc in enumerate(processed_docs):
            assert doc.state == "processed"
            assert doc.parent_id == documents[i].id
            
            # Verify the parent-child relationship
            parent = await docstore.aget(id=documents[i].id)
            assert parent.children[0] == doc.id

    @pytest.mark.asyncio
    async def test_next_with_document_splits(self, docstore, document):
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
        
        docstore.set_document_type(doctype)
        
        # Process the document
        await docstore.aadd(document)
        processed_docs = await docstore.next(document)
        
        # Verify the results
        assert len(processed_docs) == 2
        assert processed_docs[0].state == "child1"
        assert processed_docs[1].state == "child2"
        assert processed_docs[0].parent_id == document.id
        assert processed_docs[1].parent_id == document.id
        
        # Verify the parent-child relationship
        parent = await docstore.aget(id=document.id)
        assert len(parent.children) == 2
        assert processed_docs[0].id in parent.children
        assert processed_docs[1].id in parent.children

    @pytest.mark.asyncio
    async def test_next_with_error(self, docstore, document):
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
        
        docstore.set_document_type(doctype)
        
        # Process the document
        await docstore.aadd(document)
        processed_docs = await docstore.next(document)
        
        # Verify the results - should have an error document
        assert len(processed_docs) == 1
        assert processed_docs[0].state == "error"
        assert processed_docs[0].parent_id == document.id
        assert "Test process error" in processed_docs[0].content
        
        # Verify the parent-child relationship
        parent = await docstore.aget(id=document.id)
        assert len(parent.children) == 1
        assert processed_docs[0].id in parent.children

    @pytest.mark.asyncio
    async def test_next_with_missing_document_type(self, docstore, document):
        """Test processing a document without a document type."""
        pass

        # await docstore.aadd(document)
        
        # with pytest.raises(ValueError, match="Document type not set"):
        #     await docstore.next(document)

    @pytest.mark.asyncio
    async def test_finish(self, docstore, document):
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
        
        docstore.set_document_type(doctype)
        
        # Process the document through the pipeline
        document.state = "link"  # Ensure correct starting state
        await docstore.aadd(document)
        final_docs = await docstore.finish(document)
        
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
        await docstore.aadd(new_doc)
        final_docs = await docstore.finish([new_doc])
        assert len(final_docs) > 0
        assert any(doc.state == "final" for doc in final_docs)

class TestContext:
    def test_context_manager(self, sqlite_db_path, document_type):
        """Test using DocStore as a context manager."""
        with DocStore(
            connection_string=sqlite_db_path,
            document_type=document_type
        ) as store:
            store.add(Document(state="test", content="test"))
            doc = store.list(state="test")
            assert len(doc) == 1
            assert doc[0].content == "test"
