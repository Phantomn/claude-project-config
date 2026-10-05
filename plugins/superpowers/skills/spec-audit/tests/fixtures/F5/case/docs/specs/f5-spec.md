# f5 spec: 상태 레코드 생성

상위 정본: `docs/canon/status.md`

## 목표

상태 레코드 하나를 만드는 함수 `make_status(id: int, mode: str) -> dict`를 `src/status.py`에 둔다.

## 수용 기준

1. 반환값은 `{"id": id, "mode": mode}`다.
2. `mode` ∈ 레지스트리 어휘 `{"fast","safe"}` — 그 밖의 값이면 `ValueError`.
