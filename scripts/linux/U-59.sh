#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    ssh_installed=false
    telnet_ftp_enabled=false

    # Solaris 5.10 이상: SSH 활성화 여부 확인
    if [[ "$(uname -r)" =~ ^5\.[1-9][0-9]$ || "$(uname -r)" =~ ^5\.10$ ]]; then
        if svcs -Ho state ssh | grep -q "online"; then
            ssh_installed=true
        fi
    else
        # Solaris 5.9 이하: SSH 활성화 여부 확인
        if pgrep -x sshd > /dev/null; then
            ssh_installed=true
        fi
    fi

    # Telnet 및 FTP 서비스 점검
    if inetadm | egrep "telnet|ftp" | grep -q "enabled"; then
        telnet_ftp_enabled=true
    fi

    # SSH가 없고, Telnet/FTP가 활성화된 경우만 취약
    if ! $ssh_installed && $telnet_ftp_enabled; then
        echo "SSH가 없고 Telnet 또는 FTP가 활성화되어 있습니다."
        result=$((result+1))
    fi

    echo "점검 결과: $result"
    exit 1
fi


# Linux 점검

ssh_installed=false
telnet_ftp_enabled=false

# Linux에서 SSH 활성화 여부 확인
if systemctl is-active sshd > /dev/null 2>&1 || service sshd status > /dev/null 2>&1; then
    ssh_installed=true
fi

# Telnet 및 FTP 서비스 점검
if systemctl is-active telnet > /dev/null 2>&1 || systemctl is-active vsftpd > /dev/null 2>&1; then
    telnet_ftp_enabled=true
fi

# SSH가 없고, Telnet/FTP가 활성화된 경우만 취약
if ! $ssh_installed && $telnet_ftp_enabled; then
    echo "SSH가 없고 Telnet 또는 FTP가 활성화되어 있습니다."
    result=$((result+1))
fi


echo "점검 결과: $result"
