#!/usr/bin/env sh

rm -rf serenity
rm -rf test262
git clone --depth 1 https://github.com/SerenityOS/serenity.git
git clone --depth 1 https://github.com/tc39/test262.git

cd serenity/Meta/Lagom
mkdir build
cd build
cmake ..
make -j$(($(nproc)+1)) js
