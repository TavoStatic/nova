#!/usr/bin/env python3
"""Run critical test suites for observation spine fixes."""

import subprocess
import sys

test_files = [
    "tests/test_observation_spine_fixes.py",
    "tests/test_observation_spine.py",
    "tests/test_solution_trail.py",
]

print("=" * 70)
print("RUNNING CRITICAL TEST SUITES")
print("=" * 70)

all_passed = True

for test_file in test_files:
    print(f"\n{'=' * 70}")
    print(f"Running: {test_file}")
    print("=" * 70)
    
    result = subprocess.run(
        ["python", "-m", "pytest", test_file, "-v", "--tb=short"],
        capture_output=False,
        text=True
    )
    
    if result.returncode != 0:
        all_passed = False
        print(f"❌ FAILED: {test_file}")
    else:
        print(f"✅ PASSED: {test_file}")

print(f"\n{'=' * 70}")
if all_passed:
    print("✅ ALL CRITICAL TESTS PASSED")
    sys.exit(0)
else:
    print("❌ SOME TESTS FAILED")
    sys.exit(1)
