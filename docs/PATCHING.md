# Nova Patching And Teach Flow

Last verified from code: 2026-07-12

## Patch Packaging Rules

To protect Nova from regressions and downgrades, patch zip files should include `nova_patch.json` at the archive root.

Example:

```json
{
  "patch_revision": 12,
  "min_base_revision": 10,
  "notes": "memory recall tuning"
}
```

Rules:

- `patch_revision` must increase forward from the current revision
- `min_base_revision` is optional and defaults to `0`
- strict manifest mode is controlled by `policy.patch.strict_manifest`
- behavioral validation after apply is controlled by `policy.patch.behavioral_check`
- the behavioral gate timeout is controlled by `policy.patch.behavioral_check_timeout_sec`

## Teach Proposal Flow

- teach examples are stored under `updates/teaching`
- proposal archives are written under `updates`
- preview reports are written under `updates/previews`

Teach proposals now emit a forward manifest automatically:

- `patch_revision = current_revision + 1`
- `min_base_revision = current_revision`

That keeps locally generated proposals preview-eligible instead of looking like unversioned or downgrade patches.

## Patch Validation

Live patch apply has two acceptance gates after preview eligibility and approval checks:

1. compile validation
2. behavioral validation via `run_regression.py behavior` when the regression wrapper exists, with unittest discovery as fallback

If compile validation fails, Nova rolls back immediately.
If behavioral validation fails, Nova also rolls back immediately.

That same behavioral gate is reused by teach autoapply staging before any live apply is attempted.

Automated environments no longer enter the blocking local review prompt by default.

To explicitly enable interactive local proposal review:

```powershell
$env:NOVA_INTERACTIVE_PATCH_REVIEW='1'
```

Without that environment variable, proposal generation remains non-blocking and test-safe.

## Queue And Cleanup

Patch previews are synchronized into a governed Work Tree lane. Maintenance can:

- reject orphaned preview reports whose patch archive is missing
- archive superseded eligible previews in the same family
- keep approval decisions separate from preview eligibility
- expose apply readiness through control status and the control-action dispatcher

Kidney owns age/retention cleanup; patch maintenance owns patch-state reconciliation.

## Codegen Bridge

Generated code previews do not bypass patch governance. `services/codegen_patch_bridge.py` validates a codegen preview and builds a formal patch artifact. `services/codegen_memory_recorder.py` and `services/patch_promotion_memory.py` preserve reusable generated-code evidence and promoted patterns.

## Truth Rule

A successful behavior lane is not a full regression or release verdict. Patch apply, regression profile, validation artifact, build identity, and release promotion remain separate evidence owners.
