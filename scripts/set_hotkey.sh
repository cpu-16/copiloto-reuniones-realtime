#!/usr/bin/env bash
# Registra un atajo GLOBAL de GNOME para mostrar/ocultar el asistente.
# El atajo hace curl al endpoint /toggle del asistente (debe estar corriendo).
# Uso:  bash scripts/set_hotkey.sh "<Super>a"      (por defecto <Super>a)
# Quitar:  gsettings reset-recursively org.gnome.settings-daemon.plugins.media-keys
# Requiere GNOME.
set -euo pipefail

KEYBIND="${1:-<Super>a}"
cd "$(dirname "$0")/.."

PORT=$(grep -E '^\s*port' config.toml | head -1 | grep -oE '[0-9]+' || echo 8765)
TOKEN=$(grep -E '^\s*token' config.toml | head -1 | sed -E 's/.*=[[:space:]]*"?([^"]*)"?.*/\1/')
CMD="bash -c 'curl -s \"http://127.0.0.1:${PORT}/toggle?token=${TOKEN}\" >/dev/null'"

SCHEMA="org.gnome.settings-daemon.plugins.media-keys"
SLOT="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/asistente/"

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

gsettings set "${SCHEMA}.custom-keybinding:${SLOT}" name "Asistente toggle"
gsettings set "${SCHEMA}.custom-keybinding:${SLOT}" command "${CMD}"
gsettings set "${SCHEMA}.custom-keybinding:${SLOT}" binding "${KEYBIND}"

echo "✅ Atajo ${KEYBIND} -> mostrar/ocultar el asistente."
echo "   (el asistente debe estar corriendo; usa el token de config.toml)"
