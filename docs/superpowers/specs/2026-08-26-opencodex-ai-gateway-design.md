# GoldGuard OpenCodex AI Gateway Design

**Date:** 2026-08-26
**Status:** Approved architecture; implementation pending written-spec review
**Dependency:** `@bitkyc08/opencodex` 2.26.0, MIT License

## 1. Decision Summary

GoldGuard will use OpenCodex as its universal model gateway instead of rebuilding provider-specific transports in Python. OpenCodex will own provider configuration, custom OpenAI-compatible endpoints, upstream credentials, live model discovery, protocol translation, request routing, and optional web-search mediation.

GoldGuard remains the only authority for market facts, evidence freshness, strategy candidates, deterministic risk, paper/live execution, durable state, idempotency, audit, and fail-closed trading decisions. Neither OpenCodex nor any model may size a position, widen a stop, activate a strategy, mutate trading settings, or call a broker directly.

## 2. Scope

This design adds:

- an isolated, version-pinned OpenCodex gateway service;
- Gemini, OpenRouter, Google Antigravity, and custom OpenAI-compatible provider support;
- server-side provider and API-key management;
- live provider/model discovery and a searchable model browser;
- separate provider/model selection for trade decisions, context/news, and Hermes;
- an optional "use the same route everywhere" convenience setting;
- unified search evidence from native Gemini grounding, OpenRouter web search, or the local OpenCodex search sidecar;
- provider health, quota, model capability, cost metadata, and connection tests;
- local/Railway isolation and explicit production eligibility rules.

This design does not add subscription billing, customer tenancy, strategy marketplaces, or autonomous live activation.

## 3. Architecture

```text
GoldGuard dashboard
    -> authenticated GoldGuard API
        -> Provider Administration Service
            -> OpenCodex management API (private, admin token)
        -> AI Gateway Client
            -> OpenCodex data plane (private, dedicated token)
                -> Gemini API
                -> OpenRouter
                -> custom OpenAI-compatible provider
                -> local-only Antigravity OAuth provider
        -> Context Search Service
            -> native Gemini Google Search grounding, or
            -> OpenRouter web search, or
            -> local OpenCodex search sidecar
        -> deterministic strategy/checklist/risk/coordinator
        -> paper broker or separately armed Binance Spot broker
        -> SQLite ledger and audit

Hermes research service
    -> OpenCodex data plane with a separate restricted client token
    -> proposal-only GoldGuard bridge
```

OpenCodex runs as a sidecar/service, not as copied modules inside the Python application. Its Bun-native TypeScript source, provider registry, adapters, OAuth flows, model discovery, request translation, and key-pool behavior remain owned by the pinned upstream package.

If GoldGuard must modify or vendor a substantial OpenCodex source portion, the MIT copyright and license notice must ship with the distribution. Vendoring is a fallback only when a required stable service interface is unavailable.

## 4. OpenCodex Service Boundary

GoldGuard uses two separate OpenCodex credentials:

1. A data-plane token permits only model listing and inference endpoints such as `/v1/models`, `/v1/chat/completions`, and `/v1/responses`.
2. A management token permits provider/model administration. It is available only to the GoldGuard backend over loopback or Railway private networking.

The browser never receives either token and never calls OpenCodex directly.

GoldGuard will initially use these management capabilities:

- list provider presets and configured providers;
- add, edit, disable, test, and remove a provider;
- add/rotate/remove provider API keys through the dedicated key endpoints;
- list all discovered models;
- configure the selected model allowlist;
- inspect sanitized provider health, discovery status, quota, and cost metadata.

Management responses must remain redacted. API-key values, OAuth tokens, custom headers, and upstream error bodies must never be returned to the browser, GoldGuard audit text, or logs.

## 5. Isolation

GoldGuard must never reuse the operator's desktop OpenCodex home directory or Codex/ChatGPT account pool.

Local development uses a dedicated project-owned OpenCodex home, for example `./data/opencodex`, with its own data-plane and management tokens. Railway uses a separate persistent volume and sets `OPENCODEX_HOME=/data/opencodex`.

The production gateway must not mount:

- the GoldGuard SQLite volume;
- the Hermes volume;
- source-repository credentials;
- Binance credentials;
- Railway credentials;
- the operator's desktop `.codex` or `.opencodex` directories.

OpenCodex receives AI-provider credentials only. GoldGuard receives gateway client tokens but not the upstream provider keys after initial submission.

## 6. Provider and Model Browser

The Settings screen will expose three independently versioned routes:

- **Trade decision route:** structured approve/reject/hold/exit filtering.
- **Context route:** cited current-news and macro evidence.
- **Hermes route:** research, reflection grouping, and proposal generation.

Each route has:

- provider selector;
- searchable live model selector;
- current availability and last successful probe;
- free/paid indicator where the provider supplies pricing metadata;
- context window;
- text/image capability;
- structured-output and tool/search capability;
- reasoning-effort options;
- estimated input/output price where known;
- local-only or production-capable badge;
- `Test connection` action;
- exact model pinning.

OpenRouter models are fetched from its live catalog through OpenCodex. The browser can filter free variants, but paid models remain selectable whenever the OpenRouter account has credits. `openrouter/free` is permitted for paper/research experiments but is not eligible for live trading because it randomly changes the responding model.

The UI provides a convenience toggle to use one provider/model for all three routes. Internally, the routes remain separate so context collection can retain a search-capable provider even when the decision model changes.

## 7. Credential Management

Credentials supported by the first release:

- Gemini API key;
- OpenRouter API key;
- custom OpenAI-compatible provider key and base URL;
- local Google Antigravity OAuth configured in the isolated OpenCodex instance;
- generated OpenCodex management/data-plane tokens;
- generated GoldGuard session and Hermes bridge secrets.

Provider-key submission requires authenticated admin access, CSRF protection, recent reauthentication, request throttling, and audit of safe metadata only. Audit records include provider name, action, actor, time, and success/failure but never the secret.

The API exposes only `configured`, `missing`, `invalid`, or `quota-limited` credential status. It never returns a stored key.

Production should prefer Railway sealed variables or environment references supported by OpenCodex. When a key must be stored in the isolated OpenCodex volume, filesystem permissions and volume access must be restricted to that service.

Any credential pasted into chat is treated as exposed and must be rotated before production deployment. No supplied credential is committed to Git.

## 8. Google Antigravity

The local OpenCodex provider can expose models discovered from the operator's Antigravity entitlement, including Gemini 3.7 Flash and other models made available by Google.

Antigravity is classified as **local experimental/paper-only** by default because:

- the entitlement is documented for the Antigravity product rather than as a general production API;
- availability and quota are subscription- and capacity-dependent;
- OAuth refresh credentials must not be copied from the desktop runtime to Railway;
- upstream model availability can change without API-style stability guarantees.

GoldGuard may use Antigravity locally through the isolated proxy when the operator explicitly configures it. The provider is not eligible for live trading or Railway until a supported production authorization method and deployment terms are independently verified.

## 9. Web Search and Context Evidence

Model inference and evidence search are separate capabilities.

Supported search backends:

1. **Native Gemini grounding:** deployable and preferred when a Gemini API key and supported billing tier are available.
2. **OpenRouter web search:** deployable when the selected route supports search and the account has sufficient credits.
3. **OpenCodex search sidecar:** local experimental option using its separately configured hosted-search credential/quota.
4. **Disabled:** deterministic strategy continues, but entry candidates are rejected when the active policy requires current context.

Every backend must produce one canonical `ContextEvidence` contract containing:

- retrieval time and provider/model identity;
- query set;
- source URL and title;
- publication/event time when available;
- cited factual summary;
- driver, direction, severity, and contradiction flags;
- raw-provider request identifier and bounded cost/quota metadata;
- prompt-injection suspicion.

The Professional Checklist rejects entry on missing citations, stale evidence, contradictory material facts, invalid timestamps, prompt injection, quota failure, or provider failure. Search and AI failures never delay stop-loss, target, emergency, reconciliation, or risk-reducing exits.

## 10. Decision Runtime

For each entry candidate:

1. Build verified market features from closed candles and a fresh quote.
2. Run deterministic strategy gates.
3. Collect or retrieve fresh cited context through the selected context backend.
4. Run the Professional Checklist.
5. Send the bounded decision request through the selected OpenCodex provider/model route.
6. Validate the response against the strict GoldGuard schema and known reason codes.
7. Reject model/provider incompatibility, low confidence, malformed output, quota errors, and unknown reason codes.
8. Calculate quantity, stop, target, exchange rounding, fees, and risk in deterministic Python.
9. Persist intent and idempotency before any order-capable call.
10. Execute through the paper broker or separately armed live broker.
11. Persist exact provider/model, effective upstream model, prompt hash, evidence, latency, usage, cost, and result.

The model may approve or reject an existing candidate and recommend a risk-reducing exit. It cannot invent an entry, calculate size, increase risk, cancel protection, mutate configuration, or call a broker.

## 11. Failover and Reproducibility

No silent provider/model fallback is allowed for a trade decision.

The operator may configure an explicit ordered fallback policy for paper/research use. Every attempt and the actual responding provider/model must be recorded. Live mode requires an exact pinned production-capable route; a failed route rejects the entry.

Provider removal, model removal, invalid credentials, exhausted quota, 401/403, 429, timeout, malformed model discovery, capability mismatch, or gateway unavailability causes a visible degraded state and blocks new entries.

Open positions remain protected by deterministic monitoring and exits without AI.

## 12. Local and Railway Topology

### Local

- GoldGuard application;
- isolated OpenCodex gateway with project-owned home directory;
- Hermes service;
- separate persistent directories;
- optional Antigravity and OpenCodex search sidecar;
- paper mode by default.

### Railway

- service 1: GoldGuard API and bundled dashboard, one replica, `/data` volume;
- service 2: OpenCodex gateway, one replica, private only, `/data/opencodex` volume;
- service 3: Hermes, one replica, private only, `/opt/data` volume;
- separate health/readiness checks and secrets;
- provider keys entered as Railway variables or restricted gateway secrets;
- no consumer ChatGPT or Antigravity OAuth credentials by default;
- GitHub deployment waits for CI.

## 13. Security Requirements

- Pin OpenCodex to an exact reviewed version and record its license.
- Run the gateway as non-root with a read-only filesystem except its volume.
- Require authentication whenever the gateway is reachable beyond loopback.
- Keep management and data-plane tokens separate.
- Restrict the gateway to private service networking in Railway.
- Never expose the management API to the public internet.
- Validate custom provider base URLs and reject unsafe destinations by default.
- Bound catalog response bytes, model counts, provider error bodies, request timeouts, and retries.
- Redact API keys, OAuth tokens, authorization headers, custom headers, prompts containing secrets, and upstream error bodies.
- Do not allow provider/model configuration changes while live mode is armed.
- Configuration change disarms live mode and requires a fresh preflight.
- Never send Binance credentials, account balances, or unrestricted database content to OpenCodex or a model.

## 14. Testing

Required automated coverage:

- provider/model DTOs and capability filtering;
- provider toggle and independent route selection;
- add/test/rotate/remove key flows with redaction assertions;
- Gemini, OpenRouter, custom OpenAI-compatible, and fake Antigravity routes;
- live model discovery bounds, invalid shapes, duplicate IDs, and stale-cache behavior;
- free/paid filters and exact model pinning;
- structured decision compatibility and fail-closed errors;
- canonical context evidence and citation validation across search backends;
- gateway unavailable, 401/403, 429, timeout, malformed stream, and quota exhaustion;
- deterministic exits while every AI/search service is offline;
- local-only provider rejection in Railway/live mode;
- restart and configuration-change disarm;
- secret scan over source, fixtures, logs, API responses, exports, and frontend assets;
- Docker/Compose and Railway private-network health checks.

Automated tests use fake upstream servers and synthetic credentials. They never call production Binance or spend a real provider key.

## 15. Implementation Sequence

1. Add OpenCodex license attribution, pinned dependency, isolated service packaging, health checks, and local Compose topology.
2. Define GoldGuard provider, model, capability, route, and context-evidence contracts.
3. Implement authenticated OpenCodex data-plane and management clients with redaction and bounded responses.
4. Add provider/model repositories and versioned route settings.
5. Expose GoldGuard administration APIs for providers, keys, model catalogs, tests, and route selection.
6. Build the Settings model browser, filters, provider toggle, status, and connection-test UI.
7. Implement Gemini, OpenRouter, and OpenCodex-sidecar context search behind the canonical evidence contract.
8. Route the bounded trade decision and Hermes through OpenCodex.
9. Connect the durable coordinator, audit, recovery, and fail-closed state transitions.
10. Add security, integration, browser, Docker, and deployment verification.
11. Deploy the paper-only Railway topology and validate health, persistence, model discovery, and cited context.
12. Run the two-year replay and seven-day frozen paper-forward protocol before considering any live connector activation.

## 16. Acceptance Criteria

- An admin can add Gemini, OpenRouter, or a custom OpenAI-compatible provider without editing code.
- No provider key is returned by any API or browser route.
- The model browser lists live provider models and displays capabilities/status safely.
- Paid OpenRouter models work when the account has credits; free models remain selectable for paper/research.
- The user can independently select decision, context, and Hermes routes or use one route everywhere.
- Local Antigravity models appear only when the isolated local gateway has a valid login.
- Local-only providers cannot arm live mode or satisfy Railway production preflight.
- Cited context is refreshed and validated before every eligible entry.
- AI/search/provider failure blocks new entries and never blocks deterministic exits.
- Every decision records the requested and actual provider/model plus evidence, prompt hash, latency, usage, and cost metadata.
- OpenCodex, GoldGuard, Hermes, and their persistent volumes remain isolated.
- Backend, frontend, integration, security, Docker, and Railway checks pass with no real credentials in Git.

## 17. Explicit Limitations

- Provider access does not prove model quality, trading profitability, or legal availability in every region.
- Consumer subscriptions are not treated as production APIs unless the provider explicitly supports that deployment use.
- Free and routed models can disappear, throttle, or change behavior.
- Web search can be late, incomplete, contradictory, or wrong; it is evidence, not authority.
- No model or gateway may override deterministic risk or execution safety.
- Railway deployment remains paper-only until the separate live connector, preflight, and arming acceptance criteria are complete.
