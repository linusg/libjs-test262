import datetime
import re
import shlex
import subprocess
from argparse import ArgumentParser
from enum import Enum, auto
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Optional, Tuple

from ruamel.yaml import YAML


# https://github.com/tc39/test262/blob/master/INTERPRETING.md

UNCAUGHT_EXCEPTION_REGEX = re.compile(
    r"Uncaught exception: (?:\[(.*)\]|\"([a-zA-Z0-9]+)(?:.*)\")", re.MULTILINE
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
    METADATA_ERROR = auto()
    LOAD_ERROR = auto()
    TIMEOUT_ERROR = auto()
    SUCCESS = auto()
    FAILURE = auto()


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
        load_includes = f"{load_includes} load('{include_path}');"
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
        cmd = f"{js} -t {tmp_file.name}"
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
    has_syntax_error = "Parse error" in output or "Error: Unexpected token" in output
    has_load_error = "Failed to open Error:" in output
    has_uncaught_exception = "Uncaught exception:" in output

    if has_load_error:
        return test_result(TestResult.LOAD_ERROR)

    if metadata.get("negative") is not None:
        phase = metadata["negative"]["phase"]
        type_ = metadata["negative"]["type"]
        if phase == "parse":
            return success_if(has_syntax_error)
        elif phase == "runtime":
            matches = re.findall(UNCAUGHT_EXCEPTION_REGEX, output)
            return success_if(matches and matches[0] == type_)
        else:
            # Others are 'early' and 'resolution', LibJS
            # doesn't support failures in those phases
            return failure()

    if has_syntax_error or has_uncaught_exception:
        return failure()

    return success()


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
        "--timeout",
        default=10,
        type=int,
        help="timeout for each test run in seconds (defaults to 10)",
    )
    args = parser.parse_args()

    js = Path(args.js).resolve()
    test262 = Path(args.test262).resolve()

    print("Searching test files...")
    if Path(args.pattern).resolve().is_file():
        test_files = [Path(args.pattern).resolve()]
    else:
        test_files = [
            path.resolve()
            for path in test262.glob(args.pattern)
            if path.is_file() and not path.stem.endswith("FIXTURE")
        ]
    total_tests = len(test_files)
    print(f"Found {total_tests}.")

    remaining_tests = total_tests
    passed_tests = 0
    failed_tests = 0

    start_time = datetime.datetime.now()
    try:
        for i, test_file in enumerate(test_files):
            if args.verbose:
                print(f"Running test: {test_file}")
            test_result, output = run_test(js, test262, test_file, timeout=args.timeout)
            if test_result == TestResult.SUCCESS:
                passed_tests += 1
                emoji = "✅"
            elif test_result == TestResult.FAILURE:
                failed_tests += 1
                emoji = "❌"
            elif test_result == TestResult.TIMEOUT_ERROR:
                failed_tests += 1
                emoji = "💀"
            elif (
                test_result == TestResult.METADATA_ERROR
                or test_result == TestResult.LOAD_ERROR
            ):
                failed_tests += 1
                emoji = "⚠️"
            else:
                assert False
            remaining_tests -= 1
            progress = int((total_tests - remaining_tests) / total_tests * 100)
            print(f"[{progress:>3}%] {emoji} {test_file.relative_to(test262)}")
            if args.verbose and output.strip():
                print(output)
    except KeyboardInterrupt:
        pass
    end_time = datetime.datetime.now()

    print("----------------")
    print(f"Tests: {total_tests}")
    if remaining_tests:
        print(f"Remaining: {remaining_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {failed_tests}")
    print(f"Duration: {end_time-start_time}")


if __name__ == "__main__":
    main()
