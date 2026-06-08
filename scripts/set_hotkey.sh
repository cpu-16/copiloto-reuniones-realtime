#!/usr/bin/env bash
# Registra un atajo GLOBAL de GNOME que hace curl a un endpoint del asistente.
# Acciones:
#   toggle -> mostrar/ocultar la ventana        (endpoint /toggle)
#   ghost  -> modo fantasma (click-through)      (endpoint /ghost)
# Uso:
#   bash scripts/set_hotkey.sh "<Super>a"            # toggle (por defecto)
#   bash scripts/set_hotkey.sh "<Super>g" ghost      # modo fantasma
# Quitar todos:  gsettings reset-recursively org.gnome.settings-daemon.plugins.media-keys
# Requiere GNOME (el asistente debe estar corriendo).
set -euo pipefail

KEYBIND="${1:-<Super>a}"
ACTION="${2:-toggle}"
cd "$(dirname "$0")/.."

case "$ACTION" in
  toggle|ghost) ;;
  *) echo "Acción inválida: $ACTION (usa: toggle | ghost)"; exit 1 ;;
esac

PORT=$(grep -E '^\s*port' config.toml | head -1 | grep -oE '[0-9]+' || echo 8765)
TOKEN=$(grep -E '^\s*token' config.toml | head -1 | sed -E 's/.*=[[:space:]]*"?([^"]*)"?.*/\1/')
CMD="bash -c 'curl -s \"http://127.0.0.1:${PORT}/${ACTION}?token=${TOKEN}\" >/dev/null'"

SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
SLOT="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/asistente-${ACTION}/"

# Agrega el slot a la lista sin borrar tus otros atajos.
python3 - "$SLOT" <<'PY'
import ast, subprocess, sys
slot = sys.argv[1]
cur = subprocess.check_output(
    ['gsettings', 'get', 'org.gnome.settings-daemon.plugins.media-keys',
     'custom-keybindings']).decode().strip()
lst = [] if cur in ('@as []', '[]') else ast.literal_eval(cur)
if slot not in lst:
    lst.append(slot)
subprocess.run(['gsettings', 'set', 'org.gnome.settings-daemon.plugins.media-keys',
                'custom-keybindings', str(lst)], check=True)
PY

gsettings set "${SCHEMA}.custom-keybinding:${SLOT}" name "Asistente ${ACTION}"
gsettings set "${SCHEMA}.custom-keybinding:${SLOT}" command "${CMD}"
gsettings set "${SCHEMA}.custom-keybinding:${SLOT}" binding "${KEYBIND}"

echo "✅ Atajo ${KEYBIND} -> ${ACTION} del asistente."
echo "   (el asistente debe estar corriendo; usa el token de config.toml)"
