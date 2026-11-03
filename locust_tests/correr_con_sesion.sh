#!/usr/bin/env zsh
# locust_tests/correr_con_sesion.sh
#
# Repite smoke, load y stress CON sesion iniciada en el monolito, que es
# lo unico que convierte el par comparable (catalogo del monolito contra
# catalogo de books) en una medicion de verdad: sin sesion, /library/catalog
# responde 302 y se mide una redireccion, no una consulta con su plantilla.
#
# La contrasena se pide por pantalla, NO se escribe en ningun archivo, NO
# aparece en el historial del shell y se borra del entorno al terminar.
#
# Ojo con el shell: en zsh `read -p` significa "leer del coproceso", no
# "mostrar este prompt" -- es un idiom de bash. La forma de zsh es
# `read -s "VAR?prompt"`. Confundirlas deja la variable vacia y la corrida
# sale "sin credenciales" sin avisar de nada.
set -u
cd "${0:A:h}"

: ${MONO_EMAIL:=jagnt545@gmail.com}
export MONO_EMAIL
read -s "MONO_PASSWORD?Password de ${MONO_EMAIL} en el monolito: "
echo
if [[ -z "${MONO_PASSWORD}" ]]; then
  echo "No se leyo ninguna contrasena. Se aborta en vez de correr 7 minutos"
  echo "midiendo redirecciones."
  exit 1
fi
export MONO_PASSWORD

# ---------------------------------------------------------------------
# COMPROBACION PREVIA: ¿sirven estas credenciales?
#
# Este monolito responde 302 TANTO si el login funciona como si no. Lo
# que los distingue es el destino: /library/catalog cuando entra, y
# /library/auth/login cuando rechaza. Comprobarlo aqui cuesta medio
# segundo y evita descubrirlo despues de siete minutos de corrida, que
# es como se descubrio la primera vez.
# ---------------------------------------------------------------------
VM_IP="${VM_IP:-34.51.89.203}"
destino=$(curl -s -o /dev/null -D - --max-time 10 \
    -X POST "http://${VM_IP}:3000/library/auth/login" \
    --data-urlencode "email=${MONO_EMAIL}" \
    --data-urlencode "password=${MONO_PASSWORD}" \
    | tr -d '\r' | awk 'tolower($1)=="location:"{print $2}')

case "$destino" in
  "")              echo "El monolito no respondio con una redireccion. ¿Esta en pie :3000?"; exit 1 ;;
  */auth/login)    echo "CREDENCIALES RECHAZADAS: el monolito redirige a ${destino}."
                   echo "Sin sesion el catalogo responde 302 y el par comparable no se mide."
                   echo "Se aborta en vez de gastar siete minutos."; exit 1 ;;
  *)               echo "Credenciales correctas (el login redirige a ${destino}). Adelante." ;;
esac
echo

export RONDA="${RONDA:-$(date +%F)}"
export LOCUST="${LOCUST:-$HOME/anaconda3/bin/locust}"

./correr_perfiles.sh "${@:-smoke load stress}"
estado=$?

unset MONO_PASSWORD
echo
echo "--- comprobacion: en que modo corrio cada perfil ---"
grep -ah "monolito: " "evidencias/${RONDA}"/*.log | sort -u
exit $estado
