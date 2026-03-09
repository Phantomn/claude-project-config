#!/bin/bash

result=0

	# SMTP 서버의 릴레이 기능 제한 여부 확인
if ps -ef | grep -q "[s]endmail"; then
    if ! grep -q "FEATURE(\`relay_hosts_only')" /etc/mail/sendmail.mc 2> /dev/null && \
       ! grep -q "FEATURE(\`relay_hosts_only')" /etc/mail/sendmail.cf 2> /dev/null; then
        echo "릴레이 방지 설정이 적용되지 않았습니다."
        result=$((result+1))
    fi
fi

echo "점검 결과: $result"