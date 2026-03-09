#!/bin/bash

result=0

gshadow_file="/etc/gshadow"
passwd_file="/etc/passwd"
essential_groups="root bin daemon adm mail lp games ftp nobody systemd-journal wheel sys disk mem kmem cdrom man utmp kvm render tty dialout floppy tape video lock audio users input utempter shadow crontab nogroup sudo syslog fax voice"

	# 그룹 (/etc/group) 설정 파일에 불필요한 그룹, 계정 존재여부 확인
if [ -f "$gshadow_file" ]; then
    while IFS=: read -r group password admins members; do
        if echo "$essential_groups" | grep -qw "$group"; then
            continue
        fi
        if ! grep -q "^$group:" "$passwd_file"; then
            echo "불필요한 그룹 발견: $group"
            result=$((result + 1))
        elif [ -z "$members" ]; then
            echo "불필요한 그룹 발견: $group"
            result=$((result + 1))
        fi
    done < "$gshadow_file"
fi

echo "점검 결과: $result"