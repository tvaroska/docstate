"""
DocState - A library for managing documents through various processing states and transitions.
"""

from docstate.document import Document, DocumentState, DocumentType, Transition
from docstate.docstate import DocStore, Base

from sqlalchemy import create_engine, inspect
import os

# Version of the package
__version__ = "0.0.1"

# Provide easy access to key components
__all__ = [
    "Document", 
    "DocumentState", 
    "DocumentType", 
    "Transition", 
    "DocStore",
    "init_db"
]
