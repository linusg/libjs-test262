cmake_minimum_required(VERSION 3.16)
project(libjs-test262 CXX)
include(ExternalProject)

if (NOT DEFINED ENV{SERENITY_SOURCE_DIR})
    message(FATAL_ERROR "SERENITY_SOURCE_DIR not set.")
endif()

get_filename_component(SERENITY_SOURCE_DIR $ENV{SERENITY_SOURCE_DIR} ABSOLUTE)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Copied from Serenity's root CMakeLists.txt
add_compile_options(-Wall)
add_compile_options(-Wextra)
add_compile_options(-Wno-address-of-packed-member)
add_compile_options(-Wcast-align)
add_compile_options(-Wcast-qual)
add_compile_options(-Wno-deprecated-copy)
add_compile_options(-Wduplicated-cond)
add_compile_options(-Wdouble-promotion)
add_compile_options(-Wno-expansion-to-defined)
add_compile_options(-Wformat=2)
add_compile_options(-Wimplicit-fallthrough)
add_compile_options(-Wno-literal-suffix)
add_compile_options(-Wlogical-op)
add_compile_options(-Wmisleading-indentation)
add_compile_options(-Wmissing-declarations)
add_compile_options(-Wno-nonnull-compare)
add_compile_options(-Wnon-virtual-dtor)
add_compile_options(-Wno-unknown-warning-option)
add_compile_options(-Wundef)
add_compile_options(-Wunused)
add_compile_options(-Wwrite-strings)
add_compile_options(-fno-exceptions)

set(SERENITY_LIBRARIES_DIR ${SERENITY_SOURCE_DIR}/Userland/Libraries)
set(LAGOM_SOURCE_DIR ${SERENITY_SOURCE_DIR}/Meta/Lagom)
set(LAGOM_BINARY_DIR ${SERENITY_SOURCE_DIR}/Build/Lagom)
set(LAGOM_INSTALL_DIR ${CMAKE_CURRENT_BINARY_DIR}/Lagom)

# NOTE: Name can't be Lagom because it conflicts with libLagom.a
ExternalProject_Add(LagomProject
    SOURCE_DIR ${LAGOM_SOURCE_DIR}
    BINARY_DIR ${LAGOM_BINARY_DIR}
    INSTALL_DIR ${LAGOM_INSTALL_DIR}
    CMAKE_ARGS "-DBUILD_LAGOM=ON"
    CMAKE_ARGS "-DCMAKE_INSTALL_PREFIX=<INSTALL_DIR>"
    BUILD_COMMAND ${CMAKE_COMMAND} --build <BINARY_DIR> --config $<CONFIG>
    BUILD_ALWAYS ON)

set(SOURCES
    src/$262Object.cpp
    src/AgentObject.cpp
    src/GlobalObject.cpp
    src/main.cpp
)

add_executable(libjs-test262-runner ${SOURCES})
add_dependencies(libjs-test262-runner LagomProject)
target_include_directories(libjs-test262-runner
    PUBLIC ${SERENITY_SOURCE_DIR}
    PUBLIC ${SERENITY_LIBRARIES_DIR}
)

target_link_directories(libjs-test262-runner PUBLIC ${LAGOM_INSTALL_DIR}/lib)
target_link_libraries(libjs-test262-runner pthread Lagom)
