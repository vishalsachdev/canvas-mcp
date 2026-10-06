"""Unit tests for the pure grade arithmetic in core/grade_calc.py.

Every expected value below is worked out by hand in the comment next to it,
from Canvas's documented/observed rules, not from the implementation:

- current grade: graded work only; final grade: ungraded counts as 0
- excused and omit_from_final_grade assignments never count
- drop rules keep the subset with the best (drop_lowest) or worst
  (drop_highest) combined score/possible ratio, never-drop entries included in
  the ratio but never dropped
- weighted: groups with 0 possible are left out; rescale to 100 only when the
  counted weight is under 100
"""

import math

import pytest

from canvas_mcp.core import grade_calc as gc
from canvas_mcp.core.grade_calc import GradedItem, GroupRules


def item(aid, group="g1", points=10.0, score=None, **kw):
    return GradedItem(str(aid), group, float(points), None if score is None else float(score), **kw)


def course(groups, items, weighted=False, include_ungraded=False):
    return gc.calculate_course(groups, items, weighted, include_ungraded)


G1 = GroupRules("g1")


class TestUnweighted:
    def test_total_points_across_groups(self):
        # (8 + 15 + 45) / (10 + 20 + 50) = 68 / 80 = 85%
        groups = [GroupRules("g1"), GroupRules("g2")]
        items = [item(1, score=8), item(2, points=20, score=15), item(3, "g2", 50, 45)]
        result = course(groups, items)
        assert result.percent == pytest.approx(85.0)
        assert result.groups[0].score == 23 and result.groups[0].possible == 30
        assert result.groups[0].percent == pytest.approx(76.6666667)

    def test_ungraded_left_out_of_current_and_zero_in_final(self):
        # current: 68/80 = 85%; final: 68/(80+20) = 68%
        groups = [GroupRules("g1"), GroupRules("g2")]
        items = [item(1, score=8), item(2, points=20, score=15), item(3, "g2", 50, 45), item(4, "g2", 20)]
        assert course(groups, items).percent == pytest.approx(85.0)
        assert course(groups, items, include_ungraded=True).percent == pytest.approx(68.0)

    def test_excused_counts_in_neither_mode(self):
        # Excused 0/90 must not drag 9/10 down in either mode: 90% both ways.
        items = [item(1, score=9), item(2, points=90, score=0, excused=True), item(3, points=90, excused=True)]
        assert course([G1], items).percent == pytest.approx(90.0)
        assert course([G1], items, include_ungraded=True).percent == pytest.approx(90.0)

    def test_omitted_from_final_grade_never_counts(self):
        items = [item(1, score=9), item(2, points=100, score=0, counts_toward_grade=False)]
        assert course([G1], items).percent == pytest.approx(90.0)
        assert course([G1], items, include_ungraded=True).percent == pytest.approx(90.0)

    def test_pending_review_excluded_from_current_but_counted_in_final(self):
        # current: 9/10 = 90%; final: (9 + 4) / 20 = 65% (partial score kept)
        items = [item(1, score=9), item(2, score=4, pending_review=True)]
        assert course([G1], items).percent == pytest.approx(90.0)
        assert course([G1], items, include_ungraded=True).percent == pytest.approx(65.0)

    def test_zero_point_extra_credit_adds_score_only(self):
        # (10 + 5) / (10 + 0) = 150%
        items = [item(1, score=10), item(2, points=0, score=5)]
        assert course([G1], items).percent == pytest.approx(150.0)

    def test_no_graded_work_is_no_grade(self):
        assert course([G1], [item(1), item(2)]).percent is None
        assert course([G1], []).percent is None

    def test_items_in_unknown_group_are_ignored(self):
        assert course([G1], [item(1, score=5), item(2, "elsewhere", score=0)]).percent == pytest.approx(50.0)


class TestWeighted:
    def test_weighted_sum(self):
        # 0.9 * 40 + 0.8 * 60 = 36 + 48 = 84
        groups = [GroupRules("g1", 40), GroupRules("g2", 60)]
        items = [item(1, score=9), item(2, "g2", 100, 80)]
        result = course(groups, items, weighted=True)
        assert result.percent == pytest.approx(84.0)
        assert result.counted_weight == 100

    def test_group_without_graded_work_is_left_out_and_rest_rescaled(self):
        # Only g1 (40%) has graded work at 90%: 36 * 100 / 40 = 90%
        groups = [GroupRules("g1", 40), GroupRules("g2", 60)]
        items = [item(1, score=9), item(2, "g2", 100)]
        result = course(groups, items, weighted=True)
        assert result.percent == pytest.approx(90.0)
        assert result.counted_weight == 40
        # Final counts g2 as 0/100: 36 + 0 = 36%
        assert course(groups, items, weighted=True, include_ungraded=True).percent == pytest.approx(36.0)

    def test_weights_under_100_are_rescaled(self):
        # (0.9 * 30 + 0.8 * 30) / 60 * 100 = 51 / 60 * 100 = 85
        groups = [GroupRules("g1", 30), GroupRules("g2", 30)]
        items = [item(1, score=9), item(2, "g2", 10, 8)]
        assert course(groups, items, weighted=True).percent == pytest.approx(85.0)

    def test_weights_over_100_are_not_scaled_down(self):
        # 1.0 * 60 + 1.0 * 60 = 120
        groups = [GroupRules("g1", 60), GroupRules("g2", 60)]
        items = [item(1, score=10), item(2, "g2", 10, 10)]
        assert course(groups, items, weighted=True).percent == pytest.approx(120.0)

    def test_zero_counted_weight_is_no_grade(self):
        groups = [GroupRules("g1", 0), GroupRules("g2", 0)]
        items = [item(1, score=9), item(2, "g2", 10, 8)]
        assert course(groups, items, weighted=True).percent is None

    def test_zero_possible_extra_credit_group_is_left_out(self):
        # g2 holds only a 0-point bonus. Canvas filters groups on possible > 0,
        # so the bonus does not count when weighted: 0.8 * 50 / 50 * 100 = 80.
        groups = [GroupRules("g1", 50), GroupRules("g2", 50)]
        items = [item(1, score=8), item(2, "g2", 0, 5)]
        assert course(groups, items, weighted=True).percent == pytest.approx(80.0)
        # Unweighted, the same bonus counts: (8 + 5) / 10 = 130%
        assert course(groups, items, weighted=False).percent == pytest.approx(130.0)

    def test_zero_weight_group_with_work_contributes_nothing(self):
        # g2 is weight 0 but graded at 0%: 0.9 * 50 / 50 * 100 = 90
        groups = [GroupRules("g1", 50), GroupRules("g2", 0)]
        items = [item(1, score=9), item(2, "g2", 10, 0)]
        assert course(groups, items, weighted=True).percent == pytest.approx(90.0)


def entries(*pairs, ids=None):
    ids = ids or [str(i + 1) for i in range(len(pairs))]
    return [gc._Entry(ids[i], float(s), float(t), i) for i, (s, t) in enumerate(pairs)]


def kept_ids(kept):
    return [e.assignment_id for e in kept]


class TestDropRules:
    def test_no_rules_keeps_everything(self):
        kept, dropped = gc.drop_assignments(entries((1, 10), (2, 10)))
        assert kept_ids(kept) == ["1", "2"] and dropped == []

    def test_drop_lowest_equal_totals(self):
        # 5/10, 8/10, 9/10 drop 1 -> keep 8 and 9: 17/20
        grade = gc.calculate_group(
            GroupRules("g1", drop_lowest=1), [item(1, score=5), item(2, score=8), item(3, score=9)], False
        )
        assert grade.dropped == ("1",)
        assert (grade.score, grade.possible) == (17, 20)

    def test_drop_lowest_maximizes_ratio_not_lowest_percent(self):
        # A 2/10 (20%), B 0/1 (0%), C 50/100 (50%), drop 1:
        #   drop A -> 50/101 = 49.50%   <- best
        #   drop B -> 52/110 = 47.27%   (naive "lowest percent" choice)
        #   drop C ->  2/11  = 18.18%
        grade = gc.calculate_group(
            GroupRules("g1", drop_lowest=1),
            [item("A", points=10, score=2), item("B", points=1, score=0), item("C", points=100, score=50)],
            False,
        )
        assert grade.dropped == ("A",)
        assert grade.percent == pytest.approx(50 / 101 * 100)

    def test_drop_highest_minimizes_ratio(self):
        # 5/10, 8/10, 9/10 drop highest 1 -> keep 5 and 8: 13/20 = 65%
        grade = gc.calculate_group(
            GroupRules("g1", drop_highest=1), [item(1, score=5), item(2, score=8), item(3, score=9)], False
        )
        assert grade.dropped == ("3",)
        assert grade.percent == pytest.approx(65.0)

    def test_drop_lowest_and_highest_together(self):
        # 2, 5, 8, 10 out of 10; drop low 1 and high 1 -> keep 5 and 8: 13/20
        grade = gc.calculate_group(
            GroupRules("g1", drop_lowest=1, drop_highest=1),
            [item(1, score=2), item(2, score=5), item(3, score=8), item(4, score=10)],
            False,
        )
        assert sorted(grade.dropped) == ["1", "4"]
        assert (grade.score, grade.possible) == (13, 20)

    def test_never_drop_protects_the_lowest(self):
        # 2/10 is protected, so the next lowest (5/10) goes: (2 + 9) / 20 = 55%
        grade = gc.calculate_group(
            GroupRules("g1", drop_lowest=1, never_drop=frozenset({"1"})),
            [item(1, score=2), item(2, score=5), item(3, score=9)],
            False,
        )
        assert grade.dropped == ("2",)
        assert grade.kept == ("1", "3")
        assert grade.percent == pytest.approx(55.0)

    def test_never_drop_entries_are_part_of_the_ratio(self):
        # Protected P = 0/100. Candidates A = 1/2 (50%) and B = 30/100 (30%), drop 1:
        #   keep A -> (0 + 1) / (100 + 2)   =  0.98%
        #   keep B -> (0 + 30) / (100 + 100) = 15.00%   <- best, so A (the higher %) is dropped
        grade = gc.calculate_group(
            GroupRules("g1", drop_lowest=1, never_drop=frozenset({"P"})),
            [item("P", points=100, score=0), item("A", points=2, score=1), item("B", points=100, score=30)],
            False,
        )
        assert grade.dropped == ("A",)
        assert grade.percent == pytest.approx(15.0)

    def test_everything_never_drop_means_nothing_dropped(self):
        kept, dropped = gc.drop_assignments(entries((1, 10), (9, 10)), 1, 0, frozenset({"1", "2"}))
        assert kept_ids(kept) == ["1", "2"] and dropped == []

    def test_drop_lowest_clamped_to_keep_one(self):
        # drop_lowest 5 with two graded: Canvas keeps one, the best (9/10).
        kept, dropped = gc.drop_assignments(entries((3, 10), (9, 10)), 5, 0)
        assert kept_ids(kept) == ["2"] and kept_ids(dropped) == ["1"]

    def test_drop_highest_ignored_when_rules_would_empty_the_group(self):
        # 2 items, drop low 1 + high 1 >= 2: Canvas zeroes drop_highest -> keep best.
        kept, _ = gc.drop_assignments(entries((3, 10), (9, 10)), 1, 1)
        assert kept_ids(kept) == ["2"]

    def test_drop_highest_alone_clamps_too(self):
        # 2 items drop highest 5: drop_lowest 0, 0 + 5 >= 2 -> drop_highest ignored.
        kept, dropped = gc.drop_assignments(entries((3, 10), (9, 10)), 0, 5)
        assert kept_ids(kept) == ["1", "2"] and dropped == []

    def test_drops_apply_only_to_graded_work_in_current_grade(self):
        # 4/10, 9/10 graded and one ungraded; drop 1.
        # current: only the graded two compete -> drop 4: 9/10 = 90%
        # final: the ungraded counts as 0/10 and is the one dropped: 13/20 = 65%
        items = [item(1, score=4), item(2, score=9), item(3)]
        rules = [GroupRules("g1", drop_lowest=1)]
        assert course(rules, items).percent == pytest.approx(90.0)
        final = course(rules, items, include_ungraded=True)
        assert final.groups[0].dropped == ("3",)
        assert final.percent == pytest.approx(65.0)

    def test_excused_is_removed_before_dropping(self):
        # Excused must not use up the drop: 4/10 is still the one dropped.
        items = [item(1, score=4), item(2, score=9), item(3, score=0, excused=True)]
        grade = course([GroupRules("g1", drop_lowest=1)], items)
        assert grade.groups[0].dropped == ("1",)
        assert grade.percent == pytest.approx(90.0)

    def test_unpointed_group_drops_by_score(self):
        # Every total is 0 (bonus-only group): keep the two highest scores 3 and 2.
        kept, dropped = gc.drop_assignments(entries((3, 0), (1, 0), (2, 0)), 1, 0)
        assert kept_ids(kept) == ["1", "3"] and kept_ids(dropped) == ["2"]

    def test_unpointed_tie_breaks_on_assignment_id(self):
        # Equal scores: lower ID sorts first, so the lower ID is the one dropped.
        kept, dropped = gc.drop_assignments(entries((1, 0), (1, 0), ids=["20", "3"]), 1, 0)
        assert kept_ids(dropped) == ["3"] and kept_ids(kept) == ["20"]

    def test_zero_point_bonus_beats_pointed_work_when_keeping_one(self):
        # Keep 1 of {10/10, 5 bonus/0}: keeping the bonus has an unbounded ratio,
        # which is what Canvas's search converges to as well.
        kept, dropped = gc.drop_assignments(entries((10, 10), (5, 0)), 1, 0)
        assert kept_ids(kept) == ["2"] and kept_ids(dropped) == ["1"]

    @pytest.mark.parametrize("seed", range(25))
    def test_drop_lowest_matches_brute_force_optimum(self, seed):
        """Dinkelbach must reach the true best ratio for any drop count."""
        import itertools
        import random

        rng = random.Random(seed)
        n = rng.randint(2, 8)
        pairs = []
        for _ in range(n):
            total = rng.choice([1, 5, 10, 20, 50, 100])
            pairs.append((rng.randint(0, total), total))
        cant = [(rng.randint(0, 10), 10)] if rng.random() < 0.4 else []
        all_pairs = cant + pairs
        ids = [f"c{i}" for i in range(len(cant))] + [str(i) for i in range(n)]
        es = entries(*all_pairs, ids=ids)
        drop = rng.randint(1, n - 1)
        kept, _ = gc.drop_assignments(es, drop, 0, frozenset(ids[: len(cant)]))

        cant_s = sum(s for s, _ in cant)
        cant_t = sum(t for _, t in cant)
        best = max(
            (cant_s + sum(s for s, _ in combo)) / (cant_t + sum(t for _, t in combo))
            for combo in itertools.combinations(pairs, n - drop)
        )
        got = sum(e.score for e in kept) / sum(e.total for e in kept)
        assert got == pytest.approx(best, abs=1e-12)

    @pytest.mark.parametrize("seed", range(25))
    def test_drop_highest_matches_brute_force_optimum(self, seed):
        import itertools
        import random

        rng = random.Random(1000 + seed)
        n = rng.randint(2, 8)
        pairs = [(rng.randint(0, t), t) for t in (rng.choice([1, 5, 10, 50]) for _ in range(n))]
        drop = rng.randint(1, n - 1)
        kept, _ = gc.drop_assignments(entries(*pairs), 0, drop)
        worst = min(
            sum(s for s, _ in combo) / sum(t for _, t in combo)
            for combo in itertools.combinations(pairs, n - drop)
        )
        got = sum(e.score for e in kept) / sum(e.total for e in kept)
        assert got == pytest.approx(worst, abs=1e-12)

    def test_weighted_course_with_drops(self):
        # g1 (60%): 5/10, 9/10, 10/10 drop lowest 1 -> 19/20 = 95%
        # g2 (40%): 70/100
        # 0.95 * 60 + 0.70 * 40 = 57 + 28 = 85
        groups = [GroupRules("g1", 60, drop_lowest=1), GroupRules("g2", 40)]
        items = [item(1, score=5), item(2, score=9), item(3, score=10), item(4, "g2", 100, 70)]
        assert course(groups, items, weighted=True).percent == pytest.approx(85.0)


class TestHypotheticals:
    def test_apply_sets_score_and_clears_pending_and_excused(self):
        items = [item(1), item(2, score=3, pending_review=True), item(3, excused=True), item(4, score=7)]
        out = gc.apply_hypothetical_scores(items, {"1": 8, "2": 6, "3": 5})
        assert [i.score for i in out] == [8, 6, 5, 7]
        assert not any(i.pending_review or i.excused for i in out)
        # Input untouched.
        assert items[0].score is None and items[2].excused

    def test_what_if_changes_current_grade(self):
        # 9/10 graded + what-if 15/20 on the ungraded one: 24/30 = 80%
        items = [item(1, score=9), item(2, points=20)]
        out = gc.apply_hypothetical_scores(items, {"2": 15})
        assert course([G1], out).percent == pytest.approx(80.0)


class TestRequiredUniformPercent:
    def test_unweighted_requirement(self):
        # 40/50 graded, 50 points remain, target 80: need 80 - 40 = 40/50 = 80%
        items = [item(1, points=50, score=40), item(2, points=30), item(3, points=20)]
        result = gc.required_uniform_percent([G1], items, False, 80.0)
        assert result.required_percent == pytest.approx(80.0)
        assert result.remaining_ids == ("2", "3")
        assert result.remaining_points == 50
        assert result.projected_at_zero == pytest.approx(40.0)
        assert result.projected_at_full == pytest.approx(90.0)
        assert not result.already_secured and not result.needs_extra_credit

    def test_weighted_requirement_with_empty_group(self):
        # g1 (50%) done at 80%; g2 (50%) entirely remaining.
        # target 85 -> 40 + 50p = 85 -> p = 90%; target 90 -> p = 100%
        groups = [GroupRules("g1", 50), GroupRules("g2", 50)]
        items = [item(1, score=8), item(2, "g2", 100)]
        assert gc.required_uniform_percent(groups, items, True, 85).required_percent == pytest.approx(90.0)
        assert gc.required_uniform_percent(groups, items, True, 90).required_percent == pytest.approx(100.0)
        # The empty group counts once filled, so 0% on it projects to 40%, not 80%.
        assert gc.required_uniform_percent(groups, items, True, 90).projected_at_zero == pytest.approx(40.0)

    def test_already_secured(self):
        # 95/100 graded, 10 points left: 0% -> 95/110 = 86.4% >= 50
        items = [item(1, points=100, score=95), item(2)]
        result = gc.required_uniform_percent([G1], items, False, 50)
        assert result.required_percent == 0.0 and result.already_secured

    def test_unreachable(self):
        # 10/100 graded, 10 left: best case 20/110 = 18.18% < 90
        items = [item(1, points=100, score=10), item(2)]
        result = gc.required_uniform_percent([G1], items, False, 90)
        assert result.required_percent is None
        assert result.projected_at_full == pytest.approx(20 / 110 * 100)

    def test_only_reachable_with_extra_credit(self):
        # 70/100 graded, 100 left, target 90: 70 + 100p = 180 -> p = 110%
        items = [item(1, points=100, score=70), item(2, points=100)]
        result = gc.required_uniform_percent([G1], items, False, 90)
        assert result.required_percent == pytest.approx(110.0)
        assert result.needs_extra_credit

    def test_rounds_up_to_a_value_that_reaches_the_target(self):
        # 2/3 graded, 3 left, target 60: (2 + 3p) / 6 >= 0.6 -> p >= 53.333...%
        # Reported at 0.01 resolution, rounded UP so the unrounded grade makes it:
        # 53.33% gives 59.998% (short), 53.34% gives 60.003%.
        items = [item(1, points=3, score=2), item(2, points=3)]
        result = gc.required_uniform_percent([G1], items, False, 60)
        assert result.required_percent == pytest.approx(53.34)

        def at(p):
            return gc.project_uniform([G1], items, False, p).percent

        assert at(53.34) >= 60
        assert at(53.33) < 60

    def test_no_remaining_work(self):
        items = [item(1, score=8)]
        met = gc.required_uniform_percent([G1], items, False, 75)
        assert met.remaining_ids == () and met.required_percent == 0.0
        missed = gc.required_uniform_percent([G1], items, False, 85)
        assert missed.remaining_ids == () and missed.required_percent is None

    def test_remaining_excludes_excused_omitted_and_zero_point(self):
        items = [
            item(1, score=5),
            item(2, excused=True),
            item(3, counts_toward_grade=False),
            item(4, points=0),
            item(5, score=2, pending_review=True),
            item(6),
        ]
        ids = [i.assignment_id for i in gc.remaining_items(items)]
        # pending_review is not graded yet, so it is still "remaining".
        assert ids == ["5", "6"]

    def test_requirement_respects_drop_rules(self):
        # Group drops lowest 1. Graded A 2/10, B 10/10; C (10) remains.
        # target 80: keep {B, C} needs (10 + 10p) / 20 >= 0.8 -> p = 60%
        #            ({A, B} is only 60%, so C must carry it)
        rules = [GroupRules("g1", drop_lowest=1)]
        items = [item("A", score=2), item("B", score=10), item("C")]
        assert gc.required_uniform_percent(rules, items, False, 80).required_percent == pytest.approx(60.0)
        # 0% on C: C is dropped, A and B give 12/20 = 60%
        assert gc.required_uniform_percent(rules, items, False, 80).projected_at_zero == pytest.approx(60.0)

    def test_hypothetical_scores_shrink_the_remaining_set(self):
        items = gc.apply_hypothetical_scores([item(1, score=8), item(2), item(3)], {"2": 10})
        result = gc.required_uniform_percent([G1], items, False, 90)
        # (8 + 10 + 10p) / 30 >= 0.9 -> p = 90%
        assert result.remaining_ids == ("3",)
        assert result.required_percent == pytest.approx(90.0)


class TestLetters:
    @pytest.mark.parametrize(
        ("percent", "letter"),
        [(100, "A"), (94, "A"), (93.996, "A"), (93.99, "A-"), (90, "A-"), (87, "B+"),
         (61, "D-"), (60.99, "F"), (0, "F"), (-5, "F"), (120, "A")],
    )
    def test_default_scheme_boundaries(self, percent, letter):
        assert gc.letter_for_percent(percent, gc.CANVAS_DEFAULT_SCHEME) == letter

    def test_none_percent_has_no_letter(self):
        assert gc.letter_for_percent(None, gc.CANVAS_DEFAULT_SCHEME) is None

    def test_parse_course_pair_format_sorts_descending(self):
        scheme = gc.parse_grading_scheme([["P", 0.7], ["NP", 0.0], ["H", 0.9]])
        assert scheme == (("H", 0.9), ("P", 0.7), ("NP", 0.0))
        assert gc.letter_for_percent(75, scheme) == "P"

    def test_parse_grading_standard_dict_format(self):
        scheme = gc.parse_grading_scheme([{"name": "A", "value": 0.93}, {"name": "F", "value": 0}])
        assert scheme == (("A", 0.93), ("F", 0.0))

    def test_points_based_bounds_are_scaled(self):
        # A points-based standard reporting bounds in points out of 4.
        scheme = gc.parse_grading_scheme(
            [{"name": "A", "value": 3.6}, {"name": "B", "value": 2.8}, {"name": "F", "value": 0}],
            scaling_factor=4.0,
        )
        assert scheme == (("A", 0.9), ("B", 0.7), ("F", 0.0))

    @pytest.mark.parametrize(
        "bad",
        [None, [], "A", [["A"]], [{"name": "", "value": 0.9}], [["A", "0.9"]], [["A", True]],
         [["A", -0.1]], [["A", math.inf]], [["A", 5.0]]],
    )
    def test_malformed_schemes_are_rejected(self, bad):
        assert gc.parse_grading_scheme(bad) is None

    def test_find_letter(self):
        scheme = gc.CANVAS_DEFAULT_SCHEME
        assert gc.find_letter("A-", scheme) == ("A-", 90.0)
        assert gc.find_letter(" b+ ", scheme) == ("B+", 87.0)
        assert gc.find_letter("E", scheme) is None

    def test_find_letter_ambiguous_case_fold_is_rejected(self):
        scheme = (("a", 0.9), ("A", 0.8))
        assert gc.find_letter("A", scheme) == ("A", 80.0)
        assert gc.find_letter("a", scheme) == ("a", 90.0)
        assert gc.find_letter(" A ", (("a", 0.9), ("A ", 0.8))) is None


def submission(**kw):
    return kw


class TestStatusesAndModel:
    @pytest.mark.parametrize(
        ("assignment", "sub", "expected"),
        [
            ({}, submission(score=9, workflow_state="graded", late=True, points_deducted=1),
             ["graded", "late", "late penalty -1 pts"]),
            ({}, submission(score=None, missing=True, workflow_state="unsubmitted"), ["missing"]),
            ({}, submission(score=0, missing=True, workflow_state="graded"), ["graded", "marked missing"]),
            ({}, submission(excused=True, score=None, workflow_state="graded"), ["excused"]),
            ({}, submission(score=3, workflow_state="pending_review"), ["pending review (needs manual grading)"]),
            ({}, submission(score=None, workflow_state="graded"), ["grade not posted yet (hidden from you)"]),
            ({}, submission(score=None, workflow_state="submitted", submitted_at="2026-09-01T00:00:00Z"),
             ["submitted, not graded yet"]),
            ({}, submission(score=None, workflow_state="unsubmitted"), ["unsubmitted"]),
            ({"omit_from_final_grade": True}, submission(score=5), ["not counted toward final grade", "graded"]),
            ({"grading_type": "not_graded"}, None, ["not graded", "no submission record visible"]),
        ],
    )
    def test_submission_statuses(self, assignment, sub, expected):
        assert gc.submission_statuses(assignment, sub) == expected

    def test_build_grade_model(self):
        groups_json = [
            {
                "id": 7,
                "name": "Quizzes",
                "group_weight": 25,
                "rules": {"drop_lowest": 1, "never_drop": [101]},
                "assignments": [
                    {"id": 101, "points_possible": 10, "submission": {"score": 9, "workflow_state": "graded"}},
                    {"id": 102, "points_possible": 10, "submission": [{"score": 4}]},
                    {"id": 103, "points_possible": 10, "submission": [{"score": 4}, {"score": 5}]},
                    {"id": 104, "points_possible": None, "omit_from_final_grade": True},
                    {"id": 105, "points_possible": 5, "submission": {"excused": True}},
                    {"id": 106, "points_possible": 5, "submission": {"score": 2, "workflow_state": "pending_review"}},
                    {"id": 107, "points_possible": 5, "submission_types": ["not_graded"]},
                    {"id": 108, "points_possible": 5, "published": False},
                ],
            },
            {"id": 8, "name": "Exams", "group_weight": None, "rules": None, "assignments": None},
            {"name": "no id, skipped"},
        ]
        groups, items = gc.build_grade_model(groups_json)
        assert groups == [
            GroupRules("7", 25.0, 1, 0, frozenset({"101"})),
            GroupRules("8", 0.0, 0, 0, frozenset()),
        ]
        by_id = {i.assignment_id: i for i in items}
        assert by_id["101"].score == 9 and by_id["101"].group_id == "7"
        assert by_id["102"].score == 4  # single-entry list is unambiguous
        assert by_id["103"].score is None  # ambiguous list is not guessed
        assert by_id["104"].points_possible == 0 and not by_id["104"].counts_toward_grade
        assert by_id["105"].excused
        assert by_id["106"].pending_review and not by_id["106"].is_graded
        assert not by_id["107"].counts_toward_grade
        assert not by_id["108"].counts_toward_grade


class TestCanvasRounding:
    """Canvas rounds stored course scores with Ruby's Float#round(2), which
    rounds half up on the decimal value (float.c round_half_up). Expected
    values are what Ruby prints, e.g. ``60.995.round(2) # => 61.0``."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(121.99 / 200 * 100, 61.0), (59.995, 60.0), (60.995, 61.0), (63.995, 64.0),
         (1.005, 1.01), (2.675, 2.68), (84.0, 84.0), (93.994, 93.99), (0.0, 0.0),
         (-1.005, -1.01)],
    )
    def test_matches_ruby_round_half_up(self, value, expected):
        assert gc.canvas_round(value) == expected

    def test_letter_at_a_cutoff_uses_ruby_rounding(self):
        # One 200-point exam scored 121.99: Canvas stores 61.0 and shows D-
        # (default D- cutoff 61%). Python's round() would give 60.99 -> F.
        percent = course([G1], [item(1, points=200, score=121.99)]).percent
        assert gc.letter_for_percent(percent, gc.CANVAS_DEFAULT_SCHEME) == "D-"


class TestPointsBasedScheme:
    # GPA-style scheme: Canvas stores bounds as fractions with scaling_factor 4.
    GPA = (("A", 0.9), ("B", 0.8), ("C", 0.7), ("F", 0.0))

    def test_score_just_under_a_cutoff_rounds_up_in_points(self):
        # GradingStandard#scale_score: 89.9% / (100 / 4) = 3.596 -> 3.60 points
        # -> 3.60 / 4 * 100 = 90.00% -> A. As a percentage scheme it is a B.
        assert gc.letter_for_percent(89.9, self.GPA, points_based=True, scaling_factor=4.0) == "A"
        assert gc.letter_for_percent(89.9, self.GPA) == "B"

    def test_score_further_below_stays_below(self):
        # 89.79% -> 3.5916 -> 3.59 points -> 89.75% -> B
        assert gc.letter_for_percent(89.79, self.GPA, points_based=True, scaling_factor=4.0) == "B"

    def test_scaling_factor_100_is_left_alone(self):
        # scale_score returns the score unchanged when scaling_factor is 100.
        assert gc.letter_for_percent(89.9, self.GPA, points_based=True, scaling_factor=100.0) == "B"

    def test_same_scheme(self):
        assert gc.same_scheme(gc.parse_grading_scheme([list(e) for e in gc.CANVAS_DEFAULT_SCHEME]),
                              gc.CANVAS_DEFAULT_SCHEME)
        assert not gc.same_scheme((("A", 0.93), ("F", 0.0)), gc.CANVAS_DEFAULT_SCHEME)
        assert not gc.same_scheme(None, gc.CANVAS_DEFAULT_SCHEME)


class TestNonMonotoneTarget:
    """drop_lowest + drop_highest makes the grade non-monotone in the score on
    remaining work. Group keeps 1 of 3: A 1/10 graded, B ?/5 remaining, C 0/1.

    At p% on B: Canvas first keeps the best 2 by ratio, then the worst 1 of
    those. {A,B} = (1 + 0.05p)/15 beats {A,C} = 1/11 once p > 7.27, and then
    the worse of A (10%) and B (p%) is kept. So the grade is 0 for p <= 7.27,
    p for 7.27 < p <= 10, and 10 above: 8% gives 8%, 100% gives only 10%.
    """

    RULES = [GroupRules("g1", drop_lowest=1, drop_highest=1)]
    ITEMS = [item("A", points=10, score=1), item("B", points=5), item("C", points=1, score=0)]

    def test_grade_is_not_monotone(self):
        def at(p):
            return gc.project_uniform(self.RULES, self.ITEMS, False, p).percent

        assert at(8) == pytest.approx(8.0)
        assert at(0) == pytest.approx(0.0)
        assert at(5) == pytest.approx(0.0)

    def test_reachable_target_is_found(self):
        result = gc.required_uniform_percent(self.RULES, self.ITEMS, False, 8.0)
        assert result.non_monotone
        assert result.required_percent == pytest.approx(8.0)
        assert gc.project_uniform(self.RULES, self.ITEMS, False, result.required_percent).percent >= 8.0

    def test_unreachable_target_is_none(self):
        # Nothing beats 10%: 10.5% is out of reach at any uniform score.
        result = gc.required_uniform_percent(self.RULES, self.ITEMS, False, 10.5)
        assert result.required_percent is None

    def test_monotone_groups_are_not_flagged(self):
        rules = [GroupRules("g1", drop_lowest=1)]
        assert not gc.required_uniform_percent(rules, self.ITEMS, False, 8.0).non_monotone


class TestUnposted:
    """Canvas's student-visible grade ignores submissions without posted_at
    (GradeCalculator#ignore_submission?), excused flag included."""

    def test_unposted_excused_counts_as_ungraded(self):
        # HW 10/10 posted; Quiz excused but not posted. Canvas: current 100%,
        # final (10 + 0) / 20 = 50%. Treating the excusal as applied gives 100%.
        groups_json = [{
            "id": 1, "rules": {},
            "assignments": [
                {"id": 11, "points_possible": 10,
                 "submission": {"score": 10, "workflow_state": "graded", "posted_at": "2026-09-01T00:00:00Z"}},
                {"id": 12, "points_possible": 10,
                 "submission": {"excused": True, "workflow_state": "graded", "posted_at": None}},
            ],
        }]
        groups, items = gc.build_grade_model(groups_json)
        quiz = next(i for i in items if i.assignment_id == "12")
        assert not quiz.excused and quiz.score is None
        assert course(groups, items).percent == pytest.approx(100.0)
        assert course(groups, items, include_ungraded=True).percent == pytest.approx(50.0)

    def test_posted_excused_is_still_excused(self):
        _, items = gc.build_grade_model([{
            "id": 1, "assignments": [{"id": 12, "points_possible": 10, "submission": {
                "excused": True, "workflow_state": "graded", "posted_at": "2026-09-01T00:00:00Z"}}],
        }])
        assert items[0].excused

    def test_payload_without_posted_at_keeps_old_behaviour(self):
        _, items = gc.build_grade_model([{
            "id": 1, "assignments": [{"id": 12, "points_possible": 10, "submission": {
                "excused": True, "workflow_state": "graded"}}],
        }])
        assert items[0].excused

    @pytest.mark.parametrize(
        ("sub", "expected"),
        [
            ({"excused": True, "workflow_state": "graded", "posted_at": None},
             ["grade not posted yet (hidden from you)"]),
            ({"workflow_state": "graded", "posted_at": None},
             ["grade not posted yet (hidden from you)"]),
            ({"excused": True, "workflow_state": "graded", "posted_at": "2026-09-01T00:00:00Z"},
             ["excused"]),
            ({"score": None, "workflow_state": "unsubmitted", "posted_at": None}, ["unsubmitted"]),
        ],
    )
    def test_statuses(self, sub, expected):
        assert gc.submission_statuses({}, sub) == expected
