#!/bin/bash
set -e

# NyayaVoice Startup Script
echo "🚀 Starting NyayaVoice Legal Aid Assistant..."
echo "=================================================="
echo "Current directory: $(pwd)"
echo "Python version: $(python3 --version 2>/dev/null || echo 'Python not found')"
echo "PORT is set to: ${PORT:-8080}"
echo ""

# Install/update Python dependencies
echo "📦 Installing Python dependencies..."
pip install --quiet -r requirements.txt

# Check Qdrant connection
echo "🔍 Checking Qdrant connection..."
python3 -c "
import os
from qdrant_client import QdrantClient
try:
    qdrant_url = os.getenv('QDRANT_URL', ':memory:')
    if qdrant_url != ':memory:':
        client = QdrantClient(url=qdrant_url, api_key=os.getenv('QDRANT_API_KEY'))
        client.get_collections()
        print('✅ Qdrant connection successful')
    else:
        print('ℹ️  Using in-memory Qdrant')
except Exception as e:
    print(f'⚠️  Qdrant connection failed: {e}')
"

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p generated_docs logs

# Set environment variables
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
export BACKEND_URL="${BACKEND_URL:-https://$(hostname)}"

echo ""
echo "🌟 Starting uvicorn server on port ${PORT:-8080}..."
echo ""

# Start the server (no --reload in production)
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8080} \
    --workers 1 \
    --log-level info \
    --access-log
