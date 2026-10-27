# Substack article snippets

---

## 1. `products.json` — before & after (FT-04 fixture)

**Before (single-SKU fixture)**

```json
{
  "sku": "TWIRL-8PK",
  "container_id": "FT-04",
  "expected": 8,
  "worked": 4,
  "backstock": 4
}
```

**After (array-based `inventory_lines`)**

```json
{
  "container_id": "FT-04",
  "zone": "Aisle 9",
  "inventory_lines": [
    {
      "sku": "ORANGE-SODA-8PK",
      "expected": 8,
      "worked": 6,
      "backstock": 0
    },
    {
      "sku": "TWIRL-8PK",
      "expected": 8,
      "worked": 4,
      "backstock": 4
    }
  ]
}
```

---

## 2. `docker-compose.yml` — ports & volume mounts

```yaml
version: '3.8'
services:
  backend:
    build: .
    ports:
      - "8000:8000"
    environment:
      - WIP_API_KEY=dev-wip-engine-key
      - WIP_PRODUCTS_PATH=/app/data/products.json
    volumes:
      - ./data/products.json:/app/data/products.json:ro
    command: uvicorn main:app --host 0.0.0.0 --port 8000
  frontend:
    build: .
    ports:
      - "8501:8501"
    environment:
      - API_BASE_URL=http://172.18.0.1:8000/api/v1
      - WIP_API_KEY=dev-wip-engine-key
    command: streamlit run dashboard.py --server.address=0.0.0.0 --server.port=8501
    depends_on:
      - backend
```

---

## 3. Backend — locked random seed (`services/engine.py`)

```python
        self._rng = random.Random(FIXED_SIMULATION_RANDOM_SEED)
```
