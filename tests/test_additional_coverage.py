import pytest
import asyncio
from typing import List, Optional

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore


@pytest.fixture
def sqlite_connection_string():
    return "sqlite:///:memory:"


@pytest.fixture
def document_states():
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    chunk = DocumentState(name="chunk")
    embed = DocumentState(name="embed")
    return link, download, chunk, embed


@pytest.fixture
def process_func():
    async def simple_process(doc: Document) -> Document:
        return Document(
            content="Processed content",
            state="download",
            metadata={"processed": True}
        )
    return simple_process


@pytest.fixture
def document_type_with_no_docstore_errors(document_states, process_func):
    link, download, chunk, embed = document_states
    
    # Create failing process function
    async def failing_process(doc: Document) -> Document:
        if "fail" in str(doc.content).lower():
            raise ValueError("Test failure")
        return Document(
            content="Success content",
            state="download"
        )
    
    return DocumentType(
        states=[link, download, chunk, embed],
        transitions=[
            Transition(from_state=link, to_state=download, process_func=failing_process),
            Transition(from_state=download, to_state=chunk, process_func=process_func),
            Transition(from_state=chunk, to_state=embed, process_func=process_func)
        ]
    )


class TestAdditionalCoverage:
    """Tests to cover additional edge cases."""
    
    @pytest.mark.asyncio
    async def test_next_without_document_type(self, sqlite_connection_string):
        """Test next() method without setting a document type."""
        docstore = DocStore(connection_string=sqlite_connection_string)
        
        # Create a document
        doc = Document(content="Test content", state="link")
        docstore.add(doc)
        
        # Call next without setting document_type
        with pytest.raises(ValueError, match="Document type not set"):
            await docstore.next(doc)
    
    @pytest.mark.asyncio
    async def test_next_with_general_exception(self, sqlite_connection_string, document_states):
        """Test next() method with a general exception in processing."""
        link, download, _, _ = document_states
        
        # Create a process function that raises a general exception
        async def broken_process(doc: Document) -> Document:
            raise Exception("General error")
        
        # Create document type with failing transition
        doc_type = DocumentType(
            states=[link, download],
            transitions=[
                Transition(from_state=link, to_state=download, process_func=broken_process)
            ]
        )
        
        docstore = DocStore(connection_string=sqlite_connection_string, document_type=doc_type)
        
        # Create document
        doc = Document(content="Test content", state="link")
        docstore.add(doc)
        
        # Call next, which should catch the exception and create an error document
        results = await docstore.next(doc)
        
        # Verify error document was created
        assert len(results) == 1
        assert results[0].state == "error"
        assert "General error" in results[0].metadata["error"]
    
    @pytest.mark.asyncio
    async def test_finish_without_document_type(self, sqlite_connection_string):
        """Test finish() method without setting a document type."""
        docstore = DocStore(connection_string=sqlite_connection_string)
        
        # Create a document
        doc = Document(content="Test content", state="link")
        docstore.add(doc)
        
        # Call finish without setting document_type
        with pytest.raises(ValueError, match="Document type not set"):
            await docstore.finish(doc)
    
    @pytest.mark.asyncio
    async def test_finish_with_next_returning_no_docs(self, sqlite_connection_string, document_type_with_no_docstore_errors):
        """Test finish() when next() eventually returns no documents."""
        # Create DocStore with a document type that will eventually have no further transitions
        docstore = DocStore(
            connection_string=sqlite_connection_string, 
            document_type=document_type_with_no_docstore_errors
        )
        
        # Create document that will fail in processing
        doc = Document(content="FAIL test", state="link")
        docstore.add(doc)
        
        # Call finish, which should handle the error state
        final_docs = await docstore.finish(doc)
        
        # Verify we got back error documents
        assert len(final_docs) >= 1
        assert any(doc.state == "error" for doc in final_docs)
    
    @pytest.mark.asyncio
    async def test_get_by_state_single_result(self, sqlite_connection_string, document_type_with_no_docstore_errors):
        """Test get by state when only one document matches."""
        docstore = DocStore(
            connection_string=sqlite_connection_string, 
            document_type=document_type_with_no_docstore_errors
        )
        
        # Add a single document in a specific state
        doc = Document(content="Single doc", state="download")
        docstore.add(doc)
        
        # Get by state should still return a list, even with one result
        results = docstore.get(state="download")
        
        # Verify we got a list with one document
        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0].id == doc.id
