#!/bin/bash

result=0

if [[ "$(uname -s)" =~ "SunOS" ]]; then
    echo "Solaris 패치 적용 여부 점검 중..."

    # 1. 현재 적용된 패치 리스트 확인
    # 2. 최신 패치 확인 (Solaris 10 이하)
    if [[ "$(uname -r)" =~ ^5\.[0-9]$ || "$(uname -r)" == "5.10" ]]; then
		if ! showrev -p 2>/dev/null | grep -q "Patch:"; then
			echo "적용된 패치가 없습니다. (showrev -p 결과 없음)"
			result=$((result + 1))
		fi		
        if patchadd -p 2>/dev/null | grep -q "No patches"; then
            echo "적용된 패치가 없습니다. (patchadd -p 결과 없음)"
            result=$((result + 1))
        fi
    fi

    # 3. Solaris 11 이상 패키지 업데이트 확인
    if [[ "$(uname -r)" =~ ^5\.11$ ]]; then
        if pkg update -nv 2>/dev/null | grep -q "No updates available"; then
            echo "설치해야 할 업데이트가 없습니다."
        else
            echo "업데이트 가능한 패키지가 있습니다."
            result=$((result + 1))
        fi
    fi

    echo "점검 결과: $result"
    exit 1
fi


# APT의 잠금 파일 제거 함수
remove_apt_locks() {
    echo "APT: 잠금 파일 제거 중..."
    sudo rm -rf /var/lib/apt/lists/lock
    sudo rm -rf /var/lib/dpkg/lock-frontend
    sudo rm -rf /var/lib/dpkg/lock
    sudo rm -rf /var/cache/apt/archives/lock
    sudo dpkg --configure -a
}

# YUM/DNF의 잠금 파일 제거 함수
remove_yum_dnf_locks() {
    echo "YUM/DNF: 잠금 파일 제거 중..."
    sudo rm -f /var/run/yum.pid
    sudo rm -f /var/run/dnf.pid
}

# APT 확인 및 업데이트
if command -v apt > /dev/null 2>&1; then
    if sudo fuser /var/lib/dpkg/lock >/dev/null 2>&1 || sudo fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1; then
        remove_apt_locks
    fi

    apt update > /dev/null 2>&1

    updates=$(apt list --upgradable 2> /dev/null | grep -v "Listing...")
    
    if [ -n "$updates" ]; then
        echo "APT: 업데이트가 필요한 패키지가 있습니다:"
        echo "$updates"
        result=$((result + 1))
    fi
# YUM 확인 및 업데이트
elif command -v yum > /dev/null 2>&1; then
    if sudo fuser /var/run/yum.pid >/dev/null 2>&1; then
        remove_yum_dnf_locks
    fi

    updates=$(yum check-update 2> /dev/null)
    
    if [ -n "$updates" ]; then
        echo "YUM: 업데이트가 필요한 패키지가 있습니다:"
        echo "$updates"
        result=$((result + 1))
    fi
# DNF 확인 및 업데이트
elif command -v dnf > /dev/null 2>&1; then
    if sudo fuser /var/run/dnf.pid >/dev/null 2>&1; then
        remove_yum_dnf_locks
    fi

    updates=$(dnf check-update 2> /dev/null)
    
    if [ -n "$updates" ]; then
        echo "DNF: 업데이트가 필요한 패키지가 있습니다:"
        echo "$updates"
        result=$((result + 1))
    fi
fi

echo "점검 결과: $result"