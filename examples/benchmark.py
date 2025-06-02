"""
Benchmark script to compare performance with and without multiprocessing.

This script demonstrates the performance difference between:
1. Standard asyncio-only processing (single core)
2. Multiprocessing-enabled processing (multiple cores)

The benchmark creates a set of documents and processes them through the 
embedding pipeline, measuring the time taken for each approach.
"""

import asyncio
import time
import os
from typing import List

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import Docstore
from docstate.utils import configure_logging
import logging

# Configure detailed logging for visibility
configure_logging(level=logging.INFO)

# Define a CPU-intensive embedding function to highlight multiprocessing benefits
async def cpu_intensive_embed(doc: Document) -> Document:
    """
    Create a computationally expensive vector embedding for the document.
    
    This function is deliberately CPU-intensive to demonstrate the benefits of multiprocessing.
    """
    if not doc.content:
        raise ValueError("Document has no content to embed")
    
    # Simple but CPU-intensive computation that's better suited for multiprocessing
    start_time = time.time()
    
    # Deliberately CPU-intensive math operations
    result = 0
    for i in range(10000000):  # 10 million iterations
        result += i * i % 1000
    
    # Generate document embedding based on character frequencies
    char_counts = {}
    for char in doc.content.lower():
        if char.isalpha():
            char_counts[char] = char_counts.get(char, 0) + 1
    
    # Create a simple embedding vector
    total = sum(char_counts.values()) or 1
    embedding = [char_counts.get(c, 0) / total for c in "abcdefghijklmnopqrstuvwxyz"]
    
    # For debugging - check if this function runs in different processes
    process_id = os.getpid()
    thread_id = asyncio.current_task().get_name() if asyncio.current_task() else "unknown"
    compute_time = time.time() - start_time
    
    print(f"Embedding completed in {compute_time:.2f}s | PID: {process_id} | Thread: {thread_id}")
    
    return Document(
        content=str(embedding),  # Store the embedding as a string
        media_type="application/vector",
        state="embed",
        parent_id=doc.id,
        metadata={
            "vector_dimensions": len(embedding),
            "embedding_method": "cpu_intensive_char_frequency"
        }
    )

async def benchmark_processing():
    """Run benchmark comparing single-core vs multi-core processing."""
    print(f"System has {os.cpu_count()} CPU cores available")
    
    # Define document states and transitions
    text = DocumentState(name="text")
    embed = DocumentState(name="embed")
    
    transitions = [
        Transition(from_state=text, to_state=embed, process_func=cpu_intensive_embed),
    ]
    
    doc_type = DocumentType(
        states=[text, embed],
        transitions=transitions
    )
    
    # Create test documents - we'll use the same content for all for consistent benchmarking
    content = "This is a test document that will be processed through the embedding pipeline."
    docs = [
        Document(
            content=content + f" Document {i}.",
            state="text",
            media_type="text/plain",
        ) for i in range(8)  # Process 8 documents to demonstrate parallelism
    ]
    
    # 1. Test with single-core processing (no multiprocessing)
    single_core_store = Docstore(
        connection_string="sqlite+aiosqlite:///:memory:",
        document_type=doc_type,
        max_concurrency=8,  # Allow all docs to process concurrently with asyncio
        process_workers=None  # Disable multiprocessing
    )
    await single_core_store.initialize()
    
    # Add documents
    await single_core_store.add(docs)
    
    # Process with single core and measure time
    print("\nStarting single-core processing (asyncio only)...")
    single_start = time.time()
    await single_core_store.finish(docs)
    single_duration = time.time() - single_start
    print(f"Single-core processing completed in {single_duration:.2f} seconds")
    
    # Clean up
    await single_core_store.dispose()
    
    # 2. Test with multi-core processing
    multi_core_store = Docstore(
        connection_string="sqlite+aiosqlite:///:memory:",
        document_type=doc_type,
        max_concurrency=8,  # Allow all docs to process concurrently with asyncio
        process_workers=os.cpu_count()  # Use all available CPU cores
    )
    await multi_core_store.initialize()
    
    # Add documents
    await multi_core_store.add(docs)
    
    # Process with multiple cores and measure time
    print("\nStarting multi-core processing (with multiprocessing)...")
    multi_start = time.time()
    await multi_core_store.finish(docs)
    multi_duration = time.time() - multi_start
    print(f"Multi-core processing completed in {multi_duration:.2f} seconds")
    
    # Clean up
    await multi_core_store.dispose()
    
    # Calculate speedup
    speedup = single_duration / multi_duration if multi_duration > 0 else 0
    
    print(f"\nResults:")
    print(f"Single-core time: {single_duration:.2f}s")
    print(f"Multi-core time:  {multi_duration:.2f}s")
    print(f"Speedup factor:   {speedup:.2f}x")
    print(f"Efficiency:       {speedup / os.cpu_count():.2f} (speedup / # cores)")
    
    if speedup > 1:
        print("\nMultiprocessing successfully improved performance!")
    else:
        print("\nNo performance improvement observed. This could be due to:")
        print("- Overhead of process creation exceeding benefits for this workload")
        print("- System limitations or resource contention")
        print("- Benchmark design not fully utilizing multiple cores")

if __name__ == "__main__":
    asyncio.run(benchmark_processing())
