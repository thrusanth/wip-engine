#!/bin/sh
set -e

case "${APP_ROLE:-backend}" in
  backend)
    exec uvicorn main:app --host 0.0.0.0 --port 8000
    ;;
  dashboard)
    exec streamlit run dashboard.py \
      --server.address=0.0.0.0 \
      --server.port=8501
    ;;
  *)
    echo "Unknown APP_ROLE: ${APP_ROLE}. Use backend or dashboard." >&2
    exit 1
    ;;
esac
