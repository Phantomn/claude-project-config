# TeammateIdle / TaskCompleted 훅 이벤트 사용법

## 전제 조건

이 두 이벤트는 **Agent Teams(에이전트 팀)** 기능과 함께 동작하므로, 먼저 활성화가 필요합니다:

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
```

또는 `settings.json`에서:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

**주의**: Agent Teams는 현재 실험적(experimental) 기능이며, 토큰 소비가 매우 큽니다.

---

## 이벤트 개요

┌───────────────┬─────────────────────────────────────────────────┬─────────────────────────────┐
│    이벤트     │                    발생 시점                    │            용도             │
├───────────────┼─────────────────────────────────────────────────┼─────────────────────────────┤
│ TeammateIdle  │ 팀원 에이전트가 작업을 마치고 유휴 상태가 될 때 │ 새 태스크 할당, 외부 알림   │
├───────────────┼─────────────────────────────────────────────────┼─────────────────────────────┤
│ TaskCompleted │ 공유 태스크 리스트에서 태스크가 완료될 때       │ 의존 태스크 해제, 진행 추적 │
└───────────────┴─────────────────────────────────────────────────┴─────────────────────────────┘

### 기존 이벤트와의 차이

┌───────────────┬────────────────────────────────┬─────────────────────────────┐
│    이벤트     │              범위              │            대상             │
├───────────────┼────────────────────────────────┼─────────────────────────────┤
│ Stop          │ 메인 에이전트 응답 완료        │ 단일 에이전트               │
├───────────────┼────────────────────────────────┼─────────────────────────────┤
│ SubagentStop  │ 서브에이전트 작업 완료         │ Task tool로 생성된 에이전트 │
├───────────────┼────────────────────────────────┼─────────────────────────────┤
│ TaskCompleted │ 팀 태스크 리스트의 태스크 완료 │ 팀 수준 태스크 관리         │
├───────────────┼────────────────────────────────┼─────────────────────────────┤
│ TeammateIdle  │ 팀원이 유휴 상태 진입          │ 팀원 상태 감지              │
└───────────────┴────────────────────────────────┴─────────────────────────────┘

---

## 메시지 형식

### TeammateIdle 입력 (stdin으로 전달)

```json
{
  "type": "idle_notification",
  "from": "worker-1",
  "timestamp": "2026-02-06T10:30:00.000Z",
  "completedTaskId": "2",
  "completedStatus": "completed",
  "session_id": "abc123",
  "cwd": "/path/to/project"
}
```

### TaskCompleted 입력

```json
{
  "type": "task_completed",
  "from": "worker-1",
  "taskId": "2",
  "taskSubject": "Review authentication module",
  "timestamp": "2026-02-06T10:30:00.000Z",
  "session_id": "abc123",
  "cwd": "/path/to/project"
}
```

---

## 설정 예시

Hook은 `settings.json` 또는 `.claude/settings.json`에 정의합니다.

### 1) 태스크 완료 시 Slack 알림

```json
{
  "hooks": {
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "jq -r '\"Task \" + .taskId + \" (\" + .taskSubject + \") completed by \" + .from' | xargs -I{} curl -X POST -d '{\"text\":\"{}\"}' $SLACK_WEBHOOK_URL"
          }
        ]
      }
    ]
  }
}
```

### 2) 팀원 유휴 시 로그 기록

```json
{
  "hooks": {
    "TeammateIdle": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "jq -c '{event: \"teammate_idle\", agent: .from, completed_task: .completedTaskId, time: .timestamp}' >> /tmp/agent-team.log"
          }
        ]
      }
    ]
  }
}
```

### 3) 태스크 완료 시 자동 테스트 실행 (Prompt 타입)

```json
{
  "hooks": {
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Task $TASK_SUBJECT was completed. Check if related tests should be run and respond with {\"ok\": true} or {\"ok\": false, \"reason\": \"why\"}."
          }
        ]
      }
    ]
  }
}
```

---

## Agent Teams 워크플로우에서의 활용 패턴

### 패턴 1: Swarm (자기 조직화)

```
태스크 풀 → 팀원이 자율적으로 클레임
          → 완료 시 TaskCompleted 발생
          → TeammateIdle로 유휴 감지
          → 다음 미할당 태스크 자동 클레임
```

**활용 예시**:
- TeammateIdle 훅에서 미할당 태스크를 찾아 해당 팀원에게 자동 할당
- TaskCompleted 훅에서 전체 진행률 계산 후 대시보드 업데이트

### 패턴 2: Pipeline (순차 처리)

```
태스크1 완료 (TaskCompleted)
  → 태스크2 의존성 자동 해제
    → 태스크2 수행
      → TaskCompleted → 태스크3 해제 → ...
```

**활용 예시**:
- TaskCompleted 훅에서 의존 태스크를 자동 시작
- 각 단계 완료 시 로그 기록 및 알림

### 패턴 3: 병렬 전문가

```
팀 리더 → 팀원A(보안) + 팀원B(성능) + 팀원C(테스트)
        → 각각 TaskCompleted 발생
        → 모두 완료 시 리더가 결과 종합
```

**활용 예시**:
- 각 전문가의 TaskCompleted를 집계
- 모든 리뷰 완료 시 리더에게 종합 보고 트리거

---

## 실전 예시

### 예시 1: 진행률 추적

```json
{
  "hooks": {
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "echo \"$(date): Task $TASK_ID completed\" >> progress.log && wc -l progress.log"
          }
        ]
      }
    ]
  }
}
```

### 예시 2: 팀원 유휴 시 다음 작업 자동 할당

```json
{
  "hooks": {
    "TeammateIdle": [
      {
        "hooks": [
          {
            "type": "prompt",
            "prompt": "Teammate $FROM is now idle after completing task $COMPLETED_TASK_ID. Check the task list and assign the next available task if any."
          }
        ]
      }
    ]
  }
}
```

### 예시 3: 태스크 완료 시 GitHub 이슈 자동 닫기

```json
{
  "hooks": {
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "gh issue close $(jq -r '.taskSubject' | grep -oP '#\\K\\d+')"
          }
        ]
      }
    ]
  }
}
```

### 예시 4: 팀 전체 완료 감지

```bash
# 별도 스크립트: check_team_completion.sh
#!/bin/bash
TOTAL_TASKS=$(cat tasks.json | jq '.total')
COMPLETED_TASKS=$(cat progress.log | wc -l)

if [ "$COMPLETED_TASKS" -eq "$TOTAL_TASKS" ]; then
  echo "All tasks completed! 🎉"
  notify-send "Team work completed"
fi
```

```json
{
  "hooks": {
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "./check_team_completion.sh"
          }
        ]
      }
    ]
  }
}
```

---

## 환경 변수 활용

훅 명령어 내에서 사용 가능한 변수:

### TeammateIdle
- `$FROM`: 팀원 ID
- `$COMPLETED_TASK_ID`: 완료한 태스크 ID
- `$COMPLETED_STATUS`: 태스크 상태 (completed/deleted)
- `$TIMESTAMP`: 이벤트 발생 시각
- `$SESSION_ID`: 세션 ID
- `$CWD`: 작업 디렉토리

### TaskCompleted
- `$FROM`: 작업을 완료한 팀원 ID
- `$TASK_ID`: 완료된 태스크 ID
- `$TASK_SUBJECT`: 태스크 제목
- `$TIMESTAMP`: 완료 시각
- `$SESSION_ID`: 세션 ID
- `$CWD`: 작업 디렉토리

---

## 디버깅 팁

### 훅 이벤트 로깅

```json
{
  "hooks": {
    "TeammateIdle": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cat > /tmp/teammate-idle-$FROM-$(date +%s).json"
          }
        ]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cat > /tmp/task-completed-$TASK_ID-$(date +%s).json"
          }
        ]
      }
    ]
  }
}
```

### 테스트 시나리오

1. **간단한 팀 생성**:
   ```
   "2명의 팀원을 만들고, 각자 간단한 파일 읽기 태스크를 할당해줘"
   ```

2. **훅 트리거 확인**:
   ```bash
   # 로그 모니터링
   tail -f /tmp/agent-team.log
   ```

3. **TaskCompleted 검증**:
   ```bash
   # 완료된 태스크 카운트
   grep "task_completed" /tmp/agent-team.log | wc -l
   ```

---

## 제한사항

- 공식 hooks 레퍼런스에는 아직 기존 12개 이벤트만 정식 문서화되어 있으며, **TeammateIdle/TaskCompleted는 체인지로그에서만 언급**
- 세션 재개(`--resume`) 시 진행 중인 팀원 복원 불가
- 세션당 하나의 팀만 운영 가능, 중첩 팀 불가
- 분할 패널 모드는 tmux 또는 iTerm2 필요

---

## 관련 문서

- [Agent Teams 가이드](./AGENT-TEAMS-GUIDE.md)
- [Auto Memory 가이드](./AUTO-MEMORY-GUIDE.md)

---

## 참고 문서

- https://code.claude.com/docs/en/hooks
- https://code.claude.com/docs/en/agent-teams
- https://code.claude.com/docs/en/hooks-guide
