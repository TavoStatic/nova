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

## Teach Proposal Flow

- teach examples are stored under `updates/teaching`
- proposal archives are written under `updates`
- preview reports are written under `updates/previews`

Automated environments no longer enter the blocking local review prompt by default.

To explicitly enable interactive local proposal review:

```powershell
$env:NOVA_INTERACTIVE_PATCH_REVIEW='1'
```

Without that environment variable, proposal generation remains non-blocking and test-safe.