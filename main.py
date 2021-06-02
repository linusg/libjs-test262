# Copyright (c) 2020-2021, Linus Groh <linusg@serenityos.org>
# Copyright (c) 2021, Marcin Gasperowicz <xnooga@gmail.com>
# Copyright (c) 2021, Idan Horowitz <idan.horowitz@serenityos.org>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import concurrent.futures
import json
import multiprocessing
import os
import re
import signal
import subprocess
import traceback
import resource
from argparse import ArgumentParser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ruamel.yaml import YAML
from tqdm import tqdm


METADATA_YAML_REGEX = re.compile(r"/\*---\n((?:.|\n)+)\n---\*/")


class TestResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"
    METADATA_ERROR = "METADATA_ERROR"
    HARNESS_ERROR = "HARNESS_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    PROCESS_ERROR = "PROCESS_ERROR"
    RUNNER_EXCEPTION = "RUNNER_EXCEPTION"


@dataclass
class TestRun:
    file: Path
    result: TestResult
    output: str


EMOJIS = {
    TestResult.SUCCESS: "✅",
    TestResult.FAILURE: "❌",
    TestResult.SKIPPED: "⚠️",
    TestResult.METADATA_ERROR: "📄",
    TestResult.HARNESS_ERROR: "⚙️",
    TestResult.TIMEOUT_ERROR: "💀",
    TestResult.PROCESS_ERROR: "💥️",
    TestResult.RUNNER_EXCEPTION: "🐍",
}

UNSUPPORTED_FEATURES = ["IsHTMLDDA"]

CPU_COUNT = multiprocessing.cpu_count()


def get_metadata(test_file: Path) -> Optional[dict]:
    contents = test_file.resolve().read_text()
    if match := re.search(METADATA_YAML_REGEX, contents):
        metadata_yaml = match.groups()[0]
        return dict(YAML().load(metadata_yaml))
    return None


def run_script(
    libjs_test262_runner: Path,
    test262_root: Path,
    script: str,
    includes: Iterable[str],
    timeout: float,
    memory_limit: int,
) -> subprocess.CompletedProcess:
    def limit_memory():
        resource.setrlimit(
            resource.RLIMIT_AS, (memory_limit * 1024 * 1024, resource.RLIM_INFINITY)
        )

    harness_files = ["assert.js", "sta.js", *includes]
    command = [
        libjs_test262_runner,
        *[str((test262_root / "harness" / file).resolve()) for file in harness_files],
    ]
    return subprocess.run(
        command,
        input=script,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        text=True,
        timeout=timeout,
        preexec_fn=limit_memory,
        errors="ignore",  # strip invalid utf8 code points instead of throwing (to allow for invalid utf-8 tests)
    )


def run_test(
    libjs_test262_runner: Path,
    test262_root: Path,
    file: Path,
    timeout: float,
    memory_limit: int,
) -> TestRun:
    # https://github.com/tc39/test262/blob/master/INTERPRETING.md

    output = ""

    def test_run(result: TestResult) -> TestRun:
        return TestRun(file, result, output)

    def failure() -> TestRun:
        return test_run(TestResult.FAILURE)

    def success() -> TestRun:
        return test_run(TestResult.SUCCESS)

    def success_if(condition: Any) -> TestRun:
        return test_run(TestResult.SUCCESS if condition else TestResult.FAILURE)

    metadata = get_metadata(file)
    if metadata is None:
        return test_run(TestResult.METADATA_ERROR)

    if any(feature in UNSUPPORTED_FEATURES for feature in metadata.get("features", [])):
        return test_run(TestResult.SKIPPED)

    try:
        script = file.read_text()
        process = run_script(
            libjs_test262_runner,
            test262_root,
            script,
            metadata.get("includes", []),
            timeout,
            memory_limit,
        )
        output = process.stdout.strip()
        result = json.loads(output, strict=False)
    except subprocess.CalledProcessError as error:
        output = error.stdout.strip()
        return test_run(TestResult.PROCESS_ERROR)
    except subprocess.TimeoutExpired:
        return test_run(TestResult.TIMEOUT_ERROR)
    except:
        output = traceback.format_exc()
        return test_run(TestResult.RUNNER_EXCEPTION)

    # Prettify JSON output for verbose printing
    output = json.dumps(result, indent=2)

    if result.get("harness_error") is True:
        return test_run(TestResult.HARNESS_ERROR)

    if metadata.get("negative") is not None:
        expected_phase = metadata["negative"]["phase"]
        expected_type = metadata["negative"]["type"]
        error = result.get("error")
        if not error:
            return failure()
        actual_phase = error.get("phase")
        actual_type = error.get("type")
        if expected_phase == "parse" or expected_phase == "early":
            # No distinction between parse and early in the LibJS parser.
            return success_if(actual_phase == "parse")
        elif expected_phase == "runtime":
            return success_if(
                actual_phase == "runtime" and actual_type == expected_type
            )
        elif expected_phase == "resolution":
            # No modules yet :^)
            return failure()
        else:
            raise Exception(f"Unexpected phase '{expected_phase}'")

    if result.get("error"):
        return failure()

    return success()


class Runner:
    def __init__(
        self,
        libjs_test262_runner: Path,
        test262_root: Path,
        concurrency: int,
        timeout: int,
        memory_limit: int,
        silent: bool = False,
        verbose: bool = False,
    ) -> None:
        self.libjs_test262_runner = libjs_test262_runner
        self.test262_root = test262_root
        self.concurrency = concurrency
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.silent = silent
        self.verbose = verbose
        self.files: List[Path] = []
        self.result_map: Dict[str, dict] = {}
        self.total_count = 0
        self.progress = 0

    def log(self, message: str) -> None:
        if not self.silent:
            print(message)

    def find_tests(self, pattern: str) -> None:
        self.log("Searching test files...")
        if Path(pattern).resolve().is_file():
            self.files = [Path(pattern).resolve()]
        else:
            self.files = [
                path.resolve()
                for path in self.test262_root.glob(pattern)
                if path.is_file() and not path.stem.endswith("FIXTURE")
            ]
        self.files.sort()
        self.total_count = len(self.files)
        self.log(f"Found {self.total_count}.")
        self.build_result_map()

    def build_result_map(self) -> None:
        for file in self.files:
            directory = file.relative_to(self.test262_root).parent
            counter = self.result_map
            for segment in directory.parts:
                if not segment in counter:
                    counter[segment] = {"count": 1, "results": {}, "children": {}}
                    for result in TestResult:
                        counter[segment]["results"][result] = 0
                else:
                    counter[segment]["count"] += 1
                counter = counter[segment]["children"]

    def count_result(self, test_run: TestRun) -> None:
        directory = test_run.file.relative_to(self.test262_root).parent
        counter = self.result_map
        for segment in directory.parts:
            counter[segment]["results"][test_run.result] += 1
            counter = counter[segment]["children"]

    def report(self) -> None:
        def print_tree(tree, path, level):
            results = "[ "
            for k, v in tree["results"].items():
                if v > 0:
                    results += f"{EMOJIS[k]} {v:<5} "
            results += "]"
            count = tree["count"]
            passed = tree["results"][TestResult.SUCCESS]
            percentage = (passed / count) * 100
            pad = " " * (80 - len(path))
            print(f"{path}{pad}{passed:>5}/{count:<5} ({percentage:6.2f}%) {results} ")
            if passed > 0:
                for k, v in tree["children"].items():
                    print_tree(v, path + "/" + k, level + 1)

        for k, v in self.result_map.items():
            print_tree(v, k, 0)

    def process(self, file: Path) -> TestRun:
        return run_test(
            self.libjs_test262_runner,
            self.test262_root,
            file,
            timeout=self.timeout,
            memory_limit=self.memory_limit,
        )

    def run(self) -> None:
        if not self.files:
            self.log("No tests to run.")
            return
        if not self.silent:
            progressbar = tqdm(
                total=self.total_count, mininterval=1, unit="tests", smoothing=0.1
            )
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.concurrency
        ) as executor:
            futures = {executor.submit(self.process, f) for f in self.files}
            for future in concurrent.futures.as_completed(futures):
                test_run = future.result()
                self.count_result(test_run)
                if self.verbose:
                    print(f"{EMOJIS[test_run.result]} {test_run.file}")
                    if test_run.output:
                        print()
                        print(test_run.output)
                        print()
                    progressbar.refresh()
                if not self.silent:
                    progressbar.update(1)
                self.progress += 1

        if not self.silent:
            progressbar.close()
        self.log("Finished running tests.")


def main() -> None:
    parser = ArgumentParser(
        description="Run the test262 ECMAScript test suite with SerenityOS's LibJS",
        epilog=", ".join(f"{EMOJIS[result]} = {result.value}" for result in TestResult),
    )
    parser.add_argument(
        "-j",
        "--libjs-test262-runner",
        required=True,
        metavar="PATH",
        help="path to the 'libjs-test262-runner' binary",
    )
    parser.add_argument(
        "-t",
        "--test262-root",
        required=True,
        metavar="PATH",
        help="path to the 'test262' directory",
    )
    parser.add_argument(
        "-p",
        "--pattern",
        default="test/**/*.js",
        help="glob pattern used for test file searching (defaults to test/**/*.js)",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        default=CPU_COUNT,
        type=int,
        help="number of concurrent workers (defaults to number of CPU cores)",
    )
    parser.add_argument(
        "--timeout",
        default=10,
        type=int,
        help="timeout for each test run in seconds (defaults to 10)",
    )
    parser.add_argument(
        "--memory-limit",
        default=512,
        type=int,
        help="memory limit for each test run in megabytes (defaults to 512)",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the test results as JSON"
    )
    logging_group = parser.add_mutually_exclusive_group()
    logging_group.add_argument(
        "-s",
        "--silent",
        action="store_true",
        help="don't print any progress information",
    )
    logging_group.add_argument(
        "-v", "--verbose", action="store_true", help="print output of test runs"
    )
    args = parser.parse_args()

    runner = Runner(
        Path(args.libjs_test262_runner).resolve(),
        Path(args.test262_root).resolve(),
        args.concurrency,
        args.timeout,
        args.memory_limit,
        args.silent,
        args.verbose,
    )
    runner.find_tests(args.pattern)
    runner.run()
    if args.json:
        print(json.dumps(runner.result_map))
    else:
        runner.report()


if __name__ == "__main__":
    os.setpgrp()
    try:
        main()
    except KeyboardInterrupt:
        os.killpg(0, signal.SIGKILL)
