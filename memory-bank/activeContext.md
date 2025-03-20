# DocState Active Context

## Current Focus

The current development focus for DocState is implementing the state machine core with SQLAlchemy ORM integration. We are prioritizing:

1. **State Machine Implementation**: Building the robust state transition mechanism that forms the core of the library
2. **SQLAlchemy Integration**: Implementing the ORM models and database persistence layer
3. **Alembic Migration Support**: Setting up database migration capabilities for schema evolution
4. **Python 3.12+ Features**: Leveraging the latest Python language features for improved type safety and performance
5. **Build System Migration**: Converting from Poetry to uv for faster dependency management

## Recent Changes

We're focusing on the state machine implementation, SQLAlchemy integration and build system improvements. Key recent developments include:

1. **Technology Update**: Upgraded minimum Python version to 3.12+ to leverage latest language features
2. **ORM Selection**: Selected SQLAlchemy as the ORM with Alembic for database migrations
3. **State Machine Architecture**: Refined the state machine design for robust document processing
4. **Database Schema Design**: Designed SQLAlchemy models and table relationships
5. **Build System**: Converted from Poetry to uv for faster dependency management and improved developer experience
6. **Transaction Management**: Implemented robust transaction management for state transitions
7. **State History Tracking**: Added comprehensive document state history tracking and analysis
8. **Document Method Binding**: Enhanced Document instances with direct access to state history methods

## Next Steps

The immediate next steps for the state machine implementation are:

1. **State Machine Core**:
   - Implement the StateManager class for managing the state transition graph
   - Create the state transition registry and validation logic
   - Build the transition decorator with SQLAlchemy transaction support
   - Implement atomic state transitions with proper error handling

2. **SQLAlchemy Integration**:
   - Define SQLAlchemy models for Document and TransitionHistory
   - Implement session management and transaction boundaries
   - Create Alembic migration scripts for database schema
   - Build query interfaces for document filtering by state

3. **State Transition Validation**:
   - Implement validation rules for state transitions
   - Create middleware for transition logging and monitoring
   - Build state graph visualization tools
   - Implement retry policies for failed transitions

4. **Error Recovery System**:
   - Design comprehensive error state handling
   - Implement recovery paths for different error types
   - Create tools for manual intervention in error states
   - Build monitoring for stuck documents

5. **Build System Improvements**:
   - Fine-tune uv configuration for optimal performance
   - Set up CI/CD pipeline with uv for faster builds
   - Create uv-based development workflows

## Active Decisions

We are currently making decisions specific to the state machine implementation:

### State Machine Model

We've decided to implement a hybrid state machine model:

**Selected Approach**: Two-level state machine
- Top-level states are string identifiers (e.g., "processing", "validated")
- Sub-states can be represented as metadata for more granular tracking
- All state transitions are tracked in the database via SQLAlchemy

```python
# Example with sub-state tracking
@docs.transition("processing", "validated")
def validate(document: Document) -> Document:
    document.metadata["validation_level"] = "complete"
    document.metadata["validator"] = "schema_validator_v2"
    return document
```

### SQLAlchemy Integration

We've chosen a specific approach for SQLAlchemy integration:

**Selected Approach**: SQLAlchemy ORM with declarative models
- Models defined using SQLAlchemy's declarative syntax
- Alembic for managing schema migrations
- Session management handled by DocState

```python
# Example SQLAlchemy model
class Document(Base):
    __tablename__ = "documents"
    
    id = Column(UUID, primary_key=True, default=uuid.uuid4)
    state = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=True)
    metadata = Column(JSON, nullable=False, default=dict)
    uri = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    version = Column(Integer, default=1)
```

### Error Recovery Strategy

We've decided on a comprehensive error handling approach:

**Selected Approach**: Multi-level error recovery
- Each transition defines its error state
- Automatic retry system with configurable backoff
- Manual intervention APIs for human-in-the-loop recovery
- Error aggregation for monitoring and alerting

```python
# Example with retry configuration
@docs.transition("download", "processed", 
                error="download_error",
                retry=RetryPolicy(max_attempts=3, backoff=2.0))
def process_document(document: Document) -> Document:
    # Processing logic
    return document
```

### Python 3.12+ Features

We're leveraging Python 3.12+ features for the state machine:

**Key Features Used**:
- Type parameter syntax for improved generic typing
- Pattern matching for state transition logic
- Self type for better method typing
- New typing features for more precise static analysis

### Package Management

We've switched from Poetry to uv for dependency management:

**Selected Approach**: uv-based dependency management
- Faster dependency resolution with uv
- pyproject.toml for package configuration
- requirements-dev.txt for development dependencies
- install.sh script for easy setup

## Current Challenges

Key challenges specific to the state machine implementation:

1. **State Graph Complexity**: Managing complex state graphs with many possible transitions
2. **Transaction Boundaries**: Ensuring proper transaction management with SQLAlchemy
3. **Concurrent Modifications**: Handling race conditions in state transitions
4. **Migration Strategies**: Using Alembic effectively for schema evolution
5. **Error Recovery Automation**: Building intelligent retry and recovery systems
6. **State Machine Visualization**: Creating clear visualizations of complex state machines
7. **Performance Optimization**: Optimizing SQLAlchemy queries for state transitions
8. **Python 3.12 Compatibility**: Ensuring libraries work with Python 3.12+ features
9. **Dependency Management**: Optimizing uv configuration for development workflows
