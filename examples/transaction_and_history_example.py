"""
DocState Transaction Management and History Tracking Example

This example demonstrates:
1. Transaction management for state transitions
2. State history tracking
3. Using document history methods
4. Analyzing transition statistics
"""

import uuid
from datetime import datetime
from docstate import Document, DocState, START, END

# Setup connection string - this example uses SQLite in-memory
connection_string = "sqlite:///:memory:"

# Initialize DocState with table creation enabled
docs = DocState(connection_string, create_tables=True)

# Define state transitions
@docs.transition(START, "downloaded", error="download_error")
def download(document: Document) -> Document:
    """Download content (simulated)"""
    document.content = "This is the downloaded content"
    return document

@docs.transition("downloaded", "processed", error="process_error")
def process(document: Document) -> Document:
    """Process the content (simulated)"""
    document.data["word_count"] = len(document.content.split())
    return document

@docs.transition("processed", "analyzed", error="analyze_error")
def analyze(document: Document) -> Document:
    """Analyze the content (simulated)"""
    document.data["sentiment"] = "positive"
    document.data["language"] = "en"
    return document

@docs.transition("analyzed", END, error="finalize_error")
def finalize(document: Document) -> Document:
    """Finalize the document (simulated)"""
    document.data["completed_at"] = datetime.now().isoformat()
    return document

# Create a document
doc = docs(uri="https://example.com/document", data={"metadata": "Sample document"})
print(f"Created document with ID: {doc.id}")
print(f"Initial state: {doc.state}")

# Execute transitions one by one and track history
print("\nExecuting transitions...")

# First transition
doc = doc.next_step()  # Equivalent to docs.execute_transition(doc)
print(f"State after download: {doc.state}")

# Second transition
doc = doc.next_step()
print(f"State after process: {doc.state}")

# Intentionally forcing an error to demonstrate error handling
try:
    # Temporarily modify the state to cause an error
    original_state = doc.state
    with docs.transaction() as session:
        db_doc = session.query(Document).filter(Document.id == doc.id).first()
        db_doc.state = "invalid_state"  # This will cause an error in next_step
    
    doc = docs.get_document(doc.id)  # Refresh doc with invalid state
    doc.next_step()  # This will fail
except ValueError as e:
    print(f"Error caught: {e}")
    # Restore the correct state
    with docs.transaction() as session:
        db_doc = session.query(Document).filter(Document.id == doc.id).first()
        db_doc.state = original_state
    doc = docs.get_document(doc.id)  # Refresh doc with valid state

# Continue with remaining transitions
doc = doc.next_step()  # analyze
print(f"State after analyze: {doc.state}")

doc = doc.next_step()  # finalize
print(f"Final state: {doc.state}")

# View document history
print("\nDocument history:")
history = doc.get_history()
for entry in history:
    print(f"  {entry.executed_at}: {entry.from_state} -> {entry.to_state} ({entry.transition_name})")

# Get state history
print("\nState history (most recent first):")
states = doc.get_state_history()
for state in states:
    print(f"  {state}")

# Get transition statistics
print("\nTransition statistics:")
stats = doc.get_transition_stats()
for transition_name, data in stats.items():
    print(f"  {transition_name}:")
    print(f"    Count: {data['count']}")
    print(f"    Success rate: {data['success_rate']}%")
    if data['avg_duration'] is not None:
        print(f"    Average duration: {data['avg_duration']:.2f}ms")

# Available transitions from END state (should be empty)
print("\nAvailable transitions from END state:")
transitions = doc.get_available_transitions()
if transitions:
    for transition in transitions:
        print(f"  {transition}")
else:
    print("  No transitions available (END state)")

# Manual state update with transition history
print("\nManually updating document state:")
old_doc = docs.get_document(doc.id)
updated_doc = docs.update_document(old_doc, new_state="archived")
print(f"State after manual update: {updated_doc.state}")

# View all document states including manual update
print("\nComplete state history after manual update:")
states = updated_doc.get_state_history()
for state in states:
    print(f"  {state}")
