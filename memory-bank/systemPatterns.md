# System Patterns: Document State Management Module

## 1. Core Architecture

The document state management system follows a state machine pattern with persistence layer abstraction. Here's the architecture:

```mermaid
flowchart TD
    subgraph Core
        DT[DocumentType]
        DS[DocumentState]
        DI[DocumentInstance]
        DV[DocumentVersion]
        DL[DocumentLineage]
        ST[StateTransition]
    end
    
    subgraph Persistence
        PI[PersistenceInterface]
        IMP[InMemoryPersistence]
        SAP[SQLAlchemyPersistence]
        
        PI --> IMP
        PI --> SAP
    end
    
    Core --> PI
```

## 2. Key Design Patterns

### State Machine Pattern
- Documents have well-defined states (DocumentState)
- Transitions between states are explicitly defined
- Each document type has its own set of valid states
- Transition functions handle the state change logic

### Repository Pattern
- Persistence abstraction through interfaces
- Multiple implementation options (In-memory, SQLAlchemy)
- CRUD operations for document instances, versions, and lineage

### Dependency Injection
- Transition functions are injected rather than hardcoded
- Allows for flexible processing pipelines
- Consumers provide specific transition implementations

### Immutable Version History
- Each state change creates a new version
- Previous versions are preserved
- Complete document history is maintained

### Composite Pattern (Document Lineage)
- Documents can have parent-child relationships
- Multiple results can be produced from a single input
- Complex document trees can be modeled and traversed

### Branch Model
- Similar to Git's branching concept
- Alternative processing paths from the same base document
- Facilitates experimentation and comparison

## 3. Component Relationships

```mermaid
classDiagram
    class DocumentType {
        +name: str
        +states: List[DocumentState]
        +initial_state: DocumentState
    }
    
    class DocumentState {
        +name: str
        +description: Optional[str]
        +allows_multiple_outputs: bool
    }
    
    class DocumentInstance {
        +doc_id: UUID
        +doc_type: DocumentType
        +current_state: DocumentState
        +current_version: UUID
        +branch_id: Optional[UUID]
        +parent_branch_id: Optional[UUID]
        +metadata: Dict[str, Any]
    }
    
    class DocumentVersion {
        +version_id: UUID
        +created_at: datetime
        +reason: str
        +content_type: str
        +mime_type: str
        +content: Any
        +metadata: Dict[str, Any]
    }
    
    class DocumentLineage {
        +source_id: UUID
        +target_id: UUID
        +relationship_type: str
        +created_at: datetime
        +metadata: Dict[str, Any]
    }
    
    class StateTransition {
        +doc_type: DocumentType
        +from_state: DocumentState
        +to_state: DocumentState
        +transition_func: TransitionFunction
        +creates_new_version: bool
        +can_produce_multiple: bool
    }
    
    DocumentType "1" --> "*" DocumentState : contains
    DocumentInstance "1" --> "1" DocumentType : has type
    DocumentInstance "1" --> "1" DocumentState : current state
    DocumentInstance "1" --> "1" DocumentVersion : current version
    DocumentLineage "1" --> "1" DocumentVersion : source
    DocumentLineage "1" --> "1" DocumentVersion : target
    StateTransition "1" --> "1" DocumentType : applies to
    StateTransition "1" --> "1" DocumentState : from
    StateTransition "1" --> "1" DocumentState : to
```

## 4. Data Flow

```mermaid
flowchart TD
    subgraph Document_Lifecycle
        Start([Create Document]) --> Initial[Initial State]
        Initial --> |Transition 1| State1[State 1]
        State1 --> |Transition 2| State2[State 2]
        State1 --> |Branch| BranchA[Branch A: State 1']
        BranchA --> |Alt Transition| BranchState[Branch A: State 2']
    end
    
    subgraph Version_History
        V1[Version 1] --> V2[Version 2]
        V1 --> VB1[Branch Version 1]
        VB1 --> VB2[Branch Version 2]
    end
    
    Start -.-> V1
    Initial -.-> V1
    State1 -.-> V2
    BranchA -.-> VB1
    BranchState -.-> VB2
```

## 5. Key Technical Decisions

1. **Pydantic Models for Core Components**: Using Pydantic for data validation and serialization.

2. **SQLAlchemy ORM with PostgreSQL**: Primary persistence mechanism for production use.

3. **In-Memory Implementation**: For testing and lightweight use cases.

4. **UUID-Based Identity**: All entities use UUIDs for identification.

5. **Explicit State Transitions**: Transitions must be registered and are not implicit.

6. **Immutable Document History**: Previous versions are preserved and never modified.

7. **Branch-Based Experimentation**: Formal support for alternative processing paths.

8. **Multiple Output Documents**: State transitions can produce multiple results.

## 6. Extensibility Mechanisms

1. **Custom Document Types**: Define new document types with unique states and transitions.

2. **Pluggable Transition Functions**: Add custom processing logic through dependency injection.

3. **Alternative Persistence Implementations**: Implement PersistenceInterface for different storage solutions.

4. **Metadata Enrichment**: Both documents and relationships support flexible metadata.

5. **Branching Strategy**: Create custom branching strategies for different processing needs.
