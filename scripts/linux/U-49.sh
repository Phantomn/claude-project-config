#!/bin/bash

group_file="/etc/group"
result=0

root_group=$(grep "^root:" $group_file)

	# 시스템 관리자 그룹에 최소한의 계정만 존재하는지 확인
if echo "$root_group" | grep -q ":root,"; then
    echo "root 그룹에 root 이외의 계정이 포함되어 있습니다."
    result=$((result + 1))
fi

echo "점검 결과: $result"