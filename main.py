from __future__ import annotations

import concurrent.futures
import json
import multiprocessing
import os
import re
import shlex
import signal
import subprocess
import traceback
from argparse import ArgumentParser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, List, Optional

from colors import strip_color
from ruamel.yaml import YAML
from tqdm import tqdm

# https://github.com/tc39/test262/blob/master/INTERPRETING.md

UNCAUGHT_EXCEPTION_ERROR_NAME_REGEX = re.compile(
    r"Uncaught exception: \[(.+)\]", re.MULTILINE
)
TEST_SCRIPT = """\
const print = console.log;
const $262 = {{
    /* createRealm: ?, */
    /* detachArrayBuffer: ?, */
    /* evalScript: ?, */
    gc: gc,
    global: globalThis,
    agent: {{ /* ... */ }}
}};
load('{harness_assert_path}');
load('{harness_sta_path}');
{load_includes}
load('{test_file_path}');
"""


class TestResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    METADATA_ERROR = "METADATA_ERROR"
    LOAD_ERROR = "LOAD_ERROR"
    TIMEOUT_ERROR = "TIMEOUT_ERROR"
    RUNNER_EXCEPTION = "RUNNER_EXCEPTION"


@dataclass
class TestRun:
    file: Path
    result: TestResult
    output: str


EMOJIS = {
    TestResult.METADATA_ERROR: "⚠️",
    TestResult.LOAD_ERROR: "⚠️",
    TestResult.RUNNER_EXCEPTION: "💥",
    TestResult.TIMEOUT_ERROR: "💀",
    TestResult.FAILURE: "❌",
    TestResult.SUCCESS: "✅",
}

CPU_COUNT = multiprocessing.cpu_count()


def get_metadata(test_file: Path) -> Optional[dict]:
    lines = test_file.resolve().read_text().splitlines()
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip() == "/*---":
            start = i + 1
        if line.strip() == "---*/":
            end = i
    if start is None or end is None:
        return None
    return dict(YAML().load("\n".join(lines[start:end])))


def build_script(test262: Path, test_file: Path, includes: Iterable[str]) -> str:
    harness_assert_path = (test262 / "harness" / "assert.js").resolve()
    harness_sta_path = (test262 / "harness" / "sta.js").resolve()
    test_file_path = test_file.resolve()
    load_includes = ""
    for include in includes:
        include_path = (test262 / "harness" / include).resolve()
        load_includes += f"load('{include_path}');\n"
    script = TEST_SCRIPT.format(
        harness_assert_path=harness_assert_path,
        harness_sta_path=harness_sta_path,
        load_includes=load_includes,
        test_file_path=test_file_path,
    )
    return script


def run_script(js: Path, script: str, timeout: float) -> str:
    with NamedTemporaryFile(mode="w", suffix="js") as tmp_file:
        tmp_file.write(script)
        tmp_file.flush()
        cmd = f"{js} {tmp_file.name}"
        result = subprocess.run(
            shlex.split(cmd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
        )
    return result.stdout.strip()


def run_test(js: Path, test262: Path, file: Path, timeout: float) -> TestRun:
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

    script = build_script(test262, file, metadata.get("includes", []))
    try:
        output = run_script(js, script, timeout)
    except subprocess.TimeoutExpired:
        output = ""
        return test_run(TestResult.TIMEOUT_ERROR)
    except:
        output = traceback.format_exc()
        return test_run(TestResult.RUNNER_EXCEPTION)

    error_name_matches = re.findall(
        UNCAUGHT_EXCEPTION_ERROR_NAME_REGEX, strip_color(output)
    )
    error_name = error_name_matches[0] if error_name_matches else None
    has_uncaught_exception = "Uncaught exception:" in output
    has_syntax_error = has_uncaught_exception and error_name == "SyntaxError"
    has_load_error = has_uncaught_exception and "Failed to open" in output

    if has_load_error:
        return test_run(TestResult.LOAD_ERROR)

    if metadata.get("negative") is not None:
        phase = metadata["negative"]["phase"]
        type_ = metadata["negative"]["type"]
        if phase == "parse" or phase == "early":
            # FIXME: This shouldn't apply to a runtime SyntaxError
            return success_if(has_syntax_error)
        elif phase == "runtime":
            return success_if(error_name == type_)
        elif phase == "resolution":
            # No modules yet :^)
            return failure()
        else:
            raise Exception(f"Unexpected phase '{phase}'")

    if has_syntax_error or has_uncaught_exception:
        return failure()

    return success()


class Runner:
    def __init__(
        self,
        js: Path,
        test262: Path,
        concurrency: int,
        timeout: int,
        silent: bool = False,
        verbose: bool = False,
    ) -> None:
        self.js = js
        self.test262 = test262
        self.concurrency = concurrency
        self.timeout = timeout
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
                for path in self.test262.glob(pattern)
                if path.is_file() and not path.stem.endswith("FIXTURE")
            ]
        self.files.sort()
        self.total_count = len(self.files)
        self.log(f"Found {self.total_count}.")
        self.build_result_map()

    def build_result_map(self) -> None:
        for file in self.files:
            directory = file.relative_to(self.test262).parent
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
        directory = test_run.file.relative_to(self.test262).parent
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
        return run_test(self.js, self.test262, file, timeout=self.timeout)

    def run(self) -> None:
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
                    out = ""
                    if test_run.output:
                        out = test_run.output.replace("\n", "\n    ")
                        out = f" :\n{out}\n"
                    print(f"{EMOJIS[test_run.result]}  {test_run.file}{out}")
                    progressbar.refresh()
                if not self.silent:
                    progressbar.update(1)
                self.progress += 1

        if not self.silent:
            progressbar.close()
        self.log("Finished running tests.")


def main() -> None:
    parser = ArgumentParser(
        description="Run the test262 ECMAScript test suite with SerenityOS's LibJS"
    )
    parser.add_argument(
        "-j",
        "--js",
        required=True,
        metavar="PATH",
        help="path to the SerenityOS Lagom 'js' binary",
    )
    parser.add_argument(
        "-t",
        "--test262",
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
        help="number of concurrent workers",
    )
    parser.add_argument(
        "--timeout",
        default=10,
        type=int,
        help="timeout for each test run in seconds (defaults to 10)",
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
        Path(args.js).resolve(),
        Path(args.test262).resolve(),
        args.concurrency,
        args.timeout,
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
