import asyncio
from uuid import uuid4

import pytest

from docstate.docstate import DocStore
from docstate.document import Document, DocumentState, DocumentType, Transition


# Define a mock processing function that raises an exception
async def failing_process_func(doc: Document) -> Document:
    """A process function that always fails with a specific error."""
    raise ValueError("Simulated process failure")


@pytest.fixture(scope="function")
def error_handling_document_type(document_states):
    """Create a document type with a failing transition."""
    # Define states
    link = document_states["link"]
    error = DocumentState(name="error")
    download = document_states["download"]

    # Define a transition that will fail during processing
    transitions = [
        Transition(
            from_state=link, to_state=download, process_func=failing_process_func
        )
    ]

    return DocumentType(states=[link, download, error], transitions=transitions)


@pytest.fixture(scope="function")
def error_handling_docstore(sqlite_connection_string, error_handling_document_type):
    """Create a DocStore for error handling tests."""
    return DocStore(
        connection_string=sqlite_connection_string,
        document_type=error_handling_document_type,
    )


class TestDocumentErrorHandling:
    """Tests for error handling in document transitions."""

    @pytest.mark.asyncio
    async def test_failed_transition_creates_error_document(
        self, error_handling_docstore
    ):
        """Test that a failed transition creates a document in the default error state."""
        # Create a document that will trigger the failing transition
        doc = Document(
            media_type="application/uri",
            state="link",
            content="http://example.com",
            metadata={"test_id": "error_test"},
        )

        # Add document to the store
        doc_id = error_handling_docstore.add(doc)

        # Process document (will trigger the failing transition)
        result_docs = await error_handling_docstore.next(doc)

        # Verify that we got a list with one document
        assert isinstance(result_docs, list)
        assert len(result_docs) == 1

        # Get the error document
        error_doc = result_docs[0]

        # Verify error document properties
        assert error_doc.state == DocStore.ERROR_STATE
        assert error_doc.media_type == "application/json"
        assert error_doc.parent_id == doc_id
        assert "Simulated process failure" in error_doc.content

        # Verify error metadata
        assert "error" in error_doc.metadata
        assert error_doc.metadata["error"] == "Simulated process failure"
        assert error_doc.metadata["error_type"] == "ValueError"
        assert error_doc.metadata["transition_from"] == "link"
        assert error_doc.metadata["transition_to"] == "download"
        assert error_doc.metadata["original_media_type"] == "application/uri"
        assert error_doc.metadata["timestamp"] == "failing_process_func"

        # Verify parent-child relationship
        parent_doc = error_handling_docstore.get(id=doc_id)
        assert error_doc.id in parent_doc.children

        # Verify we can query error documents by state
        error_docs = error_handling_docstore.get(state=DocStore.ERROR_STATE)
        assert isinstance(error_docs, list)
        assert len(error_docs) == 1
        assert error_docs[0].id == error_doc.id

    @pytest.mark.asyncio
    async def test_custom_error_state(
        self, sqlite_connection_string, error_handling_document_type
    ):
        """Test that a custom error state can be used."""
        # Create a DocStore with a custom error state
        custom_error_state = "failed"
        docstore = DocStore(
            connection_string=sqlite_connection_string,
            document_type=error_handling_document_type,
            error_state=custom_error_state,
        )

        # Create a document that will trigger the failing transition
        doc = Document(
            media_type="application/uri", state="link", content="http://example.com"
        )

        # Add document to the store
        doc_id = docstore.add(doc)

        # Process document (will trigger the failing transition)
        result_docs = await docstore.next(doc)

        # Verify error document properties
        error_doc = result_docs[0]
        assert error_doc.state == custom_error_state

        # Verify we can query error documents by the custom state
        error_docs = docstore.get(state=custom_error_state)
        assert len(error_docs) == 1
        assert error_docs[0].id == error_doc.id

    @pytest.mark.asyncio
    async def test_list_input_with_mixed_success_and_failure(
        self, document_type, error_handling_document_type, sqlite_connection_string
    ):
        """Test handling a list of documents where some succeed and some fail."""
        # Create a DocStore with mixed transitions
        # We'll define a document type with both working and failing transitions
        link = DocumentState(name="link")
        download = DocumentState(name="download")
        error = DocumentState(name=DocStore.ERROR_STATE)

        # Regular transition
        async def working_process_func(doc: Document) -> Document:
            return Document(
                content="Success content", media_type="text/plain", state="download"
            )

        # Failing transition based on content
        async def conditional_failing_process_func(doc: Document) -> Document:
            if "fail" in doc.content:
                raise ValueError(
                    f"Failed processing document with content: {doc.content}"
                )
            return Document(
                content=f"Processed: {doc.content}",
                media_type="text/plain",
                state="download",
            )

        # Create document type with conditional failing transition
        mixed_type = DocumentType(
            states=[link, download, error],
            transitions=[
                Transition(
                    from_state=link,
                    to_state=download,
                    process_func=conditional_failing_process_func,
                )
            ],
        )

        # Create DocStore with this document type
        docstore = DocStore(
            connection_string=sqlite_connection_string, document_type=mixed_type
        )

        # Create documents - some will fail, some will succeed
        doc1 = Document(
            media_type="text/plain", state="link", content="normal document"
        )
        doc2 = Document(
            media_type="text/plain", state="link", content="fail this document"
        )
        doc3 = Document(
            media_type="text/plain", state="link", content="another normal document"
        )

        # Add documents
        docstore.add(doc1)
        docstore.add(doc2)
        docstore.add(doc3)

        # Process the list of documents
        results = await docstore.next([doc1, doc2, doc3])

        # We should have 3 results: 2 successful transitions and 1 error
        assert len(results) == 3

        # Count success and error documents
        success_docs = [d for d in results if d.state == "download"]
        error_docs = [d for d in results if d.state == "error"]

        assert len(success_docs) == 2
        assert len(error_docs) == 1

        # Verify success documents
        for doc in success_docs:
            assert "normal document" in doc.content
            assert doc.state == "download"
            assert doc.media_type == "text/plain"

        # Verify error document
        error_doc = error_docs[0]
        assert error_doc.state == DocStore.ERROR_STATE
        assert "fail this document" in error_doc.metadata["error"]
        assert error_doc.parent_id == doc2.id

        # Verify parent-child relationships
        parent2 = docstore.get(id=doc2.id)
        assert error_doc.id in parent2.children


if __name__ == "__main__":
    pytest.main()
