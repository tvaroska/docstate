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
        
    def test_str_method(self, document_state):
        """Test DocumentState string representation."""
        assert str(document_state) == "test_state"
        
    def test_str_caching(self, document_state):
        """Test that the __str__ method caches results for better performance."""
        # Call __str__ multiple times and verify it returns the same object
        str1 = str(document_state)
        str2 = str(document_state)
        # Check that the strings are the same object in memory (not just equal)
        assert str1 is str2  # This tests that caching is working


class TestTransition:
    def test_init(self, transition):
        """Test Transition initialization."""
        assert transition.from_state.name == "link"
        assert transition.to_state.name == "download"
        assert transition.process_func is not None
        
    def test_validate_process_func(self):
        """Test process_func validation."""
        link = DocumentState(name="link")
        download = DocumentState(name="download")
        
        # Valid process_func (callable)
        async def valid_func(doc):
            return doc
            
        valid_transition = Transition(
            from_state=link,
            to_state=download,
            process_func=valid_func
        )
        assert valid_transition.process_func is valid_func
        
        # Invalid process_func (not callable)
        with pytest.raises(ValueError, match="process_func must be a callable"):
            Transition(
                from_state=link,
                to_state=download,
                process_func="not callable"
            )


class TestDocumentType:
    def test_init(self, document_type):
        """Test DocumentType initialization."""
        assert len(document_type.states) == 5  # link, download, chunk, embed, error
        assert len(document_type.transitions) == 3
        
        # Test transition_cache initialization
        assert document_type.transition_cache == {}
        assert document_type.final_states_cache is None

    def test_final_property(self, document_type):
        """Test the final property returns states with no outgoing transitions."""
        final_states = document_type.final
        assert len(final_states) == 2
        assert all(state.name in ["embed", "error"] for state in final_states)
        
        # Test that the final states are cached
        assert document_type.final_states_cache is not None
        assert len(document_type.final_states_cache) == 2
        
        # Call final property again and verify it uses the cache
        final_states_2 = document_type.final
        assert final_states is document_type.final_states_cache
        assert final_states_2 is document_type.final_states_cache

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
        
        # Test that transitions are cached
        assert "link" in document_type.transition_cache
        assert "download" in document_type.transition_cache
        assert "embed" in document_type.transition_cache
        
        # Call again and verify it uses the cache
        cached_transitions = document_type.get_transition("link")
        assert cached_transitions is document_type.transition_cache["link"]
        
    def test_validate_states_and_transitions(self):
        """Test validation of states and transitions."""
        # Valid states and transitions
        state1 = DocumentState(name="state1")
        state2 = DocumentState(name="state2")
        valid_transition = Transition(
            from_state=state1,
            to_state=state2,
            process_func=lambda x: x
        )
        
        valid_doc_type = DocumentType(
            states=[state1, state2],
            transitions=[valid_transition]
        )
        assert valid_doc_type is not None
        
        # Invalid transition - unknown from_state
        unknown_state = DocumentState(name="unknown")
        invalid_transition1 = Transition(
            from_state=unknown_state,
            to_state=state2,
            process_func=lambda x: x
        )
        
        with pytest.raises(ValueError, match="Transition references unknown from_state"):
            DocumentType(
                states=[state1, state2],
                transitions=[invalid_transition1]
            )
            
        # Invalid transition - unknown to_state
        invalid_transition2 = Transition(
            from_state=state1,
            to_state=unknown_state,
            process_func=lambda x: x
        )
        
        with pytest.raises(ValueError, match="Transition references unknown to_state"):
            DocumentType(
                states=[state1, state2],
                transitions=[invalid_transition2]
            )


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
        
    def test_add_children(self, document):
        """Test add_children method."""
        child_ids = ["child1", "child2", "child3"]
        document.add_children(child_ids)
        
        # All children should be added
        for child_id in child_ids:
            assert child_id in document.children
            
        # Adding some existing and some new children
        more_child_ids = ["child2", "child3", "child4", "child5"]
        document.add_children(more_child_ids)
        
        # All unique children should be in the list without duplicates
        expected_children = ["child1", "child2", "child3", "child4", "child5"]
        assert sorted(document.children) == sorted(expected_children)
        
        # Each child should appear exactly once
        for child_id in expected_children:
            assert document.children.count(child_id) == 1
