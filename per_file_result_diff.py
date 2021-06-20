# Copyright (c) 2021, Matthew Olsson <mattco@serenityos.org>
#
# SPDX-License-Identifier: MIT

import json
from argparse import ArgumentParser
from pathlib import Path
from main import TestResult, EMOJIS


class ResultParser:
    def __init__(self, old_path: Path, new_path: Path, regressions: bool) -> None:
        old_results = json.loads(old_path.read_text())
        new_results = json.loads(new_path.read_text())

        self.duration_delta = float(new_results["duration"]) - float(
            old_results["duration"]
        )
        self.old_results: dict[str, str] = old_results["results"]
        self.new_results: dict[str, str] = new_results["results"]
        self.regressions = regressions

        self.new_tests: dict[str, str] = {}
        self.removed_tests: dict[str, str] = {}
        self.diff_tests: dict[str, dict] = {}

        self.summary: dict = {
            "new_tests": {},
            "removed_tests": {},
            "diff_tests": {},
        }

        self.summary_column_widths: dict[str, int] = {}
        self.longest_path_length = 0

        self.populate_test_dicts()
        self.populate_summary_dicts()

    def populate_test_dicts(self) -> None:
        for path, result in self.old_results.items():
            new_result = self.new_results[path]

            if new_result is None:
                self.longest_path_length = max(self.longest_path_length, len(path))
                self.removed_tests[path] = result
            elif result != new_result:
                self.longest_path_length = max(self.longest_path_length, len(path))
                self.diff_tests[path] = {
                    "old_result": result,
                    "new_result": new_result,
                }

        for path, result in self.new_results.items():
            if path not in self.old_results:
                self.longest_path_length = max(self.longest_path_length, len(path))
                self.new_tests[path] = result

    def populate_summary_dicts(self) -> None:
        # Initialize all results to zero
        for summary in self.summary.values():
            for k in TestResult:
                summary[k] = 0

        for result in self.new_tests.values():
            self.summary["new_tests"][result] += 1

        for result in self.removed_tests.values():
            self.summary["removed_tests"][result] += 1

        for result in self.diff_tests.values():
            self.summary["diff_tests"][result["old_result"]] -= 1
            self.summary["diff_tests"][result["new_result"]] += 1

        # Calculate summary column widths to make the summary look better
        for v in TestResult:
            self.summary_column_widths[v] = max(
                len(str(self.summary["new_tests"][v])) + 1,
                len(str(self.summary["removed_tests"][v])) + 1,
                len(str(self.summary["diff_tests"][v])) + 1,
            )

    def print_summary_results(self, summary_map: dict) -> None:
        for v in TestResult:
            print(
                f"{summary_map[v]:+{self.summary_column_widths[v]}d} {EMOJIS[v]}   ",
                end="",
            )

    def print_full_results(self) -> None:
        print("Duration:")
        print(f"     {self.duration_delta:+.2f}s")

        has_new_tests = len(self.new_tests) > 0
        has_removed_tests = len(self.removed_tests) > 0
        has_diff_tests = len(self.diff_tests) > 0

        if not has_new_tests and not has_removed_tests and not has_diff_tests:
            return

        print()
        print("Summary:")

        if has_new_tests:
            print("    New Tests:\n        ", end="")
            self.print_summary_results(self.summary["new_tests"])
            print()

        if has_removed_tests:
            print("    Removed Tests:\n        ", end="")
            self.print_summary_results(self.summary["removed_tests"])
            print()

        if has_diff_tests:
            print("    Diff Tests:\n        ", end="")
            self.print_summary_results(self.summary["diff_tests"])
            print()

        print()

        if has_new_tests:
            print("New Tests:")
            for path, result in self.new_tests.items():
                print(f"    {path:{self.longest_path_length}s} {EMOJIS[result]}")
            print()

        if has_removed_tests:
            print("Removed Tests:")
            for path, result in self.removed_tests.items():
                print(f"    {path:{self.longest_path_length}s} {EMOJIS[result]}")
            print()

        if has_diff_tests:
            print("Diff Tests:")
            for path, result in self.diff_tests.items():
                old_emoji = EMOJIS[result["old_result"]]
                new_emoji = EMOJIS[result["new_result"]]
                print(
                    f"    {path:{self.longest_path_length}s} {old_emoji} -> {new_emoji}"
                )

    def print_regressions(self) -> None:
        for path, result in self.diff_tests.items():
            if result["old_result"] == "PASSED":
                old_emoji = EMOJIS[TestResult.PASSED]
                new_emoji = EMOJIS[result["new_result"]]
                print(
                    f"    {path:{self.longest_path_length}s} {old_emoji} -> {new_emoji}"
                )

    def print_results(self) -> None:
        if self.regressions:
            self.print_regressions()
        else:
            self.print_full_results()


def main() -> None:
    parser = ArgumentParser(description="Compare per-file test262 results")
    parser.add_argument(
        "-o", "--old", required=True, metavar="PATH", help="the path to the old results"
    )
    parser.add_argument(
        "-n", "--new", required=True, metavar="PATH", help="the path to the new results"
    )
    parser.add_argument(
        "-r",
        "--regressions",
        action="store_true",
        help="only show regressions",
    )
    args = parser.parse_args()

    ResultParser(Path(args.old), Path(args.new), args.regressions).print_results()


if __name__ == "__main__":
    main()
