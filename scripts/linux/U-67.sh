#!/bin/bash

result=0


if [[ "$(uname -s)" =~ "SunOS" ]]; then
    # Solaris 로그온 메시지 점검

    # 서버 배너 확인
    if [[ ! -s /etc/motd ]]; then
        echo "서버 로그온 메시지가 설정되지 않았습니다. (/etc/motd)"
        result=$((result + 1))
    fi

    # Telnet 배너 확인
    if ! grep -q 'BANNER=' /etc/default/telnetd 2>/dev/null; then
        echo "Telnet 로그온 메시지가 설정되지 않았습니다. (/etc/default/telnetd)"
        result=$((result + 1))
    fi

    # FTP 배너 확인
    if ! grep -q 'BANNER=' /etc/default/ftpd 2>/dev/null; then
        echo "FTP 로그온 메시지가 설정되지 않았습니다. (/etc/default/ftpd)"
        result=$((result + 1))
    fi

    # SMTP 배너 확인
    if ! grep -q 'O Smtp GreetingMessage=' /etc/mail/sendmail.cf 2>/dev/null; then
        echo "SMTP 로그온 메시지가 설정되지 않았습니다. (/etc/mail/sendmail.cf)"
        result=$((result + 1))
    fi

    # DNS 배너 확인
    if [[ ! -s /etc/named.conf ]]; then
        echo "DNS 로그온 메시지가 설정되지 않았습니다. (/etc/named.conf)"
        result=$((result + 1))
    fi

    echo "점검 결과: $result"
    exit 1
fi

# Linux 로그온 메시지 점검
if [[ "$(uname -s)" =~ "Linux" ]]; then
    # 서버 배너 확인
    if [[ ! -s /etc/motd ]]; then
        echo "서버 로그온 메시지가 설정되지 않았습니다. (/etc/motd)"
        result=$((result + 1))
    fi

    # Telnet 배너 확인
    if [[ ! -s /etc/issue.net ]]; then
        echo "Telnet 로그온 메시지가 설정되지 않았습니다. (/etc/issue.net)"
        result=$((result + 1))
    fi

    # FTP 배너 확인
    if ! grep -q 'ftpd_banner=' /etc/vsftpd/vsftpd.conf 2>/dev/null; then
        echo "FTP 로그온 메시지가 설정되지 않았습니다. (/etc/vsftpd/vsftpd.conf)"
        result=$((result + 1))
    fi

    # SMTP 배너 확인
    if ! grep -q 'O Smtp GreetingMessage=' /etc/mail/sendmail.cf 2>/dev/null; then
        echo "SMTP 로그온 메시지가 설정되지 않았습니다. (/etc/mail/sendmail.cf)"
        result=$((result + 1))
    fi

    # DNS 배너 확인
    if [[ ! -s /etc/named.conf ]]; then
        echo "DNS 로그온 메시지가 설정되지 않았습니다. (/etc/named.conf)"
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"
