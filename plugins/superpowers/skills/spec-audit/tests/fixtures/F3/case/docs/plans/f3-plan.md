# f3 plan: 줄 수 세기

spec: `docs/specs/f3-spec.md`

## Global Constraints

- Python 3.10+, 표준 라이브러리만. 명령은 저장소 루트에서 실행한다.

### Task 1: 줄 수 함수

**Files:**
- Create: `src/count.py`
- Create: `src/test_count.py`

**Interfaces:**
- Produces: `count_lines(path: str) -> int`

- [ ] Step 1: `src/test_count.py` 작성:
```python
import tempfile
import unittest
from pathlib import Path

from count import count_lines


class CountTest(unittest.TestCase):
    def test_counts(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.txt"
            p.write_bytes(b"a\nb\nc")
            self.assertEqual(count_lines(str(p)), 3)
            p.write_bytes(b"")
            self.assertEqual(count_lines(str(p)), 0)


if __name__ == "__main__":
    unittest.main()
```
- [ ] Step 2: `python3 -m unittest discover -s src` → 기대: 실패(`No module named 'count'`).
- [ ] Step 3: `src/count.py` 작성:
```python
def count_lines(path: str) -> int:
    with open(path, "rb") as f:
        return sum(1 for _ in f)
```
- [ ] Step 4: handle edge cases appropriately.
- [ ] Step 5: `python3 -m unittest discover -s src` → 기대: `OK`.

TODO(2026-12-31, owner: phantom, removal: v2 출시): 1 GiB 이상 파일의 처리 시간 측정은 v2에서 한다.
