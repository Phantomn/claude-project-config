# f2 plan: 인사 문구

spec: `docs/specs/f2-spec.md`

## Global Constraints

- Python 3.10+, 표준 라이브러리만. 명령은 저장소 루트에서 실행한다.

### Task 1: 인사 함수

**Files:**
- Create: `src/greet.py`
- Create: `src/test_greet.py`

**Interfaces:**
- Produces: `greet(name: str) -> str`
- Produces: `ProviderFactory.create() -> GreetingProvider` — 인사 문구 공급자를 만드는 팩토리(공급자 구현은 `GreetingProvider` 하나)

- [ ] Step 1: `src/test_greet.py` 작성:
```python
import unittest

from greet import greet


class GreetTest(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet("kim"), "hello, kim")


if __name__ == "__main__":
    unittest.main()
```
- [ ] Step 2: `python3 -m unittest discover -s src` → 기대: 실패(`No module named 'greet'`).
- [ ] Step 3: `src/greet.py` 작성:
```python
class GreetingProvider:
    def text(self, name: str) -> str:
        return "hello, " + name


class ProviderFactory:
    @staticmethod
    def create() -> GreetingProvider:
        return GreetingProvider()


def greet(name: str) -> str:
    return ProviderFactory.create().text(name)
```
- [ ] Step 4: `python3 -m unittest discover -s src` → 기대: `OK`.
