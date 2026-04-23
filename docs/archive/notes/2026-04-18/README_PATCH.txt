# Patch packaging notes
#
# To protect Nova from regressions/downgrades, include a manifest file at zip root:
#
#   nova_patch.json
#
# Example:
# {
#   "patch_revision": 12,
#   "min_base_revision": 10,
#   "notes": "memory recall tuning"
# }
#
# Rules:
# - patch_revision must be an integer greater than current revision
# - min_base_revision is optional, default 0
# - In strict mode (policy.patch.strict_manifest=true), patches without manifest are rejected
