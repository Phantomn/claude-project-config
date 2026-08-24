# harness-core

프로젝트마다 복사돼 갈라지던 하네스 자산의 **단일 저장 위치**. 프로젝트는 사본을 두지 않고
`enabledPlugins` 로 참조한다.

## 왜 이 플러그인이 생겼나

2026-08-24 실측: 같은 개념의 훅이 프로젝트 3벌로 갈라져 있었고(`auto-approve-readonly.sh` —
agent·analysis·bounty, **셋 다 내용 상이**), 하네스 파일 98개 중 2개 이상 프로젝트가 공유하는
8개의 **완전동일본은 0개**였다. 반대로 유일하게 동일했던 2개는 아무도 안 건드린 템플릿 잔재였다.
*실제로 쓰이는 것은 전부 갈라졌고, 갈라지지 않은 것은 아무도 안 쓴 것이다.*

## 담는 기준

**이빨(teeth)이 있는 것만.** 자기검증 없는 자산을 공유하면 결함도 함께 배포된다.
현재: `auto-approve-readonly.sh` + `t_auto_approve_rm.py`(20 케이스).

## 프로젝트별 값 (env 노브 — settings.json 의 `env`)

| 노브 | 기본 | 뜻 |
|---|---|---|
| `HARNESS_RM_REPO_DIRS` | `src\|lib\|app\|docs\|scripts\|.claude` | 재귀삭제 시 ask 로 올릴 저장소 추적 트리. 저장소마다 다르다 |
| `HARNESS_CODEREAD_GUARD` | `0`(끔) | bash 코드읽기 차단. **codegraph/serena 가 실제로 붙은 프로젝트에서만 켠다** — 없는 프로젝트에서 켜면 없는 도구를 권하며 막는다 |

## 자기검증

```bash
python3 "$CLAUDE_PLUGIN_ROOT/hooks/t_auto_approve_rm.py"   # 20 케이스
```
