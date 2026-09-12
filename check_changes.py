#!/usr/bin/env python3
"""Check work tree state after external changes."""

import work_tree
import json
from pathlib import Path

print("=" * 60)
print("WORK TREE STATE CHECK")
print("=" * 60)

# Reload from database
work_tree.reload_state_from_db()
trees = list(work_tree._BRANCHES.keys())
print(f"\nTotal branches in work tree: {len(trees)}")

# Find target tree with blocked branches
target_tree = None
for bid in trees:
    b = work_tree.get_branch(bid)
    if b and ('Signal Intake' in b.objective or 'Runtime Governance' in b.objective):
        target_tree = bid
        break

if target_tree:
    print(f"\nTarget tree: {target_tree}")
    tree = work_tree.get_branch(target_tree)
    payload = tree.source_payload if tree else {}
    
    print(f"Objective: {tree.objective if tree else 'N/A'}")
    print(f"State: {tree.state if tree else 'N/A'}")
    
    blocked = payload.get('blocked_branches', [])
    if blocked:
        print(f"\n  BLOCKED BRANCHES ({len(blocked)}):")
        for b in blocked:
            print(f"    - {b}")
    else:
        print("\n  No blocked branches")
    
    print(f"\nPayload keys: {sorted(payload.keys())}")
    
    # Check for observation spine activity
    if 'recurring_finding_lifecycle' in payload:
        rec = payload['recurring_finding_lifecycle']
        print(f"\nRecurring findings: {rec}")
else:
    print("\nTarget tree not found (Signal Intake / Runtime Governance)")

print("\n" + "=" * 60)
print("CHECKING CRITICAL FIX IMPLEMENTATION")
print("=" * 60)

# Check if critical fixes are in place
print("\n1. Checking observation_spine.py for per-branch lock usage...")
obs_spine_file = Path("services/observation_spine.py")
if obs_spine_file.exists():
    content = obs_spine_file.read_text()
    has_branch_lock = "_acquire_branch_lock" in content
    has_prune = "prune_expired_judgments" in content
    print(f"   - Uses _acquire_branch_lock: {has_branch_lock}")
    print(f"   - Uses prune_expired_judgments: {has_prune}")
else:
    print("   File not found")

print("\n2. Checking solution_trail.py for pruning logic...")
trail_file = Path("services/solution_trail.py")
if trail_file.exists():
    content = trail_file.read_text()
    has_prune = "_prune_expired_judgments" in content
    has_evaluate = "judgment_still_suppresses" in content
    print(f"   - Defines _prune_expired_judgments: {has_prune}")
    print(f"   - Evaluates still_suppresses: {has_evaluate}")
else:
    print("   File not found")

print("\n3. Checking work_tree.py for per-branch locks...")
wt_file = Path("work_tree.py")
if wt_file.exists():
    content = wt_file.read_text()
    has_locks = "_BRANCH_LOCKS" in content
    has_acquire = "_acquire_branch_lock" in content
    print(f"   - Defines _BRANCH_LOCKS: {has_locks}")
    print(f"   - Defines _acquire_branch_lock: {has_acquire}")
else:
    print("   File not found")

print("\n4. Checking policy.json for observation_spine config...")
policy_file = Path("policy.json")
if policy_file.exists():
    try:
        with open(policy_file) as f:
            policy = json.load(f)
        has_obs_section = "observation_spine" in policy
        if has_obs_section:
            obs_config = policy["observation_spine"]
            print(f"   - observation_spine.enabled: {obs_config.get('enabled')}")
            print(f"   - repeat_unchanged_threshold: {obs_config.get('repeat_unchanged_threshold')}")
            print(f"   - window_size: {obs_config.get('window_size')}")
        else:
            print("   - observation_spine section NOT FOUND")
    except Exception as e:
        print(f"   Error reading policy.json: {e}")
else:
    print("   File not found")

print("\n" + "=" * 60)
