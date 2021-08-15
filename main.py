#!/usr/bin/env python3
# Copyright (c) 2020-2021, Linus Groh <linusg@serenityos.org>
# Copyright (c) 2021, Marcin Gasperowicz <xnooga@gmail.com>
# Copyright (c) 2021, Idan Horowitz <idan.horowitz@serenityos.org>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import concurrent.futures
import datetime
import json
import multiprocessing
import os
import re
import resource
import signal
import subprocess
import traceback
from argparse import ArgumentParser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Literal

from ruamel.yaml import YAML
from tqdm import tqdm

# \s* after opening and before closing marker as some (2 as of
# 2021-06-06) tests have trailing /leading whitespace there.
METADATA_YAML_REGEX = re.compile(r"/\*---\s*\n((?:.|\n)+)\n\s*---\*/")


class TestResult(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
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
    output: str | None
    exit_code: int | None
    strict_mode: bool | None


@dataclass
class Metadata:
    features: list[str]
    flags: list[
        Literal[
            "onlyStrict",
            "noStrict",
            "module",
            "raw",
            "async",
            "generated",
            "CanBlockIsFalse",
        ]
    ]
    includes: list[str]
    locale: list[str]
    negative: NegativeMetadata | None


@dataclass
class NegativeMetadata:
    phase: Literal["parse", "early", "resolution", "runtime"]
    type: str


EMOJIS = {
    TestResult.PASSED: "✅",
    TestResult.FAILED: "❌",
    TestResult.SKIPPED: "⚠️",
    TestResult.METADATA_ERROR: "📄",
    TestResult.HARNESS_ERROR: "⚙️",
    TestResult.TIMEOUT_ERROR: "💀",
    TestResult.PROCESS_ERROR: "💥️",
    TestResult.RUNNER_EXCEPTION: "🐍",
}

NON_FAIL_RESULTS = [TestResult.PASSED, TestResult.SKIPPED]

UNSUPPORTED_FEATURES = []

CPU_COUNT = multiprocessing.cpu_count()


def get_metadata(test_file: Path) -> Metadata | None:
    contents = test_file.resolve().read_text()
    if match := re.search(METADATA_YAML_REGEX, contents):
        metadata_yaml = match.groups()[0]
        metadata = dict(YAML().load(metadata_yaml))
        return Metadata(
            features=metadata.get("features", []),
            flags=metadata.get("flags", []),
            includes=metadata.get("includes", []),
            locale=metadata.get("locale", []),
            negative=NegativeMetadata(
                phase=metadata["negative"]["phase"],
                type=metadata["negative"]["type"],
            )
            if "negative" in metadata
            else None,
        )
    return None


def run_script(
    libjs_test262_runner: Path,
    test262_root: Path,
    script: str,
    includes: Iterable[str],
    use_bytecode: bool,
    as_module: bool,
    timeout: float,
    memory_limit: int,
) -> subprocess.CompletedProcess:
    def limit_memory():
        resource.setrlimit(
            resource.RLIMIT_AS, (memory_limit * 1024 * 1024, resource.RLIM_INFINITY)
        )

    harness_files = ["assert.js", "sta.js", *includes]
    command = [
        str(libjs_test262_runner),
        *(["-b"] if use_bytecode else []),
        *(["-m"] if as_module else []),
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
    use_bytecode: bool,
    timeout: float,
    memory_limit: int,
    strict_mode: bool | None = None,
) -> TestRun:
    # https://github.com/tc39/test262/blob/master/INTERPRETING.md

    output: str | None = None
    exit_code: int | None = None

    def test_run(result: TestResult) -> TestRun:
        return TestRun(file, result, output, exit_code, strict_mode)

    def failed() -> TestRun:
        return test_run(TestResult.FAILED)

    def passed() -> TestRun:
        return test_run(TestResult.PASSED)

    def passed_if(condition: Any) -> TestRun:
        return test_run(TestResult.PASSED if condition else TestResult.FAILED)

    metadata = get_metadata(file)
    if metadata is None:
        return test_run(TestResult.METADATA_ERROR)

    if any(feature in UNSUPPORTED_FEATURES for feature in metadata.features):
        return test_run(TestResult.SKIPPED)

    if strict_mode is None:
        args = (
            libjs_test262_runner,
            test262_root,
            file,
            use_bytecode,
            timeout,
            memory_limit,
        )
        if "module" in metadata.flags:
            # Will be forced to be strict by interpreting as module do not add 'use strict';
            return run_test(*args, strict_mode=False)
        if "onlyStrict" in metadata.flags:
            return run_test(*args, strict_mode=True)
        elif "noStrict" in metadata.flags or "raw" in metadata.flags:
            return run_test(*args, strict_mode=False)
        elif (
            first_run := run_test(*args, strict_mode=True)
        ).result != TestResult.PASSED:
            return first_run
        return run_test(*args, strict_mode=False)

    includes = metadata.includes
    if "async" in metadata.flags:
        includes.append("doneprintHandle.js")

    script = file.read_text()
    if strict_mode:
        script = f'"use strict";\n{script}'

    as_module = "module" in metadata.flags

    try:
        process = run_script(
            libjs_test262_runner,
            test262_root,
            script,
            includes,
            use_bytecode,
            as_module,
            timeout,
            memory_limit,
        )
    except subprocess.CalledProcessError as e:
        output = e.stdout.strip()
        exit_code = e.returncode
        return test_run(TestResult.PROCESS_ERROR)
    except subprocess.TimeoutExpired:
        return test_run(TestResult.TIMEOUT_ERROR)

    output = str(process.stdout.strip())
    exit_code = process.returncode
    result = json.loads(output, strict=False)

    # Prettify JSON output for verbose printing
    output = json.dumps(result, indent=2, ensure_ascii=False)

    if result.get("harness_error") is True:
        return test_run(TestResult.HARNESS_ERROR)

    if negative := metadata.negative:
        error = result.get("error")
        if not error:
            return failed()
        phase = error.get("phase")
        type_ = error.get("type")
        if negative.phase == "parse" or negative.phase == "early":
            # No distinction between parse and early in the LibJS parser.
            return passed_if(phase == "parse" and type_ == negative.type)
        elif negative.phase == "runtime":
            return passed_if(phase == "runtime" and type_ == negative.type)
        elif negative.phase == "resolution":
            # No modules yet :^)
            return failed()
        else:
            raise Exception(f"Unexpected phase '{negative.phase}'")

    if result.get("error"):
        return failed()

    if "async" in metadata.flags:
        result_output = result.get("output", "")
        return passed_if(
            "Test262:AsyncTestComplete" in result_output
            and "Test262:AsyncTestFailure" not in result_output
        )

    return passed()


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
        use_bytecode: bool = False,
        per_file: bool = False,
        fail_only: bool = False,
    ) -> None:
        self.libjs_test262_runner = libjs_test262_runner
        self.test262_root = test262_root
        self.concurrency = concurrency
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.silent = silent
        self.verbose = verbose
        self.use_bytecode = use_bytecode
        self.per_file = per_file
        self.fail_only = fail_only
        self.files: list[Path] = []
        self.directory_result_map: dict[str, dict] = {}
        self.file_result_map: dict[str, str] = {}
        self.total_count = 0
        self.progress = 0
        self.duration = datetime.timedelta()

    def log(self, message: str) -> None:
        if not self.silent and not self.per_file:
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

        if not self.per_file:
            self.build_directory_result_map()

    def build_directory_result_map(self) -> None:
        for file in self.files:
            directory = file.relative_to(self.test262_root).parent
            counter = self.directory_result_map
            for segment in directory.parts:
                if not segment in counter:
                    counter[segment] = {"count": 1, "results": {}, "children": {}}
                    for result in TestResult:
                        counter[segment]["results"][result] = 0
                else:
                    counter[segment]["count"] += 1
                counter = counter[segment]["children"]

    def count_result(self, test_run: TestRun) -> None:
        relative_file = test_run.file.relative_to(self.test262_root)
        if self.per_file:
            self.file_result_map[str(relative_file)] = test_run.result.name
        else:
            directory = relative_file.parent
            counter = self.directory_result_map
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
            passed = tree["results"][TestResult.PASSED]
            percentage = (passed / count) * 100
            pad = " " * (80 - len(path))
            print(f"{path}{pad}{passed:>5}/{count:<5} ({percentage:6.2f}%) {results} ")
            if passed > 0:
                for k, v in tree["children"].items():
                    print_tree(v, path + "/" + k, level + 1)

        for k, v in self.directory_result_map.items():
            print_tree(v, k, 0)

    def process(self, file: Path) -> TestRun:
        try:
            return run_test(
                self.libjs_test262_runner,
                self.test262_root,
                file,
                use_bytecode=self.use_bytecode,
                timeout=self.timeout,
                memory_limit=self.memory_limit,
            )
        except:
            return TestRun(
                file,
                result=TestResult.RUNNER_EXCEPTION,
                output=traceback.format_exc(),
                exit_code=None,
                strict_mode=None,
            )

    def run(self) -> None:
        if not self.files:
            self.log("No tests to run.")
            return
        show_progress = not self.silent
        if show_progress:
            progressbar = tqdm(
                total=self.total_count, mininterval=1, unit="tests", smoothing=0.1
            )
        start = datetime.datetime.now()
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.concurrency
        ) as executor:
            futures = {executor.submit(self.process, f) for f in self.files}
            for future in concurrent.futures.as_completed(futures):
                test_run = future.result()
                self.count_result(test_run)
                if self.verbose or (
                    self.fail_only and test_run.result not in NON_FAIL_RESULTS
                ):
                    if show_progress:
                        # prevent progressbars in the middle of verbose results
                        progressbar.clear()
                    print(
                        f"{EMOJIS[test_run.result]} {test_run.file}"
                        f"{' (strict mode)' if test_run.strict_mode else ''}"
                    )
                    if test_run.output:
                        print()
                        print(test_run.output)
                        print()
                    if test_run.exit_code:
                        signalnum = test_run.exit_code * -1
                        if not test_run.output:
                            print()
                        print(f"{signal.strsignal(signalnum)}: {signalnum}")
                        print()
                    if show_progress:
                        progressbar.refresh()
                if show_progress:
                    progressbar.update(1)
                self.progress += 1

        end = datetime.datetime.now()
        self.duration = end - start
        if show_progress:
            progressbar.close()
        self.log(f"Finished running tests in {self.duration}.")


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
        "-b",
        "--use-bytecode",
        action="store_true",
        help="Use the bytecode interpreter to run the tests",
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
    parser.add_argument(
        "--per-file",
        action="store_true",
        help="show per-file results instead of per-directory results",
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
    parser.add_argument(
        "-f", "--fail-only", action="store_true", help="only show failed tests"
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
        args.use_bytecode,
        args.per_file,
        args.fail_only,
    )
    runner.find_tests(args.pattern)
    runner.run()
    if args.json:
        data = {
            "duration": runner.duration.total_seconds(),
            "results": runner.file_result_map
            if args.per_file
            else runner.directory_result_map,
        }
        print(json.dumps(data))
    else:
        runner.report()


if __name__ == "__main__":
    os.setpgrp()
    try:
        main()
    except KeyboardInterrupt:
        os.killpg(0, signal.SIGKILL)
