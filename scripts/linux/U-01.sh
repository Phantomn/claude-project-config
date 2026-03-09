#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then

    # Telnet 설정 확인
    if grep -q '^CONSOLE=/dev/console' /etc/default/login; then
        echo "/etc/default/login Telnet."
        result=$((result+1))
    fi

    # SSH PermitRootLogin 설정 확인
    if egrep 'PermitRootLogin no' /etc/ssh/sshd_config > /dev/null 2>&1; then
		echo "PermitRootLogin."
        result=$((result+1))
    fi

	echo ">> $result"
	exit 1
fi


if ps aux | grep "[t]elnet" > /dev/null 2>&1; then
    if grep -E '^pts/[0-9]+' /etc/securetty > /dev/null 2>&1; then
        echo "/etc/securetty 파일에 pts/x 설정이 있습니다."
        result=$((result+1))
    fi
    if ! grep -E '^auth\s+required\s+/lib/security/pam_securetty.so' /etc/pam.d/login > /dev/null 2>&1; then
        echo "/etc/pam.d/login 파일에 PAM 설정이 올바르게 구성되지 않았습니다."
        result=$((result+1))
    fi
fi

if ps aux | grep "[s]sh" > /dev/null 2>&1; then
    if ! grep -E '^PermitRootLogin\s+No' /etc/ssh/sshd_config > /dev/null 2>&1; then
        echo "/etc/ssh/sshd_config 파일에서 PermitRootLogin 설정이 No로 설정되지 않았습니다."
        result=$((result+1))
    fi
fi 

echo "점검 결과: $result"