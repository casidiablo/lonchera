#!/usr/bin/env bash
set -euo pipefail

# Default app name
APP_NAME=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --app)
            APP_NAME="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Read the version from the VERSION file
VERSION=$(cat VERSION)

# Get the short commit hash of the current branch
COMMIT=$(git rev-parse --short HEAD)

# Get the current branch name
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# Check if there are uncommitted changes
if [[ -n $(git status --porcelain) ]]; then
    DIRTY=" (dirty)"
else
    DIRTY=""
fi

# Construct the version string
if [[ "$BRANCH" == "master" || "$BRANCH" == "main" ]]; then
    FULL_VERSION="${VERSION}${DIRTY}"
else
    FULL_VERSION="${VERSION}@${BRANCH}${DIRTY}"
fi

# Run the deploy command with the constructed version
if [[ -n "$APP_NAME" ]]; then
    fly deploy --app "$APP_NAME" --env VERSION="$FULL_VERSION" --env COMMIT="$COMMIT"
else
    fly deploy --env VERSION="$FULL_VERSION" --env COMMIT="$COMMIT"
fi