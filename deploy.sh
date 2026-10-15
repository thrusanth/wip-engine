#!/usr/bin/env bash
set -euo pipefail

RESOURCE_GROUP="${RESOURCE_GROUP:-thrusanth-rg}"
ACR_NAME="${ACR_NAME:-wipengine4821}"
IMAGE_NAME="${IMAGE_NAME:-wip-engine}"
BACKEND_APP="${BACKEND_APP:-wip-backend}"
DASHBOARD_APP="${DASHBOARD_APP:-wip-dashboard}"

TAG="$(git rev-parse --short HEAD)"
FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${TAG}"

echo "Building and pushing ${FULL_IMAGE} ..."
if az acr build -g "${RESOURCE_GROUP}" -r "${ACR_NAME}" -t "${IMAGE_NAME}:${TAG}" .; then
  echo "ACR cloud build succeeded."
else
  echo "az acr build failed; falling back to local docker buildx (linux/amd64) ..."
  docker buildx build --platform linux/amd64 -t "${FULL_IMAGE}" --load .
  az acr login -g "${RESOURCE_GROUP}" -n "${ACR_NAME}"
  docker push "${FULL_IMAGE}"
fi

echo "Updating Container Apps to ${FULL_IMAGE} ..."
az containerapp update -g "${RESOURCE_GROUP}" -n "${BACKEND_APP}" --image "${FULL_IMAGE}"
az containerapp update -g "${RESOURCE_GROUP}" -n "${DASHBOARD_APP}" --image "${FULL_IMAGE}"

echo "Done. Backend and dashboard now run image tag ${TAG}."
