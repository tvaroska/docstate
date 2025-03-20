# DocState

DocState is a library designed to manage state transitions for documents in a database. It provides a clean, declarative way to define and execute document processing pipelines, with built-in error handling and state tracking.

## Features

- **Declarative Pipeline Definition**: Define document processing pipelines using simple decorator syntax
- **Automatic State Tracking**: Document states are automatically tracked and persisted
- **Error Handling**: Dedicated error states with the ability to retry or resume processing
- **Database Integration**: Built-in support for document persistence
- **Atomic Transitions**: State transitions are atomic, ensuring consistency
- **Extensible Architecture**: Easy to extend with custom state transitions and processors

## Installation

### Using uv (Recommended)

DocState now uses uv as its build system for faster and more reliable dependency management.

```bash
# Clone the repository
git clone https://github.com/docstate/docstate.git
cd docstate

# Option 1: Use the install script
./install.sh

# Option 2: Manual installation
# Create a virtual environment
uv venv

# Activate the virtual environment
source .venv/bin/activate

# Install in development mode with all extras
uv pip install -e ".[dev,http,ai]"
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/docstate/docstate.git
cd docstate

# Create a virtual environment
python -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Install in development mode with all extras
pip install -e ".[dev,http,ai]"
```

## Basic Usage

```python
import requests
from docstate import Document, DocState, START, END

# Initialize DocState with database connection
docs = DocState(connection_string)

# Define state transitions
@docs.transition(START, 'download', error='download_error')
def download(document: Document) -> Document:
    """Download content from document's URI"""
    response = requests.get(document.uri)
    document.content = response.text
    return document

@docs.transition('download', END, error='summary_error')
def summarize(document: Document) -> Document:
    """Process the document content"""
    document.metadata['word_count'] = len(document.content.split())
    return document

# Create and process a document
doc = docs(uri='https://www.example.com')

# Check initial state
assert doc.state == START

# Execute next transition (download)
doc.next_step()

# Check state after download
assert doc.state == 'download'

# Execute final transition (summarize)
doc.next_step()

# Check final state
assert doc.state == END
```

## Development

```bash
# Install development dependencies
uv pip install -r requirements-dev.txt

# Run tests
pytest

# Format code
black docstate
isort docstate

# Type checking
mypy docstate
```

## Requirements

- Python 3.12+
- SQLAlchemy 2.0+
- Alembic 1.10+
- Pydantic 2.0+

## License

MIT License
