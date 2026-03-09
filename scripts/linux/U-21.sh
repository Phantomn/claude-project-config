#!/bin/bash

result=0

	# 익명 FTP 접속 허용 여부 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    if [[ "$(uname -r)" =~ ^5\.[0-9]$ ]]; then
        # Solaris 5.9 이하: /etc/inetd.conf에서 r-command 서비스 확인
        if grep -E "shell|login|exec" /etc/inetd.conf | grep -v "^#" > /dev/null 2>&1; then
            echo "불필요한 r-command 서비스(shell, login, exec)가 /etc/inetd.conf에 활성화되어 있습니다."
            result=$((result+1))
        fi
    else
        # Solaris 5.10 이상: inetadm으로 r-command 서비스 확인
        if inetadm | egrep "shell|rlogin|rexec" | grep "online" > /dev/null 2>&1; then
            echo "불필요한 r-command 서비스(shell, rlogin, rexec)가 활성화되어 있습니다."
            result=$((result+1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi


for service in rsh rlogin rexec; do
    service_file="/etc/xinetd.d/$service"
    if [ -f "$service_file" ]; then
        if grep -q "disable.*no" "$service_file" 2> /dev/null; then
            echo "$service 서비스가 활성화되어 있습니다." > /dev/null 2>&1
            result=$((result+1))
        fi
    fi
done

if ls -alL /etc/xinetd.d/* 2> /dev/null | egrep "rsh|rlogin|rexec" | egrep -v "grep|klogin|kshell|kexec" > /dev/null 2>&1; then
    echo "r-command 계열 서비스가 활성화되어 있습니다." > /dev/null 2>&1
    result=$((result+1))
fi

echo "점검 결과: $result"