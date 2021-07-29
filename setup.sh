#!/usr/bin/env bash
TEST262_SOURCE_DIR="${TEST262_SOURCE_DIR:-test262}"
LIBJS_TEST262_BUILD_DIR="Build"

log() {
    echo -e "\033[0;34m[${1}]\033[0m ${2}"
}

if [[ ! -d "${TEST262_SOURCE_DIR}" ]]; then
    log test262 "Source directory not found, cloning repository"
    git clone --depth 1 https://github.com/tc39/test262.git
fi

mkdir -p "${LIBJS_TEST262_BUILD_DIR}"
pushd "${LIBJS_TEST262_BUILD_DIR}"
    log libjs-test262-runner "Running CMake..."
    cmake -GNinja .. -DSERENITY_SOURCE_DIR="${SERENITY_SOURCE_DIR}"

    log libjs-test262-runner "Building..."
    cmake --build .
popd
