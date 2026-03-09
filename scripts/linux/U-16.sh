#!/bin/bash

result=0

	# 존재하지 않는 device 파일 확인
while IFS= read -r line; do
    echo "$line"
    result=$((result+1))
done < <(find /dev –type f –exec ls –l {} \; 2> /dev/null)

echo "점검 결과: $result"