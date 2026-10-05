# f7 spec: 줄 파서 Rust 이식

## 목표

`legacy/parser.c`의 `parse_line`을 Rust로 이식해 `rust/src/parser.rs`(신규)에 둔다. 이식 후에도 C 구현과 같은 입력에 같은 결과를 내야 한다.

## 요구

1. `parse_line(line: &str) -> Option<(&str, &str)>` — 첫 `=` 앞을 key, 뒤를 value로 돌려준다.
2. `=`가 없으면 `None`을 돌려준다.
3. C 구현은 이식이 끝날 때까지 지우지 않는다.
