#!/bin/bash

result=0

	#관리자만 at.allow파일과 at.deny 파일 제어가능여부 확인
check_file_permissions() {
    local file=$1
    local required_permissions=640
    if [ -f "$file" ]; then
        permissions=$(stat -c "%a" "$file")
        if ! [ "$permissions" -le "$required_permissions" ]; then
            echo "$file 파일의 권한이 $permissions 입니다."
            result=$((result + 1))
        fi

        owner=$(stat -c "%U" "$file")
        if ! [ "$owner" = "root" ]; then
            echo "$file 파일의 소유자가 $owner 입니다."
            result=$((result + 1))
        fi
    fi
}

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    # Solaris에서 at 명령어 사용 가능 여부 확인
    if ls -l /etc/cron.d/at.allow 2>/dev/null | awk '{print $1}' | egrep '^-rw-.*w' > /dev/null 2>&1; then
        echo "/etc/cron.d/at.allow 파일의 권한이 640 이상입니다."
        result=$((result + 1))
    fi

    if ls -l /etc/cron.d/at.deny 2>/dev/null | awk '{print $1}' | egrep '^-rw-.*w' > /dev/null 2>&1; then
        echo "/etc/cron.d/at.deny 파일의 권한이 640 이상입니다."
        result=$((result + 1))
    fi

    # 일반 사용자 at 명령어 사용 가능 여부 확인
    if ! [ -f /etc/cron.d/at.allow ] && [ -f /etc/cron.d/at.deny ]; then
        echo "일반 사용자가 at 명령어를 사용할 수 있습니다."
        result=$((result + 1))
    fi

	check_file_permissions "/etc/cron.d/at.allow"
	check_file_permissions "/etc/cron.d/at.deny"
    echo "점검 결과: $result"
    exit 1
fi




at_command=$(command -v at)
if [ -n "$at_command" ]; then
    at_permissions=$(stat -c "%a" "$at_command")
    if ! [ "$at_permissions" -eq 750 ]; then
        echo "'at' 명령어의 권한이 $at_permissions 입니다."
        result=$((result + 1))
    fi
fi


check_file_permissions "/etc/at.allow"
check_file_permissions "/etc/at.deny"

echo "점검 결과: $result"