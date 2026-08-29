FROM nousresearch/hermes-agent:latest

WORKDIR /app
COPY hermes/config.yaml /app/config.yaml
COPY hermes/SOUL.md /app/SOUL.md
COPY hermes/healthcheck.sh /app/healthcheck.sh

RUN chmod +x /app/healthcheck.sh

CMD ["gateway", "run"]

