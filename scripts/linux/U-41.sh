#!/bin/bash

result=0

	# 웹 서버의 루트 디렉터리와 OS의 루트 디렉터리 일치여부 확인
apache_conf="/etc/httpd/conf/httpd.conf"  
default_paths=("/usr/local/apache/htdocs" "/usr/local/apache2/htdocs" "/var/www/html")
document_root=$(grep -i "^DocumentRoot" "$apache_conf" 2> /dev/null | awk '{print $2}' | tr -d '"')

is_default_path=false
for path in "${default_paths[@]}"; do
    if [ "$document_root" = "$path" ]; then
        is_default_path=true
        break
    fi
done

if [ "$is_default_path" = true ]; then
    echo "DocumentRoot가 기본 경로로 설정되어 있습니다: $document_root. 별도의 디렉터리로 설정하십시오."
    result=$((result+1))
fi

echo "점검 결과: $result"