# 축 refs

## 4.4.1 감사 축 (refs 행)

| `refs` | 참조 실재(4.4.3), 심볼 3분류·경로 해석·파일 참조(4.4.2), 문서 간·문서 내부 충돌(class `cross-doc-conflict`: 대상 각 문서의 내부 모순, 대상 사이, 대상·other, other 내부), PLAN 내부 정합(Task Consumes ⊆ 앞선 Task Produces, Global Constraints 값 = spec 원문 값, 생성 Step이 사용보다 앞, 삭제 Step이 마지막 사용보다 뒤), N≥2 짝 동기화(직전 diff가 바꾼 용어·값·심볼을 언급하는 **모든 곳** — 배정 범위 밖 target 허용) |

## 4.4.2 심볼·경로·파일 참조

- 심볼 3분류: `existing`(지금 실재) / `created`(PLAN `Create` 파일·Interfaces `Produces`·spec의 "신규" 표기) / `deleted`(지금 실재 + 삭제 Step이 마지막 사용 Step 뒤).
  근거 없으면 `ref-missing`(`align`).
- 경로 해석 순서(실재 확인은 작업트리): ① `<tree>` ② 문서 디렉토리에서 위로 처음 `package.json`·`pyproject.toml`·`Cargo.toml`·`go.mod`가 있는 디렉토리 ③ 문서 디렉토리.
- 파일 참조 = 본문 백틱 안 경로 토큰(`/` 포함 또는 `.`+영숫자 확장자로 끝남)과 PLAN `Files:` 블록. 실재·PLAN Create 합집합·"신규" 표기 중 하나면 통과.

## 4.4.3 참조 종류별 검증 수단

| 종류 | 수단(사용 가능한 첫 것) |
|---|---|
| 코드 심볼 | serena `find_symbol` 또는 codegraph `codegraph_explore`(ToolSearch, 프로젝트에 붙어 있을 때) → `git grep -n -w` → Read |
| 파일 경로 | `git ls-files` / `ls` + PLAN Create 합집합 |
| 문서 링크 `[[Note]]`, `[x](a.md#sec)` | 파일 존재 + 앵커 제목 존재(Read) |
| 설정 키 | JSON: `jq` / YAML·TOML: Read |
| 정본 진술 | 해당 절 Read 후 대조 |
| 외부 URL | WebFetch |

serena는 세션 프로젝트를 읽으므로 세션 프로젝트가 `<tree>`일 때만 쓰고(`activate_project` 금지), codegraph는 `projectPath=<tree>`로 쓴다. 그 밖은 `git -C <tree> grep -n -w`·Read. harness-core `code-read-guard`가 켜진 프로젝트(`HARNESS_CODEREAD_GUARD=1`)에서는 Bash로 저장소 안 코드 파일을 읽을 수 없으므로 serena/codegraph 또는 Read 도구를 쓴다.
특정 도구를 강제하지 않는다 — `evidence`에 근거를 남긴다.
