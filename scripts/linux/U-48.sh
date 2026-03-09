#!/bin/bash

result=0

passwd_file="/etc/passwd"
log_file="/var/log/wtmpx"


# 시스템 계정 중 불필요한 계정 존재여부 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then
    result=0  # 결과 초기화

	# 불필요한 계정 점검
	if egrep "lp|uucp|nuucp" "$passwd_file" > /dev/null 2>&1; then
		echo "불필요한 계정(lp, uucp, nuucp)이 /etc/passwd 파일에 존재합니다."
		result=$((result + 1))
	fi


    # Solaris 로그인 기록 점검
    if [ -f "/var/adm/wtmpx" ]; then
        last -f /var/adm/wtmpx | while read -r user tty date time rest; do
            if [[ "$date" != "**Never" ]] && [[ "$date" != "" ]]; then
                login_date="$date $time"
                login_epoch=$(perl -MTime::Piece -e 'print Time::Piece->strptime("'"$login_date"'", q{%b %d %H:%M})->epoch' 2>/dev/null)
                if [ $? -eq 0 ]; then
                    current_epoch=$(date +%s)
                    days_since_login=$(( (current_epoch - login_epoch) / 86400 ))
                    if [ "$days_since_login" -gt 365 ]; then
                        echo "$user: $days_since_login 일 동안 로그인하지 않음."
                        result=$((result + 1))
                    fi
                fi
            fi
        done
    fi

    # Solaris authlog 점검
    if [ -f "/var/log/authlog" ]; then
        grep "sshd.*session opened" /var/log/authlog | awk '{print $1, $2, $3, $(NF-1)}' | while read -r month day time user; do
            login_date="$month $day $time"
            login_epoch=$(perl -MTime::Piece -e 'print Time::Piece->strptime("'"$login_date"'", q{%b %d %H:%M})->epoch' 2>/dev/null)
            if [ $? -eq 0 ]; then
                current_epoch=$(date +%s)
                days_since_login=$(( (current_epoch - login_epoch) / 86400 ))
                if [ "$days_since_login" -gt 365 ]; then
                    echo "$user: $days_since_login 일 동안 로그인하지 않음."
                    result=$((result + 1))
                fi
            fi
        done
    fi

    # Solaris sulog 점검
    if [ -f "/var/adm/sulog" ]; then
        grep -E "SU |SU-" /var/adm/sulog | awk '{print $2, $3, $4, $(NF-1)}' | while read -r month day time user; do
            login_date="$month $day $time"
            login_epoch=$(perl -MTime::Piece -e 'print Time::Piece->strptime("'"$login_date"'", q{%b %d %H:%M})->epoch' 2>/dev/null)
            if [ $? -eq 0 ]; then
                current_epoch=$(date +%s)
                days_since_login=$(( (current_epoch - login_epoch) / 86400 ))
                if [ "$days_since_login" -gt 365 ]; then
                    echo "$user: $days_since_login 일 동안 su 명령 사용 기록 없음."
                    result=$((result + 1))
                fi
            fi
        done
    fi

    echo "점검 결과: $result"
    exit 1
fi



if [ -f "$log_file" ]; then
 # Linux 로그인 기록 점검
    lastlog | while read -r user tty date time rest; do
        # "Never logged in" 필터링
        if [[ "$date" != "**Never" ]] && [[ "$date" != "" ]]; then
            # 날짜를 epoch 형식으로 변환
            login_date="$date $time"
            login_epoch=$(date -d "$login_date" +%s 2>/dev/null)
            if [ $? -eq 0 ]; then
                current_epoch=$(date +%s)
                days_since_login=$(( (current_epoch - login_epoch) / 86400 ))
                if [ "$days_since_login" -gt 365 ]; then
                    echo "$user: $days_since_login 일 동안 로그인하지 않음."
                    result=$((result + 1))
                fi
            fi
        fi
    done
fi

echo "점검 결과: $result"