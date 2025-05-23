# Active Context: Document Processing Pipeline

## Current Focus
- Implementing streaming capabilities for large document handling
- Optimizing database queries for better performance with large datasets
- Expanding document format support (PDF, DOCX, HTML)
- Creating comprehensive API documentation
- Developing monitoring tools for pipeline execution

## Recent Changes
- Implemented Document, DocumentState, DocumentType, and Transition classes
- Developed DocStore with SQLAlchemy for document persistence
- Implemented state machine architecture with DocumentState and Transition classes
- Implemented processing function implementations (download_document, chunk_document, embed_document)
- Built parent-child relationship tracking with proper database updates
- Fixed DocumentType.final property implementation
- Fixed inconsistency between "cmetadata" in database and "metadata" in Document objects
- Added error handling for processing functions
- Created comprehensive unit tests for Document classes
- Created integration tests for the full pipeline
- Implemented a complete pipeline example with working processing functions
- Updated `DocStore.next` method to accept either a single `Document` or `List[Document]` and return `List[Document]`, enabling batch processing
- Updated relevant unit tests for `DocStore.next`
- Renamed `content_type` to `media_type` throughout the codebase for better standards alignment
- Added `url` field to Document class for direct URL storage
- Implemented RAG example with error handling for invalid URLs
- Added extensive error handling tests with custom error states
- Added support for batch processing with mixed success and failure scenarios
- Implemented `finish()` method in DocStore to process documents through entire pipeline
- Implemented `list()` method in DocStore with filtering by state, metadata, and leaf nodes
- Integrated with real embedding libraries (VertexAI Embeddings)
- Integrated with PGVector for vector storage
- Integrated with LangChain text splitters for improved document chunking
- Added comprehensive tests for all new methods and integrations

## Next Steps
- Implement streaming for large document handling
- Optimize database queries for high-volume use cases
- Create more comprehensive API documentation
- Add more examples for custom pipelines
- Develop a monitoring system for pipeline execution
- Add support for additional document formats (PDF, DOCX, etc.)
- Implement concurrency via `asyncio.gather` in `DocStore.next` for better performance
- Create a database migration strategy for schema changes

## Active Decisions and Considerations
- Using SQLAlchemy as the backend with proper database field mappings
- Implemented asynchronous functions for all document processing steps
- DocStore.next() handles metadata/cmetadata conversion properly
- Unit tests validate the complete pipeline functionality
- Using VertexAI for embeddings in the RAG example
- Using LangChain text splitters for document chunking
- Investigating streaming options for handling very large documents
- RAG example demonstrates practical usage in real-world scenario
- Error handling supports custom error states defined at DocStore initialization
- The list() method provides flexible querying with metadata filtering and leaf node options
- The finish() method streamlines processing documents through the entire pipeline
