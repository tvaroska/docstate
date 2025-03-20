"""
DocState - Document State Management Library

Setup script for installing the docstate package.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="docstate",
    version="0.1.0",
    author="DocState Team",
    author_email="info@docstate.example.com",
    description="A library for managing document state transitions in a database",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/docstate/docstate",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.12",
    install_requires=[
        "sqlalchemy>=2.0.0",
        "alembic>=1.10.0",
        "pydantic>=2.0.0",
        "tenacity>=8.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "mypy>=1.0.0",
            "black>=23.0.0",
            "isort>=5.0.0",
            "flake8>=6.0.0",
            "sphinx>=6.0.0",
        ],
        "http": [
            "requests>=2.0.0",
            "aiohttp>=3.0.0",
        ],
        "ai": [
            "google-generativeai>=0.3.0",
            "transformers>=4.0.0",
            "langchain>=0.0.1",
        ],
    },
)
