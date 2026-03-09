#!/bin/bash

result=0
passwd_file="/etc/passwd"

	# /etc/passwd 파일 내 UID가 동일한 사용자 계정 존재여부 확인
awk -F: '{print $3}' "$passwd_file" | sort | uniq -d | while read -r uid; do
    echo "중복된 UID: $uid"
    grep ":$uid:" "$passwd_file"
    result=$((result + 1))
done

echo "점검 결과: $result"