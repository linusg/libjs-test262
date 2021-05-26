#!/usr/bin/env sh

red=`tput setaf 9`
green=`tput setaf 10`
reset=`tput sgr0`

js="serenity/Build/js"

if [ ! -f "${js}" ]; then
    echo "${js} not found, run setup.sh first"
    exit 1
fi

for f in test262/harness/*.js; do
    filename=$(basename $f)
    output=$("${js}" "${f}" 2>&1)
    if echo "${output}" | grep -q "SyntaxError"; then
        printf "[ ${red}FAIL${reset} ]"
    else
        printf "[ ${green}PASS${reset} ]"
    fi
    echo " ${filename}"
done
