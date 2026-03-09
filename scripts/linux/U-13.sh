#!/bin/bash

result=0

	# 취약한 SUID, SGID 설정파일 확인
while IFS= read -r line; do
	echo "$line"
    result=$((result+1))
done < <(find / -type f \( -perm -4000 -o -perm -2000 \) -exec ls -ld {} \; 2> /dev/null)

if [ "$result" -gt 0 ]; then
	echo "$result개의 SUID 또는 SGID 설정 파일이 발견되었습니다."
fi 

echo "점검 결과: $result"