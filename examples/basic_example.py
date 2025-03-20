"""
Basic DocState Example

This script demonstrates a simple document processing pipeline
using the DocState library.
"""

import requests
from docstate import Document, DocState, START, END

# Initialize DocState with database connection
# Using SQLite for this example
docs = DocState("sqlite:///example.db", create_tables=True)


# Define state transitions
@docs.transition(START, "downloaded", error="download_error")
def download(document: Document) -> Document:
    """Download content from document's URI"""
    print(f"Downloading content from {document.uri}")
    
    # Only proceed if we have a URI to download from
    if not document.uri:
        raise ValueError("Document URI is required for download")
    
    try:
        response = requests.get(document.uri)
        response.raise_for_status()  # Raise exception for HTTP errors
        document.content = response.text
        document.metadata["content_type"] = response.headers.get("Content-Type")
        document.metadata["status_code"] = response.status_code
        return document
    except requests.RequestException as e:
        print(f"Download error: {e}")
        raise


@docs.transition("downloaded", "processed", error="process_error")
def process(document: Document) -> Document:
    """Process the downloaded content"""
    print("Processing document content")
    
    if not document.content:
        raise ValueError("Document has no content to process")
    
    # Simple processing: count words and characters
    words = document.content.split()
    document.metadata["word_count"] = len(words)
    document.metadata["char_count"] = len(document.content)
    
    # Extract title (very simple approach)
    if "<title>" in document.content and "</title>" in document.content:
        start = document.content.find("<title>") + len("<title>")
        end = document.content.find("</title>")
        document.metadata["title"] = document.content[start:end].strip()
    
    return document


@docs.transition("processed", END, error="summary_error")
def summarize(document: Document) -> Document:
    """Generate a simple summary of the document"""
    print("Generating document summary")
    
    # Create a very simple summary (first 100 characters)
    if document.content:
        # Remove HTML tags for summary (very crude approach)
        text = document.content.replace("<", " <").replace(">", "> ")
        words = text.split()
        summary = " ".join(words[:30])  # First 30 words
        document.metadata["summary"] = summary
    
    return document


def main():
    """Run the example document processing pipeline"""
    print("Creating document...")
    
    # Create a document to process
    doc = docs(uri="https://python.org/")
    
    # Check initial state
    print(f"Initial state: {doc.state}")
    
    # Execute the pipeline step by step
    try:
        # Download step
        print("\nExecuting download transition...")
        doc = docs.execute_transition(doc, "download")
        print(f"New state: {doc.state}")
        print(f"Content type: {doc.metadata.get('content_type')}")
        
        # Process step
        print("\nExecuting process transition...")
        doc = docs.execute_transition(doc, "process")
        print(f"New state: {doc.state}")
        print(f"Word count: {doc.metadata.get('word_count')}")
        print(f"Title: {doc.metadata.get('title')}")
        
        # Summarize step
        print("\nExecuting summarize transition...")
        doc = docs.execute_transition(doc, "summarize")
        print(f"Final state: {doc.state}")
        print(f"Summary: {doc.metadata.get('summary')}")
    
    except ValueError as e:
        print(f"Error in pipeline: {e}")
        # Show the document's error state
        doc = docs.get_document(doc.id)
        print(f"Document error state: {doc.state}")


if __name__ == "__main__":
    main()
