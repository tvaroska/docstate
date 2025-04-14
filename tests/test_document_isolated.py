import pytest
from uuid import uuid4
from docstate.document import Document


class TestDocumentIsolated:
    """Unit tests focused exclusively on the Document class."""

    def test_document_initialization(self, root_document):
        """Test that a Document can be initialized with the required fields."""
        # Test using fixture for root document
        doc = root_document
        
        # ID should be auto-generated
        assert doc.id is not None
        assert len(doc.id) > 0
        assert doc.content_type == "text"
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
        assert doc.content_type == "text"
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
            Document(
                content_type="text",
                state=123  # State should be a string
            )

    def test_document_with_invalid_content_type(self):
        """Test that setting an invalid content_type raises a validation error."""
        with pytest.raises(ValueError):
            Document(
                content_type=123,  # content_type should be a string
                state="link"
            )

    def test_document_with_invalid_children(self):
        """Test that setting invalid children raises a validation error."""
        with pytest.raises(ValueError):
            Document(
                content_type="text",
                state="link",
                children="not-a-list"  # children should be a list
            )
        
        with pytest.raises(ValueError):
            Document(
                content_type="text",
                state="link",
                children=[1, 2, 3]  # children should be a list of strings
            )

    def test_document_with_invalid_metadata(self):
        """Test that setting invalid metadata raises a validation error."""
        with pytest.raises(ValueError):
            Document(
                content_type="text",
                state="link",
                metadata="not-a-dict"  # metadata should be a dict
            )

    def test_document_serialization(self):
        """Test that a Document can be serialized to a dictionary."""
        doc_id = str(uuid4())
        doc = Document(
            id=doc_id,
            content="Test content",
            content_type="text",
            state="download",
            metadata={"key": "value"}
        )
        
        # Convert to dict
        doc_dict = doc.model_dump()
        
        assert isinstance(doc_dict, dict)
        assert doc_dict["id"] == doc_id
        assert doc_dict["content"] == "Test content"
        assert doc_dict["content_type"] == "text"
        assert doc_dict["state"] == "download"
        assert doc_dict["metadata"] == {"key": "value"}
        assert doc_dict["parent_id"] is None
        assert doc_dict["children"] == []

    def test_document_model_validate(self):
        """Test that a Document can be created from a dictionary."""
        doc_id = str(uuid4())
        doc_dict = {
            "id": doc_id,
            "content": "Test content",
            "content_type": "text",
            "state": "download",
            "metadata": {"key": "value"},
            "parent_id": None,
            "children": []
        }
        
        # Create document from dict
        doc = Document.model_validate(doc_dict)
        
        assert doc.id == doc_id
        assert doc.content == "Test content"
        assert doc.content_type == "text"
        assert doc.state == "download"
        assert doc.metadata == {"key": "value"}
        assert doc.parent_id is None
        assert doc.children == []

    def test_document_default_values(self):
        """Test that Document sets proper default values."""
        # Create with minimal required fields
        doc = Document(
            content_type="text",
            state="link"
        )
        
        # Check default values
        assert doc.content is None
        assert doc.parent_id is None
        assert doc.children == []
        assert doc.metadata == {}
        
        # ID should be a UUID string
        assert isinstance(doc.id, str)
        assert len(doc.id) > 0


if __name__ == "__main__":
    pytest.main()
