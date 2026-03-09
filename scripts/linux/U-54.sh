#!/bin/bash

result=0
hosts_lpd_file="/etc/hosts.lpd"

	# /etc/hosts.lpd 파일의 삭제 및 권한 적절여부 확인
if [ -f "$hosts_lpd_file" ]; then
    owner=$(ls -l "$hosts_lpd_file" | awk '{print $3}')
    if [ "$owner" != "root" ]; then
        echo "hosts.lpd 파일의 소유자가 root가 아닙니다. 현재 소유자: $owner"
        result=$((result + 1))
    fi

    permissions=$(stat -c "%a" "$hosts_lpd_file")
    if [ "$permissions" -ne 600 ]; then
        echo "hosts.lpd 파일의 권한이 600이 아닙니다. 현재 권한: $permissions"
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"