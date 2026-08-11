import hashlib
import json

from pipeline import generate_sbi_identity_proposals as proposals
from pipeline import sbi_identity_config as config
from pipeline import sbi_ingest


def write_config(path, overrides=(), exclusions=()):
    path.write_text(json.dumps({"overrides": list(overrides),
                                "exclusions": list(exclusions)}), encoding="utf-8")


def test_exact_sha_approved_unapproved_and_exclusion(tmp_path):
    digest = "a" * 64
    path = tmp_path / "decisions.json"
    base = {"local_sha256": digest, "filename": "note.pdf", "ipo_id": 7,
            "isin": "INE000000001", "evidence": "owner record"}
    write_config(path, [{**base, "owner_approved": False}])
    assert config.reviewed_decision(digest, "note.pdf", path=path).kind == "unapproved_override"
    write_config(path, [{**base, "owner_approved": True}])
    assert config.reviewed_decision(digest, "note.pdf", path=path).kind == "override"
    write_config(path, exclusions=[{"local_sha256": digest, "filename": "note.pdf",
                                    "classification": "junk", "evidence": "review"}])
    assert config.reviewed_decision(digest, "note.pdf", path=path).kind == "exclusion"


def test_ingest_hashes_before_identity_and_unapproved_writes_nothing(tmp_path, monkeypatch):
    note = tmp_path / "Unknown_IPO Note.pdf"; note.write_bytes(b"pdf")
    digest = hashlib.sha256(b"pdf").hexdigest()
    decision = config.ReviewedDecision("unapproved_override", {})
    monkeypatch.setattr(sbi_ingest, "reviewed_decision",
                        lambda sha, filename: decision if sha == digest else None)
    monkeypatch.setattr(sbi_ingest, "resolve_ipo",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("identity queried")))
    monkeypatch.setattr(sbi_ingest, "store_document",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("write")))
    result = sbi_ingest.ingest_file(object(), note, owner_approved=True)
    assert result["status"] == "UNRESOLVED" and result["local_sha256"] == digest


def test_generator_unique_ambiguous_and_missing_are_one_row_each():
    inventory = [
        {"company": "Anand and Sons", "filename": "a.pdf", "local_sha256": "a" * 64},
        {"company": "Turtlemint", "filename": "t.pdf", "local_sha256": "b" * 64},
        {"company": "Absent", "filename": "x.pdf", "local_sha256": "c" * 64},
    ]
    spine = [
        {"ipo_id": 1, "isin": "INE000000001", "name_display": "Anand & Sons"},
        {"ipo_id": 2, "isin": "INE000000002", "name_display": "Turtlemint Fintech"},
        {"ipo_id": 3, "isin": "INE000000003", "name_display": "Turtlemint Insurance"},
    ]
    rows = proposals.generate(inventory, spine)
    assert [row["status"] for row in rows] == ["EXACT_VARIANT", "AMBIGUOUS", "NO_ROW_FOUND"]
    assert len(rows) == len(inventory) and len(rows[1]["candidates"]) == 2
    assert "owner_approved" not in proposals.markdown(rows)


def test_transition_report_requires_three_deterministic_absences():
    expected = "CLOSED_PRELISTING_SOURCE_MISSING company=Ardee action=owner_attention"
    assert sbi_ingest.transition_cohort_report(
        "Ardee", canonical_row=None, override=None,
        supported_feed_exact_match=False) == expected
    assert sbi_ingest.transition_cohort_report(
        "Ardee", canonical_row=None, override=None,
        supported_feed_exact_match=None) is None
