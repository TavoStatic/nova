# Nova Tooling Roadmap

Date: 2026-03-15

This file is the centralized roadmap for Nova's current tool surface and the next tooling phases.

## Current Tool Surface

Nova already has working capability in these areas:

- web access on allowlisted domains
- file read and keyword search inside the allowed root
- screenshot and camera vision input
- speech-to-text and text-to-speech
- deterministic policy, memory, weather, and research flows
- HTTP chat UI and control room administration
- session-aware, privacy-safe browser and CLI chat

## Current Gaps

These areas are either thin, ad-hoc, or not yet operator-friendly:

- structured filesystem editing tools exposed to Nova itself
- terminal and shell task execution through a governed tool contract
- richer diagnostics and operator repair actions from the UI
- explicit workspace/project tooling awareness
- IDE-style integrations for code navigation and project operations
- stronger capability inventory beyond the minimal `capabilities.json`

## Recommended Build Order

### Phase 1: Safe Local Operator Tools

Focus on tools Nova can use locally with tight policy control.

- `files.list`: list allowed directories and files
- `files.read`: read text files with size limits
- `files.write_patch`: controlled text patch application for allowed files
- `files.search`: keyword and pattern search
- `process.run`: approved local commands with audit logging
- `logs.tail`: view runtime log slices

Outcome:

- Nova becomes materially more useful for local operator and coding workflows without broadening risk too quickly.

### Phase 2: Better Workspace and Code Tools

This is the practical bridge toward the “like this Visual Studio Code app” direction.

- project file map and language-aware file search
- symbol/index lookup for Python modules in the workspace
- test runner entry points for focused module execution
- diagnostics viewer for recent failures and runtime state
- code patch preview and approval flow exposed in the control room

Outcome:

- Nova becomes able to inspect, reason about, and act on local code/projects in a much more IDE-like way.

### Phase 3: Knowledge and Research Tool Upgrades

- structured local knowledge pack management UI
- stronger document ingestion workflow for curated project knowledge
- source pinning and result bookmarking for research sessions
- saved operator playbooks and reusable action recipes

Outcome:

- less duplicated manual research and easier reuse of verified project knowledge.

### Phase 4: IDE-Adjacent Integration

If desired later, this can grow into a stronger workstation helper layer.

- open file / jump to line operations
- recent project/workspace awareness
- patch staging and review assistance
- task templates for build, test, and diagnostics
- optional bridge to editor automation if a safe local interface is defined

Outcome:

- Nova starts to function as a practical local coding/operator companion rather than just a chat wrapper.

## Immediate Next Tooling Targets

These are the best next additions with the current repo shape:

1. Add a governed local file listing and search tool surface.
2. Add a controlled command runner with allowlist and audit logging.
3. Add a control-room panel for tool inventory and recent tool actions.
4. Expand `capabilities.json` into a richer, maintained capability registry.

## Guardrails

Each new tool should follow these rules:

- respect `policy.json`
- log actions to runtime audit trails
- expose clear success/failure output
- prefer deterministic behavior over best-effort hidden fallbacks
- avoid write or exec actions without explicit operator intent