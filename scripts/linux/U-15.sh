#!/bin/bash

result=0

	# World Writable 파일 여부 확인
while IFS= read -r line; do
    echo "$line"
    result=$((result+1))
done < <(find / \( -path /proc -o -path /sys \) -prune -o -type f -perm -0002 -exec ls -l {} \; 2> /dev/null)

if [ "$result" -gt 0 ]; then
	echo "$result개의 World Writable 파일이 발견되었습니다."
fi 

echo "점검 결과: $result"