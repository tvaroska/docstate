import pytest
from typing import List

from docstate.document import Document, DocumentState, DocumentType, Transition
from tests.fixtures import (
    document, document_state, document_states, document_type, 
    document_with_children, mock_process_func, transition, transitions
)


class TestDocumentState:
    def test_init(self, document_state):
        """Test DocumentState initialization."""
        assert document_state.name == "test_state"

    def test_eq_with_state(self, document_state):
        """Test DocumentState equality with another DocumentState."""
        other_state = DocumentState(name="test_state")
        assert document_state == other_state
        
        different_state = DocumentState(name="different")
        assert document_state != different_state

    def test_eq_with_string(self, document_state):
        """Test DocumentState equality with a string."""
        assert document_state == "test_state"
        assert document_state != "different"

    def test_hash(self, document_state):
        """Test DocumentState hash is based on name."""
        state_set = {document_state, DocumentState(name="test_state")}
        assert len(state_set) == 1  # Both states hash to the same value


class TestTransition:
    def test_init(self, transition):
        """Test Transition initialization."""
        assert transition.from_state.name == "link"
        assert transition.to_state.name == "download"
        assert transition.process_func is not None


class TestDocumentType:
    def test_init(self, document_type):
        """Test DocumentType initialization."""
        assert len(document_type.states) == 5  # link, download, chunk, embed, error
        assert len(document_type.transitions) == 3

    def test_final_property(self, document_type):
        """Test the final property returns states with no outgoing transitions."""
        final_states = document_type.final
        assert len(final_states) == 2
        assert all(state.name in ["embed", "error"] for state in final_states)

    def test_get_transition(self, document_type):
        """Test getting transitions from a state."""
        # Test with DocumentState object
        link_state = DocumentState(name="link")
        transitions = document_type.get_transition(link_state)
        assert len(transitions) == 1
        assert transitions[0].from_state.name == "link"
        assert transitions[0].to_state.name == "download"
        
        # Test with string
        transitions = document_type.get_transition("download")
        assert len(transitions) == 1
        assert transitions[0].from_state.name == "download"
        assert transitions[0].to_state.name == "chunk"
        
        # Test with no transitions
        transitions = document_type.get_transition("embed")
        assert len(transitions) == 0


class TestDocument:
    def test_init(self, document):
        """Test Document initialization."""
        assert document.state == "link"
        assert document.content == "Test content"
        assert document.media_type == "text/plain"
        assert document.url == "https://example.com/test"
        assert document.metadata == {"test": True}
        assert document.id is not None
        assert document.parent_id is None
        assert document.children == []

    def test_is_root(self, document):
        """Test is_root property."""
        assert document.is_root is True
        
        child_doc = Document(
            state="child",
            content="Child content",
            parent_id=document.id
        )
        assert child_doc.is_root is False

    def test_has_children(self, document, document_with_children):
        """Test has_children property."""
        assert document.has_children is False
        
        parent, _ = document_with_children
        assert parent.has_children is True

    def test_add_child(self, document):
        """Test add_child method."""
        child_id = "child123"
        document.add_child(child_id)
        assert child_id in document.children
        
        # Adding the same child again shouldn't duplicate
        document.add_child(child_id)
        assert document.children.count(child_id) == 1
