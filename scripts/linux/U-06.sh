#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then

    # 소유자가 존재하지 않는 파일 및 디렉터리 확인
    if find / -nouser -o -nogroup -xdev -ls 2>/dev/null | grep . > /dev/null 2>&1; then
        echo "소유자가 존재하지 않는 파일 또는 디렉터리가 있습니다."
        result=$((result+1))
    fi

    echo "점검 결과: $result"
    exit 1
fi


	# 최상위 디렉토리 목록 생성 및 검색 수행
find / -mindepth 1 -maxdepth 1 -type d 2>/dev/null | xargs -r -P "$(nproc)" -I {} find {} \( -nouser -o -nogroup \) -print -quit 2>/dev/null && {
    echo "소유자 또는 소유 그룹이 없는 파일이 존재합니다." > /dev/null 2>&1
    result=$((result + 1))
}

	# 최종 결과 출력
echo "점검 결과: $result"