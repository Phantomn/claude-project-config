#!/bin/bash

result=0

profile_file="/etc/profile"
csh_files="/etc/csh.login /etc/csh.cshrc"

	# 사용자 쉘에 대한 환경설정 파일에서 session timeout설정여부 확인
if grep -q "TMOUT" "$profile_file"; then
    tmout_value=$(grep "TMOUT=" "$profile_file" | cut -d= -f2)
    if ! [ "$tmout_value" -le 600 ]; then
        echo "TMOUT 값이 600초(10분) 초과로 설정되어 있습니다: $tmout_value 초"
        result=$((result + 1))
    fi
else
    echo "$profile_file 에 TMOUT 설정이 없습니다."
    result=$((result + 1))
fi

for csh_file in $csh_files; do
    if [ -f "$csh_file" ]; then
        if grep -q "autologout" "$csh_file"; then
            autologout_value=$(grep "autologout" "$csh_file" | awk -F= '{print $2}')
            if ! [ "$autologout_value" -le 10 ]; then
                echo "$csh_file 파일에 autologout 값이 10분 초과로 설정되어 있습니다: $autologout_value 분"
                result=$((result + 1))
            fi
        else
            echo "$csh_file 파일에 autologout 설정이 없습니다."
            result=$((result + 1))
        fi
    fi
done

echo "점검 결과: $result"