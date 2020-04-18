#!/usr/bin/env sh

for f in test262/harness/*.js; do
    printf "%-30s" $(basename $f)
    output=$(serenity/Meta/Lagom/build/js "$f" 2>&1)
    if echo $output | grep -q 'Syntax Error: Unexpected token'; then
        echo "Syntax Error"
        continue
    fi
    if echo $output | grep -q 'Uncaught exception: '; then
        echo "Runtime Error"
        continue
    fi
    echo "Success!"
done
