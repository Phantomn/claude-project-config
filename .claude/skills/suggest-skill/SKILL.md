---
name: suggest-skill
description: >
  현재 작업 컨텍스트에 맞는 로컬 스킬 추천.
  UserPromptSubmit 훅으로 자동 실행되며, /suggest-skill로 수동 호출도 가능.
  Use when: 어떤 스킬을 써야 할지 모를 때, 특정 작업에 맞는 명령어 확인
triggers:
  - "/suggest-skill"
  - "어떤 스킬"
  - "어떤 명령"
---

# suggest-skill

현재 프롬프트 키워드를 분석해 관련 로컬 스킬을 최대 3개 추천한다.

## 동작 방식

- **자동**: UserPromptSubmit 훅 → 매 프롬프트마다 키워드 분석 → stdout으로 추천 배너 출력
- **수동**: `/suggest-skill` 호출 → 현재 컨텍스트 기반 추천

## 출력 예시

```
💡 추천 스킬: /verify | /wrap
```

## 키워드 매핑

| 키워드 | 추천 |
|--------|------|
| 코드, 수정, 구현, fix | `/verify` |
| 아이디어, 막연, 기획 | `/brainstorm` |
| 계획, 단계, 분해, todo | `/breakdown` |
| 심볼, 함수, 클래스, 아키텍처 | `/mcp-analyze` |
| 문서, 공식, 라이브러리, api | `/mcp-docs` |
| 검색, 최신, 웹 | `/mcp-search` |
| 테스트, e2e, playwright | `/mcp-test` |
| 커밋, commit, push | `/commit` |
| 생각, 추론, 전략 | `/thinking` |
| 병렬, 패널 | `/panel` |
| 세션, 마무리, wrap | `/wrap` |
| 어제, 이전, 히스토리 | `/recall` |
| 어떤 스킬, 스킬 찾기 | `/find-skills` |
| 에이전트 팀, team | `/team-assemble` |
| 워크트리, worktree | `/worktree-sync` |

## 파일 위치

- 스크립트: `.claude/skills/suggest-skill/scripts/suggest-skill.py`
- 훅 설정: `.claude/settings.json` → `UserPromptSubmit`
