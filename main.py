import concurrent.futures
import multiprocessing
import os
import re
import shlex
import signal
import subprocess
import traceback
from argparse import ArgumentParser
from enum import Enum, auto
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Optional, Tuple

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


class TestResult(Enum):
    SUCCESS = auto()
    FAILURE = auto()
    METADATA_ERROR = auto()
    LOAD_ERROR = auto()
    TIMEOUT_ERROR = auto()
    RUNNER_EXCEPTION = auto()


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


def run_test(
    js: Path, test262: Path, test_file: Path, timeout: float
) -> Tuple[TestResult, str]:
    def test_result(test_result: TestResult) -> Tuple[TestResult, str]:
        return test_result, output

    def failure() -> Tuple[TestResult, str]:
        return test_result(TestResult.FAILURE)

    def success() -> Tuple[TestResult, str]:
        return test_result(TestResult.SUCCESS)

    def success_if(condition: Any) -> Tuple[TestResult, str]:
        return test_result(TestResult.SUCCESS if condition else TestResult.FAILURE)

    output = ""
    metadata = get_metadata(test_file)
    if metadata is None:
        return test_result(TestResult.METADATA_ERROR)

    script = build_script(test262, test_file, metadata.get("includes", []))
    try:
        output = run_script(js, script, timeout)
    except subprocess.TimeoutExpired:
        return test_result(TestResult.TIMEOUT_ERROR)
    except:
        output = traceback.format_exc()
        return test_result(TestResult.RUNNER_EXCEPTION)

    error_name_matches = re.findall(
        UNCAUGHT_EXCEPTION_ERROR_NAME_REGEX, strip_color(output)
    )
    error_name = error_name_matches[0] if error_name_matches else None
    has_uncaught_exception = "Uncaught exception:" in output
    has_syntax_error = has_uncaught_exception and error_name == "SyntaxError"
    has_load_error = has_uncaught_exception and "Failed to open" in output

    if has_load_error:
        return test_result(TestResult.LOAD_ERROR)

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
    def __init__(self, concurrency: int, timeout: int) -> None:
        self.concurrency = concurrency
        self.timeout = timeout
        self.test262 = None
        self.js = None
        self.files = []
        self.result_map = {}
        self.total_count = 0
        self.progress = 0
        self.verbose = False

    def set_verbose(self, verbose: bool) -> None:
        self.verbose = verbose

    def set_interpreter(self, js_path: str) -> None:
        self.js = Path(js_path).resolve()

    def find_tests(self, base_path: str, pattern: str) -> None:
        self.test262 = Path(base_path).resolve()
        print("Searching test files...")
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
        print(f"Found {self.total_count}.")
        self.build_result_map()

    def build_result_map(self) -> None:
        for path in self.files:
            p = Path(path).relative_to(self.test262).parent
            counter = self.result_map
            for segment in p.parts:
                if not segment in counter:
                    counter[segment] = {"count": 1, "results": {}, "children": {}}
                    for r in TestResult:
                        counter[segment]["results"][r] = 0
                else:
                    counter[segment]["count"] += 1
                counter = counter[segment]["children"]

    def count_result(self, result) -> None:
        file, test_result, output = result
        p = file.relative_to(self.test262).parent
        counter = self.result_map
        for segment in p.parts:
            counter[segment]["results"][test_result] += 1
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

    def process(self, file: Path) -> Tuple[Path, TestResult, str]:
        test_result, output = run_test(
            self.js, self.test262, file, timeout=self.timeout
        )

        return (file, test_result, output)

    def run(self) -> None:
        self.progressbar = tqdm(
            total=self.total_count, mininterval=1, unit="tests", smoothing=0.1
        )
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.concurrency
        ) as executor:
            futures = {executor.submit(self.process, f) for f in self.files}
            for future in concurrent.futures.as_completed(futures):
                file, test_result, output = future.result()
                self.count_result((file, test_result, output))
                if self.verbose:
                    out = ""
                    if len(output) > 0:
                        out = output.replace("\n", "\n    ")
                        out = f" :\n{out}\n"
                    print(f"{EMOJIS[test_result]}  {file}{out}")
                    self.progressbar.refresh()
                self.progress += 1
                self.progressbar.update(1)

        self.progressbar.close()
        print("Finished running tests.")


def main() -> None:
    parser = ArgumentParser(
        description="Run the test262 ECMAScript test suite with SerenityOS's LibJS"
    )
    parser.add_argument(
        "-j", "--js", required=True, help="path to the SerenityOS Lagom 'js' binary"
    )
    parser.add_argument(
        "-t", "--test262", required=True, help="path to the 'test262' directory"
    )
    parser.add_argument(
        "-p",
        "--pattern",
        default="test/**/*.js",
        help="glob pattern used for test file searching (defaults to test/**/*.js)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="print output of test runs"
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
    args = parser.parse_args()

    runner = Runner(args.concurrency, args.timeout)
    runner.set_verbose(args.verbose)
    runner.set_interpreter(args.js)
    runner.find_tests(args.test262, args.pattern)
    runner.run()
    runner.report()


if __name__ == "__main__":
    os.setpgrp()
    try:
        main()
    except KeyboardInterrupt:
        os.killpg(0, signal.SIGKILL)
