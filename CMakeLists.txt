cmake_minimum_required(VERSION 3.16)
project(libjs-test262 CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(CMAKE_SKIP_BUILD_RPATH FALSE)
set(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)
# See slide 100 of the following ppt :^)
# https://crascit.com/wp-content/uploads/2019/09/Deep-CMake-For-Library-Authors-Craig-Scott-CppCon-2019.pdf
if (NOT APPLE)
    set(CMAKE_INSTALL_RPATH $ORIGIN)
endif()
set(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

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

include (FetchContent)
include (cmake/FetchLagom.cmake)

find_package(Threads REQUIRED)

set(SOURCES
    src/$262Object.cpp
    src/AgentObject.cpp
    src/GlobalObject.cpp
    src/IsHTMLDDA.cpp
    src/main.cpp
)

add_executable(libjs-test262-runner ${SOURCES})
target_link_libraries(libjs-test262-runner Threads::Threads Lagom::Core Lagom::JS)
install(TARGETS libjs-test262-runner RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX})
