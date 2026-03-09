#!/bin/bash

result=0
sendmail_cf="/etc/mail/sendmail.cf"

	# SMTP 서비스 사용 시 vrfy, expn 명령어 확인
if [ -f "$sendmail_cf" ]; then
    if ! egrep "O\s+PrivacyOptions=.*(noexpn|novrfy|goaway)" "$sendmail_cf"; then
        echo "'$sendmail_cf' 파일에서 noexpn, novrfy, 또는 goaway 옵션이 설정되어 있지 않습니다."
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"