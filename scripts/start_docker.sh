#!/bin/bash

# Navigate to project root
cd "$(dirname "$0")/.."

# Check if .env exists, if not, copy from .env.example
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please update the .env file with your specific configurations (especially API keys)."
fi

# Build and start the environment
echo "Starting LedgerAlpha Docker environment..."
docker-compose up -d --build

# Show status
docker-compose ps

echo "Environment is starting up. You can check logs with: docker-compose logs -f app"
