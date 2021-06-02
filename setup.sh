#!/usr/bin/env sh

SERENITY_SOURCE_DIR="${SERENITY_SOURCE_DIR:-serenity}"
TEST262_SOURCE_DIR="${TEST262_SOURCE_DIR:-test262}"
LAGOM_BUILD_DIR="${SERENITY_SOURCE_DIR}/Build/lagom"
# Lagom-only build with cmake ../../Meta/Lagom
LAGOM_STATIC_LIB_1="${LAGOM_BUILD_DIR}/libLagom.a"
# Full build with cmake ../..
LAGOM_STATIC_LIB_2="${LAGOM_BUILD_DIR}/Meta/Lagom/libLagom.a"
LIBJS_TEST262_BUILD_DIR="Build"

log() {
    echo -e "\033[0;34m[${1}]\033[0m ${2}"
}

if [[ ! -d "${SERENITY_SOURCE_DIR}" ]]; then
    log serenity "Source directory not found, cloning repository"
    git clone --depth 1 https://github.com/SerenityOS/serenity.git
fi

if [[ ! -d "${TEST262_SOURCE_DIR}" ]]; then
    log test262 "Source directory not found, cloning repository"
    git clone --depth 1 https://github.com/tc39/test262.git
fi

if [[ -d "${LAGOM_BUILD_DIR}" ]]; then
    # If you got your own serenity source tree and build, we're not going to mess with it.
    if [[ -f "${LAGOM_STATIC_LIB_1}" ]]; then
        log Lagom "Using existing Lagom build at ${LAGOM_STATIC_LIB_1}"
    elif [[ -f "${LAGOM_STATIC_LIB_2}" ]]; then
        log Lagom "Using existing Lagom build at ${LAGOM_STATIC_LIB_2}"
    else
        # We can warn you if libLagom.a does not exist, though.
        log Lagom "ERROR: The Lagom build directory already exists but libLagom.a wasn't found, build it first!"
        exit 1
    fi
else
    mkdir -p "${LAGOM_BUILD_DIR}"
    pushd "${LAGOM_BUILD_DIR}"
        log Lagom "Running CMake..."
        cmake -GNinja -DBUILD_LAGOM=ON ../../Meta/Lagom

        log Lagom "Building..."
        ninja libLagom.a
    popd
fi

mkdir -p "${LIBJS_TEST262_BUILD_DIR}"
pushd "${LIBJS_TEST262_BUILD_DIR}"
    log libjs-test262-runner "Running CMake..."
    export SERENITY_SOURCE_DIR="${SERENITY_SOURCE_DIR}"
    cmake -GNinja ..

    log libjs-test262-runner "Building..."
    ninja libjs-test262-runner
popd
