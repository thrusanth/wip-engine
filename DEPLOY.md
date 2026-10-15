# Deploy WIP Engine to Azure Container Apps

Target subscription and resource group (hard limits):

- Subscription: `45c900ea-090a-4bc6-9384-01c9b3174788`
- Resource group: `thrusanth-rg` (UK South)
- Do **not** use `az containerapp up` (it may create its own resource group).

One Docker image serves both roles via `APP_ROLE` (`backend` | `dashboard`) and `./start.sh`.

## Prerequisites

- Azure CLI logged in: `az account set --subscription 45c900ea-090a-4bc6-9384-01c9b3174788`
- Container Apps extension: `az extension add --name containerapp` (if needed)
- Git repo at the project root

Generate production secrets locally (do **not** commit these):

```bash
export WIP_API_KEY="$(openssl rand -hex 24)"
export BOUNCER_EDGE_TOKEN="$(openssl rand -hex 24)"
```

## 1. Local smoke test

```bash
docker compose up --build
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8501/
```

Ensure `start.sh` is executable on the host if you bind-mount the repo into the dashboard service (`chmod +x start.sh`).

## 2. Azure Container Registry (Basic)

Pick a globally unique lowercase name, e.g. `wipengine4821`:

```bash
az acr create -g thrusanth-rg -n wipengine4821 --sku Basic --location uksouth
```

## 3. Build and push image

```bash
TAG="$(git rev-parse --short HEAD)"
az acr build -g thrusanth-rg -r wipengine4821 -t "wip-engine:${TAG}" .
```

If `az acr build` fails with tasks or permission errors:

```bash
docker buildx build --platform linux/amd64 -t "wipengine4821.azurecr.io/wip-engine:${TAG}" --load .
az acr login -g thrusanth-rg -n wipengine4821
docker push "wipengine4821.azurecr.io/wip-engine:${TAG}"
```

## 4. Container Apps environment

Creates a Log Analytics workspace in `thrusanth-rg` automatically if you omit one:

```bash
az containerapp env create -g thrusanth-rg -n wip-env -l uksouth
```

Note the environment default domain from the output (example: `jollyglacier-64da93d8.uksouth.azurecontainerapps.io`).

## 5. Backend app (`wip-backend`)

Exactly **one** replica (in-memory state + in-process simulator). No Azure Files mounts (SQLite WAL).

```bash
TAG="$(git rev-parse --short HEAD)"

az containerapp create -g thrusanth-rg -n wip-backend \
  --environment wip-env \
  --image "wipengine4821.azurecr.io/wip-engine:${TAG}" \
  --registry-server wipengine4821.azurecr.io \
  --registry-identity system \
  --system-assigned \
  --ingress external --target-port 8000 \
  --min-replicas 1 --max-replicas 1 \
  --cpu 0.25 --memory 0.5Gi \
  --secrets wip-api-key="${WIP_API_KEY}" bouncer-edge-token="${BOUNCER_EDGE_TOKEN}" \
  --env-vars \
    APP_ROLE=backend \
    WIP_API_KEY=secretref:wip-api-key \
    BOUNCER_EDGE_TOKEN=secretref:bouncer-edge-token \
    WIP_PRODUCTS_PATH=/app/data/products.json \
    BOUNCER_BUFFER_PATH=/app/data/bouncer_audit.db
```

The CLI assigns **AcrPull** on the registry to the app’s system-assigned identity when using `--registry-identity system`.

Backend URL:

```bash
az containerapp show -g thrusanth-rg -n wip-backend --query properties.configuration.ingress.fqdn -o tsv
```

## 6. Dashboard app (`wip-dashboard`)

```bash
BACKEND_FQDN="$(az containerapp show -g thrusanth-rg -n wip-backend --query properties.configuration.ingress.fqdn -o tsv)"

az containerapp create -g thrusanth-rg -n wip-dashboard \
  --environment wip-env \
  --image "wipengine4821.azurecr.io/wip-engine:${TAG}" \
  --registry-server wipengine4821.azurecr.io \
  --registry-identity system \
  --system-assigned \
  --ingress external --target-port 8501 \
  --min-replicas 1 --max-replicas 1 \
  --cpu 0.25 --memory 0.5Gi \
  --secrets wip-api-key="${WIP_API_KEY}" \
  --env-vars \
    APP_ROLE=dashboard \
    API_BASE_URL="https://${BACKEND_FQDN}/api/v1" \
    WIP_API_KEY=secretref:wip-api-key
```

If the Streamlit UI is blank or WebSockets fail behind ingress, patch `start.sh` dashboard branch to add:

`--server.enableCORS=false --server.enableXsrfProtection=false`

Then rebuild and redeploy.

## 7. Verify

```bash
BACKEND_FQDN="$(az containerapp show -g thrusanth-rg -n wip-backend --query properties.configuration.ingress.fqdn -o tsv)"
DASHBOARD_FQDN="$(az containerapp show -g thrusanth-rg -n wip-dashboard --query properties.configuration.ingress.fqdn -o tsv)"

curl -s -o /dev/null -w "backend /: %{http_code}\n" "https://${BACKEND_FQDN}/"
curl -s -o /dev/null -w "backend /docs: %{http_code}\n" "https://${BACKEND_FQDN}/docs"
curl -s -o /dev/null -w "dashboard /: %{http_code}\n" "https://${DASHBOARD_FQDN}/"

BOUNCER_CV_WEBHOOK_URL="https://${BACKEND_FQDN}/api/v1/bouncer/cv-detection" \
BOUNCER_EDGE_TOKEN="${BOUNCER_EDGE_TOKEN}" \
python3 tests/simulate_cv_traffic.py
```

Open `https://${DASHBOARD_FQDN}/` in a browser.

## 8. Redeploy (new image tag)

```bash
chmod +x deploy.sh
./deploy.sh
```

Or manually:

```bash
TAG="$(git rev-parse --short HEAD)"
az acr build -g thrusanth-rg -r wipengine4821 -t "wip-engine:${TAG}" .
az containerapp update -g thrusanth-rg -n wip-backend --image "wipengine4821.azurecr.io/wip-engine:${TAG}"
az containerapp update -g thrusanth-rg -n wip-dashboard --image "wipengine4821.azurecr.io/wip-engine:${TAG}"
```

## Live deployment (reference)

| Resource | Name |
|----------|------|
| ACR | `wipengine4821` |
| Container Apps environment | `wip-env` |
| Log Analytics workspace | `workspace-thrusanthrgCgJ1` |
| Backend app | `wip-backend` |
| Dashboard app | `wip-dashboard` |
| Image tag (initial) | `d8ae372` |

URLs:

- Backend: https://wip-backend.jollyglacier-64da93d8.uksouth.azurecontainerapps.io/
- Dashboard: https://wip-dashboard.jollyglacier-64da93d8.uksouth.azurecontainerapps.io/

Container App secrets hold `WIP_API_KEY` and `BOUNCER_EDGE_TOKEN` (not stored in git). Retrieve only from Azure Portal / CLI if you need to rotate them:

```bash
az containerapp secret list -g thrusanth-rg -n wip-backend -o table
```
