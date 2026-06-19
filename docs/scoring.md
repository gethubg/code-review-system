# Scoring & Verdicts

The production score is a single number from 0 to 100 that summarises overall code quality. It is calculated deterministically by the Synthesizer after all three agents complete.

---

## Score Formula

```
score = 100 − Σ(finding_count × severity_weight)
```

Clamped to `[0, 100]`.

### Severity weights

| Severity | Weight (points per finding) |
|---|---|
| `critical` | 20 |
| `high` | 10 |
| `medium` | 4 |
| `low` | 1 |
| `info` | 0 |

**Example**

A repo with:
- 0 critical
- 2 high
- 5 medium
- 8 low

```
deductions = (0 × 20) + (2 × 10) + (5 × 4) + (8 × 1)
           = 0 + 20 + 20 + 8
           = 48

score = max(0, 100 − 48) = 52
```

---

## Critical security override

If any finding has `severity = "critical"` and `agent = "security"`, the score is hard-capped at **30** regardless of the formula result.

The rationale: a single exploitable vulnerability makes a codebase unshippable regardless of how many other things are correct.

---

## Verdict thresholds

| Score range | Verdict |
|---|---|
| 80 – 100 | **PRODUCTION READY** |
| 50 – 79 | **NEEDS IMPROVEMENT** |
| 0 – 49 | **NOT PRODUCTION READY** |

---

## Worked examples

### Example A — Green repo

| Agent | Critical | High | Medium | Low |
|---|---|---|---|---|
| Bug | 0 | 0 | 1 | 2 |
| Security | 0 | 0 | 0 | 1 |
| Coverage | 0 | 0 | 1 | 3 |
| **Total** | **0** | **0** | **2** | **6** |

```
deductions = (2 × 4) + (6 × 1) = 14
score = 100 − 14 = 86 → PRODUCTION READY
```

---

### Example B — Security incident

| Agent | Critical | High | Medium | Low |
|---|---|---|---|---|
| Bug | 0 | 1 | 3 | 5 |
| Security | 1 | 2 | 1 | 0 |
| Coverage | 0 | 0 | 2 | 4 |
| **Total** | **1** | **3** | **6** | **9** |

```
raw deductions = (1×20) + (3×10) + (6×4) + (9×1) = 73
raw score      = 100 − 73 = 27

critical security override applies → score = min(27, 30) = 27
→ NOT PRODUCTION READY
```

---

### Example C — Middle ground

| Agent | Critical | High | Medium | Low |
|---|---|---|---|---|
| Bug | 0 | 1 | 4 | 3 |
| Security | 0 | 1 | 2 | 2 |
| Coverage | 0 | 1 | 3 | 5 |
| **Total** | **0** | **3** | **9** | **10** |

```
deductions = (3×10) + (9×4) + (10×1) = 76
score = 100 − 76 = 24 → NOT PRODUCTION READY
```

Wait — with only `high` findings this result feels harsh. The formula is intentionally strict because unresolved `high` findings represent real production risk.

---

## Finding count caps

To prevent a single extremely noisy agent from distorting the score, a per-agent cap applies before weighting:

| Agent | Max findings counted |
|---|---|
| Bug | 50 |
| Security | 50 |
| Coverage | 50 |

Findings beyond the cap are recorded and displayed in the UI but do not contribute further score deductions.

---

## Per-severity score display

The UI colour-codes the score badge:

| Score | Badge colour |
|---|---|
| ≥ 80 | Green (`--color-completed`) |
| 50–79 | Amber (`--color-medium`) |
| < 50 | Red (`--color-critical`) |

The same colour scale is used for the verdict text in `ResultsPage.tsx` via `verdictColor()`.
