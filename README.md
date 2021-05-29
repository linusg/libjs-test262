# LibJS test262

> Run the [Official ECMAScript Conformance Test Suite](https://github.com/tc39/test262) with [SerenityOS](https://github.com/SerenityOS/serenity)'s [`LibJS`](https://github.com/SerenityOS/serenity/tree/master/Libraries/LibJS)

## Installation

Install `git`, `cmake`, `ninja`, `gcc`/`clang` and `python3` (3.7+).

To install the script's dependencies, run:

```console
pip3 install -r requirements.txt
```

Dependencies are:

- `ansicolors` for stripping color codes from the output
- `ruamel.yaml` for parsing the test's YAML metadata
- `tqdm` for displaying a progress bar

## Usage

To clone test262, clone SerenityOS and build `js` (standalone as part of Lagom), run:

```console
./setup.sh
```

If this succeeds, run:

```console
python3 main.py --js ./serenity/Build/js --test262 ./test262/
```

## Options

```text
usage: main.py [-h] -j PATH -t PATH [-p PATTERN] [-c CONCURRENCY] [--timeout TIMEOUT] [--memory-limit MEMORY_LIMIT] [--json] [-s | -v]

Run the test262 ECMAScript test suite with SerenityOS's LibJS

optional arguments:
  -h, --help            show this help message and exit
  -j PATH, --js PATH    path to the SerenityOS Lagom 'js' binary
  -t PATH, --test262 PATH
                        path to the 'test262' directory
  -p PATTERN, --pattern PATTERN
                        glob pattern used for test file searching (defaults to test/**/*.js)
  -c CONCURRENCY, --concurrency CONCURRENCY
                        number of concurrent workers (defaults to number of CPU cores)
  --timeout TIMEOUT     timeout for each test run in seconds (defaults to 10)
  --memory-limit MEMORY_LIMIT
                        memory limit for each test run in megabytes (defaults to 512)
  --json                print the test results as JSON
  -s, --silent          don't print any progress information
  -v, --verbose         print output of test runs
```

## Current status

As some of the testing utilities in test262's harness still fail to parse, the
results are more or less useless. You'll see a few passing tests, but once
LibJS can fully parse and execute them this will be more useful!

## Testing the test harness

Run:

```console
./test-harness.sh
```

This will try to run all the JavaScript files in `test262/harness` through `js`
and report if a syntax error occurred. Run the actual tests as described above
to check for runtime errors, as some files depend on others.

As of 2021-05-29:

```text
[ PASS ] arrayContains.js
[ PASS ] assert.js
[ PASS ] assertRelativeDateMs.js
[ FAIL ] async-gc.js
[ FAIL ] atomicsHelper.js
[ PASS ] byteConversionValues.js
[ PASS ] compareArray.js
[ PASS ] compareIterator.js
[ PASS ] dateConstants.js
[ PASS ] decimalToHexString.js
[ PASS ] deepEqual.js
[ PASS ] detachArrayBuffer.js
[ PASS ] doneprintHandle.js
[ PASS ] fnGlobalObject.js
[ FAIL ] hidden-constructors.js
[ PASS ] isConstructor.js
[ PASS ] nans.js
[ PASS ] nativeFunctionMatcher.js
[ PASS ] promiseHelper.js
[ PASS ] propertyHelper.js
[ PASS ] proxyTrapsHelper.js
[ PASS ] regExpUtils.js
[ PASS ] sta.js
[ PASS ] tcoHelper.js
[ PASS ] testAtomics.js
[ PASS ] testBigIntTypedArray.js
[ PASS ] testIntl.js
[ PASS ] testTypedArray.js
[ PASS ] timer.js
[ PASS ] typeCoercion.js
[ PASS ] wellKnownIntrinsicObjects.js
```
