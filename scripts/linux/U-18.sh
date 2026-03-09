#!/bin/bash

result=0

	# 접속 IP 주소 제한 및 포트 제한 여부확인
if [ -f /etc/hosts.deny ]; then
    if ! grep -q "ALL: ALL" /etc/hosts.deny 2> /dev/null; then
        echo "/etc/hosts.deny 파일에 'ALL: ALL' 설정이 없습니다."
        result=$((result+1))
    fi
fi

if command -v iptables > /dev/null 2>&1; then
    if ! iptables -L 2> /dev/null | grep -q "Chain INPUT"; then
        echo "IPTables가 활성화되어 있지 않습니다."
        result=$((result+1))
    fi
fi

if [ -f /etc/ipf/ipf.conf ]; then
    if ! grep -q "block in" /etc/ipf/ipf.conf 2> /dev/null; then
        echo "/etc/ipf/ipf.conf 파일에 'block in' 설정이 없습니다."
        result=$((result+1))
    fi
fi

if command -v inetadm > /dev/null 2>&1; then
    if ! inetadm -p 2> /dev/null | grep -q "tcp_wrappers=true"; then
        echo "TCP Wrapper가 Solaris에서 활성화되어 있지 않습니다."
        result=$((result+1))
    fi

    if [ -f /var/adm/inetd.sec ]; then
        if ! grep -q "ALL: DENY" /var/adm/inetd.sec 2> /dev/null; then
            echo "/var/adm/inetd.sec 파일에 'ALL: DENY' 설정이 없습니다."
            result=$((result+1))
        fi
    fi
fi

echo "점검 결과: $result"