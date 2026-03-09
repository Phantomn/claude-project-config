#!/bin/bash

result=0
passwd_file="/etc/passwd"
restricted_accounts="^daemon|^bin|^sys|^adm|^listen|^nobody|^nobody4|^noaccess|^diag|^operator|^games|^gopher"

	# 로그인이 불필요한 계정에 쉘 부여여부 확인
while IFS=: read -r username password uid gid info home shell; do
    if [[ "$shell" =~ /bin/bash|/bin/sh|/usr/bin/bash|/usr/bin/sh ]]; then
        echo "$username 계정에 로그인 가능한 쉘($shell)이 부여되어 있습니다."
        ((result + 1))
    fi
done < <(egrep "$restricted_accounts" "$passwd_file")

echo "점검 결과: $result"