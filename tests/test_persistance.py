import pytest
import uuid
from datetime import datetime
from typing import Optional

from docstate.core import (
    DocumentState, DocumentType, DocumentInstance, 
    DocumentVersion, DocumentLineage
)
from docstate.persistence import InMemoryPersistence
from docstate.alchemy import SQLAlchemyPersistence


@pytest.fixture
def document_type():
    """Fixture providing a sample DocumentType."""
    states = [
        DocumentState(name="initial", description="Initial state"),
        DocumentState(name="processed", description="Processed state")
    ]
    return DocumentType(
        name="TestDoc",
        states=states,
        initial_state=states[0]
    )

@pytest.fixture
def document_instance(document_type):
    """Fixture providing a sample DocumentInstance."""
    return DocumentInstance(
        doc_id=uuid.uuid4(),
        doc_type=document_type,
        current_state=document_type.initial_state,
        current_version=uuid.uuid4(),
        branch_id=None,  # Main branch
        parent_branch_id=None,
        metadata={"test": "data"}
    )

@pytest.fixture
def document_version(document_instance):
    """Fixture providing a sample DocumentVersion."""
    return DocumentVersion(
        version_id=document_instance.current_version,
        created_at=datetime.now(),
        reason="Initial version",
        content_type="json",
        mime_type="application/json",
        content={"content": "Sample content"},
        metadata={"version_meta": "test"}
    )

@pytest.fixture
def document_lineage(document_instance, document_version):
    """Fixture providing a sample DocumentLineage."""
    target_version_id = uuid.uuid4()
    return DocumentLineage(
        source_id=document_version.version_id,
        target_id=target_version_id,
        relationship_type="version",
        created_at=datetime.now(),
        metadata={"lineage_meta": "test"}
    )

@pytest.fixture
def persistence():
    """Fixture providing a fresh InMemoryPersistence instance."""
    return InMemoryPersistence()

@pytest.fixture
def sqlalchemy_persistence():
    """Fixture providing a fresh SQLAlchemyPersistence instance with SQLite in-memory database."""
    # Use SQLite in-memory database for testing
    persistence = SQLAlchemyPersistence("sqlite:///:memory:", echo=False)
    persistence.init_db()  # Initialize database tables
    yield persistence
    persistence.drop_db()  # Clean up after tests


class TestInMemoryPersistence:
    """Tests for the InMemoryPersistence implementation."""

    def test_save_and_load_document_instance(self, persistence, document_instance):
        """Test saving and loading a document instance."""
        # Save the instance
        persistence.save_document_instance(document_instance)
        
        # Load it back
        loaded = persistence.load_document_instance(document_instance.doc_id, document_instance.branch_id)
        
        # Verify it's the same instance
        assert loaded is not None
        assert loaded.doc_id == document_instance.doc_id
        assert loaded.current_state.name == document_instance.current_state.name
        assert loaded.current_version == document_instance.current_version
        assert loaded.metadata == document_instance.metadata

    def test_save_and_load_document_version(self, persistence, document_version):
        """Test saving and loading a document version."""
        # Save the version
        persistence.save_document_version(document_version)
        
        # Load it back
        loaded = persistence.load_document_version(document_version.version_id)
        
        # Verify it's the same version
        assert loaded is not None
        assert loaded.version_id == document_version.version_id
        assert loaded.reason == document_version.reason
        assert loaded.content_type == document_version.content_type
        assert loaded.mime_type == document_version.mime_type
        assert loaded.content == document_version.content
        assert loaded.metadata == document_version.metadata

    def test_save_and_load_document_lineage(self, persistence, document_lineage):
        """Test saving and loading document lineage relationships."""
        # Save the lineage
        persistence.save_document_lineage(document_lineage)
        
        # Load lineage for the source document
        lineages = persistence.load_document_lineage(document_lineage.source_id)
        
        # Verify it contains our saved lineage
        assert len(lineages) == 1
        assert lineages[0].source_id == document_lineage.source_id
        assert lineages[0].target_id == document_lineage.target_id
        assert lineages[0].relationship_type == document_lineage.relationship_type
        assert lineages[0].metadata == document_lineage.metadata

    def test_load_document_versions(self, persistence, document_instance, document_version, document_lineage):
        """Test loading all versions for a document."""
        # Setup: Save everything
        persistence.save_document_instance(document_instance)
        persistence.save_document_version(document_version)
        persistence.save_document_lineage(document_lineage)
        
        # Save a target version that would be linked by our lineage
        target_version = DocumentVersion(
            version_id=document_lineage.target_id,
            created_at=datetime.now(),
            reason="Follow-up version",
            content_type="json",
            mime_type="application/json",
            content={"content": "Updated content"},
            metadata={"version": "2"}
        )
        persistence.save_document_version(target_version)
        
        # Test loading versions
        versions = persistence.load_document_versions(document_lineage.source_id)
        
        # Verify we get the expected versions
        assert len(versions) == 1  # Should find only the target (follow-up) version
        assert versions[0].version_id == target_version.version_id
        assert versions[0].reason == target_version.reason

    def test_load_document_branches(self, persistence, document_instance):
        """Test loading all branches for a document."""
        # Save the main branch
        persistence.save_document_instance(document_instance)
        
        # Create and save a branch
        branch_id = uuid.uuid4()
        branch_instance = DocumentInstance(
            doc_id=document_instance.doc_id,
            doc_type=document_instance.doc_type,
            current_state=document_instance.current_state,
            current_version=uuid.uuid4(),
            branch_id=branch_id,
            parent_branch_id=document_instance.branch_id,
            metadata={"branch": "test branch"}
        )
        persistence.save_document_instance(branch_instance)
        
        # Load all branches
        branches = persistence.load_document_branches(document_instance.doc_id)
        
        # Verify we get both branches
        assert len(branches) == 2
        branch_ids = {b.branch_id for b in branches}
        assert document_instance.branch_id in branch_ids
        assert branch_id in branch_ids

    def test_get_next_branch_id(self, persistence, document_instance):
        """Test generation of unique branch IDs."""
        # Save an instance first
        persistence.save_document_instance(document_instance)
        
        # Get a new branch ID
        branch_id = persistence.get_next_branch_id(document_instance.doc_id)
        
        # Verify it's a valid UUID and not the same as the existing branch
        assert isinstance(branch_id, uuid.UUID)
        assert branch_id != document_instance.branch_id
        
        # Create a new branch with this ID and save it
        branch = DocumentInstance(
            doc_id=document_instance.doc_id,
            doc_type=document_instance.doc_type,
            current_state=document_instance.current_state,
            current_version=uuid.uuid4(),
            branch_id=branch_id,
            parent_branch_id=document_instance.branch_id,
            metadata={}
        )
        persistence.save_document_instance(branch)
        
        # Get another branch ID and verify it's different
        another_branch_id = persistence.get_next_branch_id(document_instance.doc_id)
        assert another_branch_id != branch_id
        assert another_branch_id != document_instance.branch_id

    def test_complex_document_workflow(self, persistence, document_type):
        """Test a more complex workflow with multiple versions and branches."""
        # Create initial document
        doc_id = uuid.uuid4()
        main_branch_id = None  # Main branch
        
        # Initial version
        initial_version_id = uuid.uuid4()
        
        # Create and save initial document instance
        doc = DocumentInstance(
            doc_id=doc_id,
            doc_type=document_type,
            current_state=document_type.states[0],  # initial state
            current_version=initial_version_id,
            branch_id=main_branch_id,
            parent_branch_id=None,
            metadata={"initial": True}
        )
        persistence.save_document_instance(doc)
        
        # Save initial version
        initial_version = DocumentVersion(
            version_id=initial_version_id,
            created_at=datetime.now(),
            reason="Document created",
            content_type="json",
            mime_type="application/json",
            content={"initial": "content"},
            metadata={}
        )
        persistence.save_document_version(initial_version)
        
        # Create a second version (state transition on main branch)
        second_version_id = uuid.uuid4()
        second_version = DocumentVersion(
            version_id=second_version_id,
            created_at=datetime.now(),
            reason="Processed document",
            content_type="json",
            mime_type="application/json",
            content={"processed": "content"},
            metadata={}
        )
        persistence.save_document_version(second_version)
        
        # Update document instance to point to new version with new state
        doc.current_version = second_version_id
        doc.current_state = document_type.states[1]  # processed state
        persistence.save_document_instance(doc)
        
        # Save lineage connecting versions
        lineage = DocumentLineage(
            source_id=initial_version_id,
            target_id=second_version_id,
            relationship_type="version",
            created_at=datetime.now(),
            metadata={}
        )
        persistence.save_document_lineage(lineage)
        
        # Create a branch from the initial version
        branch_id = persistence.get_next_branch_id(doc_id)
        branch_version_id = uuid.uuid4()
        
        # Create and save branch instance
        branch = DocumentInstance(
            doc_id=doc_id,
            doc_type=document_type,
            current_state=document_type.states[0],  # Still in initial state on branch
            current_version=branch_version_id,
            branch_id=branch_id,
            parent_branch_id=main_branch_id,
            metadata={"branch": "experimental"}
        )
        persistence.save_document_instance(branch)
        
        # Save branch version
        branch_version = DocumentVersion(
            version_id=branch_version_id,
            created_at=datetime.now(),
            reason="Created branch",
            content_type="json",
            mime_type="application/json",
            content={"branched": "content"},
            metadata={}
        )
        persistence.save_document_version(branch_version)
        
        # Save lineage for branch
        branch_lineage = DocumentLineage(
            source_id=initial_version_id,
            target_id=branch_version_id,
            relationship_type="branch",
            created_at=datetime.now(),
            metadata={}
        )
        persistence.save_document_lineage(branch_lineage)
        
        # Now perform tests
        
        # 1. Verify we can load both branches
        branches = persistence.load_document_branches(doc_id)
        assert len(branches) == 2
        
        # 2. Verify main branch is in processed state
        main = persistence.load_document_instance(doc_id, main_branch_id)
        assert main is not None
        assert main.current_state.name == "processed"
        assert main.current_version == second_version_id
        
        # 3. Verify experimental branch is still in initial state
        exp = persistence.load_document_instance(doc_id, branch_id)
        assert exp is not None
        assert exp.current_state.name == "initial"
        assert exp.current_version == branch_version_id
        
        # 4. Verify lineage shows both relationships
        lineages = persistence.load_document_lineage(initial_version_id)
        assert len(lineages) == 2
        relationship_types = {l.relationship_type for l in lineages}
        assert "version" in relationship_types
        assert "branch" in relationship_types


class TestSQLAlchemyPersistence:
    """Tests for the SQLAlchemyPersistence implementation using SQLite in-memory database."""
    
    def test_save_and_load_document_instance(self, sqlalchemy_persistence, document_instance):
        """Test saving and loading a document instance."""
        # Save the instance
        sqlalchemy_persistence.save_document_instance(document_instance)
        
        # Load it back
        loaded = sqlalchemy_persistence.load_document_instance(document_instance.doc_id, document_instance.branch_id)
        
        # Verify it's the same instance
        assert loaded is not None
        assert loaded.doc_id == document_instance.doc_id
        assert loaded.current_state.name == document_instance.current_state.name
        assert loaded.current_version == document_instance.current_version
        assert loaded.metadata == document_instance.metadata

    def test_save_and_load_document_version(self, sqlalchemy_persistence, document_version):
        """Test saving and loading a document version."""
        # Save the version
        sqlalchemy_persistence.save_document_version(document_version)
        
        # Load it back
        loaded = sqlalchemy_persistence.load_document_version(document_version.version_id)
        
        # Verify it's the same version
        assert loaded is not None
        assert loaded.version_id == document_version.version_id
        assert loaded.reason == document_version.reason
        assert loaded.content_type == document_version.content_type
        assert loaded.mime_type == document_version.mime_type
        assert loaded.content == document_version.content
        assert loaded.metadata == document_version.metadata

    def test_save_and_load_document_lineage(self, sqlalchemy_persistence, document_lineage):
        """Test saving and loading document lineage relationships."""
        # Save the lineage
        sqlalchemy_persistence.save_document_lineage(document_lineage)
        
        # Load lineage for the source document
        lineages = sqlalchemy_persistence.load_document_lineage(document_lineage.source_id)
        
        # Verify it contains our saved lineage
        assert len(lineages) == 1
        assert lineages[0].source_id == document_lineage.source_id
        assert lineages[0].target_id == document_lineage.target_id
        assert lineages[0].relationship_type == document_lineage.relationship_type
        assert lineages[0].metadata == document_lineage.metadata

    def test_load_document_versions(self, sqlalchemy_persistence, document_instance, document_version, document_lineage):
        """Test loading all versions for a document."""
        # Setup: Save everything
        sqlalchemy_persistence.save_document_instance(document_instance)
        sqlalchemy_persistence.save_document_version(document_version)
        sqlalchemy_persistence.save_document_lineage(document_lineage)
        
        # Save a target version that would be linked by our lineage
        target_version = DocumentVersion(
            version_id=document_lineage.target_id,
            created_at=datetime.now(),
            reason="Follow-up version",
            content_type="json",
            mime_type="application/json",
            content={"content": "Updated content"},
            metadata={"version": "2"}
        )
        sqlalchemy_persistence.save_document_version(target_version)
        
        # Test loading versions
        versions = sqlalchemy_persistence.load_document_versions(document_lineage.source_id)
        
        # Verify we get the expected versions
        assert len(versions) == 1  # Should find only the target (follow-up) version
        assert versions[0].version_id == target_version.version_id
        assert versions[0].reason == target_version.reason

    def test_load_document_branches(self, sqlalchemy_persistence, document_instance):
        """Test loading all branches for a document."""
        # Save the main branch
        sqlalchemy_persistence.save_document_instance(document_instance)
        
        # Create and save a branch
        branch_id = uuid.uuid4()
        branch_instance = DocumentInstance(
            doc_id=document_instance.doc_id,
            doc_type=document_instance.doc_type,
            current_state=document_instance.current_state,
            current_version=uuid.uuid4(),
            branch_id=branch_id,
            parent_branch_id=document_instance.branch_id,
            metadata={"branch": "test branch"}
        )
        sqlalchemy_persistence.save_document_instance(branch_instance)
        
        # Load all branches
        branches = sqlalchemy_persistence.load_document_branches(document_instance.doc_id)
        
        # Verify we get both branches
        assert len(branches) == 2
        branch_ids = {b.branch_id for b in branches}
        assert document_instance.branch_id in branch_ids
        assert branch_id in branch_ids

    def test_get_next_branch_id(self, sqlalchemy_persistence, document_instance):
        """Test generation of unique branch IDs."""
        # Save an instance first
        sqlalchemy_persistence.save_document_instance(document_instance)
        
        # Get a new branch ID
        branch_id = sqlalchemy_persistence.get_next_branch_id(document_instance.doc_id)
        
        # Verify it's a valid UUID and not the same as the existing branch
        assert isinstance(branch_id, uuid.UUID)
        assert branch_id != document_instance.branch_id
        
        # Create a new branch with this ID and save it
        branch = DocumentInstance(
            doc_id=document_instance.doc_id,
            doc_type=document_instance.doc_type,
            current_state=document_instance.current_state,
            current_version=uuid.uuid4(),
            branch_id=branch_id,
            parent_branch_id=document_instance.branch_id,
            metadata={}
        )
        sqlalchemy_persistence.save_document_instance(branch)
        
        # Get another branch ID and verify it's different
        another_branch_id = sqlalchemy_persistence.get_next_branch_id(document_instance.doc_id)
        assert another_branch_id != branch_id
        assert another_branch_id != document_instance.branch_id

    def test_complex_document_workflow(self, sqlalchemy_persistence, document_type):
        """Test a more complex workflow with multiple versions and branches."""
        # Create initial document
        doc_id = uuid.uuid4()
        main_branch_id = None  # Main branch
        
        # Initial version
        initial_version_id = uuid.uuid4()
        
        # Create and save initial document instance
        doc = DocumentInstance(
            doc_id=doc_id,
            doc_type=document_type,
            current_state=document_type.states[0],  # initial state
            current_version=initial_version_id,
            branch_id=main_branch_id,
            parent_branch_id=None,
            metadata={"initial": True}
        )
        sqlalchemy_persistence.save_document_instance(doc)
        
        # Save initial version
        initial_version = DocumentVersion(
            version_id=initial_version_id,
            created_at=datetime.now(),
            reason="Document created",
            content_type="json",
            mime_type="application/json",
            content={"initial": "content"},
            metadata={}
        )
        sqlalchemy_persistence.save_document_version(initial_version)
        
        # Create a second version (state transition on main branch)
        second_version_id = uuid.uuid4()
        second_version = DocumentVersion(
            version_id=second_version_id,
            created_at=datetime.now(),
            reason="Processed document",
            content_type="json",
            mime_type="application/json",
            content={"processed": "content"},
            metadata={}
        )
        sqlalchemy_persistence.save_document_version(second_version)
        
        # Update document instance to point to new version with new state
        doc.current_version = second_version_id
        doc.current_state = document_type.states[1]  # processed state
        sqlalchemy_persistence.save_document_instance(doc)
        
        # Save lineage connecting versions
        lineage = DocumentLineage(
            source_id=initial_version_id,
            target_id=second_version_id,
            relationship_type="version",
            created_at=datetime.now(),
            metadata={}
        )
        sqlalchemy_persistence.save_document_lineage(lineage)
        
        # Create a branch from the initial version
        branch_id = sqlalchemy_persistence.get_next_branch_id(doc_id)
        branch_version_id = uuid.uuid4()
        
        # Create and save branch instance
        branch = DocumentInstance(
            doc_id=doc_id,
            doc_type=document_type,
            current_state=document_type.states[0],  # Still in initial state on branch
            current_version=branch_version_id,
            branch_id=branch_id,
            parent_branch_id=main_branch_id,
            metadata={"branch": "experimental"}
        )
        sqlalchemy_persistence.save_document_instance(branch)
        
        # Save branch version
        branch_version = DocumentVersion(
            version_id=branch_version_id,
            created_at=datetime.now(),
            reason="Created branch",
            content_type="json",
            mime_type="application/json",
            content={"branched": "content"},
            metadata={}
        )
        sqlalchemy_persistence.save_document_version(branch_version)
        
        # Save lineage for branch
        branch_lineage = DocumentLineage(
            source_id=initial_version_id,
            target_id=branch_version_id,
            relationship_type="branch",
            created_at=datetime.now(),
            metadata={}
        )
        sqlalchemy_persistence.save_document_lineage(branch_lineage)
        
        # Now perform tests
        
        # 1. Verify we can load both branches
        branches = sqlalchemy_persistence.load_document_branches(doc_id)
        assert len(branches) == 2
        
        # 2. Verify main branch is in processed state
        main = sqlalchemy_persistence.load_document_instance(doc_id, main_branch_id)
        assert main is not None
        assert main.current_state.name == "processed"
        assert main.current_version == second_version_id
        
        # 3. Verify experimental branch is still in initial state
        exp = sqlalchemy_persistence.load_document_instance(doc_id, branch_id)
        assert exp is not None
        assert exp.current_state.name == "initial"
        assert exp.current_version == branch_version_id
        
        # 4. Verify lineage shows both relationships
        lineages = sqlalchemy_persistence.load_document_lineage(initial_version_id)
        assert len(lineages) == 2
        relationship_types = {l.relationship_type for l in lineages}
        assert "version" in relationship_types
        assert "branch" in relationship_types
