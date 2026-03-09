#!/bin/bash

result=0

    # everyone 공유 여부 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    if grep -E "everyone" /etc/dfs/dfstab /etc/dfs/sharetab > /dev/null 2>&1; then
        echo "/etc/dfs/dfstab 또는 /etc/dfs/sharetab에서 everyone 공유가 설정되어 있습니다."
        result=$((result+1))
    fi

    echo "점검 결과: $result"
    exit 1
fi


exports_file="/etc/exports"

if [ -f "$exports_file" ]; then
    while IFS= read -r line; do
        if echo "$line" | grep -q "^#"; then
            continue
        fi
        
        if ! echo "$line" | grep -qE "(\s(rw|ro)\s?=.*)"; then
            echo "접근 제한이 설정되지 않은 공유 디렉터리 설정이 있습니다: $line" > /dev/null 2>&1
            result=$((result+1))
        fi
    done < "$exports_file"
fi

echo "점검 결과: $result"
