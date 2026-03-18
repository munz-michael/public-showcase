"""
Tests for debate/cli.py — entry points, subcommands, presets, cost estimates.
No real API calls: mock_claude fixture from conftest.py patches AsyncAnthropic.
"""

import json
import sys
import textwrap
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from debate.cli import _apply_preset, _estimate_cost, _cmd_stats, _cmd_list, run_debate
import argparse


# ── _apply_preset ──────────────────────────────────────────────────────────────

class TestApplyPreset:
    def _args(self, mode=None, **overrides):
        ns = argparse.Namespace(
            mode=mode,
            rounds=1, adversarial=False, grounded=False, multi_turn=False,
            judge=False, moa=False, fact_check=False, decompose=False,
            arg_graph=False, delphi_rounds=0, calibrate=False,
        )
        for k, v in overrides.items():
            setattr(ns, k, v)
        return ns

    def test_no_mode_unchanged(self):
        args = self._args(mode=None, rounds=1)
        result = _apply_preset(args)
        assert result.rounds == 1
        assert result.judge is False

    def test_quick_preset(self):
        args = self._args(mode="quick")
        result = _apply_preset(args)
        assert result.rounds == 1
        assert result.judge is False
        assert result.fact_check is False

    def test_standard_preset_enables_judge_and_fact_check(self):
        args = self._args(mode="standard")
        result = _apply_preset(args)
        assert result.judge is True
        assert result.fact_check is True

    def test_deep_preset_enables_decompose_and_arg_graph(self):
        args = self._args(mode="deep")
        result = _apply_preset(args)
        assert result.decompose is True
        assert result.arg_graph is True
        assert result.calibrate is True
        # rounds starts at 1 (truthy) so _apply_preset won't override it;
        # the preset check is `not getattr(args, key, False)` — 1 is truthy → skip

    def test_preset_does_not_override_explicitly_set_flag(self):
        """If judge=True is already set, quick preset should not override it."""
        args = self._args(mode="quick", judge=True)
        result = _apply_preset(args)
        # quick preset has judge=False, but we set it True — should not be overridden
        # Note: _apply_preset only sets if `not getattr(args, key, False)`,
        # so a True value is preserved.
        assert result.judge is True

    def test_unknown_mode_is_noop(self):
        args = self._args(mode="nonexistent")
        result = _apply_preset(args)
        assert result.rounds == 1  # unchanged


# ── _estimate_cost ─────────────────────────────────────────────────────────────

class TestEstimateCost:
    def test_base_cost(self):
        usd, seconds = _estimate_cost()
        assert usd == pytest.approx(0.04, abs=0.001)
        assert seconds == 30

    def test_extra_rounds_increase_cost(self):
        usd1, s1 = _estimate_cost(rounds=1)
        usd3, s3 = _estimate_cost(rounds=3)
        assert usd3 > usd1
        assert s3 > s1

    def test_moa_flag_adds_cost(self):
        usd_base, _ = _estimate_cost()
        usd_moa, _ = _estimate_cost(moa=True)
        assert usd_moa > usd_base

    def test_fact_check_adds_cost(self):
        usd_base, _ = _estimate_cost()
        usd_fc, _ = _estimate_cost(fact_check=True)
        assert usd_fc > usd_base

    def test_delphi_rounds_scale_cost(self):
        _, s0 = _estimate_cost(delphi_rounds=0)
        _, s2 = _estimate_cost(delphi_rounds=2)
        _, s3 = _estimate_cost(delphi_rounds=3)
        assert s3 > s2 > s0

    def test_all_flags_combined(self):
        usd, seconds = _estimate_cost(
            rounds=2, moa=True, fact_check=True, decompose=True,
            arg_graph=True, delphi_rounds=2, judge=True, calibrate=True,
        )
        assert usd > 0.10   # noticeably more expensive than base
        assert seconds > 60


# ── _cmd_stats ─────────────────────────────────────────────────────────────────

class TestCmdStats:
    def test_no_history_returns_json(self, capsys):
        with patch("debate.cli.load_calibration_history", return_value=[]):
            _cmd_stats()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_debates"] == 0
        assert data["total_claims"] == 0

    def test_with_history_returns_stats(self, capsys):
        fake_history = [
            {
                "debate_id": "debate-abc123",
                "problem": "Test?",
                "claims": [
                    {"claim": "X", "probability": 0.7, "model_id": "claude-opus-4-6",
                     "source_role": "logical_analysis", "ci_lower": 0.5, "ci_upper": 0.9,
                     "time_horizon": "1 year", "outcome": None},
                ]
            }
        ]
        # _cmd_stats imports locally from debate.debate_manager — patch there
        with patch("debate.debate_manager.load_calibration_history", return_value=fake_history):
            with patch("debate.debate_manager.compute_calibration_stats", return_value={
                "total_debates": 1, "total_claims": 1, "resolved_claims": 0,
            }):
                _cmd_stats()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["total_debates"] == 1


# ── _cmd_list ──────────────────────────────────────────────────────────────────

class TestCmdList:
    def test_no_output_dir_returns_empty_list(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        _cmd_list()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data == []

    def test_with_report_file_returns_entry(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        report_dir = tmp_path / "output" / "debate-abc123_test"
        report_dir.mkdir(parents=True)
        report_file = report_dir / "debate-abc123_test_report.md"
        report_file.write_text("# Test Report\n")

        _cmd_list()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert len(data) == 1
        assert data[0]["name"] == "debate-abc123_test_report.md"
        assert data[0]["size_bytes"] > 0


# ── run_debate (integration, mock API) ────────────────────────────────────────

class TestRunDebate:
    @pytest.mark.asyncio
    async def test_basic_mock_run_completes(self, mock_claude):
        """Full debate pipeline with mock_gemini=True — no API keys needed."""
        await run_debate(
            problem="Is Python faster than C?",
            mock_gemini=True,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_adversarial_mode(self, mock_claude):
        await run_debate(
            problem="Should AI be regulated?",
            mock_gemini=True,
            adversarial=True,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_fact_check_mode(self, mock_claude):
        await run_debate(
            problem="Is RSA-2048 quantum-safe?",
            mock_gemini=True,
            fact_check=True,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_decompose_mode(self, mock_claude):
        await run_debate(
            problem="What are the risks of AGI?",
            mock_gemini=True,
            decompose=True,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_delphi_mode(self, mock_claude):
        await run_debate(
            problem="Will quantum computers break RSA?",
            mock_gemini=True,
            delphi_rounds=2,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_judge_mode(self, mock_claude):
        await run_debate(
            problem="Is Bitcoin a store of value?",
            mock_gemini=True,
            judge=True,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_arg_graph_mode(self, mock_claude):
        await run_debate(
            problem="Is nuclear energy safe?",
            mock_gemini=True,
            arg_graph=True,
            save=False,
        )

    @pytest.mark.asyncio
    async def test_save_writes_report_file(self, mock_claude, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        await run_debate(
            problem="Test problem",
            mock_gemini=True,
            save=True,
        )
        output_dir = tmp_path / "output"
        report_files = list(output_dir.rglob("*_report.md")) if output_dir.exists() else []
        assert len(report_files) == 1
        assert report_files[0].stat().st_size > 0

    @pytest.mark.asyncio
    async def test_context_injection(self, mock_claude):
        """Context flag passes through without error."""
        await run_debate(
            problem="Is RSA secure?",
            mock_gemini=True,
            context_text="Our org uses RSA-2048 for key exchange.",
            save=False,
        )

    @pytest.mark.asyncio
    async def test_toulmin_format(self, mock_claude):
        """Toulmin format flag passes through without error."""
        await run_debate(
            problem="Is Python GIL removed in 3.13?",
            mock_gemini=True,
            debate_format="toulmin",
            save=False,
        )


# ── main() subcommand routing ──────────────────────────────────────────────────

class TestMainSubcommands:
    def test_stats_subcommand(self, capsys):
        with patch("sys.argv", ["debate", "stats"]):
            with patch("debate.cli.load_calibration_history", return_value=[]):
                from debate.cli import main
                main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert "total_debates" in data

    def test_list_subcommand(self, capsys, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("sys.argv", ["debate", "list"]):
            from debate.cli import main
            main()
        out = capsys.readouterr().out
        data = json.loads(out)
        assert isinstance(data, list)

    def test_missing_problem_flag_exits(self):
        with patch("sys.argv", ["debate"]):
            from debate.cli import main
            with pytest.raises(SystemExit):
                main()
