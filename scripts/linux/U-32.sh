#!/bin/bash

result=0

	# SMTP 서비스 사용 시 일반사용자의 q 옵션 제한여부 확인
if ps -ef | grep -q "[s]endmail"; then
    if ! grep -v '^ *#' /etc/mail/sendmail.cf | grep -q "PrivacyOptions.*restrictqrun" 2> /dev/null; then
        echo "restrictqrun 옵션이 적용되지 않았습니다."
        result=$((result+1))
    fi
fi

echo "점검 결과: $result"