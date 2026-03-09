#!/bin/bash

result=0

	# NIS 서비스 확인
if [[ "$(uname -s)" =~ "SunOS" && "$(uname -r)" =~ ^5\.([1-9][0-9]|10)$ ]]; then
    if svcs -a | grep nis | egrep "enabled|online"; then
        echo "NIS 서비스가 활성화되어 있습니다."
		result=$((result+1))
    fi
    echo "점검 결과: $result"
    exit 1	
fi


if ps -ef | egrep "ypserv|ypbind|ypxfrd|rpc.yppasswdd|rpc.ypupdated" | egrep -v "grep" > /dev/null 2>&1; then
    echo "NIS 또는 NIS+ 관련 서비스가 구동 중입니다." 
    result=$((result+1))
fi

echo "점검 결과: $result"