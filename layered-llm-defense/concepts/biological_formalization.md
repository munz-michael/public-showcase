# Biological Formalization for LLM Defense

> Formal transfer of biological antifragility models to Layer 2
> (Antifragile Shell) and adjacent layers of the Layered LLM Defense
> architecture.

This document collects the six biological models used by LLD as
architectural primitives, with their mathematical form, the
corresponding LLD primitive, and a Python sketch.

The complete English-language treatment is in
[`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md),
Section 4 (Biologically-inspired Primitives).

---

## 1. Hormesis curve for security rules

### 1.1 Biological foundation

In biology, hormesis is the principle that small doses of a
stressor strengthen an organism while large doses harm it.
Applied to security: too few attacks mean a rule has not been
tested (fragile); an optimal attack density strengthens the rule
(antifragile); too many false positives produce autoimmunity, where
the rule begins to block legitimate requests.

### 1.2 Mathematical formalization

```
Let D(r)    be the defense strength of a security rule r.
Let A       = {a1, a2, ..., an} be the set of attacks against r.
Let B(ai)   = 1 if attack ai was blocked, 0 otherwise.
Let FP(r)   be the false positive rate of r.

Hormesis zones:

  [Zone 1: Untested]   |A| = 0     → D(r) = D_base(r)  (UNKNOWN, untrusted)
  [Zone 2: Benefit]    |A| small   → D(r) rises convexly with each block
  [Zone 3: Peak]       |A| optimal → maximum defense strength
  [Zone 4: Autoimmune] FP(r) > θ_FP → rule overreacts, blocks legit traffic

  ┌─────────────────────────────────────────┐
  │          *  *                            │
  │       *        *                         │  D(r)
  │    *              *                      │
  │  *                   *                   │
  │ *                       *                │
  │*                            *  *  *      │
  └─────────────────────────────────────────┘
   Zone 1   Zone 2    Zone 3      Zone 4
```

### 1.3 Convex defense strength formula

```
D(r, A) = D_base(r) * (1 + alpha * sum_{a in A} B(a)) * H(FP(r))

where:
  alpha    = strengthening rate (default 0.05)
  H(FP)    = autoimmunity damping function:
               H(FP) = 1                      if FP < theta_FP
               H(FP) = 1 - k * (FP - theta_FP) if FP >= theta_FP
```

`alpha` is small and capped (`hormesis_cap = 2.0`) so that the
convex strengthening curve flattens before any single rule
dominates the decision.

### 1.4 Python sketch

```python
def defense_strength(rule, attack_history, fp_rate,
                      alpha=0.05, theta_fp=0.10, k=2.0,
                      cap=2.0):
    """Defense strength with hormesis curve."""
    blocks = sum(1 for a in attack_history if a.blocked)
    base_amplification = 1 + alpha * blocks
    base_amplification = min(base_amplification, cap)

    if fp_rate < theta_fp:
        damping = 1.0
    else:
        damping = max(0.0, 1.0 - k * (fp_rate - theta_fp))

    return rule.base_strength * base_amplification * damping
```

See [`lld/layer2_antifragile.py`](../lld/layer2_antifragile.py) for
the production implementation.

---

## 2. Immune memory (attack pattern persistence)

### 2.1 Biological foundation

Memory T-cells provide a fast secondary immune response to known
antigens. Applied to security: previously seen attack patterns
should be blocked instantly, while novel patterns require slower
analysis.

### 2.2 Mapping

| Biological model | LLD equivalent |
|---|---|
| Antigen | Attack pattern hash |
| Memory T-cell | SQLite row in `attack_memory` |
| Primary response (slow) | Full pattern analysis through Layer 2 |
| Secondary response (fast) | Pattern-hash lookup in O(1), <5 ms |
| Affinity maturation | False-positive feedback adjusts confidence |

### 2.3 Schema

```sql
CREATE TABLE attack_memory (
    pattern_hash    TEXT PRIMARY KEY,
    attack_type     TEXT,
    result          TEXT,         -- 'blocked' / 'bypassed' / 'false_positive'
    confidence      REAL,
    first_seen      TIMESTAMP,
    last_seen       TIMESTAMP,
    occurrence_count INTEGER
);
```

### 2.4 Python sketch

```python
class ImmuneMemory:
    """Persistent attack memory."""

    def fast_check(self, pattern_hash):
        row = self.db.execute(
            "SELECT result, confidence FROM attack_memory "
            "WHERE pattern_hash = ?", (pattern_hash,)
        ).fetchone()
        if row is None:
            return None  # primary response — analyse fully
        result, confidence = row
        if result == "blocked" and confidence > 0.8:
            return True  # secondary response — block immediately
        return None
```

See [`lld/layer2_antifragile.py`](../lld/layer2_antifragile.py).

---

## 3. Barbell strategy (90/10 split)

### 3.1 Biological foundation

Taleb's barbell strategy: combine extreme conservatism in the bulk
of your portfolio with extreme exploration in a small fraction.
Applied to security: 90% of decisions go through the formally
proven core (Layer 1), while 10% explore via heuristics (Layer 2).

### 3.2 Mapping

```
90% conservative tier (Layer 1, formally verified)
  - Pydantic schemas
  - Invariant monitor with regex patterns for SQL/XSS/PII
  - Constrained decoder
  - Schema-valid output guarantee

10% exploratory tier (Layer 2, antifragile heuristics)
  - Pattern learner with Mahalanobis distance
  - Hormesis-calibrated dynamic rules
  - Self-Adversarial Loop with thymus selection
```

The exploratory tier may produce false positives or miss novel
attacks, but it cannot weaken the conservative tier — Layer 1
runs independently and its decisions are not influenced by Layer 2
state. This is the "barbell isolation" property.

---

## 4. Wolff's Law (context-specific hardening)

### 4.1 Biological foundation

Wolff's Law states that bone remodels itself in response to local
mechanical stress. Bone tissue adapts where load is applied, not
globally. Applied to security: a security rule should harden in
the *context* where it has been challenged, not globally.

### 4.2 Mapping

```
Context = (endpoint, intent, risk_level, route)

For each (rule, context) pair, maintain a separate hardening counter.
A rule that has been challenged 50 times in the /admin/login context
becomes very strong THERE but stays at baseline strength for /search.
```

### 4.3 Python sketch

```python
def context_strength(rule, context, alpha=0.05):
    """Per-context defense strength (Wolff's Law)."""
    hardenings = rule.context_history.get(context, [])
    blocks = sum(1 for h in hardenings if h.blocked)
    return rule.base_strength * (1 + alpha * blocks)
```

---

## 5. Antifragility grade (rule quality scoring)

### 5.1 Biological foundation

Forrest et al. (1997) "Computer Immunology" describes how the
immune system implicitly grades the quality of its T-cells: cells
that survive selection AND successfully respond to antigens get
promoted, cells that fail get pruned.

### 5.2 Mapping to security rule grades

| Grade | Survival rate | Challenge count | Action |
|---|---|---|---|
| A+ | > 95% | > 100 | Promote, use in fast path |
| A | > 90% | > 50 | Active, monitor |
| B | > 80% | > 20 | Active |
| C | > 70% | > 10 | Active, candidate for tightening |
| D | > 60% | any | Warning, candidate for review |
| F | < 60% | any | Deactivate, log for analysis |
| -- | any | < 10 | Untested, do not trust |

### 5.3 Python sketch

```python
def antifragility_grade(rule):
    """Quality grade for a security rule."""
    if rule.challenge_count < 10:
        return "--"
    survival_rate = rule.blocked_count / rule.challenge_count
    if survival_rate > 0.95 and rule.challenge_count > 100:
        return "A+"
    if survival_rate > 0.90 and rule.challenge_count > 50:
        return "A"
    if survival_rate > 0.80 and rule.challenge_count > 20:
        return "B"
    if survival_rate > 0.70 and rule.challenge_count > 10:
        return "C"
    if survival_rate > 0.60:
        return "D"
    return "F"
```

---

## 6. Security Chaos Monkey

### 6.1 Concept

Inspired by Netflix's Chaos Engineering practice. The Security
Chaos Monkey injects controlled attacks against security rules and
evaluates the reaction of the four-layer architecture. Rules that
survive a challenge are strengthened (Section 1, hormesis); rules
that fail are flagged for review and a patch suggestion is
generated.

### 6.2 Five challenge types

| Challenge type | Description | Target layer |
|---|---|---|
| Direct injection | Raw injection patterns (SQL, XSS, prompt) | L1 |
| Jailbreak wrapping | Role-play (DAN, EVIL, STAN), "ignore previous" | L1 + L2 |
| Obfuscation | Unicode, base64, ROT13, leet, spacing tricks | L2 |
| GCG-style suffixes | Adversarial-suffix patterns from public corpora | L1 + L2 |
| Cross-layer bypass | Multi-vector attacks targeting layer boundaries | L1-L4 |

### 6.3 Result handling

```python
def process_challenge_result(rule, challenge_type, result,
                              confidence, context):
    if result == "blocked":
        # Rule survived → antifragile strengthening
        # D(r, ctx) += alpha (Wolff's Law: context-only)
        immune_memory.record_attack(
            rule_id=rule.id,
            attack_type=challenge_type,
            result="blocked",
            confidence=confidence,
        )
        rule.recalculate_grade(context=context)

    elif result == "bypassed":
        # Rule failed → alert + suggested patch
        alert_security_team(rule, challenge_type, context)
        suggest_rule_patch(rule, challenge_content)
        rule.recalculate_grade(context=context)

    elif result == "false_positive":
        # Falsely blocked → hormesis calibration
        # If FP rate above threshold, reduce sensitivity
        rule.record_false_positive(context=context)
        if rule.false_positive_rate > THETA_FP_HIGH:
            rule.deactivate(reason="autoimmune")
```

See [`lld/sal_loop.py`](../lld/sal_loop.py) for the production
Self-Adversarial Loop implementation.

---

## 7. Summary: biological models → LLD primitives

| Biological model | LLD primitive | Section |
|---|---|---|
| Antigen | Security rule | -- |
| Challenge | Attack / Chaos Monkey test | 6 |
| Trust score / mass | Defense strength D(r) | 1, 4 |
| Hormesis curve | FP-based damping | 1 |
| Memory T-cell | `attack_memory` SQLite row | 2 |
| Fast secondary response | Pattern-hash lookup (<5 ms) | 2 |
| Barbell (90/10 portfolio) | Barbell (90/10 formal/heuristic) | 3 |
| Wolff's Law | Context-specific hardening | 4 |
| Antifragility grade | Security rule grade (A+ to --) | 5 |
| Knowledge Chaos Monkey | Security Chaos Monkey | 6 |
| Five challenge types | Five security challenge types | 6 |
| Via Negativa (composting) | Rule deactivation at grade F | 5 |
| Shannon diversity index | Multi-model diversity (Layer 4 MTD) | 3 |
| Cross-layer calibration | Cross-layer calibration via correlation engine | 1, 5 |

---

## References

- Taleb, N.N. (2012). *Antifragile: Things That Gain from Disorder*. Random House.
- Forrest, S., Hofmeyr, S.A., Somayaji, A. (1997). "Computer Immunology." *Communications of the ACM* 40(10):88-96.
- Netflix Chaos Engineering — arXiv:1702.05843
- OWASP LLM Top 10 (2025)
- See [`outputs/technical_report_2026-04-07.md`](../outputs/technical_report_2026-04-07.md) Section 4 for the complete treatment
