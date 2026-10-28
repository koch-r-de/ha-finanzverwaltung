# Explizites FROM statt build.yaml/BUILD_FROM - seit der Umstellung des
# Home-Assistant-Builders auf BuildKit (April 2026) wird kein Basis-Image
# mehr automatisch durchgereicht. Das Image ist multi-arch (amd64 und
# aarch64 werden vom selben Tag aufgelöst, armv7 seit v2.5 nicht mehr
# angeboten, weil ungetestet).
FROM ghcr.io/home-assistant/base-python:3.12-alpine3.22

WORKDIR /app

# Schrift für das PDF-Handbuch der Hilfe (seit v2.1): DejaVu enthält
# Umlaute, „…“ und Pfeile.
RUN apk add --no-cache font-dejavu

COPY requirements-docker.txt ./requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app ./app
COPY run.py ./run.py
COPY run.sh /
RUN chmod a+x /run.sh

LABEL \
  io.hass.version="3.0" \
  io.hass.type="addon" \
  io.hass.arch="amd64|aarch64"

ENV FINANZAPP_VERSION="3.0"
ENV FINANZAPP_VERSION_DATUM="2026-10-28"

CMD [ "/run.sh" ]
