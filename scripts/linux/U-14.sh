#!/bin/bash

result=0

	# 홈 디렉터리 내의 환경변수 파일 소유자, 쓰기권한 확인
for user in $(cut -d: -f1 /etc/passwd); do

    home_dir=$(eval echo ~$user)
    
    if [ -d "$home_dir" ]; then

        files=".bashrc .profile .bash_profile .zshrc"
        
        for file in $files; do
            file_path="$home_dir/$file"
            
            if [ -f "$file_path" ]; then
                owner=$(ls -ld "$file_path" | awk '{print $3}')
                
                if [ "$owner" != "$user" ] && [ "$owner" != "root" ]; then
                    echo "$file_path 파일의 소유자가 $owner 입니다."
                    result=$((result+1))
                fi

                if [ "$(stat -c "%A" "$file_path" | cut -c6)" = "w" ] || [ "$(stat -c "%A" "$file_path" | cut -c9)" = "w" ]; then
                    echo "$file_path 파일에 소유자 이외의 사용자에게 쓰기 권한이 부여되어 있습니다."
                    result=$((result+1))
                fi
            fi
        done
    fi
done

echo "점검 결과: $result"