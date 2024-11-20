#!/usr/bin/env bash
VERSION_FILE="VERSION"
CURRENT_VERSION=$(cat $VERSION_FILE)
LAST_COMMIT_MESSAGE=$(git log -1 --pretty=%B)

# Check if VERSION file has staged changes
if git diff --cached --name-only | grep -q "$VERSION_FILE"; then
  echo "VERSION file has staged changes. Skipping version bump."
  exit 0
fi

if [[ $LAST_COMMIT_MESSAGE != *"Bump version to"* ]]; then
  IFS='.' read -r -a version_parts <<< "$CURRENT_VERSION"
  ((version_parts[2]++))
  NEW_VERSION="${version_parts[0]}.${version_parts[1]}.${version_parts[2]}"
  echo $NEW_VERSION > $VERSION_FILE
  echo "Version bumped to $NEW_VERSION. Please stage and commit the VERSION file."
  exit 1
fi