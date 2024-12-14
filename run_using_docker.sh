#!/usr/bin/env bash
set -euo pipefail

# Load environment variables from .env file if it exists
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Generate version by combining VERSION file content with timestamp
BASE_VERSION=$(cat VERSION)
TIMESTAMP=$(date +"%Y%m%d_%H%M")
VERSION="${BASE_VERSION}-${TIMESTAMP}"

# Name of the Docker image
IMAGE_NAME="lonchera"

# Full image name with version
FULL_IMAGE_NAME="${IMAGE_NAME}:${VERSION}"

echo "Building Docker image: ${FULL_IMAGE_NAME}"

# Build the Docker image
docker build -t "${FULL_IMAGE_NAME}" .

echo "Docker image built successfully"

echo "Stopping any existing container named ${IMAGE_NAME}"
docker stop "${IMAGE_NAME}" || true

docker rm "${IMAGE_NAME}" 2>/dev/null || true

echo "Running Docker container as daemon"

# Use the data directory from the environment variable or default to PWD
DATA_DIR="${DATA_DIR:-$PWD}"

# Run the Docker container as a daemon
docker run -d \
    -v "${DATA_DIR}:/data" \
    -e DB_PATH=/data/lonchera.db \
    -e TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}" \
    ${DEEPINFRA_API_KEY:+-e DEEPINFRA_API_KEY="${DEEPINFRA_API_KEY}"} \
    --name "${IMAGE_NAME}" \
    "${FULL_IMAGE_NAME}"

echo "Docker container is now running as a daemon"

# Print the container ID
CONTAINER_ID=$(docker ps -q -f name="${IMAGE_NAME}")
echo "Container ID: ${CONTAINER_ID}"

# if CONTAINER_ID is empty, then the container is not running
# show an error message and exit with a non-zero status
if [ -z "${CONTAINER_ID}" ]; then
  echo "Container is not running"
  exit 1
fi

# log the container output
docker logs -f lonchera
