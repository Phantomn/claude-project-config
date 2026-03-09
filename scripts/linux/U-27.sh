#!/bin/bash

result=0

	# 불필요한 RPC 서비스 확인
if [[ "$(uname -s)" =~ "SunOS" ]]; then

    if [[ "$(uname -r)" =~ ^5\.(10|11|[1-9][0-9])$ ]]; then
        # Solaris 5.10 이상: 불필요한 RPC 서비스가 활성화되었는지 확인
        if inetadm | grep rpc | grep enabled | egrep "ttdbserver|rex|rstart|rusers|spray|wall|rquota" > /dev/null 2>&1; then
            echo "불필요한 RPC 서비스(ttdbserver, rex, rstart, rusers, spray, wall, rquota)가 활성화되어 있습니다."
            result=$((result+1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi


if systemctl is-active rpcbind > /dev/null 2>&1; then
    echo "RPC 서비스(rpcbind)가 활성화되어 있습니다." 
    result=$((result+1))
fi

if service rpcbind status > /dev/null 2>&1; then
    if service rpcbind status | grep -q "running"; then
        echo "RPC 서비스가 활성화되어 있습니다." 
        result=$((result+1))
    fi
fi

if systemctl is-active portmap > /dev/null 2>&1; then
    echo "RPC 서비스(portmap)가 활성화되어 있습니다."
    result=$((result+1))
elif service portmap status > /dev/null 2>&1; then
    if service portmap status | grep -q "running"; then
        echo "RPC 서비스(portmap)가 활성화되어 있습니다."
        result=$((result+1))
    fi
fi

echo "점검 결과: $result"