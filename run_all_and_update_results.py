# Copyright (c) 2021, Linus Groh <linusg@serenityos.org>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from argparse import ArgumentParser
from pathlib import Path


def run_command(command: str, **kwargs) -> str:
    process = subprocess.run(
        shlex.split(command), stdout=subprocess.PIPE, text=True, **kwargs
    )
    return process.stdout.strip()


def get_git_revision(path: Path) -> str:
    return run_command(f"git --git-dir {path / '.git'} rev-parse HEAD")


def get_git_commit_timestamp(path: Path) -> int:
    return int(run_command(f"git --git-dir {path / '.git'} log -1 --pretty=format:%ct"))


def main() -> None:
    # NOTE: There's deliberately no error handling here, if any of
    # these fail we might as well let the script blow up in our face -
    # the result would be incomplete anyway.

    parser = ArgumentParser(
        description=(
            "Run the test262 and test262-parser-tests with "
            "LibJS and update the results JSON file"
        )
    )
    parser.add_argument(
        "--serenity",
        required=True,
        metavar="PATH",
        help="path to the 'serenity' directory",
    )
    parser.add_argument(
        "--test262",
        required=True,
        metavar="PATH",
        help="path to the 'test262' directory",
    )
    parser.add_argument(
        "--test262-parser-tests",
        required=True,
        metavar="PATH",
        help="path to the 'test262-parser-tests' directory",
    )
    parser.add_argument(
        "--results-json",
        required=True,
        metavar="PATH",
        help="path to the results JSON file",
    )
    args = parser.parse_args()

    libjs_test262 = Path(__file__).parent
    serenity = Path(args.serenity)
    test262 = Path(args.test262)
    test262_parser_tests = Path(args.test262_parser_tests)
    results_json = Path(args.results_json)

    if results_json.exists():
        results = json.loads(results_json.read_text())
    else:
        results_json.parent.mkdir(mode=0o755, parents=True, exists_ok=True)
        results_json.touch(mode=0o644)
        results = []

    commit_timestamp = get_git_commit_timestamp(serenity)
    run_timestamp = int(time.time())

    serenity_test_js = serenity / "Build/lagom/test-js"
    if not serenity_test_js.exists():
        serenity_test_js = serenity / "Build/lagom/Meta/Lagom/test-js"
    libjs_test262_main_py = libjs_test262 / "main.py"
    libjs_test262_runner = libjs_test262 / "Build/libjs-test262-runner"

    version_serenity = get_git_revision(serenity)
    version_libjs_test262 = get_git_revision(libjs_test262)
    version_test262 = get_git_revision(test262)
    version_test262_parser_tests = get_git_revision(test262_parser_tests)

    result_for_current_revision = (
        result
        for result in results
        if result["versions"]["serenity"] == version_serenity
    )
    if next(result_for_current_revision, None):
        print(
            f"Result for revision {version_serenity[:7]} already exists, "
            "remove it manually if you wish to re-run the tests."
        )
        sys.exit(1)

    test_js_output = json.loads(
        run_command(
            f"{serenity_test_js} --test262-parser-tests {test262_parser_tests} --json",
            env={"SERENITY_SOURCE_DIR": str(serenity)},
        )
    )
    test_js_results = test_js_output["results"]["tests"]

    libjs_test262_output = json.loads(
        # This is not the way, but I can't be bothered to import this stuff. :^)
        run_command(
            f"python3 {libjs_test262_main_py} "
            f"--libjs-test262-runner {libjs_test262_runner} "
            f"--test262 {test262} "
            "--silent --json"
            # " -p 'test/built-ins/Boolean/**/*'"
        )
    )
    libjs_test262_results = libjs_test262_output["results"]["test"]["results"]

    result = {
        "commit_timestamp": commit_timestamp,
        "run_timestamp": run_timestamp,
        "versions": {
            "serenity": version_serenity,
            "libjs-test262": version_libjs_test262,
            "test262": version_test262,
            "test262-parser-tests": version_test262_parser_tests,
        },
        "tests": {
            "test262": {
                "duration": libjs_test262_output["duration"],
                "results": {
                    "total": libjs_test262_output["results"]["test"]["count"],
                    "passed": libjs_test262_results["PASSED"],
                    "failed": libjs_test262_results["FAILED"],
                    "skipped": libjs_test262_results["SKIPPED"],
                    "metadata_error": libjs_test262_results["METADATA_ERROR"],
                    "harness_error": libjs_test262_results["HARNESS_ERROR"],
                    "timeout_error": libjs_test262_results["TIMEOUT_ERROR"],
                    "process_error": libjs_test262_results["PROCESS_ERROR"],
                    "runner_exception": libjs_test262_results["RUNNER_EXCEPTION"],
                },
            },
            "test262-parser-tests": {
                "duration": test_js_output["duration"],
                "results": {
                    "total": test_js_results["total"],
                    "passed": test_js_results["passed"],
                    "failed": test_js_results["failed"],
                    # Ignore "skipped", there's no skipping of test262-parser-tests
                },
            },
        },
    }
    results.append(result)
    results_json.write_text(f"{json.dumps(results)}\n")


if __name__ == "__main__":
    main()
