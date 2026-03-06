# Basic Instruction
- **MUST** 항상 한글로 응답
- MVP 우선, YAGNI/KISS 엄격 적용
- Over-Engineering/Mocking/Sample Code/임시 데이터 금지
- 실행 결과 기반 판단 (미리 짐작 금지)
- 문서는 제일 마지막에 작성

# Priority System
🔴 **CRITICAL**: 보안, 데이터 안전, 프로덕션 안정성
🟡 **IMPORTANT**: 품질, 유지보수성, 전문성
🟢 **RECOMMENDED**: 최적화, 스타일, 모범 사례

# Core Rules

## 필수 (🔴)
- `git status && git branch` 먼저 실행
- Read → Write/Edit (읽기 후 수정)
- Feature branches만 사용 (main/master 직접 작업 금지)
- TODO/FIXME에 Expiry/Owner/Removal 필수
- 절대 경로 사용, 자동 커밋 금지

## 중요 (🟡)
- 3단계 이상 → TodoWrite 필수
- 시작한 구현은 완료까지 (부분 구현 금지)
- 요청한 것만 구현 (MVP 우선)
- 전문적 언어 사용 (마케팅 용어 금지)
- 임시 파일 정리

## 권장 (🟢)
- 병렬 작업 우선 (순차보다 효율적)
- 명확한 네이밍 컨벤션
- MCP > Native > Basic 도구 선택
- 배치 작업 활용

# Output Style
- 결론 먼저 (BLUF)
- 간결하고 정확하게
- **굵은 글씨**로 핵심 강조
- 모호하면 질문 먼저

# Workflow
```
/plan → 구현 → /verify → /wrap → /commit
```

# Tool Selection
| 작업 | 최선 | 대안 |
|------|------|------|
| 3+ 파일 편집 | MultiEdit | 개별 Edit |
| 복잡한 분석 | 네이티브 추론 | - |
| 공식 문서 | Context7 MCP | 웹 검색 |
| 웹 검색 | Tavily MCP | WebSearch |
| 심볼 작업 | Serena MCP | 수동 검색 |
| 바이너리 분석 | IDA Pro MCP | - |
| 문서/세션 검색 | QMD (`qmd search/vsearch/query`) | grep |

# QMD 검색

문서나 세션 컨텍스트가 필요할 때 QMD를 사용한다. `/recall`로 세션 시작 전 컨텍스트를 로드하거나, 작업 중 직접 검색한다.

## 컬렉션

| 컬렉션 | 내용 | 검색 모드 |
|--------|------|-----------|
| `xgt_plc` | XGT PLC 프로토콜 | `query` |
| `iec_62443_4_2` | IEC 62443-4-2 표준 | `query` |
| `threat_modeling` | 위협 모델링 | `query` |
| `side_job` | 사이드 프로젝트 | `query` |
| `locked_shield` | Locked Shields | `query` |
| `achilles_certificates` | Achilles 인증 | `query` |
| `cmds_process` | CMDS 프로세스 | `query` |
| `topic_security` | 보안 지식 | `query` |
| `topic_ai` | AI/LLM 지식 | `search` |
| `topic_automation` | 자동화 지식 | `search` |
| `topic_career` | 커리어 | `search` |
| `topic_software-engineering` | SW 엔지니어링 | `search` |
| `daily` | Daily Notes | `vsearch` |
| `sessions` | Claude Code 세션 히스토리 | `vsearch` |

## 언제 사용하나

- 프로젝트 문서/결정사항 참조 → `qmd query "<키워드>" -c <컬렉션> -n 5`
- 과거 세션 검색 → `qmd vsearch "<키워드>" -c sessions -n 5`
- 정확한 용어 검색 → `qmd search "<키워드>" -c <컬렉션> -n 5`
- 세션 시작 전 컨텍스트 로드 → `/recall <프로젝트명 또는 날짜>`

## 세션 인덱스 갱신

```bash
python3 ~/.claude/skills/recall/scripts/extract-sessions.py --output ~/.claude/qmd-sessions && qmd update
```

# Git Safety
- `git status` 먼저
- Feature branch 사용
- 작은 단위 커밋
- `git diff` 확인 후 스테이징
- 위험 작업 전 커밋 (롤백 포인트)

---

# Available Extensions
> `/load [category]`로 상세 문서 로드

## Modes
| 플래그 | 설명 | 로드 |
|--------|------|------|
| `--brainstorm` | 협업 발견, 요구사항 탐색 | `/load brainstorm` |
| `--uc` | 토큰 효율 모드 | `/load token-efficiency` |
| `--research` | 체계적 조사, 리서치 | `/load deep-research` |

## MCP Servers
| 플래그 | 용도 | 로드 |
|--------|------|------|
| `--context7` | 공식 라이브러리 문서 | `/load context7` |
| `--serena` | 심볼 작업, 프로젝트 메모리 | `/load serena` |
| `--tavily` | 웹 검색, 리서치 | `/load tavily` |
| `--ida` | 바이너리 리버싱 | `/load ida` |

## Bulk Load
```
/load modes      # 모든 모드 문서
/load mcp        # 모든 MCP 문서
```

---

# Quick Reference

## Symbol System (--uc 모드)
```
→ leads to    ⇒ transforms    ← rollback    ⇄ bidirectional
✅ done       ❌ failed       ⚠️ warning    🔄 in progress
⚡ perf       🔍 analysis     🛡️ security   📦 deploy
```

## Abbreviations
```
cfg config   impl implementation   arch architecture
req requirements   deps dependencies   val validation
```

---

# Extension Paths
```
~/.claude/extensions/
├── modes/       # brainstorming, introspection, task-management, ...
├── mcp/         # context7, serena, tavily, ida
├── business/    # panel-examples, symbols
└── research/    # config
~/.claude/references/
├── rules-full.md
├── flags-full.md
└── principles-full.md
```
