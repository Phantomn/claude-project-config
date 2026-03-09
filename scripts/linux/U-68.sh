#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    file="/etc/dfs/dfstab"

    if [[ -f "$file" ]]; then
        # 파일 소유자 확인
        owner=$(ls -l "$file" | awk '{print $3}')
        if [[ "$owner" != "root" ]]; then
            echo "NFS 접근제어 파일 ($file) 소유자가 root가 아닙니다."
            result=$((result + 1))
        fi

        # 파일 권한 확인
        permission=$(stat -c "%a" "$file" 2>/dev/null || ls -l "$file" | awk '{print $1}')
        if ! [[ "$permission" -le 644 ]]; then
            echo "NFS 접근제어 파일 ($file) 권한이 644보다 큽니다. (현재: $permission)"
            result=$((result + 1))
        fi
    else
        echo "NFS 접근제어 파일 ($file)이 존재하지 않습니다."
    fi

    echo "점검 결과: $result"
    exit 1
fi



nfs_files=(
    "/etc/exports"
    "/etc/idmapd.conf"
    "/etc/nfs.conf"
)

for file in "${nfs_files[@]}"; do
    if [ -f "$file" ]; then
        owner=$(stat -c "%U" "$file")
        if [ "$owner" != "root" ]; then
            echo "$file 파일의 소유자가 root가 아닙니다. 현재 소유자: $owner"
            result=$((result + 1))
        fi

        permissions=$(stat -c "%a" "$file")
        if ! [ "$permissions" -le 644 ]; then
            echo "$file 파일의 권한이 644보다 큽니다. (현재 권한: $permissions)"
            result=$((result + 1))
        fi
    fi
done

echo "점검 결과: $result"