import logging
import sys
import asyncio
from datetime import datetime

# Create logger for the docstate module
docstate_logger = logging.getLogger('docstate')

def configure_logging(level=logging.INFO, enable_stdout=True):
    """
    Configure the docstate logger with a standardized format and handlers.
    
    Args:
        level: The logging level to use. Default is logging.INFO.
        enable_stdout: Whether to log to stdout. Default is True.
    
    Returns:
        The configured logger instance.
    """
    # Clear any existing handlers to avoid duplicate logs
    if docstate_logger.handlers:
        docstate_logger.handlers.clear()
    
    # Set the logging level
    docstate_logger.setLevel(level)
    
    # Create a formatter with a detailed format
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s:%(module)s] [%(process)d:%(thread)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Add stdout handler if enabled
    if enable_stdout:
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(formatter)
        docstate_logger.addHandler(stdout_handler)
    
    return docstate_logger

# Configure the logger with default settings
configure_logging()

def log_document_transition(from_state, to_state, doc_id, success=True, error=None):
    """
    Log a document state transition with relevant details.
    
    Args:
        from_state: The original state of the document.
        to_state: The target state the document is transitioning to.
        doc_id: The ID of the document being processed.
        success: Whether the transition was successful. Default is True.
        error: Error information if the transition failed. Default is None.
    """
    if success:
        docstate_logger.info(
            f"Document transition: {from_state} → {to_state} | ID: {doc_id}"
        )
    else:
        docstate_logger.error(
            f"Document transition failed: {from_state} → {to_state} | ID: {doc_id} | Error: {error}"
        )

def log_document_processing(doc_id, process_function, start_time=None):
    """
    Log document processing information, optionally including duration.
    
    Args:
        doc_id: The ID of the document being processed.
        process_function: The name of the processing function being applied.
        start_time: Optional datetime when processing started to calculate duration.
    """
    message = f"Processing document | ID: {doc_id} | Function: {process_function}"
    
    if start_time:
        duration = (datetime.now() - start_time).total_seconds()
        message += f" | Duration: {duration:.2f}s"
    
    docstate_logger.info(message)

def log_document_operation(operation, doc_id, details=None):
    """
    Log general document operations like creation, deletion, updates.
    
    Args:
        operation: The operation being performed (e.g., 'create', 'delete', 'update').
        doc_id: The ID of the document.
        details: Optional additional details about the operation.
    """
    message = f"Document {operation} | ID: {doc_id}"
    if details:
        message += f" | Details: {details}"
    
    docstate_logger.info(message)

def run_async(async_func, *args, **kwargs):
    """
    Run an asynchronous function synchronously.
    
    This utility function allows calling async functions from synchronous code.
    It handles creating or getting an event loop as needed.
    
    Args:
        async_func: The asynchronous function to run.
        *args: Positional arguments to pass to the async function.
        **kwargs: Keyword arguments to pass to the async function.
        
    Returns:
        The return value of the async function.
        
    Raises:
        Any exception that the async function raises.
    """
    try:
        # Get the current event loop or create a new one
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If there's no event loop in the current thread, create one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # If the loop is closed, create a new one
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # If the loop is already running, use run_coroutine_threadsafe
        if loop.is_running():
            future = asyncio.run_coroutine_threadsafe(async_func(*args, **kwargs), loop)
            return future.result()
        else:
            # Otherwise use run_until_complete
            return loop.run_until_complete(async_func(*args, **kwargs))
    except Exception as e:
        docstate_logger.error(f"Error running async function {async_func.__name__}: {str(e)}")
        raise
