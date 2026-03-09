#!/bin/bash

result=0

	# su 명령어 사용을 허용하는 사용자를 지정한 그룹 설정여부 확인
if grep -q "^wheel:" /etc/group; then
    group_members=$(grep "^wheel:" /etc/group | cut -d: -f4)
    
    if [ -n "$group_members" ]; then
        echo "wheel 그룹 내 구성원: $group_members"
    fi
else
    echo "'wheel' 그룹이 존재하지 않습니다." 
    result=$((result + 1))
    	
fi

if grep -q "pam_wheel.so" /etc/pam.d/su; then
    if ! grep -q "group=wheel" /etc/pam.d/su; then
        echo "pam_wheel.so 설정에서 'group=wheel'이 누락되었습니다."
        result=$((result + 1))
    fi
else
    echo "/etc/pam.d/su 파일에 pam_wheel.so 설정이 없습니다." 
    result=$((result + 1))
fi

for file in /usr/bin/su /bin/su; do
    if [ -e "$file" ]; then
        su_permission=$(ls -l $file | awk '{print $1}')
        if [ "$su_permission" != "-rwsr-x---" ]; then
            echo "'$file' 파일의 권한이 적절하지 않습니다."
            result=$((result + 1))
        fi
    fi
done


echo "점검 결과: $result"
