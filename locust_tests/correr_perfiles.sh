#!/usr/bin/env bash
# locust_tests/correr_perfiles.sh
# Corre los seis perfiles en orden y deja las evidencias en evidencias/:
#   <perfil>_stats.csv, _failures.csv, _stats_history.csv, _exceptions.csv
#   <perfil>.html  (reporte con graficas)
#   <perfil>.log   (consola, con el veredicto del umbral)
# No se pasa --host: cada clase de usuario trae el suyo.
set -u
cd "$(dirname "$0")"
mkdir -p evidencias
PERFILES="${@:-smoke load stress spike soak quiebre}"
for PERFIL in $PERFILES; do
  echo "=============== $PERFIL  ($(date +%H:%M:%S)) ==============="
  PERFIL="$PERFIL" locust --headless \
      --csv "evidencias/${PERFIL}" \
      --html "evidencias/${PERFIL}.html" \
      2>&1 | tee "evidencias/${PERFIL}.log" | tail -4
done
echo "=============== terminado $(date +%H:%M:%S) ==============="
