# Search Provider Architecture

Date: 2026-04-02

## Purpose

This document defines the target search-provider architecture for Nova as the runtime core of NYO System.

It describes:

- provider roles
- routing expectations
- self-repair and fallback behavior
- command-center controls
- the boundary between current implementation and target design

Nova should not treat all network retrieval as one undifferentiated search function. It should expose a provider stack with explicit roles so web retrieval, knowledge lookup, troubleshooting lookup, and code search remain inspectable and governable.

## Design Goals

The provider stack should satisfy these constraints:

1. keep the broad web layer replaceable without changing Nova's higher-level routing contract
2. prefer structured sources when the user intent is clearly factual, technical, or code-oriented
3. keep operator control explicit through policy and the command center
4. degrade safely when providers fail instead of collapsing immediately into silent generic fallback
5. preserve route and provider observability in status, ledger, and operator surfaces
6. allow local self-repair for operator-managed providers such as SearXNG

## Provider Roles

### 1. SearXNG

Role:

- primary broad web broker
- default provider for general search and open web research
- local, operator-managed provider with self-repair and command-center controls

Responsibilities:

- aggregate broad web results
- respect operator-configured endpoint and availability state
- serve as the first stop for open-ended web retrieval when no more specific provider clearly fits

Current Nova state:

- implemented as a direct provider
- command-center provider and endpoint controls exist
- local endpoint probing and self-repair now exist for common localhost drift

### 2. Wikipedia API

Role:

- structured knowledge provider
- preferred for encyclopedia-style fact lookup, background summaries, people, places, and topic overviews

Responsibilities:

- return concise, high-confidence summaries
- reduce dependence on broad search for well-covered factual topics
- preserve source clarity when the answer is encyclopedia-derived rather than search-derived

Target Nova behavior:

- route fact and overview prompts here before broad search when the user is clearly asking for background knowledge rather than fresh web results

### 3. StackExchange API

Role:

- structured troubleshooting and implementation provider
- preferred for programming errors, developer Q&A, operations diagnostics, and technical how-to searches

Responsibilities:

- return accepted or high-signal answers when the turn is clearly troubleshooting-oriented
- reduce noisy general-web search for developer debugging prompts

Target Nova behavior:

- route technical question and debugging requests here before or alongside broad web search when the request looks like a Q&A retrieval problem rather than a generic research task

### 4. Whoogle

Role:

- optional fallback provider
- secondary broad-search escape hatch when SearXNG is degraded, misconfigured, or operator-disabled

Responsibilities:

- provide an additional operator-managed web-search path
- remain optional and off by default unless the operator explicitly enables it

Architectural rule:

- Whoogle should not be a core dependency if SearXNG is already the primary broker. It is a fallback and resilience tool, not the main search identity for Nova.

### 5. HTML Fallback

Role:

- legacy low-contract fallback path
- emergency-only retrieval lane when richer providers are unavailable

Responsibilities:

- keep Nova from losing all search capability when configured providers are absent
- remain visibly second-class in routing and diagnostics

Architectural rule:

- Nova should keep this path for resilience, but it should not be the preferred outcome when a structured or operator-managed provider is available.

### 6. Brave

Role:

- direct hosted-provider alternative to SearXNG
- useful when the operator wants a simple API-backed web provider instead of a local broker

Responsibilities:

- provide direct web search when the operator selects it
- rely on operator-provided API credentials

Current Nova state:

- direct provider support exists in the runtime and command-center provider selection

## Target Routing Model

Nova should separate search into provider families instead of sending everything to one tool.

### Routing Classes

1. broad web search
2. structured knowledge lookup
3. structured troubleshooting lookup
4. deep multi-source web research

### Intended Mapping

| Turn shape | Preferred provider | Secondary provider | Notes |
| --- | --- | --- | --- |
| general web lookup | SearXNG | Brave, Whoogle, HTML fallback | broad search and recent web content |
| factual topic overview | Wikipedia API | SearXNG | use structured summary first |
| technical troubleshooting | StackExchange API | SearXNG | prefer accepted Q&A over noisy web search |
| repo or code discovery | SearXNG | StackExchange API, HTML fallback | broad research path for public code and repo discovery |
| deep research | SearXNG + web gather | provider-specific supplements | orchestration may mix providers |

### Routing Rule

The decision spine should answer two questions separately:

1. is this a search task at all?
2. if yes, which search family best fits the request?

That prevents one broad `web_search` route from becoming a catch-all for:

- encyclopedia lookup
- coding help
- open web research

## Provider Contract

Every provider should eventually implement a common internal contract.

Suggested provider result shape:

```text
provider_id
provider_family
query
normalized_query
result_kind
title
url
snippet
source_confidence
structured_fields
raw_payload_reference
```

This lets Nova unify:

- operator display
- ledger logging
- fallback decisions
- result ranking
- provider comparison

## Self-Repair And Fallback Policy

### SearXNG Self-Repair

Nova now supports local SearXNG endpoint recovery behavior.

Target self-repair contract:

1. try the configured endpoint first
2. if it is local and fails, probe known local alternatives
3. if a known local alternative succeeds repeatedly or is explicitly validated, persist the repaired endpoint
4. record the repair in policy audit and operator-visible status

This is appropriate only for local operator-managed endpoints such as localhost SearXNG. It should not silently rewrite remote hosted-provider endpoints.

### Fallback Precedence

Suggested fallback order for broad web retrieval:

1. configured broad-search primary provider
2. confirmed local self-repair candidate if allowed
3. optional secondary broad-search provider such as Whoogle
4. HTML fallback
5. explicit operator-visible failure

Suggested fallback order for structured providers:

1. matching structured provider
2. broad web broker if the structured provider is unavailable
3. explicit operator-visible failure if the request required that structure and broad search is too weak

## Command-Center Controls

The command center should own the operator-facing search governance surface.

### Required Controls

1. active provider selection
2. endpoint display and mutation for operator-managed providers
3. live provider probe result
4. self-repair result visibility
5. provider priority and fallback order
6. provider-specific enable or disable state
7. relevant credential-health state for hosted providers

### Required Status Signals

1. configured provider
2. configured endpoint
3. resolved endpoint if auto-detected
4. last successful provider probe
5. last self-repair event
6. last provider failure note
7. last provider selected for actual search traffic

## Current Implementation Versus Target Architecture

### Current

- `searxng` supported as a direct provider
- `html` fallback supported
- `brave` supported as a direct provider
- command center supports provider and endpoint control
- local SearXNG endpoint self-repair exists for common localhost drift

### Target Next

1. formal provider-family routing in the decision spine
2. native Wikipedia adapter
3. native StackExchange adapter
4. optional Whoogle adapter
5. provider-level ledger and telemetry fields
6. command-center visibility for provider health and fallback order

## Recommended Implementation Order

1. keep SearXNG as the default broad-search broker
2. finish operator-visible self-repair and failover controls
3. add Wikipedia as the first structured provider
4. add StackExchange as the structured troubleshooting provider
5. add provider-family routing rules before adding more backends
6. keep Whoogle optional until there is a proven resilience need

## Design Decision

Nova should be built around a provider architecture, not a single search box.

The recommended long-term stack is:

- SearXNG for broad web search
- Wikipedia API for structured knowledge
- StackExchange API for structured troubleshooting
- optional Whoogle for fallback broad search
- optional Brave as a direct hosted-provider alternative

That gives Nova three clearly separated search capabilities:

- web search
- knowledge lookup
- troubleshooting search

The architectural rule is simple:

Nova should route to the best provider family first, then degrade visibly and safely when a provider is unavailable.