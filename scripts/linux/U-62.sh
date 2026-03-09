#!/bin/bash

result=0
ftpusers_file="/etc/ftpusers"

	# FTP 접근제어 설정파일에 관리자 외 비인가자들 수정제한 여부 확인
if [ -f "$ftpusers_file" ]; then
    owner=$(stat -c "%U" "$ftpusers_file")
    if [ "$owner" != "root" ]; then
        echo "$ftpusers_file 파일의 소유자가 root가 아닙니다. (현재 소유자: $owner)"
        result=$((result + 1))
    fi

    permissions=$(stat -c "%a" "$ftpusers_file")
    if [ "$permissions" -gt 640 ]; then
        echo "$ftpusers_file 파일의 권한이 640보다 큽니다. (현재 권한: $permissions)"
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"