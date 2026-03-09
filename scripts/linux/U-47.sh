#!/bin/bash

result=0

	# 시스템 정책에 패스워드 최소 사용기간 설정 적용여부 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    result=0

    # Solaris: 패스워드 최소 사용기간 확인
    min_weeks=$(egrep '^MINWEEKS=[0-9]+' /etc/default/passwd | cut -d= -f2)

    if [[ -z "$min_weeks" || "$min_weeks" -eq 0 ]]; then
        echo "'MINWEEKS' 설정이 $min_weeks 입니다. (기준: 1 이상)"
        result=$((result+1))
    fi

    echo "점검 결과: $result"
    exit 1
fi



min_days=$(grep -E '^PASS_MIN_DAYS' /etc/login.defs | awk '{print $2}')

if [ -z "$min_days" ]; then
    echo "'PASS_MIN_DAYS' 설정이 /etc/login.defs 파일에서 누락되었습니다." > /dev/null 2>&1
    result=$((result + 1))
elif [ "$min_days" -lt 1 ]; then
    echo "'PASS_MIN_DAYS' 설정이 $min_days 입니다. 최소 1일 이상이어야 합니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"