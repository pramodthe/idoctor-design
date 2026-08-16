"""Unit tests for the critic→designer loop and Paperclip hit mapping."""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from backend.agents.critic import (
    _criticize_design,
    _decide_route,
    _loop_decision,
    _round_progress_score,
)
from backend.agents.graph_policy import MAX_DESIGN_RETRIES, route_after_critic
from backend.tools.paperclip import (
    allowlist_from_hits,
    compact_search_hits,
    source_id_allowed,
    spec_from_search_hits,
)


def test_route_fixture_never_redesigns():
    assert (
        route_after_critic({"mode": "fixture", "critic_route": "redesign", "design_retry_count": 0})
        == "experiment"
    )


def test_route_replay_never_redesigns():
    assert (
        route_after_critic({"mode": "replay", "critic_route": "redesign", "design_retry_count": 0})
        == "experiment"
    )


def test_route_live_redesign_within_iteration_budget():
    assert (
        route_after_critic({"mode": "live", "critic_route": "redesign", "design_retry_count": 0})
        == "designer"
    )
    assert (
        route_after_critic(
            {
                "mode": "live",
                "critic_route": "redesign",
                "design_retry_count": MAX_DESIGN_RETRIES,
            }
        )
        == "experiment"
    )


def test_route_live_promote_goes_to_experiment():
    assert (
        route_after_critic({"mode": "live", "critic_route": "experiment", "design_retry_count": 0})
        == "experiment"
    )


def test_paperclip_hits_become_mutations_with_real_ids():
    payload = {
        "source": "paperclip_cli",
        "results": [
            {
                "id": "35120633",
                "title": "Y96D and H95D confer sotorasib resistance in KRAS G12C",
                "snippet": "The Y96D substitution abolished sotorasib binding.",
            },
            {
                "id": "NCT04185883",
                "title": "CodeBreaK trial",
                "snippet": "Patients with KRAS G12C; R68S noted in resistance.",
            },
        ],
    }
    hits = compact_search_hits(payload)
    spec = spec_from_search_hits(hits, origin="paperclip")
    assert spec is not None
    assert spec["provenance"] == "live"
    ids = {m["id"] for m in spec["mutations"]}
    assert "Y96D" in ids
    assert "H95D" in ids
    assert "R68S" in ids
    y96 = next(m for m in spec["mutations"] if m["id"] == "Y96D")
    assert y96["sources"][0]["id"] == "35120633"
    assert y96["effect_on_sotorasib"] == "loss"
    allowed = allowlist_from_hits(hits)
    assert source_id_allowed("35120633", allowed)
    assert source_id_allowed("PMID:35120633", allowed)
    assert not source_id_allowed("99999999", allowed)


def test_mcp_tool_texts_yield_real_ids_not_result_sets():
    from backend.tools.paperclip_mcp import hits_from_tool_texts

    texts = [
        json.dumps(
            {
                "source": "europepmc",
                "results": [
                    {
                        "id": "35120633",
                        "title": "Y96D abolishes sotorasib binding",
                        "snippet": "The Y96D substitution abolished sotorasib binding.",
                    }
                ],
            }
        ),
        "search returned s_abc123 PMID:35120633 and NCT04185883 for KRAS G12C H95D",
    ]
    hits = hits_from_tool_texts(texts)
    ids = {h["id"] for h in hits}
    assert "35120633" in ids
    assert "NCT04185883" in ids
    assert not any(str(i).lower().startswith("s_") for i in ids)


def test_decide_route_redesigns_when_no_promote():
    items = [
        {
            "subject_kind": "design",
            "verdict": "reject",
            "reasons": ["low_iptm"],
        },
        {"subject_kind": "smallmol", "verdict": "hold"},
    ]
    assert _decide_route(items, "live", 0) == "redesign"
    assert _decide_route(items, "live", MAX_DESIGN_RETRIES) == "experiment"
    assert _decide_route(items, "fixture", 0) == "experiment"
    assert _decide_route(
        [{"subject_kind": "design", "verdict": "promote"}], "live", 0
    ) == "experiment"


def _candidate(**overrides):
    candidate = {
        "id": "des_test",
        "plddt": 88.0,
        "iptm": 0.81,
        "fold_method": "tamarind:alphafold2_multimer",
        "novelty": {"identity": 0.2, "method": "mmseqs2"},
    }
    candidate.update(overrides)
    return candidate


def _bars():
    return {
        "max_pdb_identity": 0.4,
        "min_plddt": 70,
        "min_iptm": 0.75,
        "require_mutant_score": True,
    }


def test_proxy_mutant_scores_cannot_promote():
    verdict = _criticize_design(
        _candidate(),
        _bars(),
        {
            "wt_score": -8.0,
            "mutant_scores": {"Y96D": -7.2},
            "evaluation_method": "sequence_proxy_v2",
        },
        ["Y96D"],
    )
    assert verdict["verdict"] == "hold"
    assert "proxy_only_evaluation" in verdict["reasons"]


def test_verified_candidate_can_promote():
    verdict = _criticize_design(
        _candidate(),
        _bars(),
        {
            "wt_score": -8.0,
            "mutant_scores": {"Y96D": -7.2},
            "evaluation_method": "boltz_complex",
        },
        ["Y96D"],
    )
    assert verdict["verdict"] == "promote"
    assert verdict["reasons"] == ["passes_spec"]


def test_verified_complex_iptm_candidate_can_promote():
    verdict = _criticize_design(
        _candidate(),
        _bars(),
        {
            "wt_score": 0.83,
            "mutant_scores": {"Y96D": 0.78},
            "evaluation_method": "tamarind_alphafold_multimer_complex_iptm",
            "score_kind": "iptm",
            "score_direction": "higher_is_better",
        },
        ["Y96D"],
    )
    assert verdict["verdict"] == "promote"


def test_complex_iptm_collapse_is_rejected():
    verdict = _criticize_design(
        _candidate(),
        _bars(),
        {
            "wt_score": 0.84,
            "mutant_scores": {"Y96D": 0.61},
            "evaluation_method": "tamarind_alphafold_multimer_complex_iptm",
            "score_kind": "iptm",
            "score_direction": "higher_is_better",
        },
        ["Y96D"],
    )
    assert verdict["verdict"] == "reject"
    assert "wt_only_signal" in verdict["reasons"]


def test_unverified_structure_metric_cannot_promote():
    verdict = _criticize_design(
        _candidate(fold_method="heuristic_v1"),
        _bars(),
        {
            "wt_score": -8.0,
            "mutant_scores": {"Y96D": -7.2},
            "evaluation_method": "boltz_complex",
        },
        ["Y96D"],
    )
    assert verdict["verdict"] == "hold"
    assert "unverified_structure_metric" in verdict["reasons"]


def test_evidence_gap_stops_instead_of_generating_around_it():
    items = [
        {
            "subject_kind": "design",
            "verdict": "hold",
            "reasons": ["proxy_only_evaluation"],
        }
    ]
    assert _loop_decision(items, "live", 0) == ("experiment", "evidence_gap")


def test_tool_failure_stops_before_redesign():
    items = [
        {
            "subject_kind": "design",
            "verdict": "reject",
            "reasons": ["low_iptm", "missing_mutant_evaluation"],
        }
    ]
    assert _loop_decision(
        items,
        "live",
        0,
        verification_failures=["complex:timeout"],
    ) == ("experiment", "evidence_tool_failure")


def test_recoverable_failure_redesigns_then_stops_at_budget():
    items = [
        {
            "subject_kind": "design",
            "verdict": "reject",
            "reasons": ["low_iptm"],
        }
    ]
    assert _loop_decision(items, "live", 0, max_iterations=3) == (
        "redesign",
        "recoverable_design_failure",
    )
    assert _loop_decision(items, "live", 2, max_iterations=3) == (
        "experiment",
        "iteration_budget_exhausted",
    )


def test_no_improvement_budget_stops_loop():
    items = [
        {
            "subject_kind": "design",
            "verdict": "reject",
            "reasons": ["low_iptm"],
        }
    ]
    assert _loop_decision(
        items,
        "live",
        1,
        no_improvement_rounds=2,
        max_iterations=4,
        max_no_improvement_rounds=2,
    ) == ("experiment", "no_improvement")


def test_oracle_preserves_evaluation_provenance():
    from backend.evaluation.oracle import design_deltas

    rows = design_deltas(
        [{"id": "d1"}],
        {
            "d1": {
                "wt_score": -8.0,
                "mutant_scores": {"Y96D": -7.0},
                "method": "boltz_complex",
                "confidence": "model",
                "score_kind": "iptm",
                "score_direction": "higher_is_better",
            }
        },
    )
    assert rows[0]["evaluation_method"] == "boltz_complex"
    assert rows[0]["evaluation_confidence"] == "model"
    assert rows[0]["score_kind"] == "iptm"
    assert rows[0]["score_direction"] == "higher_is_better"


def test_progress_does_not_count_heuristic_structure_as_verified():
    delta = {
        "d1": {
            "wt_score": 0.8,
            "mutant_scores": {"Y96D": 0.76},
            "evaluation_method": "tamarind_complex_iptm",
        }
    }
    heuristic = _round_progress_score(
        [
            {
                "id": "d1",
                "plddt": 90,
                "iptm": 0.82,
                "fold_method": "heuristic_v1",
                "novelty": {"identity": 0.2, "method": "rcsb_mmseqs2"},
            }
        ],
        delta,
        _bars(),
    )
    verified = _round_progress_score(
        [
            {
                "id": "d1",
                "plddt": 90,
                "iptm": 0.82,
                "fold_method": "tamarind:alphafold2_multimer_complex",
                "novelty": {"identity": 0.2, "method": "rcsb_mmseqs2"},
            }
        ],
        delta,
        _bars(),
    )
    assert heuristic == 0.6
    assert verified == 1.0


def test_rcsb_no_hit_is_conservative_verified_upper_bound():
    from backend.tools.novelty import search_pdb_sequence

    class Response:
        status_code = 204

    with patch("backend.tools.novelty.requests.post", return_value=Response()):
        result = search_pdb_sequence("ACDEFGHIKLMNPQRSTVWYACDE")
    assert result["method"] == "rcsb_mmseqs2"
    assert result["identity"] == 0.3
    assert result["identity_is_upper_bound"] is True


def test_graph_contains_evidence_repair_nodes():
    from backend.pipeline import build_idoctor_design_graph

    graph = build_idoctor_design_graph()
    assert {"novelty", "complex"}.issubset(graph.nodes)


def test_incomplete_complex_panel_is_not_trusted():
    from backend.agents.complex_evaluator import run_complex_evaluator

    with tempfile.TemporaryDirectory() as temp_dir:
        state = {
            "run_dir": temp_dir,
            "mode": "live",
            "scientific_spec": {
                "success_bars": {"max_pdb_identity": 0.4, "min_plddt": 70},
                "mutations": [{"id": "Y96D"}],
            },
            "designs": {
                "designs": [
                    {
                        **_candidate(),
                        "sequence": "ACDEFGHIKLMNPQRSTVWYACDE",
                    }
                ]
            },
            "verification_failures": [],
        }
        with (
            patch("backend.agents.complex_evaluator.FAST_DEV", False),
            patch(
                "backend.agents.complex_evaluator._target_panel",
                return_value=("G12C", {"G12C": "AAAA", "Y96D": "AAAD"}),
            ),
            patch(
                "backend.agents.complex_evaluator.tamarind.submit_complex_panel",
                return_value={
                    "metrics": {"G12C": {"iptm": 0.82, "plddt": 88.0}},
                    "errors": ["Y96D: timeout"],
                },
            ),
        ):
            result = run_complex_evaluator(state)

    assert result["design_scores"] == {}
    assert any("incomplete complex panel" in item for item in result["verification_failures"])


def test_live_graph_executes_critic_redesign_and_promote_rounds():
    """The compiled graph must actually traverse the bounded retry edge."""
    import backend.pipeline as pipeline
    from backend.config import RUNS_DIR

    run_id = f"test-loop-{uuid.uuid4().hex[:8]}"
    run_dir = RUNS_DIR / run_id
    calls = {"designer": 0}
    spec = {
        "schema_version": "1.0",
        "provenance": "live",
        "hypothesis": "A binder should retain interface confidence on Y96D.",
        "target": {"name": "KRAS G12C", "gene": "KRAS", "pdb_id": "6OIM", "uniprot_id": "P01116", "clinical_hook": "resistance"},
        "pocket_residues": ["Cys12", "His95", "Tyr96"],
        "success_bars": {"max_pdb_identity": 0.7, "min_plddt": 70, "min_iptm": 0.75, "require_mutant_score": True},
        "mutations": [{"id": "Y96D", "effect_on_sotorasib": "loss", "notes": "", "sources": []}],
        "failed_small_molecules": [],
        "structures": [],
    }

    def trace(agent: str) -> list[dict]:
        return [{"agent": agent, "agent_name": agent, "duration_seconds": 0.0, "model": None, "input_summary": "test", "output_summary": "test", "steps": [], "tool_calls": [], "llm_calls": []}]

    def fake_evidence(state, progress_cb=None):
        (Path(state["run_dir"]) / "spec.json").write_text(json.dumps(spec))
        return {"scientific_spec": spec, "hypothesis": spec["hypothesis"], "provenance_nodes": {"evidence": "live"}, "agent_traces": trace("evidence")}

    def fake_designer(state, progress_cb=None):
        calls["designer"] += 1
        retry = calls["designer"] > 1
        did = "design_retry" if retry else "design_initial"
        designs = [{
            "id": did,
            "sequence": "ACDEFGHIKLMNPQRSTVWY" * 3,
            "length": 60,
            "molecule_type": "miniprotein",
            "constraint_scores": {},
            "plddt": 82.0,
            "iptm": 0.82 if retry else 0.70,
            "pdb_path": "data/test.pdb",
            "novelty": {"identity": 0.2, "method": "rcsb_mmseqs2"},
            "fold_method": "tamarind:alphafold2_multimer",
            "provenance": "live",
            "iteration": 2 if retry else 1,
            "lineage": {"iteration": 2 if retry else 1, "parent_ids": ["design_initial"] if retry else [], "failure_codes": ["low_iptm"] if retry else []},
        }]
        doc = {"schema_version": "1.0", "designs": designs, "meta": {"design_engine": "test"}}
        path = Path(state["run_dir"]) / "designs.json"
        path.write_text(json.dumps(doc))
        (Path(state["run_dir"]) / "designs.fasta").write_text(f">{did}\n{designs[0]['sequence']}\n")
        return {"designs": doc, "provenance_nodes": {"designer": "live"}, "agent_traces": trace("designer"), "design_retry_count": 1 if retry else 0}

    def fake_structure(state, progress_cb=None):
        return {"designs": state["designs"], "provenance_nodes": {"structure": "live"}, "agent_traces": trace("structure")}

    def fake_novelty(state, progress_cb=None):
        return {"designs": state["designs"], "verification_failures": [], "provenance_nodes": {"novelty": "live"}, "agent_traces": trace("novelty")}

    def fake_complex(state, progress_cb=None):
        did = state["designs"]["designs"][0]["id"]
        score = 0.82 if did == "design_retry" else 0.70
        scores = {did: {"wt_score": score, "mutant_scores": {"Y96D": 0.78 if did == "design_retry" else 0.62}, "method": "tamarind_alphafold_multimer_complex_iptm", "confidence": "predicted_complex", "score_kind": "iptm", "score_direction": "higher_is_better"}}
        (Path(state["run_dir"]) / "complex_scores.json").write_text(json.dumps(scores))
        return {"designs": state["designs"], "design_scores": scores, "verification_failures": [], "provenance_nodes": {"complex": "live"}, "agent_traces": trace("complex")}

    def fake_physics(state, progress_cb=None):
        smallmol = {"schema_version": "1.0", "compounds": []}
        (Path(state["run_dir"]) / "smallmol.json").write_text(json.dumps(smallmol))
        return {"smallmol": smallmol, "provenance_nodes": {"physics": "live"}, "agent_traces": trace("physics")}

    def fake_evaluator(state, progress_cb=None):
        did = state["designs"]["designs"][0]["id"]
        score = 0.82 if did == "design_retry" else 0.70
        eval_result = {"schema_version": "1.0", "smallmol_spearman_rho": None, "smallmol_n": 0, "smallmol_note": "test", "disagreements": [], "design_deltas": [{"id": did, "wt_score": score, "mutant_scores": {"Y96D": 0.78 if did == "design_retry" else 0.62}, "note": "test", "evaluation_method": "tamarind_alphafold_multimer_complex_iptm", "evaluation_confidence": "predicted_complex", "score_kind": "iptm", "score_direction": "higher_is_better"}]}
        (Path(state["run_dir"]) / "eval.json").write_text(json.dumps(eval_result))
        return {"eval_result": eval_result, "provenance_nodes": {"evaluate": "live"}, "agent_traces": trace("evaluate")}

    def fake_experiment(state, progress_cb=None):
        (Path(state["run_dir"]) / "experiment.md").write_text("# test")
        return {"experiment_md": "# test", "provenance_nodes": {"experiment": "live"}, "agent_traces": trace("experiment")}

    try:
        with patch.object(pipeline, "run_evidence", fake_evidence), patch.object(pipeline, "run_designer", fake_designer), patch.object(pipeline, "run_structure", fake_structure), patch.object(pipeline, "run_novelty", fake_novelty), patch.object(pipeline, "run_complex_evaluator", fake_complex), patch.object(pipeline, "run_physics", fake_physics), patch.object(pipeline, "run_evaluator", fake_evaluator), patch.object(pipeline, "run_experiment", fake_experiment), patch("backend.agents.critic.FAST_DEV", True), patch.object(pipeline, "export_from_run", lambda *_args, **_kwargs: None):
            result = pipeline.run_idoctor_design(mode="live", run_id=run_id)

        history = result["loop_history"]
        assert calls["designer"] == 2
        assert len(history["iterations"]) == 2
        assert history["iterations"][0]["route"] == "redesign"
        assert history["iterations"][0]["redesign_feedback"]["priority_codes"] == ["low_iptm"]
        assert history["iterations"][1]["decision_reason"] == "promoted"
        assert result["designs"]["designs"][0]["id"] == "design_retry"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def test_sqlite_checkpoint_resumes_after_interruption():
    import backend.pipeline as pipeline

    interrupted = False

    def stop_before_novelty(agent, status, **_kwargs):
        nonlocal interrupted
        if agent == "novelty" and status == "running" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated interruption")

    with tempfile.TemporaryDirectory() as temp_dir:
        runs_dir = Path(temp_dir)
        with patch.object(pipeline, "RUNS_DIR", runs_dir):
            try:
                pipeline.run_idoctor_design(
                    mode="fixture",
                    run_id="resume-test",
                    progress_callback=stop_before_novelty,
                )
            except RuntimeError as exc:
                assert "simulated interruption" in str(exc)
            else:
                raise AssertionError("pipeline did not simulate an interruption")
            assert (runs_dir / "resume-test" / "langgraph.sqlite").is_file()
            result = pipeline.run_idoctor_design(
                mode="fixture", run_id="resume-test", resume=True
            )
            assert result["status"] == "completed"
            assert result["checkpointed"] is True


def test_hits_without_frozen_mutations_yield_no_spec():
    hits = [{"id": "1", "title": "Unrelated influenza paper", "snippet": "neuraminidase"}]
    assert spec_from_search_hits(hits) is None


def test_flatten_traces_includes_tools_and_route():
    from backend.agents.lab_log import flatten_traces

    events = flatten_traces(
        [
            {
                "agent": "evidence",
                "steps": [{"action": "MCP", "detail": "search"}],
                "tool_calls": [{"tool": "paperclip", "input": {"command": 'search -s pmc "Y96D"'}}],
                "output_summary": "4 mutations",
            },
            {
                "agent": "critic",
                "steps": [],
                "tool_calls": [],
                "output_summary": "no promote",
                "critic_route": "redesign",
            },
        ]
    )
    kinds = [e["kind"] for e in events]
    assert "tool" in kinds
    assert "route" in kinds
    assert any("search -s pmc" in e["text"] for e in events)
