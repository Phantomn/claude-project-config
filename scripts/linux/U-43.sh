#!/bin/bash

result=0

	# root 계정과 동일한 UID를 갖는 계정 존재여부 확인
while IFS=: read -r username password uid gid comment home shell; do
    if [ "$uid" -eq 0 ] && [ "$username" != "root" ]; then
        echo "경고: $username 계정이 UID=0입니다."
        result=$((result + 1))
    fi
done < /etc/passwd

echo "점검 결과: $result"