from typing import Optional, Dict, List
from uuid import UUID
import uuid
from datetime import datetime

from abc import ABC, abstractmethod
from docstate.core import DocumentInstance, DocumentVersion, DocumentLineage

class PersistenceInterface(ABC):
    """Abstract Base Class for storing and retrieving document state."""

    @abstractmethod
    def save_document_instance(self, instance: DocumentInstance) -> None:
        """Saves or updates the state of a document instance/branch in persistent storage."""
        pass

    @abstractmethod
    def save_document_version(self, version: DocumentVersion) -> None:
        """Saves a new document version."""
        pass

    @abstractmethod
    def save_document_lineage(self, lineage: DocumentLineage) -> None:
        """Saves a document lineage relationship."""
        pass

    @abstractmethod
    def load_document_instance(self, doc_id: UUID, branch_id: Optional[UUID] = None) -> Optional[DocumentInstance]:
        """Loads a specific document instance/branch."""
        pass

    @abstractmethod
    def load_document_version(self, version_id: UUID) -> Optional[DocumentVersion]:
        """Loads a specific document version."""
        pass

    @abstractmethod
    def load_document_versions(self, doc_id: UUID) -> List[DocumentVersion]:
        """Loads all versions for a document."""
        pass

    @abstractmethod
    def load_document_lineage(self, doc_id: UUID) -> List[DocumentLineage]:
        """Loads all lineage relationships for a document."""
        pass

    @abstractmethod
    def load_document_branches(self, doc_id: UUID) -> List[DocumentInstance]:
        """Loads all branches for a document."""
        pass

    @abstractmethod
    def get_next_branch_id(self, doc_id: UUID) -> UUID:
        """Generates a unique branch ID for a document."""
        pass

class InMemoryPersistence(PersistenceInterface):
    """An in-memory implementation of the PersistenceInterface using dictionaries."""

    def __init__(self):
        """Initializes the in-memory storage."""
        self._instances: Dict[UUID, Dict[Optional[UUID], DocumentInstance]] = {}
        self._versions: Dict[UUID, DocumentVersion] = {}
        self._lineage: Dict[UUID, List[DocumentLineage]] = {}

    def save_document_instance(self, instance: DocumentInstance) -> None:
        """Saves or updates a document instance."""
        if instance.doc_id not in self._instances:
            self._instances[instance.doc_id] = {}
        self._instances[instance.doc_id][instance.branch_id] = instance

    def save_document_version(self, version: DocumentVersion) -> None:
        """Saves a document version."""
        self._versions[version.version_id] = version

    def save_document_lineage(self, lineage: DocumentLineage) -> None:
        """Saves a lineage relationship."""
        if lineage.source_id not in self._lineage:
            self._lineage[lineage.source_id] = []
        self._lineage[lineage.source_id].append(lineage)

    def load_document_instance(self, doc_id: UUID, branch_id: Optional[UUID] = None) -> Optional[DocumentInstance]:
        """Loads a specific document instance."""
        doc_branches = self._instances.get(doc_id)
        if doc_branches:
            return doc_branches.get(branch_id)
        return None

    def load_document_version(self, version_id: UUID) -> Optional[DocumentVersion]:
        """Loads a specific version."""
        return self._versions.get(version_id)

    def load_document_versions(self, doc_id: UUID) -> List[DocumentVersion]:
        """Loads all versions for a document."""
        versions = []
        for lineage in self._lineage.get(doc_id, []):
            version = self._versions.get(lineage.target_id)
            if version:
                versions.append(version)
        return versions

    def load_document_lineage(self, doc_id: UUID) -> List[DocumentLineage]:
        """Loads all lineage relationships for a document."""
        return self._lineage.get(doc_id, [])

    def load_document_branches(self, doc_id: UUID) -> List[DocumentInstance]:
        """Loads all branches for a document."""
        doc_branches = self._instances.get(doc_id)
        if doc_branches:
            return list(doc_branches.values())
        return []

    def get_next_branch_id(self, doc_id: UUID) -> UUID:
        """Generates a unique branch ID for a document."""
        while True:
            new_branch_id = uuid.uuid4()
            if doc_id not in self._instances or new_branch_id not in self._instances[doc_id]:
                return new_branch_id
