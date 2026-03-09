#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    # Solaris FTP 서비스 점검
    ftp_enabled=false

    # inetd.conf에서 FTP 서비스 확인
    if grep -q "ftp" /etc/inetd.conf 2>/dev/null; then
        ftp_enabled=true
    fi

    # vsftpd 또는 proftpd 서비스가 실행 중인지 확인
    if ps -ef | egrep "vsftpd|proftpd" | grep -v "grep" > /dev/null; then
        ftp_enabled=true
    fi

    # FTP 서비스가 활성화되어 있으면 result+1
    if $ftp_enabled; then
        echo "FTP 서비스가 활성화되어 있습니다."
        result=$((result + 1))
    fi

    echo "점검 결과: $result"
    exit 1
fi


# Linux FTP 서비스 점검

# FTP 서비스 활성화 여부 확인
if ps -ef | grep -v "grep" | grep -q "ftp"; then
    echo "FTP 서비스가 실행 중입니다."
    result=$((result + 1))
fi

# vsftpd 또는 proftpd 서비스 실행 여부 확인
if ps -ef | egrep "vsftpd|proftpd" | grep -v "grep" > /dev/null; then
    echo "vsftpd 또는 proftpd 서비스가 실행 중입니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"
