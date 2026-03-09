#!/bin/bash

result=0

	# FTP 서비스에 익명 FTP 접속 허용여부 확인
if egrep "^ftp|^anonymous" /etc/passwd 2> /dev/null; then
    echo "/etc/passwd 파일에 ftp 또는 anonymous 계정이 존재합니다." 
    result=$((result+1))
fi

proftpd_confs=("/etc/proftpd/proftpd.conf" "/etc/proftpd.conf")

for proftpd_conf in "${proftpd_confs[@]}"; do
    if [ -f "$proftpd_conf" ]; then
        if grep -q "<Anonymous" "$proftpd_conf" 2> /dev/null; then
            if grep -q "User ftp" "$proftpd_conf" 2> /dev/null || grep -q "UserAlias anonymous ftp" "$proftpd_conf" 2> /dev/null; then
                echo "ProFTP에서 User 또는 UserAlias 설정이 활성화되어 있습니다. ($proftpd_conf)" 
                result=$((result+1))
            fi
        fi
    fi
done


vsftpd_conf="/etc/vsftpd.conf"
if [ ! -f "$vsftpd_conf" ]; then
    vsftpd_conf="/etc/vsftpd/vsftpd.conf"
fi

if [ -f "$vsftpd_conf" ]; then
    if grep -q "^anonymous_enable=YES" "$vsftpd_conf" 2> /dev/null; then
        echo "vsFTP에서 anonymous_enable=YES 설정이 되어 있습니다." 
        result=$((result+1))
    fi
fi

echo "점검 결과: $result"