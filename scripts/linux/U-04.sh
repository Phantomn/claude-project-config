#!/bin/bash

result=0

    # 패스워드 암호화 활성화여부 확인
if ! [ -f /etc/shadow ]; then
    echo "/etc/shadow 파일이 없습니다. 패스워드 암호화가 활성화되지 않았을 수 있습니다." > /dev/null 2>&1
    result=$((result+1))
fi

    # 패스워드를 암호화하여 저장하지 않는 경우 확인
while IFS=: read -r username password rest; do
    if [ "$password" != "x" ]; then
        echo "/etc/passwd 파일에서 $username 계정의 두 번째 필드가 'x'가 아닙니다. ($password)" > /dev/null 2>&1
    fi
done < /etc/passwd

echo "점검 결과: $result"