#!/usr/bin/with-contenv bashio
# Startskript des Add-ons.
#
# /data ist bei Home-Assistant-Add-ons immer automatisch als
# persistentes Verzeichnis verfügbar (kein zusätzlicher 'map'-Eintrag
# in config.yaml nötig) - dort liegen finanzdaten.db und die Backups.
export FINANZAPP_DATENVERZEICHNIS=/data
export FINANZAPP_PORT=8099

cd /app
exec python3 run.py
