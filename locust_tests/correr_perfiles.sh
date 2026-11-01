#!/usr/bin/env bash
# locust_tests/correr_perfiles.sh
# Corre los seis perfiles en orden y deja las evidencias en
# evidencias/<RONDA>/ (por omision, la fecha de hoy):
#   <perfil>_stats.csv, _failures.csv, _stats_history.csv, _exceptions.csv
#   <perfil>.html  (reporte con graficas)
#   <perfil>.log   (consola, con el veredicto del umbral)
#
# Cada tanda va en su propia carpeta a proposito: el despliegue de la VM
# cambio entre el 2026-10-30 y el 2026-11-01, y mezclar en el mismo sitio
# evidencias de dos contratos distintos invita a compararlas como si
# fueran lo mismo.
#
# No se pasa --host: cada clase de usuario trae el suyo.
#
#   ./correr_perfiles.sh                 # los seis, carpeta = hoy
#   RONDA=2026-11-01 ./correr_perfiles.sh quiebre
set -u
cd "$(dirname "$0")"
LOCUST="${LOCUST:-locust}"
RONDA="${RONDA:-$(date +%F)}"
DIR="evidencias/${RONDA}"
mkdir -p "$DIR"
PERFILES="${@:-smoke load stress spike soak quiebre}"
for PERFIL in $PERFILES; do
  echo "=============== $PERFIL  ($(date +%H:%M:%S)) ==============="
  PERFIL="$PERFIL" "$LOCUST" --headless \
      --csv "${DIR}/${PERFIL}" \
      --html "${DIR}/${PERFIL}.html" \
      2>&1 | tee "${DIR}/${PERFIL}.log" | tail -4
done
echo "=============== terminado $(date +%H:%M:%S) ==============="
