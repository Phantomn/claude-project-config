#!/bin/bash

result=0

path_value=$(echo "$PATH")

    # PATH 변수 변조된 명령어 삽입방지여부 확인
case "$path_value" in
    *:.:* | .:* | *::*) 
        echo "PATH 변수에 '.' 또는 '::'이 포함되어 있습니다." > /dev/null 2>&1
        result=$((result+1))
        ;;
esac

echo "점검 결과: $result"