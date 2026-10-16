from __future__ import annotations

from promptci.snapshots import SnapshotStore, signature_of, snapshots_file


def test_new_then_same(tmp_path):
    store = SnapshotStore(snapshots_file(tmp_path, "My Flow"))
    assert store.compare("step1", "sig-a", "out") == "new"
    store.record("step1", "sig-a", "m", "out")
    assert store.compare("step1", "sig-a", "out") == "same"


def test_output_drift(tmp_path):
    store = SnapshotStore(snapshots_file(tmp_path, "flow"))
    store.record("s", "sig", "m", "original output")
    assert store.compare("s", "sig", "changed output") == "output_drift"


def test_signature_drift(tmp_path):
    store = SnapshotStore(snapshots_file(tmp_path, "flow"))
    store.record("s", "sig-old", "m", "out")
    assert store.compare("s", "sig-new", "out") == "signature_drift"


def test_survives_reload(tmp_path):
    path = snapshots_file(tmp_path, "flow")
    SnapshotStore(path).record("s", "sig", "m", "out")
    reloaded = SnapshotStore(path)
    assert reloaded.compare("s", "sig", "out") == "same"


def test_signature_depends_on_everything():
    a = signature_of("prompt", "m", {"x": 1})
    assert a != signature_of("prompt changed", "m", {"x": 1})
    assert a != signature_of("prompt", "other", {"x": 1})
    assert a != signature_of("prompt", "m", {"x": 2})


def test_output_drift_ignores_trailing_whitespace(tmp_path):
    store = SnapshotStore(snapshots_file(tmp_path, "flow"))
    store.record("s", "sig", "m", "out\n")
    assert store.compare("s", "sig", "out") == "same"
