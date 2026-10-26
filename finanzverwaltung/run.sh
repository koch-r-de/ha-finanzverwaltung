#!/usr/bin/with-contenv bashio
# Startskript des Add-ons.
#
# /data ist bei Home-Assistant-Add-ons immer automatisch als
# persistentes Verzeichnis verfügbar (kein zusätzlicher 'map'-Eintrag
# in config.yaml nötig) - dort liegen finanzdaten.db und die Backups.
export FINANZAPP_DATENVERZEICHNIS=/data
export FINANZAPP_PORT=8099
# Befund Q (2.6.2): Herkunftsprüfung, Standard „protokoll“
if bashio::config.has_value 'herkunft_pruefen'; then
  export FINANZAPP_HERKUNFT_PRUEFEN="$(bashio::config 'herkunft_pruefen')"
else
  export FINANZAPP_HERKUNFT_PRUEFEN=protokoll
fi

cd /app
exec python3 run.py
