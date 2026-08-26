# OpenCodex Gateway for GoldGuard

OpenCodex (@bitkyc08/opencodex@2.26.0) acts as the unified, isolated AI provider hub for GoldGuard.

## Features
- OpenAI-compatible API (`/v1/chat/completions`, `/v1/models`, `/healthz`)
- Provider routing: Gemini, Antigravity, OpenRouter, Anthropic, OpenAI
- Live model auto-discovery via `GET /v1/models`
- Key isolation: upstream keys stay inside gateway memory/volume and never leak to core logs
