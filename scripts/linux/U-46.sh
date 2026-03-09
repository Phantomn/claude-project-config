#!/bin/bash

result=0

	# 시스템 정책에 패스워드 최대사용기간 설정 적용여부 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    result=0

    if [[ "$(uname -r)" =~ ^5\.[1-9][0-9]$ || "$(uname -r)" =~ ^5\.10$ ]]; then
        # Solaris 5.10 이상: 패스워드 최대 사용기간 확인
        max_weeks=$(egrep '^MAXWEEKS=[0-9]+' /etc/default/passwd | cut -d= -f2)

        if [[ -z "$max_weeks" || "$max_weeks" -gt 12 ]]; then
            echo "'MAXWEEKS' 설정이 $max_weeks 입니다. (기준: 12 이하)"
            result=$((result+1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi


max_days=$(grep -E '^PASS_MAX_DAYS' /etc/login.defs | awk '{print $2}')

if [ -z "$max_days" ]; then
    echo "'PASS_MAX_DAYS' 설정이 /etc/login.defs 파일에서 누락되었습니다."
    result=$((result + 1))
elif [ "$max_days" -gt 90 ]; then
    echo "'PASS_MAX_DAYS' 설정이 $max_days 입니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"