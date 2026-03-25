# Nova Patching and Teach Flow

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

Live patch apply now has two acceptance gates:

1. compile validation
2. behavioral validation via `python -m unittest discover -s tests -f`

If compile validation fails, Nova rolls back immediately.
If behavioral validation fails, Nova also rolls back immediately.

That same behavioral gate is reused by teach autoapply staging before any live apply is attempted.

Automated environments no longer enter the blocking local review prompt by default.

To explicitly enable interactive local proposal review:

```powershell
$env:NOVA_INTERACTIVE_PATCH_REVIEW='1'
```

Without that environment variable, proposal generation remains non-blocking and test-safe.