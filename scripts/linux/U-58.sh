#!/bin/bash

result=0

hidden_files=$(find / -type f -name ".*" 2>/dev/null)

	# 숨김 파일 및 디렉터리 내 의심스러운 파일 확인
if [ -n "$hidden_files" ]; then
    echo "숨김 파일이 존재하고 있습니다 :"
    echo "$hidden_files"
    result=$((result + 1))
fi

hidden_dirs=$(find / -type d -name ".*" 2>/dev/null)

if [ -n "$hidden_dirs" ]; then
    echo "숨김 디렉터리가 존재하고 있습니다 :"
    echo "$hidden_dirs"
    result=$((result + 1))
fi

echo "점검 결과: $result"