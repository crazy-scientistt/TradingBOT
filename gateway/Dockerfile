FROM oven/bun:1.2-alpine

WORKDIR /app

COPY package.json ./
RUN bun install

COPY start.sh config.example.json ./
RUN chmod +x start.sh \
  && mkdir -p /app/.opencodex

# Root on Railway so a mounted volume at /app/.opencodex is writable.
ENV HOME=/app
ENV OPENCODEX_HOME=/app/.opencodex
ENV PORT=10100
ENV CI=1

EXPOSE 10100

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=8 \
  CMD bun -e 'fetch("http://127.0.0.1:"+(process.env.PORT||"10100")+"/healthz").then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))'

ENTRYPOINT ["/app/start.sh"]
