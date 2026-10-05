# f1 plan: 설정 도구

spec: `pkg/docs/specs/f1-spec.md`

## Global Constraints

- `timeout=30` (초) — 요청 시간 제한.
- Python 3.10+, 표준 라이브러리만. 명령은 저장소 루트에서 실행한다.

## Review Focus

- `parse_config`는 JSON 파일 내용을 그대로 dict로 돌려준다.
- `parse_config`는 파일이 없으면 `FileNotFoundError`를 그대로 올린다.

### Task 1: 설정 파서

**Files:**
- Create: `src/config.py`
- Create: `src/test_config.py`
- Create: `Cargo.toml`

**Interfaces:**
- Produces: `parse_config(path: str) -> dict`

- [ ] Step 1: `src/test_config.py` 작성:
```python
import unittest

from config import parse_config


class ParseConfigTest(unittest.TestCase):
    def test_reads_json(self):
        self.assertEqual(parse_config("config.json"), {"a": {"c": 1}})


if __name__ == "__main__":
    unittest.main()
```
- [ ] Step 2: `python3 -m unittest discover -s src` → 기대: 실패(`No module named 'config'`).
- [ ] Step 3: `src/config.py` 작성:
```python
import json


def parse_config(path: str) -> dict:
    with open(path) as f:
        return json.load(f)
```
- [ ] Step 4: `python3 -m unittest discover -s src` → 기대: `OK`.
- [ ] Step 5: `Cargo.toml` 작성:
```toml
[package]
name = "f1"
version = "0.1.0"
edition = "2021"
```
- [ ] Step 6: `grep -c '^name = "f1"$' Cargo.toml` → 기대 출력 `1`.

### Task 2: 시간 제한 값

**Files:**
- Modify: `src/config.py`

- [ ] Step 1: `src/config.py` 끝에 `TIMEOUT = 30` 한 줄을 덧붙인다.
- [ ] Step 2: `python3 -c 'import sys; sys.path.insert(0, "src"); import config; print(config.TIMEOUT)'` → 기대 출력 `30`.

### Task 3: 계층 정리

**Files:**
- Create: `src/layers.py`

**Interfaces:**
- Produces: `clear_layers(x)`

- [ ] Step 1: `src/layers.py` 작성:
```python
def clear_layers(x: list) -> list:
    return []
```
- [ ] Step 2: `python3 -c 'import sys; sys.path.insert(0, "src"); from layers import clear_layers; print(clear_layers([1, 2]))'` → 기대 출력 `[]`.

### Task 4: 요약 문자열

**Files:**
- Create: `src/report.py`

**Interfaces:**
- Consumes: Task 1 `parse_config(path: str) -> dict`
- Produces: `summary(cfg: dict) -> str`

- [ ] Step 1: `src/report.py` 작성:
```python
def summary(cfg: dict) -> str:
    return ",".join(sorted(cfg))
```
- [ ] Step 2: `python3 -c 'import sys; sys.path.insert(0, "src"); from config import parse_config; from report import summary; print(summary(parse_config("config.json")))'` → 기대 출력 `a`.

### Task 5: 실행 함수

**Files:**
- Create: `src/run.py`

**Interfaces:**
- Consumes: Task 1 `parse_config(path: str) -> dict`
- Consumes: Task 3 `clear_full_layers(x)`
- Produces: `run(path: str) -> list`

- [ ] Step 1: `src/run.py` 작성:
```python
from config import parse_config
from layers import clear_full_layers


def run(path: str) -> list:
    return clear_full_layers(list(parse_config(path)))
```
- [ ] Step 2: `python3 -c 'import sys; sys.path.insert(0, "src"); from run import run; print(run("config.json"))'` → 기대 출력 `[]`.
