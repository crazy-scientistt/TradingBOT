FROM nousresearch/hermes-agent:latest

WORKDIR /app

# Railway and local compose both use this directory as the build context.
COPY config.yaml /app/config.yaml
COPY SOUL.md /app/SOUL.md
COPY healthcheck.sh /app/healthcheck.sh
COPY skills /app/skills

RUN chmod +x /app/healthcheck.sh

EXPOSE 8642

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=8 \
    CMD /app/healthcheck.sh

CMD ["gateway", "run"]
