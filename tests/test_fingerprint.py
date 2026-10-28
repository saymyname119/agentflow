from approvalflow.storage import fingerprint


def test_reordered_evidence_does_not_invalidate_identical_content(snapshot, policy):
    second = snapshot.files[0].model_copy(update={"filename": "docs/setup.md"})
    snapshot.files.append(second)
    snapshot.checks.append(snapshot.checks[0].model_copy(update={"name": "lint"}))
    before = fingerprint(snapshot, policy)
    snapshot.files.reverse()
    snapshot.checks.reverse()
    assert fingerprint(snapshot, policy) == before
    snapshot.checks[0].conclusion = "failure"
    assert fingerprint(snapshot, policy) != before


def test_engine_update_invalidates_old_evidence_binding(snapshot, policy, monkeypatch):
    import approvalflow.storage as storage
    before = fingerprint(snapshot, policy)
    monkeypatch.setattr(storage, "POLICY_ENGINE_VERSION", "next-engine")
    assert fingerprint(snapshot, policy) != before
