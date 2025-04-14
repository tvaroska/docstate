import uuid

from docstate.core import DocumentState, DocumentType, DocumentInstance
from docstate.persistence import InMemoryPersistence

states = [
    DocumentState(name="initial", description="Registred URL"),
    DocumentState(name="mime", description="Check MIME"),
    DocumentState(name="process", description="Processed")
]

dtype = DocumentType(
    name="TestDoc",
    states=states,
    initial_state=states[0]
)

storage = InMemoryPersistence()

doc_id = uuid.uuid4()

url1 =  DocumentInstance(
        doc_id=doc_id,
        doc_type=dtype,
        current_state=dtype.initial_state,
        current_version=uuid.uuid4(),
        branch_id=None,  # Main branch
        parent_branch_id=None,
        content='http://www.sme.sk',
        content_type='url'
    )

storage.save_document_instance(url1)

url2 = storage.load_document_instance(doc_id=doc_id)

pass