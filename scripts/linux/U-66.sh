#!/bin/bash

result=0

	# SNMP Community String 복잡성 설정 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    if [[ "$(uname -r)" =~ ^5\.[1-9][0-9]*$ || "$(uname -r)" =~ ^5\.10$ ]]; then
        # Solaris 10 이상
        if egrep "rocommunity\s+public|rwcommunity\s+private" /etc/sma/snmp/snmpd.conf 2>/dev/null || \
           egrep "rocommunity\s+public|rwcommunity\s+private" /etc/snmpd.conf 2>/dev/null; then
            echo "SNMP Community 이름이 public 또는 private 입니다."
            result=$((result + 1))
        fi
    else
        # Solaris 9 이하
        if egrep "read-community\s+public|write-community\s+private" /etc/snmp/conf/snmpd.conf 2>/dev/null || \
           egrep "read-community\s+public|write-community\s+private" /etc/snmpd.conf 2>/dev/null; then
            echo "SNMP Community 이름이 public 또는 private 입니다."
            result=$((result + 1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi



snmpd_conf="/etc/snmp/snmpd.conf"

if [ -f "$snmpd_conf" ]; then
    if grep -qE "community\s+public|community\s+private" "$snmpd_conf"; then
        echo "'$snmpd_conf' 파일에서 디폴트 커뮤니티명(public 또는 private)이 사용 중입니다."
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"