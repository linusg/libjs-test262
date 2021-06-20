cmake_minimum_required(VERSION 3.16)
project(libjs-test262 CXX)

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

# FIXME: I have not idea how to CMake :^)
if(EXISTS ${SERENITY_SOURCE_DIR}/Build/lagom/libLagom.a)
    # Lagom-only build with cmake ../../Meta/Lagom
    set(LIBLAGOM_PATH ${SERENITY_SOURCE_DIR}/Build/lagom/libLagom.a)
elseif(EXISTS ${SERENITY_SOURCE_DIR}/Build/lagom/Meta/Lagom/libLagom.a)
    # Full build with cmake ../..
    set(LIBLAGOM_PATH ${SERENITY_SOURCE_DIR}/Build/lagom/Meta/Lagom/libLagom.a)
else()
    message(FATAL_ERROR "libLagom.a not found!")
endif()

set(SOURCES
    src/$262Object.cpp
    src/AgentObject.cpp
    src/GlobalObject.cpp
    src/IsHTMLDDA.cpp
    src/main.cpp
)

add_executable(libjs-test262-runner ${SOURCES})
target_include_directories(libjs-test262-runner
    PUBLIC ${SERENITY_SOURCE_DIR}
    PUBLIC ${SERENITY_LIBRARIES_DIR}
)
target_link_libraries(libjs-test262-runner pthread ${LIBLAGOM_PATH})
