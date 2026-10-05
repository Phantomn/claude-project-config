# f5 plan: 상태 레코드 생성

spec: `docs/specs/f5-spec.md`

## Global Constraints

- Python 3.10+, 표준 라이브러리만. 명령은 저장소 루트에서 실행한다.

### Task 1: make_status

**Files:**
- Create: `src/status.py`

**Interfaces:**
- Produces: `make_status(id: int, mode: str) -> dict`

- [ ] Step 1: `src/status.py` 작성:
```python
MODES = {"fast", "safe"}


def make_status(id: int, mode: str) -> dict:
    if mode not in MODES:
        raise ValueError(mode)
    return {"id": id, "mode": mode}
```
- [ ] Step 2: `python3 -c 'import sys; sys.path.insert(0, "src"); from status import make_status; print(make_status(1, "fast"))'` → 기대 출력 `{'id': 1, 'mode': 'fast'}`.
- [ ] Step 3: `python3 -c 'import sys; sys.path.insert(0, "src"); from status import make_status; make_status(1, "auto")'` → 기대: exit 1, stderr 끝 줄 `ValueError: auto`.
