# LibJS test262

> Run the [Official ECMAScript Conformance Test Suite](https://github.com/tc39/test262) with [SerenityOS](https://github.com/SerenityOS/serenity)'s [`LibJS`](https://github.com/SerenityOS/serenity/tree/master/Userland/Libraries/LibJS)

## Installation

Install `git`, `cmake`, `ninja`, `gcc`/`clang` and `python3` (3.8+).

To install the script's dependencies, run:

```console
pip3 install -r requirements.txt
```

Dependencies are:

- `ruamel.yaml` for parsing the test's YAML metadata
- `tqdm` for displaying a progress bar

## Usage

To clone test262, clone SerenityOS, build Lagom, and build `libjs-test262-runner`, run:

```console
./setup.sh
```

The repositories will only be cloned if they don't exist yet locally, so you
can use this script for development of the test runner as well.

If `SERENITY_SOURCE_DIR` is set, it will be used instead. However, if the Lagom
build directory already exists, the script will not touch your build in that
case, so you'll need to build `libLagom.a` yourself.

Once that's done, run:

```console
python3 main.py --libjs-test262-runner ./Build/libjs-test262-runner --test262-root ./test262/
```

## Options

```text
usage: main.py [-h] -j PATH [-b] -t PATH [-p PATTERN] [-c CONCURRENCY] [--timeout TIMEOUT] [--memory-limit MEMORY_LIMIT] [--json] [--per-file] [-s | -v] [-f]

Run the test262 ECMAScript test suite with SerenityOS's LibJS

optional arguments:
  -h, --help            show this help message and exit
  -j PATH, --libjs-test262-runner PATH
                        path to the 'libjs-test262-runner' binary
  -b, --use-bytecode    Use the bytecode interpreter to run the tests
  -t PATH, --test262-root PATH
                        path to the 'test262' directory
  -p PATTERN, --pattern PATTERN
                        glob pattern used for test file searching (defaults to test/**/*.js)
  -c CONCURRENCY, --concurrency CONCURRENCY
                        number of concurrent workers (defaults to number of CPU cores * 5)
  --timeout TIMEOUT     timeout for each test run in seconds (defaults to 10)
  --memory-limit MEMORY_LIMIT
                        memory limit for each test run in megabytes (defaults to 512)
  --json                print the test results as JSON
  --per-file            show per-file results instead of per-directory results
  -s, --silent          don't print any progress information
  -v, --verbose         print output of test runs
  -f, --fail-only       only show failed tests
```

## Current status

Most of the tests run to completion and yield correct results. Few of the test
harness files do not parse yet or generate runtime errors, those are listed in
the results under a separate category, as are tests that fail to parse their
metadata, time out, or crash the engine (todo assertion failures, mostly).
