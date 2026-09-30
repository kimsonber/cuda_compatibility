#!/usr/bin/env python3
"""
Simple test runner for nvcc wrapper.

Test files (.test) contain:
  - An nvcc command line (first line starting with RUN:)
  - CHECK: <pattern>  — pattern must appear in stdout+stderr
  - CHECK-NOT: <pattern> — pattern must NOT appear in stdout+stderr

The line containing "Failed to load config file" is automatically excluded
from CHECK/CHECK-NOT matching, as it's environment-specific.

Usage:
  python3 run_tests.py                    # run all .test files in the same dir
  python3 run_tests.py path/to/test.test  # run a specific test
"""

import subprocess
import sys
import os
import tempfile
import re


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                          "..", "..", "..", ".."))
BUILD_DIR = os.path.join(REPO_ROOT, "configs", "binary_config", "build")
NVCC_BIN = os.path.join(BUILD_DIR, "nvcc_wrapper", "nvcc")


def make_cu_file():
    tmpdir = tempfile.mkdtemp()
    cu_path = os.path.join(tmpdir, "test.cu")
    with open(cu_path, "w") as f:
        f.write("__global__ void kernel() {}\n")
    return cu_path, tmpdir


def run_test(test_path):
    with open(test_path) as f:
        lines = f.readlines()

    # Find RUN: line
    run_line = None
    checks = []
    not_checks = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("RUN:"):
            run_line = stripped[len("RUN:"):].strip()
        elif stripped.startswith("CHECK-NOT:"):
            not_checks.append(stripped[len("CHECK-NOT:"):].strip())
        elif stripped.startswith("CHECK:"):
            checks.append(stripped[len("CHECK:"):].strip())

    if not run_line:
        print(f"  FAIL: no RUN: line found in {test_path}")
        return False

    # Build command
    # Replace %s with temp .cu file path
    cu_path, tmpdir = make_cu_file()
    try:
        # Tokenize the run_line into args
        import shlex
        cmd_args = shlex.split(run_line)

        # Replace %s with cu_path if present
        cmd_args = [a.replace("%s", cu_path) for a in cmd_args]

        # If %s wasn't used, check if there's a .cu file arg; if not, add it
        if "%s" not in run_line:
            has_cu_file = any(a.endswith(".cu") for a in cmd_args)
            if not has_cu_file:
                cmd_args.append(cu_path)

        # First arg should be either the nvcc binary path or just "nvcc"
        if cmd_args[0] == "nvcc":
            cmd_args[0] = NVCC_BIN
        elif cmd_args[0] != NVCC_BIN and not cmd_args[0].startswith("/"):
            cmd_args.insert(0, NVCC_BIN)

        result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=30)
        output = result.stdout + "\n" + result.stderr if result.stderr else result.stdout

        # Filter out the "Failed to load config file" line
        filtered_lines = [
            line for line in output.split("\n")
            if "Failed to load config file" not in line
        ]
        filtered_output = "\n".join(filtered_lines)

        # Run CHECK:
        for pattern in checks:
            if pattern not in filtered_output:
                print(f"  FAIL: CHECK: '{pattern}' not found in output")
                print(f"  Output was:\n{filtered_output[:2000]}")
                return False

        # Run CHECK-NOT:
        for pattern in not_checks:
            if pattern in filtered_output:
                print(f"  FAIL: CHECK-NOT: '{pattern}' found in output (should be absent)")
                print(f"  Output was:\n{filtered_output[:2000]}")
                return False

        print(f"  PASS")
        return True

    except subprocess.TimeoutExpired:
        print(f"  FAIL: timeout")
        return False
    except Exception as e:
        print(f"  FAIL: {e}")
        return False
    finally:
        import shutil
        shutil.rmtree(tmpdir)


def main():
    if len(sys.argv) > 1:
        test_files = sys.argv[1:]
    else:
        test_dir = os.path.dirname(os.path.abspath(__file__))
        test_files = sorted(
            os.path.join(test_dir, f)
            for f in os.listdir(test_dir)
            if f.endswith(".test")
        )

    if not test_files:
        print("No .test files found.")
        sys.exit(1)

    passed = 0
    failed = 0

    for tf in test_files:
        name = os.path.basename(tf)
        print(f"  [{name}] ", end="", flush=True)
        if run_test(tf):
            passed += 1
        else:
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed, {passed+failed} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
