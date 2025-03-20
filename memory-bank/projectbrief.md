# DocState - Document State Management Library

## Project Brief

DocState is a library designed to manage state transitions for documents in a database. It provides a clean, declarative way to define and execute document processing pipelines, with built-in error handling and state tracking.

## Core Purpose

The library solves the challenge of managing complex document processing workflows by:

1. Tracking document state throughout its lifecycle
2. Providing a declarative interface for defining state transitions
3. Handling errors gracefully with dedicated error states
4. Maintaining consistency through atomic operations
5. Supporting resumable processing pipelines

## Key Concepts

### Document
Represents a document entity with properties like content, metadata, and URI. Documents move through a series of states as they undergo processing.

### DocState
The main controller class that:
- Manages document state transitions
- Provides decorators for defining transition functions
- Tracks current document state
- Handles the execution of state transitions

### State Transitions
Functions decorated with `@docs.transition` that:
- Transform documents from one state to another
- Can specify error states for handling exceptions
- Execute business logic for document processing

### Special States
- `START`: Initial state for all documents
- `END`: Terminal state indicating successful processing
- Error states: Custom states that capture processing failures

## Usage Examples

### Basic Example: Web Content Processing Pipeline

```python
import requests
from google import genai
from docstate import Document, DocState, START, END

# Initialize DocState with database connection
docs = DocState(connection_string)
client = genai.client(GEMINI_API_KEY)

# Define state transitions
@docs.transition(START, 'download', error='download_error')
def download(document: Document) -> Document:
    """Download content from document's URI"""
    response = requests.get(document.uri)
    document.content = response.text
    return document

@docs.transition('download', END, error='summary_error')
def summary(document: Document) -> Document:
    """Generate summary using Gemini LLM"""
    response = client.models.generate_content(
        model='gemini-2.0-flash-001', 
        contents=['Summarize document', document.content]
    )
    document.metadata['summary'] = response.candidates[0].content.parts[0].text
    return document

# Create and process a document
doc = docs(uri='https://www.python.org/about/gettingstarted/')

# Check initial state
assert doc.state == START

# Execute next transition (download)
doc.next_step()

# Check state after download
assert doc.state == 'download'

# Execute final transition (summary)
doc.next_step()

# Check final state
assert doc.state == END

# Access the generated summary
print(doc.metadata['summary'])
```

### Advanced Example: Multi-step Document Analysis Pipeline

```python
from docstate import Document, DocState, START, END
import requests
import nltk
from sklearn.feature_extraction.text import TfidfVectorizer
from transformers import pipeline

docs = DocState(connection_string)

# Download content
@docs.transition(START, 'downloaded', error='download_error')
def download(document: Document) -> Document:
    response = requests.get(document.uri)
    document.content = response.text
    return document

# Clean and tokenize
@docs.transition('downloaded', 'processed', error='process_error')
def process(document: Document) -> Document:
    tokens = nltk.word_tokenize(document.content)
    document.metadata['tokens'] = tokens
    document.metadata['word_count'] = len(tokens)
    return document

# Extract keywords using TF-IDF
@docs.transition('processed', 'keywords_extracted', error='keyword_error')
def extract_keywords(document: Document) -> Document:
    vectorizer = TfidfVectorizer(max_features=10)
    tfidf_matrix = vectorizer.fit_transform([document.content])
    keywords = vectorizer.get_feature_names_out()
    document.metadata['keywords'] = keywords.tolist()
    return document

# Generate summary
@docs.transition('keywords_extracted', 'summarized', error='summary_error')
def summarize(document: Document) -> Document:
    summarizer = pipeline("summarization")
    summary = summarizer(document.content, max_length=100, min_length=30)
    document.metadata['summary'] = summary[0]['summary_text']
    return document

# Classify document
@docs.transition('summarized', END, error='classification_error')
def classify(document: Document) -> Document:
    classifier = pipeline("text-classification")
    result = classifier(document.content)
    document.metadata['category'] = result[0]['label']
    document.metadata['category_score'] = result[0]['score']
    return document
```

## Key Features

1. **Declarative Pipeline Definition**: Define document processing pipelines using simple decorator syntax
2. **Automatic State Tracking**: Document states are automatically tracked and persisted
3. **Error Handling**: Dedicated error states with the ability to retry or resume processing
4. **Database Integration**: Built-in support for document persistence
5. **Atomic Transitions**: State transitions are atomic, ensuring consistency
6. **Extensible Architecture**: Easy to extend with custom state transitions and processors

## Technical Requirements

- Python 3.8+
- Database with connection string support (PostgreSQL, MongoDB, etc.)
- Optional integrations with various processing libraries

## Intended Use Cases

- Content aggregation and processing systems
- Document analysis pipelines
- Web scraping and content extraction workflows
- ML-powered document processing
- Automated content generation systems
- Asynchronous document processing queues

## Development Roadmap

1. Core state management functionality
2. Database integration layer
3. Error handling and recovery mechanisms
4. Parallel processing support
5. Monitoring and observability features
6. CLI tools for managing document states
