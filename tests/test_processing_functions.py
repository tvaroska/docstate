import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from docstate.document import Document
from examples.rag import download_document, chunk_document, embed_document
from tests.fixtures import (
    document, mock_httpx_client, mock_splitter, mock_vectorstore
)


class TestDownloadDocument:
    @pytest.mark.asyncio
    async def test_download_document_success(self, document, mock_httpx_client):
        """Test successful document download."""
        # Set up the document with a URL
        doc = Document(
            state="link",
            url="https://example.com/test",
            media_type="text/plain"
        )
        
        # Process the document
        result = await download_document(doc)
        
        # Verify the result
        assert result.state == "download"
        assert result.content == "Downloaded content"
        assert result.media_type == "text/plain"
        assert result.metadata["source_url"] == doc.content
        
        # Verify the HTTP client was called correctly
        mock_client = mock_httpx_client.return_value.__aenter__.return_value
        mock_client.get.assert_called_once_with("https://example.com/test")
        mock_client.get.return_value.raise_for_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_document_missing_url(self, document):
        """Test document download with missing URL."""
        # Set up the document without a URL
        doc = Document(
            state="link",
            content="No URL here",
            media_type="text/plain"
        )
        
        # Process the document - should raise ValueError
        with pytest.raises(ValueError, match="Expected url"):
            await download_document(doc)

    @pytest.mark.asyncio
    async def test_download_document_request_error(self, document):
        """Test document download with request error."""
        # Set up the document with a URL
        doc = Document(
            state="link",
            url="https://example.com/test",
            media_type="text/plain"
        )
        
        # Mock the httpx client to raise a RequestError
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            
            # Create a request error
            request = MagicMock()
            request.url = "https://example.com/test"
            error = httpx.RequestError("Connection error", request=request)
            mock_instance.get.side_effect = error
            
            mock_client.return_value = mock_instance
            
            # Process the document - should raise RuntimeError
            with pytest.raises(RuntimeError, match="An error occurred while requesting"):
                await download_document(doc)

    @pytest.mark.asyncio
    async def test_download_document_http_status_error(self, document):
        """Test document download with HTTP status error."""
        # Set up the document with a URL
        doc = Document(
            state="link",
            url="https://example.com/test",
            media_type="text/plain"
        )
        
        # Mock the httpx client to raise an HTTPStatusError
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.__aenter__.return_value = mock_instance
            
            # Create an HTTP status error
            request = MagicMock()
            request.url = "https://example.com/test"
            response = MagicMock()
            response.status_code = 404
            response.text = "Not Found"
            
            # Set up the raise_for_status method to raise the error
            def raise_status():
                error = httpx.HTTPStatusError("404 Not Found", request=request, response=response)
                raise error
            
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = raise_status
            mock_instance.get.return_value = mock_response
            
            mock_client.return_value = mock_instance
            
            # Process the document - should raise RuntimeError
            with pytest.raises(RuntimeError, match="Error response"):
                await download_document(doc)


class TestChunkDocument:
    @pytest.mark.asyncio
    async def test_chunk_document_success(self, mock_splitter):
        """Test successful document chunking."""
        # Set up the document
        doc = Document(
            state="download",
            content="This is a long document that will be split into chunks.",
            media_type="text/plain",
            metadata={"source": "test"}
        )
        
        # Process the document
        result = await chunk_document(doc)
        
        # Verify the result
        assert len(result) == 2  # Two chunks based on mock_splitter
        assert result[0].state == "chunk"
        assert result[0].content == "Chunk 1"
        assert result[0].media_type == "text/plain"
        assert result[0].metadata["source"] == "test"
        assert result[0].metadata["chunk_index"] == 0
        assert result[0].metadata["total_chunks"] == 2
        
        assert result[1].state == "chunk"
        assert result[1].content == "Chunk 2"
        assert result[1].metadata["chunk_index"] == 1
        assert result[1].metadata["total_chunks"] == 2
        
        # Verify the splitter was called correctly
        mock_splitter_instance = mock_splitter.return_value
        mock_splitter_instance.split_text.assert_called_once_with(doc.content)

    @pytest.mark.asyncio
    async def test_chunk_document_invalid_media_type(self):
        """Test document chunking with invalid media type."""
        # Set up the document with invalid media type
        doc = Document(
            state="download",
            content="This is a document with invalid media type.",
            media_type="application/pdf",  # Not text/plain
            metadata={"source": "test"}
        )
        
        # Process the document - should raise ValueError
        with pytest.raises(ValueError, match="Expected media_type 'text/plain'"):
            await chunk_document(doc)


class TestEmbedDocument:
    @pytest.mark.asyncio
    async def test_embed_document_success(self, mock_vectorstore):
        """Test successful document embedding."""
        # Set up the document
        doc = Document(
            state="chunk",
            content="This is a document to embed.",
            media_type="text/plain",
            metadata={"source": "test"}
        )
        
        with patch("examples.rag.vectorstore") as mock_vs:
            mock_vs.add_texts.return_value = ["embedding_id"]
            # Set mock_vs.add_texts to return the correct value
            mock_vs.add_texts = MagicMock(return_value=["embedding_id"])
            
            # Process the document
            result = await embed_document(doc)
            
            # Verify the result
            assert result.state == "embed"
            assert result.content == "embedding_id"
            assert result.media_type == "vector"
            assert result.metadata["source"] == "test"
            assert result.metadata["vector_dimensions"] == 1
            assert result.metadata["embedding_method"] == "test_hash"
            
            # Verify the vectorstore was called correctly
            mock_vs.add_texts.assert_called_once_with([doc.content])

    @pytest.mark.asyncio
    async def test_embed_document_invalid_media_type(self):
        """Test document embedding with invalid media type."""
        # Set up the document with invalid media type
        doc = Document(
            state="chunk",
            content="This is a document with invalid media type.",
            media_type="application/pdf",  # Not text/plain
            metadata={"source": "test"}
        )
        
        # Process the document - should raise ValueError
        with pytest.raises(ValueError, match="Expected media_type 'text/plain'"):
            await embed_document(doc)
