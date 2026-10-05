# f6 plan: 상태 확인 스크립트

spec: `docs/specs/f6-spec.md`

## Global Constraints

- Python 3.10+, 표준 라이브러리만. 명령은 저장소 루트에서 실행한다.

### Task 1: probe 스크립트

**Files:**
- Create: `scripts/probe.py`

- [ ] Step 1: 파이썬 동작 확인 — `python3 -c 'print(1+1)'` → 기대 출력 `3`.
- [ ] Step 2: 서버 응답 확인 — `curl -fsS http://203.0.113.10/health` → 기대: HTTP 200 응답(exit 0).
- [ ] Step 3: `scripts/probe.py` 작성:
```python
import sys
import urllib.request


def main() -> int:
    try:
        with urllib.request.urlopen("http://203.0.113.10/health", timeout=5) as r:
            ok = r.status == 200
    except OSError:
        ok = False
    print("ok" if ok else "down")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
```
- [ ] Step 4: `python3 scripts/probe.py; echo "exit=$?"` → 기대: 서버가 200이면 `ok`·`exit=0`, 아니면 `down`·`exit=1`.
