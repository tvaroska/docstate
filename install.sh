#!/bin/bash
# install.sh - Install DocState using uv

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "Creating virtual environment with uv..."
  uv venv
fi

# Install the package in development mode with all extras
echo "Installing DocState with uv..."
uv pip install -e ".[dev,http,ai]"

echo "Installation complete!"
echo "Activate the virtual environment with: source .venv/bin/activate"
