
# Deprecated


#!/bin/bash
current_path=$(pwd)
cd "$(dirname "$current_path")/pipelines"

PORT="${PORT:-42802}"
uvicorn main:app --port $PORT --host 0.0.0.0 --forwarded-allow-ips '*'