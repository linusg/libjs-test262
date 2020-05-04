#!/usr/bin/env sh

red=`tput setaf 9`
green=`tput setaf 10`
reset=`tput sgr0`

for f in test262/harness/*.js; do
    filename=$(basename $f)
    output=$(serenity/Meta/Lagom/build/js "${f}" 2>&1)
    if echo $output | grep -q 'Syntax Error: Unexpected token'; then
        printf "[ ${red}FAIL${reset} ]"
    else
        printf "[ ${green}PASS${reset} ]"
    fi
    echo " ${filename}"
done
