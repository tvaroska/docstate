"""
DocState - A fully asynchronous library for managing documents through various processing states and transitions.
Optimized for high performance.
"""

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import Docstore, Base

# Version of the package
__version__ = "0.0.2"

# Provide easy access to key components
__all__ = [
    "Document", 
    "DocumentState", 
    "DocumentType", 
    "Transition", 
    "Docstore"
]
