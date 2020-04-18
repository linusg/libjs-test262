# LibJS test262

> Run the [Official ECMAScript Conformance Test Suite](https://github.com/tc39/test262) with [SerenityOS](https://github.com/SerenityOS/serenity)'s [`LibJS`](https://github.com/SerenityOS/serenity/tree/master/Libraries/LibJS)

## Installation

Install `git`, `make`, `cmake`, `gcc`/`clang` and `python3` (3.6+).

To install the script's dependencies, run:

```console
$ pip3 install -r requirements.txt
```

The only dependency for now is `ruamel.yaml` for parsing the test's YAML metadata.

## Usage

To clone test262, clone SerenityOS and build `js` (standalone as part of Lagom), run:

```console
$ ./setup.sh
```

If this succeeds, run:

```console
$ python3 main.py --js ./serenity/Meta/Lagom/build/js --test262 ./test262/
```

## Options

```
usage: main.py [-h] -j JS -t TEST262 [-p PATTERN] [-v] [--timeout TIMEOUT]

Run the test262 ECMAScript test suite with SerenityOS's LibJS

optional arguments:
  -h, --help            show this help message and exit
  -j JS, --js JS        path to the SerenityOS Lagom 'js' binary
  -t TEST262, --test262 TEST262
                        path to the 'test262' directory
  -p PATTERN, --pattern PATTERN
                        glob pattern used for test file searching (defaults to
                        test/**/*.js)
  -v, --verbose         print output of test runs
  --timeout TIMEOUT     timeout for each test run in seconds (defaults to 10)
```

## Current status

As many of the testing utilities in test262's harness fail, the results are more
or less useless. You'll see a few passing tests, but once LibJS can fully parse
and execute those this will be more useful!

## Testing the test harness

Run:

```console
$ ./test-harness.sh
```

This will run all the JavaScript files in `test262/harness` through `js` and report
if a syntax or runtime error occurred.

As of 2020-04-18:

```
arrayContains.js              Success!
assert.js                     Success!
assertRelativeDateMs.js       Success!
async-gc.js                   Syntax Error
atomicsHelper.js              Syntax Error
byteConversionValues.js       Success!
compareArray.js               Syntax Error
compareIterator.js            Runtime Error
dateConstants.js              Success!
decimalToHexString.js         Syntax Error
deepEqual.js                  Syntax Error
detachArrayBuffer.js          Success!
doneprintHandle.js            Syntax Error
fnGlobalObject.js             Success!
isConstructor.js              Success!
nans.js                       Runtime Error
nativeFunctionMatcher.js      Syntax Error
promiseHelper.js              Syntax Error
propertyHelper.js             Syntax Error
proxyTrapsHelper.js           Success!
regExpUtils.js                Syntax Error
sta.js                        Success!
tcoHelper.js                  Success!
testAtomics.js                Syntax Error
testBigIntTypedArray.js       Runtime Error
testIntl.js                   Syntax Error
testTypedArray.js             Runtime Error
timer.js                      Syntax Error
typeCoercion.js               Syntax Error
wellKnownIntrinsicObjects.js  Syntax Error
```
