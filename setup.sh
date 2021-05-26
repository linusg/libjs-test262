#!/usr/bin/env sh

printf "Removing cloned serenity repo... "
rm -rf serenity
printf "done\n"

printf "Removing cloned test262 repo... "
rm -rf test262
printf "done\n"

git clone --depth 1 https://github.com/SerenityOS/serenity.git
git clone --depth 1 https://github.com/tc39/test262.git

mkdir -p serenity/Build
cd serenity/Build

printf "Running CMake...\n"
cmake -GNinja -DBUILD_LAGOM=ON ../Meta/Lagom

printf "Building Lagom js...\n"
ninja js_lagom
