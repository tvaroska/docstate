import asyncio
from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore

async def test_finish_method():
    """Simple test to verify the finish method implementation."""
    # Create a very basic document type with a simple transition
    link = DocumentState(name="link")
    download = DocumentState(name="download")
    
    # Define a simple processing function
    async def simple_process(doc):
        return Document(
            content="Processed content",
            state="download",
            metadata={"processed": True}
        )
    
    # Create document type
    doc_type = DocumentType(
        states=[link, download],
        transitions=[
            Transition(from_state=link, to_state=download, process_func=simple_process)
        ]
    )
    
    # Create DocStore with in-memory SQLite
    docstore = DocStore(connection_string="sqlite:///:memory:", document_type=doc_type)
    
    # Create test document
    doc = Document(
        content="Test content",
        state="link",
        metadata={"test": True}
    )
    
    # Use finish method
    final_docs = await docstore.finish(doc)
    
    # Print results
    print("\nTest results:")
    print(f"Number of final documents: {len(final_docs)}")
    for doc in final_docs:
        print(f"- Document state: {doc.state}")
        print(f"- Document content: {doc.content}")
    
    # Basic assertions
    assert len(final_docs) == 1
    assert final_docs[0].state == "download"
    assert final_docs[0].content == "Processed content"
    
    print("\nTest passed successfully!")

if __name__ == "__main__":
    # Run the test
    asyncio.run(test_finish_method())
