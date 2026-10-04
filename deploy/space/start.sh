#!/bin/sh
# One public port (7860, the dashboard). The API stays private on localhost inside the container.
set -eu

uvicorn services.api.main:create_app --factory --host 127.0.0.1 --port 8010 &

i=0
until python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health')" 2>/dev/null; do
    i=$((i + 1))
    if [ "$i" -ge 60 ]; then
        echo "API did not become healthy in 60s" >&2
        exit 1
    fi
    sleep 1
done

export API_URL=http://127.0.0.1:8010
exec streamlit run services/dashboard/app.py \
    --server.address 0.0.0.0 --server.port 7860 --server.headless true \
    --server.enableCORS false --server.enableXsrfProtection false \
    --browser.gatherUsageStats false
