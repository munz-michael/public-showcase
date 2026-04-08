"""
SAL — Self-Adversarial Loop.

Chains RedTeamGenerator + ThymusSelector into an autonomous
hardening loop that converges toward equilibrium.

Biological analogy: thymus-inspired dual selection.
- Generate attack variants (red team)
- Test them (positive selection)
- Derive rules from bypasses (rule derivation)
- Eliminate autoimmune rules (negative selection / thymus check)
- Result: defense strengthens without becoming autoimmune
"""

from dataclasses import dataclass, field
from typing import Optional

from .defense import LayeredDefense
from .sal_red_team import AttackVariant, RedTeamGenerator
from .sal_thymus import (
    DerivedRule,
    NegativeSelectionResult,
    PositiveSelectionResult,
    ThymusSelector,
)


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------

@dataclass
class RoundStats:
    """Statistics for a single SAL round."""
    round_number: int
    mutations_tested: int
    bypasses_found: int
    rules_derived: int
    rules_accepted: int
    rules_rejected: int
    rules_calibrated: int
    bypass_rate: float
    defense_strength: float
    new_dynamic_patterns: int
    new_dynamic_keywords: int


@dataclass
class SALReport:
    """Final report from a complete SAL run."""
    rounds: list[RoundStats] = field(default_factory=list)
    total_mutations_tested: int = 0
    total_bypasses_found: int = 0
    total_rules_derived: int = 0
    total_rules_accepted: int = 0
    total_rules_rejected: int = 0
    initial_bypass_rate: float = 0.0
    final_bypass_rate: float = 0.0
    equilibrium_reached: bool = False
    equilibrium_round: Optional[int] = None


# ---------------------------------------------------------------------------
# SelfAdversarialLoop
# ---------------------------------------------------------------------------

class SelfAdversarialLoop:
    """
    Autonomous defense hardening loop.

    Each round:
    1. Red Team generates N mutations from current bypasses
    2. Each mutation is tested (positive selection)
    3. New bypasses -> derive candidate rules
    4. Candidate rules -> thymus test (negative selection)
    5. Accepted rules -> add to defense
    6. Measure: bypass rate, FP rate, defense_strength, rules_added
    7. If no new bypasses found -> equilibrium reached -> stop
    """

    def __init__(
        self,
        defense: LayeredDefense,
        legitimate_inputs: list[str],
        max_rounds: int = 10,
        mutations_per_bypass: int = 10,
        novel_count: int = 5,
        seed: int = 42,
    ) -> None:
        self.defense = defense
        self.red_team = RedTeamGenerator(seed=seed)
        self.thymus = ThymusSelector(defense, legitimate_inputs)
        self.max_rounds = max_rounds
        self.mutations_per_bypass = mutations_per_bypass
        self.novel_count = novel_count
        self.round_stats: list[RoundStats] = []

    def run(
        self,
        seed_bypasses: list[tuple[str, str]],
    ) -> SALReport:
        """
        Run the full self-adversarial loop.

        seed_bypasses: list of (input_text, output_text) that bypass the defense.
        Returns SALReport with convergence metrics.
        """
        report = SALReport()
        current_bypasses = list(seed_bypasses)

        # Measure initial bypass rate from seeds
        if seed_bypasses:
            initial_bypass_count = 0
            for inp, out in seed_bypasses:
                result = self.thymus.test_attack(inp, out)
                if result.outcome == "bypass":
                    initial_bypass_count += 1
            report.initial_bypass_rate = initial_bypass_count / len(seed_bypasses)
        else:
            report.initial_bypass_rate = 0.0

        for round_num in range(1, self.max_rounds + 1):
            stats = self._run_round(round_num, current_bypasses)
            self.round_stats.append(stats)
            report.rounds.append(stats)

            # Update totals
            report.total_mutations_tested += stats.mutations_tested
            report.total_bypasses_found += stats.bypasses_found
            report.total_rules_derived += stats.rules_derived
            report.total_rules_accepted += stats.rules_accepted
            report.total_rules_rejected += stats.rules_rejected

            # Check for equilibrium: no new bypasses found
            if stats.bypasses_found == 0:
                report.equilibrium_reached = True
                report.equilibrium_round = round_num
                break

            # Collect new bypasses for next round
            # (they were already collected in _run_round)

        # Measure final bypass rate by retesting all seed bypasses
        if seed_bypasses:
            final_bypass_count = 0
            for inp, out in seed_bypasses:
                result = self.thymus.test_attack(inp, out)
                if result.outcome == "bypass":
                    final_bypass_count += 1
            report.final_bypass_rate = final_bypass_count / len(seed_bypasses)
        else:
            report.final_bypass_rate = 0.0

        return report

    def _run_round(
        self,
        round_number: int,
        current_bypasses: list[tuple[str, str]],
    ) -> RoundStats:
        """Execute a single SAL round."""
        mutations_tested = 0
        bypasses_found = 0
        rules_derived = 0
        rules_accepted = 0
        rules_rejected = 0
        rules_calibrated = 0
        new_dynamic_patterns = 0
        new_dynamic_keywords = 0
        new_bypasses: list[tuple[str, str]] = []

        # Step 1: Generate mutations from current bypasses
        all_variants: list[AttackVariant] = []
        for inp, out in current_bypasses:
            variants = self.red_team.generate_variants(
                inp, out,
                n=self.mutations_per_bypass,
                generation=round_number,
            )
            all_variants.extend(variants)

        # Also generate novel cross-category variants
        if len(current_bypasses) >= 2:
            novels = self.red_team.generate_novel(
                current_bypasses,
                n=self.novel_count,
            )
            all_variants.extend(novels)

        # Step 2: Test each variant (positive selection)
        for variant in all_variants:
            mutations_tested += 1
            result = self.thymus.test_attack(
                variant.input_text,
                variant.output_text,
            )
            if result.outcome == "bypass":
                bypasses_found += 1
                new_bypasses.append((variant.input_text, variant.output_text))

        # Step 3: Derive candidate rules from new bypasses
        candidate_rules: list[DerivedRule] = []
        for inp, out in new_bypasses:
            derived = self.thymus.derive_rule(inp, out)
            candidate_rules.extend(derived)
            rules_derived += len(derived)

        # Step 4: Thymus test (negative selection) for each candidate rule
        for candidate in candidate_rules:
            neg_result = self.thymus.test_rule(
                candidate.pattern,
                candidate.rule_name,
            )

            if neg_result.verdict == "accept":
                rules_accepted += 1
                # Add to defense
                added = self._apply_rule(candidate)
                if added == "pattern":
                    new_dynamic_patterns += 1
                elif added == "keyword":
                    new_dynamic_keywords += 1

            elif neg_result.verdict == "calibrate":
                rules_calibrated += 1
                # Still add, but with a note (hormesis warning)
                added = self._apply_rule(candidate)
                if added == "pattern":
                    new_dynamic_patterns += 1
                elif added == "keyword":
                    new_dynamic_keywords += 1

            else:
                rules_rejected += 1

        # Update current_bypasses for next round (in-place)
        current_bypasses.clear()
        current_bypasses.extend(new_bypasses)

        # Compute bypass rate for this round
        bypass_rate = bypasses_found / mutations_tested if mutations_tested > 0 else 0.0

        return RoundStats(
            round_number=round_number,
            mutations_tested=mutations_tested,
            bypasses_found=bypasses_found,
            rules_derived=rules_derived,
            rules_accepted=rules_accepted,
            rules_rejected=rules_rejected,
            rules_calibrated=rules_calibrated,
            bypass_rate=bypass_rate,
            defense_strength=self.defense.defense_strength,
            new_dynamic_patterns=new_dynamic_patterns,
            new_dynamic_keywords=new_dynamic_keywords,
        )

    def _apply_rule(self, rule: DerivedRule) -> str:
        """
        Apply a derived rule to the defense.
        Returns "pattern" or "keyword" depending on what was added.
        """
        if rule.source == "output":
            # Output-side: add as invariant monitor pattern
            self.defense.formal_verifier.monitor.add_pattern(
                rule.pattern,
                rule.rule_name,
            )
            return "pattern"
        else:
            # Input-side: add both as monitor pattern (for output checks)
            # and as keyword for anomaly scoring
            self.defense.formal_verifier.monitor.add_pattern(
                rule.pattern,
                rule.rule_name,
            )
            # Extract a keyword from the rule name for keyword scoring
            keyword = rule.rule_name.replace("_", " ").lower()
            # Only add meaningful keywords (not generic ones)
            if len(keyword) > 4:
                self.defense.pattern_learner.add_keyword(keyword)
                return "keyword"
            return "pattern"
