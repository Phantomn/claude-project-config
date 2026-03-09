#!/bin/bash

result=0

	# ftpusers 파일 root 계정 포함여부 확인
ftp_files=("/etc/ftpusers" "/etc/ftpd/ftpusers")
for file in "${ftp_files[@]}"; do
    if [ -f "$file" ]; then
        if grep -q "^root" "$file"; then
            echo "$file 파일에서 root 계정이 등록되어 있습니다."
            result=$((result + 1))
        fi
    fi
done

proftp_file="/etc/proftpd.conf"
if [ -f "$proftp_file" ]; then
    if grep -q "RootLogin on" "$proftp_file"; then
        echo "$proftp_file 파일에서 root 계정이 접속 가능하도록 설정되어 있습니다."
        result=$((result + 1))
    fi
fi

vsftp_files=("/etc/vsftp/ftpusers" "/etc/vsftp/user_list" "/etc/vsftpd.ftpusers" "/etc/vsftpd.user_list")
for file in "${vsftp_files[@]}"; do
    if [ -f "$file" ]; then
        if grep -q "^root" "$file"; then
            echo "$file 파일에서 root 계정이 등록되어 있습니다."
            result=$((result + 1))
        fi
    fi
done

echo "점검 결과: $result"