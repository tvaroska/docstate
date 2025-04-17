from uuid import uuid4

import pytest

from docstate.document import Document, DocumentState, DocumentType, Transition


class TestDocument:
    """Unit tests for the Document class."""

    def test_document_initialization(self, root_document):
        """Test that a Document can be initialized with the required fields."""
        # Test minimal initialization
        doc = root_document

        # ID should be auto-generated
        assert doc.id is not None
        assert len(doc.id) > 0
        assert doc.media_type == "text/plain"
        assert doc.state == "link"
        assert doc.content is None
        assert doc.parent_id is None
        assert doc.children == []
        assert doc.metadata == {}

    def test_document_initialization_with_all_fields(self, document_with_all_fields):
        """Test that a Document can be initialized with all fields."""
        doc = document_with_all_fields

        assert doc.id is not None
        assert doc.content == "Example content"
        assert doc.media_type == "text/plain"
        assert doc.state == "download"
        assert doc.parent_id is not None
        assert len(doc.children) == 2
        assert doc.metadata == {"source": "test", "timestamp": "2025-04-10"}

    def test_is_root_property(self, root_document, child_document):
        """Test the is_root property."""
        # Document with no parent should be a root document
        assert root_document.is_root is True

        # Document with a parent should not be a root document
        assert child_document.is_root is False

    def test_has_children_property(self, root_document, document_with_children):
        """Test the has_children property."""
        # Document with no children
        assert root_document.has_children is False

        # Document with children
        assert document_with_children.has_children is True

        # Add a child to a document with no children
        root_document.children.append(str(uuid4()))
        assert root_document.has_children is True

    def test_add_child_method(self, root_document):
        """Test the add_child method."""
        doc = root_document
        assert doc.has_children is False

        # Add a child
        child_id = str(uuid4())
        doc.add_child(child_id)
        assert doc.has_children is True
        assert child_id in doc.children
        assert len(doc.children) == 1

        # Adding the same child again should not create a duplicate
        doc.add_child(child_id)
        assert len(doc.children) == 1

        # Adding a different child should work
        second_child_id = str(uuid4())
        doc.add_child(second_child_id)
        assert len(doc.children) == 2
        assert second_child_id in doc.children

    def test_document_with_invalid_state(self):
        """Test that setting an invalid state type raises a validation error."""
        with pytest.raises(ValueError):
            Document(content_type="text", state=123)  # State should be a string

    def test_document_with_invalid_content_type(self):
        """Test that setting an invalid content_type raises a validation error."""
        with pytest.raises(ValueError):
            Document(media_type=123, state="link")  # content_type should be a string

    def test_document_with_invalid_children(self):
        """Test that setting invalid children raises a validation error."""
        with pytest.raises(ValueError):
            Document(
                content_type="text",
                state="link",
                children="not-a-list",  # children should be a list
            )

        with pytest.raises(ValueError):
            Document(
                content_type="text",
                state="link",
                children=[1, 2, 3],  # children should be a list of strings
            )

    def test_document_with_invalid_metadata(self):
        """Test that setting invalid metadata raises a validation error."""
        with pytest.raises(ValueError):
            Document(
                content_type="text",
                state="link",
                metadata="not-a-dict",  # metadata should be a dict
            )


class TestDocumentState:
    """Unit tests for the DocumentState class."""

    def test_document_state_initialization(self, document_states):
        """Test that a DocumentState can be initialized."""
        state = document_states["link"]
        assert state.name == "link"

    def test_document_state_equality(self, document_states):
        """Test that DocumentState equality works as expected."""
        state1 = document_states["link"]
        state2 = DocumentState(name="link")
        state3 = document_states["download"]

        # Two states with the same name should be equal
        assert state1 == state2

        # Two states with different names should not be equal
        assert state1 != state3

        # A state should be equal to its name string
        assert state1 == "link"
        assert state1 != "download"

        # A state should not be equal to non-string, non-DocumentState
        assert state1 != 123
        assert state1 != ["link"]

    def test_document_state_hash(self, document_states):
        """Test that DocumentState can be used as a dictionary key."""
        state1 = document_states["link"]
        state2 = DocumentState(name="link")
        state3 = document_states["download"]

        # Create a dictionary with states as keys
        state_dict = {state1: "Value for link", state3: "Value for download"}

        # We should be able to access the values using both the original state
        # and an equal state
        assert state_dict[state1] == "Value for link"
        assert (
            state_dict[state2] == "Value for link"
        )  # state2 has the same name as state1
        assert state_dict[state3] == "Value for download"


class TestTransition:
    """Unit tests for the Transition class."""

    def test_transition_initialization(self, document_states, mock_process_functions):
        """Test that a Transition can be initialized."""
        from_state = document_states["link"]
        to_state = document_states["download"]

        transition = Transition(
            from_state=from_state,
            to_state=to_state,
            process_func=mock_process_functions["download"],
        )

        assert transition.from_state == from_state
        assert transition.to_state == to_state
        assert transition.process_func == mock_process_functions["download"]


class TestDocumentType:
    """Unit tests for the DocumentType class."""

    def test_document_type_initialization(self, document_type):
        """Test that a DocumentType can be initialized."""
        assert len(document_type.states) == 4
        assert len(document_type.transitions) == 3

    def test_get_transition(self, document_type, document_states, transitions):
        """Test the get_transition method."""
        # Get transitions from link state
        link_transitions = document_type.get_transition(document_states["link"])
        assert len(link_transitions) == 1
        assert link_transitions[0] == transitions["download"]

        # Get transitions from download state
        download_transitions = document_type.get_transition(document_states["download"])
        assert len(download_transitions) == 1
        assert download_transitions[0] == transitions["chunk"]

        # Get transitions using string state name
        link_transitions_by_string = document_type.get_transition("link")
        assert len(link_transitions_by_string) == 1
        assert link_transitions_by_string[0] == transitions["download"]

        # Get transitions from a state with no outgoing transitions
        embed_transitions = document_type.get_transition(document_states["embed"])
        assert len(embed_transitions) == 0

    def test_final_property(self, document_type, document_states):
        """Test the final property that identifies terminal states."""
        final_states = document_type.final

        # Only embed state should be final (no outgoing transitions)
        assert len(final_states) == 1
        assert final_states[0] == document_states["embed"]


if __name__ == "__main__":
    pytest.main()
