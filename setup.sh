#!/usr/bin/env sh

rm -rf serenity
rm -rf test262
git clone --depth 1 https://github.com/SerenityOS/serenity.git
git clone --depth 1 https://github.com/tc39/test262.git

mkdir -p serenity/Build
cd serenity/Build
cmake ../Meta/Lagom -DBUILD_LAGOM=1
make -j$(($(nproc)+1)) js_lagom
