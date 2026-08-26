FROM oven/bun:1.2-alpine

WORKDIR /app

COPY package.json ./
RUN bun install

EXPOSE 10100

USER bun

ENTRYPOINT ["bun", "x", "opencodex", "--port", "10100"]
