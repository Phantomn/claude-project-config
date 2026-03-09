#!/bin/bash

result=0
ftp_shell=$(grep "^ftp:" /etc/passwd | cut -d: -f7)
allowed_shells="/bin/false /usr/sbin/nologin /sbin/nologin"

	# ftp 기본 계정에 쉘 설정여부 확인
if ! echo "$allowed_shells" | grep -qw "$ftp_shell"; then
    echo "FTP 계정의 쉘이 허용된 쉘 목록에 없습니다. 현재 설정된 쉘: $ftp_shell"
    result=$((result + 1))
fi

echo "점검 결과: $result"
