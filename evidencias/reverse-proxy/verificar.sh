#!/usr/bin/env bash
# Integración local con respuestas simuladas, sin acceder a la VM.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
work=$(mktemp -d)
container="library-gateway-proof-$$"
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT
export NO_PROXY="${NO_PROXY:+$NO_PROXY,}127.0.0.1,localhost"
export no_proxy="$NO_PROXY"
python3 - "$root/docs/nginx/library.conf" "$work/mock.conf" <<'PY'
import sys
from pathlib import Path
s = Path(sys.argv[1]).read_text().replace('listen 80;', 'listen 8080;')
for port in (3000, 5000, 5001, 5002, 5003, 5004, 5005):
    s += f'''\nserver {{ listen 127.0.0.1:{port}; default_type application/json; location / {{ return 200 '{{"port":{port},"uri":"$request_uri","method":"$request_method"}}'; }} }}\n'''
Path(sys.argv[2]).write_text(s)
PY
docker run -d --rm --name "$container" -p 127.0.0.1:18081:8080 -v "$work/mock.conf:/etc/nginx/conf.d/default.conf:ro" nginx:stable-alpine >/dev/null
docker exec "$container" nginx -t
cd "$root"
python3 evidencias/reverse-proxy/prueba_gateway.py
node evidencias/reverse-proxy/prueba_gateway.js
mvn -q -f apps/JavaDesktop_app/pom.xml compile dependency:build-classpath -Dmdep.outputFile="$work/classpath.txt"
java -cp "apps/JavaDesktop_app/target/classes:$(cat "$work/classpath.txt")" evidencias/reverse-proxy/PruebaGateway.java
