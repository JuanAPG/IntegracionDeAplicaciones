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

export RONDA="${RONDA:-$(date +%F)}"
export LOCUST="${LOCUST:-$HOME/anaconda3/bin/locust}"

./correr_perfiles.sh "${@:-smoke load stress}"
estado=$?

unset MONO_PASSWORD
echo
echo "--- comprobacion: en que modo corrio cada perfil ---"
grep -ah "monolito: " "evidencias/${RONDA}"/*.log | sort -u
exit $estado
