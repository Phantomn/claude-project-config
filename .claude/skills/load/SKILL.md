---
name: load
description: 컨텍스트 확장 문서 로드. 필요한 모드/MCP/비즈니스/리서치 문서를 현재 세션에 로드합니다.
triggers:
  - "/load"
  - "문서 로드"
  - "확장 로드"
---

# /load - Context Extension Loader

컨텍스트 확장 문서를 필요에 따라 로드합니다.

## Usage
```
/load [category|file]
```

## Categories

| 카테고리 | 로드 대상 | 예상 토큰 |
|---------|----------|----------|
| `modes` | 모든 모드 문서 (5개) | ~4,700 |
| `mcp` | 모든 MCP 문서 (4개) | ~2,300 |
| `rules` | 전체 행동 규칙 | ~3,000 |
| `flags` | 전체 플래그 문서 | ~1,500 |
| `principles` | 엔지니어링 원칙 | ~700 |
| `all` | 전체 (비상용) | ~20,000 |

## Specific Files

### Modes
| 이름 | 경로 |
|------|------|
| `brainstorm` | `~/.claude/extensions/modes/brainstorming.md` |
| `token-efficiency` | `~/.claude/extensions/modes/token-efficiency.md` |
| `deep-research` | `~/.claude/extensions/modes/deep-research.md` |

### MCP Servers
| 이름 | 경로 |
|------|------|
| `context7` | `~/.claude/extensions/mcp/context7.md` |
| `serena` | `~/.claude/extensions/mcp/serena.md` |
| `tavily` | `~/.claude/extensions/mcp/tavily.md` |
| `ida` | `~/.claude/extensions/mcp/ida.md` |

## Execution

사용자가 `/load [target]`을 요청하면:

1. **카테고리 로드** (modes, mcp, business, research, all):
   - 해당 디렉토리의 모든 `.md` 파일을 Read 도구로 순차 로드
   - 예: `/load modes` → `~/.claude/extensions/modes/*.md` 전체 로드

2. **개별 파일 로드**:
   - 매핑 테이블에서 경로 찾기
   - Read 도구로 해당 파일 로드
   - 예: `/load brainstorm` → `~/.claude/extensions/modes/brainstorming.md` 로드

3. **확인 메시지 출력**:
   ```
   ✅ [target] 로드 완료 (~X 토큰)
   ```

## Examples

```bash
# 모든 모드 문서 로드
/load modes

# Sequential MCP 문서만 로드
/load sequential

# 비즈니스 패널 전체 로드
/load business

# 전체 규칙 문서 로드
/load rules

# 전체 확장 로드 (비상용)
/load all
```

## Notes

- 세션 시작 시 기본 CLAUDE.md만 로드됨 (~2,500 토큰)
- 필요한 확장만 로드하여 토큰 효율 유지
- `all` 로드는 비상 시에만 사용 (전체 ~25,000 토큰)
