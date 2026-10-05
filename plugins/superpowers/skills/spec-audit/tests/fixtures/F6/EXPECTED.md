# F6: 실행으로 반증되는 기대 출력과 네트워크가 필요한 Step (7.3)
targets: docs/plans/f6-plan.md docs/specs/f6-spec.md
round 1 must: exec-fail @ docs/plans/f6-plan.md:14
round 1 must: unverifiable-step|exec-fail|*unverified @ docs/plans/f6-plan.md:15
outcome: any
