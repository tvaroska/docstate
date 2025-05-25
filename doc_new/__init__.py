"""
DocState - A fully asynchronous library for managing documents through various processing states and transitions.
Optimized for high performance.
"""

from doc_new.document import Document, DocumentState, DocumentType, Transition
from doc_new.docstate import AsyncDocStore, Base

# Version of the package
__version__ = "0.1.0"

# Provide easy access to key components
__all__ = [
    "Document", 
    "DocumentState", 
    "DocumentType", 
    "Transition", 
    "AsyncDocStore"
]
