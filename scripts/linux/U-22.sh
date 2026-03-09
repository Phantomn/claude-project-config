#!/bin/bash

result=0

crontab_path=$(command -v crontab)

	# crontab 명령어 권한 및 소유자 확인
if [ -n "$crontab_path" ]; then
    crontab_perm=$(stat -c "%a" "$crontab_path")
    if [ "$crontab_perm" -gt 750 ]; then
        echo "crontab 명령어의 권한이 $crontab_perm 입니다."
        result=$((result+1))
    fi

    crontab_owner=$(stat -c "%U" "$crontab_path")
    if [ "$crontab_owner" != "root" ]; then
        echo "crontab 명령어의 소유자가 $crontab_owner 입니다."
        result=$((result+1))
    fi
fi

cron_files="/etc/crontab /etc/cron.allow /etc/cron.deny /var/spool/cron"

for file in $cron_files; do
    if [ -f "$file" ]; then
        file_perm=$(stat -c "%a" "$file")
        if [ "$file_perm" -gt 640 ]; then
            echo "$file 파일의 권한이 $file_perm 입니다."
            result=$((result+1))
        fi

        file_owner=$(stat -c "%U" "$file")
        if [ "$file_owner" != "root" ]; then
            echo "$file 파일의 소유자가 $file_owner 입니다."
            result=$((result+1))
        fi
    fi
done

echo "점검 결과: $result"