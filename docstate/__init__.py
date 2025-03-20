"""
DocState - Document State Management Library

A library designed to manage state transitions for documents in a database.
It provides a clean, declarative way to define and execute document processing
pipelines, with built-in error handling and state tracking.
"""

from docstate.constants import START, END
from docstate.models import Document, TransitionHistory, Base
from docstate.state_manager import StateManager, StateTransition
from docstate.docstate import DocState

__version__ = "0.1.0"
__all__ = [
    "DocState",
    "Document", 
    "TransitionHistory", 
    "Base", 
    "StateManager",
    "StateTransition",
    "START", 
    "END"
]
