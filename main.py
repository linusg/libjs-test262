#!/usr/bin/env python3
# Copyright (c) 2020-2021, Linus Groh <linusg@serenityos.org>
# Copyright (c) 2021, Marcin Gasperowicz <xnooga@gmail.com>
# Copyright (c) 2021, Idan Horowitz <idan.horowitz@serenityos.org>
# Copyright (c) 2021, David Tuin <davidot@serenityos.org>
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import concurrent.futures
import datetime
import glob
import json
import multiprocessing
import os
import resource
import signal
import subprocess
import sys
import threading
import traceback
from argparse import ArgumentParser
from dataclasses import dataclass
from collections import Counter
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from tqdm import tqdm


class TestResult(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    METADATA_ERROR = "METADATA_ERROR"
    HARNESS_ERROR = "HARNESS_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    PROCESS_ERROR = "PROCESS_ERROR"
    RUNNER_EXCEPTION = "RUNNER_EXCEPTION"
    TODO_ERROR = "TODO_ERROR"


@dataclass
class TestRun:
    file: Path
    result: TestResult
    output: str | None
    exit_code: int | None
    strict_mode: bool | None


EMOJIS = {
    TestResult.PASSED: "✅",
    TestResult.FAILED: "❌",
    TestResult.SKIPPED: "⚠️",
    TestResult.METADATA_ERROR: "📄",
    TestResult.HARNESS_ERROR: "⚙️",
    TestResult.TIMEOUT_ERROR: "💀",
    TestResult.PROCESS_ERROR: "💥️",
    TestResult.RUNNER_EXCEPTION: "🐍",
    TestResult.TODO_ERROR: "📝",
}

NON_FAIL_RESULTS = [TestResult.PASSED, TestResult.SKIPPED]

CPU_COUNT = multiprocessing.cpu_count()
BATCH_SIZE = 250

progress_mutex = threading.Lock()


def run_streaming_script(
    libjs_test262_runner: Path,
    test262_root: Path,
    use_bytecode: bool,
    parse_only: bool,
    timeout: int,
    memory_limit: int,
    test_file_paths: list[Path],
) -> subprocess.CompletedProcess:
    def limit_memory():
        resource.setrlimit(
            resource.RLIMIT_AS, (memory_limit * 1024 * 1024, resource.RLIM_INFINITY)
        )

    command = [
        str(libjs_test262_runner),
        *(["-b"] if use_bytecode else []),
        *(["--parse-only"] if parse_only else []),
        "--harness-location",
        str((test262_root / "harness").resolve()),
        "-t",
        str(timeout),
    ]

    return subprocess.run(
        command,
        input="\n".join(str(path) for path in test_file_paths),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        text=True,
        preexec_fn=limit_memory,
        errors="ignore",  # strip invalid utf8 code points instead of throwing (to allow for invalid utf-8 tests)
    )


def run_tests(
    libjs_test262_runner: Path,
    test262_root: Path,
    test_file_paths: list[Path],
    use_bytecode: bool,
    parse_only: bool,
    timeout: int,
    memory_limit: int,
    on_progress_change: Callable[[int, dict[str, int]], None] | None,
    forward_stderr: Callable[[str], None] | None,
) -> list[TestRun]:

    current_test = 0
    results = []

    def add_result(
        iteration_results: list[TestRun],
        result: TestResult,
        output: str = "",
        exit_code: int = 0,
        strict_mode: bool = False,
    ) -> None:
        iteration_results.append(
            TestRun(
                test_file_paths[current_test], result, output, exit_code, strict_mode
            )
        )

    new_results = []
    while current_test < len(test_file_paths):
        start_count = current_test
        process_failed = False
        results.extend(new_results)
        new_results = []

        try:
            process_result: Any = run_streaming_script(
                libjs_test262_runner,
                test262_root,
                use_bytecode,
                parse_only,
                timeout,
                memory_limit,
                test_file_paths[current_test : current_test + BATCH_SIZE],
            )
        except subprocess.CalledProcessError as e:
            process_failed = True
            process_result = e

        test_results = [
            part.strip() for part in process_result.stdout.strip().split("\0")
        ]
        have_stopping_result = False

        while test_results:
            if not test_results[0].startswith("RESULT "):
                break

            test_result_string = test_results.pop(0).removeprefix("RESULT ")

            try:
                test_result = json.loads(test_result_string, strict=False)
            except json.decoder.JSONDecodeError:
                raise Exception(f"Could not parse JSON from '{test_result_string}'")

            file_name = Path(test_result["test"])

            if file_name != test_file_paths[current_test]:
                raise Exception(
                    f"Unexpected result from test {file_name} but expected result from {test_file_paths[current_test]}"
                )

            strict_mode = test_result.get("strict_mode", False)

            test_result_state = TestResult.FAILED

            result = test_result["result"]
            if result == "harness_error":
                test_result_state = TestResult.HARNESS_ERROR
            elif result == "metadata_error":
                test_result_state = TestResult.METADATA_ERROR
            elif result == "timeout":
                have_stopping_result = True
                test_result_state = TestResult.TIMEOUT_ERROR
            elif result == "assert_fail":
                have_stopping_result = True
                test_result_state = TestResult.PROCESS_ERROR
            elif result == "passed":
                test_result_state = TestResult.PASSED
            elif result == "skipped":
                test_result_state = TestResult.SKIPPED
            elif result == "todo_error":
                test_result_state = TestResult.TODO_ERROR
            elif result != "failed":
                raise Exception(f"Unknown error code: {result} from {test_result}")

            if strict_output := test_result.get("strict_output"):
                output = strict_output
            elif non_strict_output := test_result.get("output"):
                output = non_strict_output
            else:
                output = json.dumps(test_result, indent=2, ensure_ascii=False)

            add_result(new_results, test_result_state, output, strict_mode=strict_mode)
            current_test += 1

        if process_failed and not have_stopping_result:
            if forward_stderr is not None and process_result.stderr.strip() != "":
                forward_stderr(
                    f"Last tests ran: {test_file_paths[current_test]} before failing with stderr output:\n\n"
                    + process_result.stderr
                )

            add_result(
                new_results,
                TestResult.PROCESS_ERROR,
                "\n".join(test_results),
                process_result.returncode,
            )
            current_test += 1
        elif forward_stderr is not None and process_result.stderr.strip() != "":
            forward_stderr(
                "Process did not fail but still there is stderr output:\n\n"
                + process_result.stderr
            )

        if on_progress_change is not None:
            on_progress_change(
                current_test - start_count,
                Counter(EMOJIS[x.result] for x in new_results),
            )

    results.extend(new_results)
    return results


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
        track_per_file: bool = False,
        fail_only: bool = False,
        parse_only: bool = False,
        forward_stderr: bool = False,
        summary: bool = False,
    ) -> None:
        self.libjs_test262_runner = libjs_test262_runner
        self.test262_root = test262_root
        self.concurrency = concurrency
        self.timeout = timeout
        self.memory_limit = memory_limit
        self.silent = silent
        self.verbose = verbose
        self.use_bytecode = use_bytecode
        self.track_per_file = track_per_file
        self.fail_only = fail_only
        self.files: list[Path] = []
        self.directory_result_map: dict[str, dict] = {}
        self.file_result_map: dict[str, str] = {}
        self.total_count = 0
        self.duration = datetime.timedelta()
        self.parse_only = parse_only
        self.update_function: Callable[[int], None] | None = None
        self.print_output: Callable[[Optional[Any]], Any] = print

        self.forward_stderr_function: Callable[[str], None] | None
        if forward_stderr:
            if self.silent:
                self.forward_stderr_function = lambda message: print(
                    message, file=sys.stderr
                )
            else:
                self.forward_stderr_function = lambda message: tqdm.write(
                    message, file=sys.stderr
                )
        else:
            self.forward_stderr_function = None

        self.summary = summary

    def log(self, message: str) -> None:
        if not self.silent:
            self.print_output(message)

    def find_tests(self, pattern: str, ignore: str) -> None:
        if Path(pattern).resolve().is_file():
            self.files = [Path(pattern).resolve()]
        else:
            ignored_files = set(
                glob.iglob(str(self.test262_root / ignore), recursive=True)
            )
            for path in glob.iglob(str(self.test262_root / pattern), recursive=True):
                found_path = Path(path)
                if (
                    found_path.is_dir()
                    or "_FIXTURE" in found_path.stem
                    or not found_path.exists()
                    or path in ignored_files
                ):
                    continue

                self.files.append(found_path)

        self.files.sort()
        self.total_count = len(self.files)
        self.log(f"Found {self.total_count}.")

        if self.total_count == 0:
            return

        if not self.summary:
            self.build_directory_result_map()
        else:
            root_folder = self.files[0].relative_to(self.test262_root).parent.parts[0]
            self.directory_result_map = {
                root_folder: {
                    "count": self.total_count,
                    "results": {result: 0 for result in TestResult},
                    "children": {},
                }
            }

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
        if self.track_per_file:
            self.file_result_map[str(relative_file)] = test_run.result.name

        directory = relative_file.parent
        counter = self.directory_result_map

        if self.summary:
            counter[directory.parts[0]]["results"][test_run.result] += 1
            return

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
            self.print_output(
                f"{path}{pad}{passed:>5}/{count:<5} ({percentage:6.2f}%) {results} "
            )
            if passed > 0:
                for k, v in tree["children"].items():
                    print_tree(v, path + "/" + k, level + 1)

        for k, v in self.directory_result_map.items():
            print_tree(v, k, 0)

    def process_list(self, files: list[Path]) -> list[TestRun]:
        if not files:
            return []

        try:
            return run_tests(
                self.libjs_test262_runner,
                self.test262_root,
                files,
                use_bytecode=self.use_bytecode,
                parse_only=self.parse_only,
                timeout=self.timeout,
                memory_limit=self.memory_limit,
                on_progress_change=self.update_function,
                forward_stderr=self.forward_stderr_function,
            )
        except Exception as e:
            return [
                TestRun(
                    file,
                    result=TestResult.RUNNER_EXCEPTION
                    if i == 0
                    else TestResult.SKIPPED,
                    output=traceback.format_exc() if i == 0 else "",
                    exit_code=None,
                    strict_mode=None,
                )
                for i, file in enumerate(files)
            ]

    def run(self) -> None:
        if not self.files:
            self.log("No tests to run.")
            return

        workers = self.concurrency

        amount_of_work_lists = workers
        if self.total_count > workers * workers * 4:
            amount_of_work_lists = workers * 4

        amount_of_work_lists = min(amount_of_work_lists, self.total_count)
        work_lists: list[list[Path]] = [[] for _ in range(amount_of_work_lists)]

        for index, test_path in enumerate(self.files):
            work_lists[index % amount_of_work_lists].append(test_path)

        if not self.silent:
            progressbar = tqdm(
                total=self.total_count, mininterval=1, unit="tests", smoothing=0.1
            )

            def update_progress(value, new_results, total_stats=Counter()):
                progress_mutex.acquire()
                total_stats.update(new_results)
                try:
                    progressbar.update(value)
                    progressbar.set_postfix(**total_stats)
                finally:
                    progress_mutex.release()

            self.update_function = update_progress

            def write_output(message: Any):
                tqdm.write(message)

            self.print_output = write_output

        start = datetime.datetime.now()

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self.process_list, file_list)
                for file_list in work_lists
            ]

            for future in concurrent.futures.as_completed(futures):
                test_runs = future.result()
                for test_run in test_runs:
                    self.count_result(test_run)
                    if self.verbose or (
                        self.fail_only and test_run.result not in NON_FAIL_RESULTS
                    ):
                        self.print_output(
                            f"{EMOJIS[test_run.result]} {test_run.file}"
                            f"{' (strict mode)' if test_run.strict_mode else ''}"
                        )
                        if test_run.output:
                            self.print_output("")
                            self.print_output(test_run.output)
                            self.print_output("")

                        if test_run.exit_code:
                            signalnum = test_run.exit_code * -1
                            if not test_run.output:
                                self.print_output("")
                                self.print_output(
                                    f"{signal.strsignal(signalnum)}: {signalnum}"
                                )
                                self.print_output("")

        if not self.silent:
            progressbar.close()

        end = datetime.datetime.now()
        self.duration = end - start

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
        default=None,
        type=str,
        metavar="PATH",
        help="output per-file results to file",
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
    parser.add_argument(
        "--parse-only",
        action="store_true",
        help="only parse the test files and fail/pass based on that",
    )
    parser.add_argument(
        "--ignore",
        default="",
        help="ignore any tests matching the glob",
    )
    parser.add_argument(
        "--forward-stderr",
        action="store_true",
        help="forward all stderr output to the stderr of the script",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="only show the top level results",
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
        args.per_file is not None,
        args.fail_only,
        args.parse_only,
        args.forward_stderr,
        args.summary,
    )
    runner.find_tests(args.pattern, args.ignore)
    runner.run()
    if args.json:
        data = {
            "duration": runner.duration.total_seconds(),
            "results": runner.directory_result_map,
        }
        print(json.dumps(data))
    else:
        runner.report()

    if args.per_file is not None:
        data = {
            "duration": runner.duration.total_seconds(),
            "results": runner.file_result_map,
        }
        with open(args.per_file, "w") as per_file_file:
            json.dump(data, per_file_file)


if __name__ == "__main__":
    os.setpgrp()
    try:
        main()
    except KeyboardInterrupt:
        os.killpg(0, signal.SIGKILL)
