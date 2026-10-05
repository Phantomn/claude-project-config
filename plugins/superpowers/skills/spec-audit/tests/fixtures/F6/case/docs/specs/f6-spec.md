# f6 spec: 상태 확인 스크립트

## 목표

서버 `203.0.113.10`의 `/health`가 HTTP 200을 돌려주는지 확인해 결과를 출력하는 스크립트 `scripts/probe.py`를 만든다.

## 요구

1. `python3 scripts/probe.py`는 응답 코드가 200이면 `ok`를 출력하고 exit 0, 그 밖이거나 연결 실패면 `down`을 출력하고 exit 1.
2. 표준 라이브러리 `urllib.request`만 쓰고 시간 제한은 5초다.
