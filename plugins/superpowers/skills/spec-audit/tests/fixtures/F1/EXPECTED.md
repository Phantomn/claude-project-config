# F1: refs 단언 모음 (7.3)
targets: docs/plans/f1-plan.md pkg/docs/specs/f1-spec.md
round 1 must: ref-missing @ pkg/docs/specs/f1-spec.md:20
round 1 must: interface-mismatch|ref-missing @ docs/plans/f1-plan.md:105
round 1 must: constraint-drift|cross-doc-conflict @ docs/plans/f1-plan.md:7
round 1 must: ref-missing|ref-mismatch @ pkg/docs/specs/f1-spec.md:21
round 1 must: ref-missing @ pkg/docs/specs/f1-spec.md:22
round 1 must_not: ref-missing @ pkg/docs/specs/f1-spec.md:9
round 1 must_not: ref-missing @ pkg/docs/specs/f1-spec.md:18
round 1 must_not: ref-missing @ pkg/docs/specs/f1-spec.md:14
round 1 must_not: ref-missing @ pkg/docs/specs/f1-spec.md:19
round 1 must_not: requirement-uncovered|unverifiable-step @ docs/plans/f1-plan.md:15-58
round 1 must_not: requirement-uncovered|unverifiable-step @ docs/plans/f1-plan.md:12
round 1 must: unverifiable-step|requirement-uncovered @ docs/plans/f1-plan.md:13
round 1 header_contains: 6.4.2-phantomn.6
outcome: any
