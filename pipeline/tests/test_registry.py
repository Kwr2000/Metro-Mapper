import json

import pytest

from mm import registry, runner
from mm.manifests import ManifestError


def test_compiles_repo_manifests(repo):
    runner.run("demo_points", mode="fixture")
    reg = registry.compile_registry()
    demo = next(l for l in reg.layers if l.id == "demo_landmarks")
    assert demo.data_url == "data/layers/demo_landmarks.geojson"
    assert demo.freshness == "fixture_only"  # fixture data never presented as current
    assert demo.as_of == "2026-10-23"
    on_disk = json.loads((repo / "web/public/registry.json").read_text())
    assert on_disk["site_title"] == "Metro Mapper"
    assert demo.id in [l["id"] for l in on_disk["layers"]]
    published = json.loads((repo / "web/public/data/layers/demo_landmarks.geojson").read_text())
    assert published["test_data"] is True


def test_new_layer_needs_only_a_manifest(repo):
    text = (repo / "layers" / "demo_landmarks.yaml").read_text()
    text = text.replace("id: demo_landmarks", "id: demo_parks_only").replace(
        "title: Demo landmarks", "title: Demo parks only")
    (repo / "layers" / "demo_parks_only.yaml").write_text(text + "where: {kind: park}\n")
    runner.run("demo_points", mode="fixture")
    reg = registry.compile_registry()
    assert {"demo_landmarks", "demo_parks_only"} <= {l.id for l in reg.layers}
    parks = json.loads((repo / "web/public/data/layers/demo_parks_only.geojson").read_text())
    assert [f["id"] for f in parks["features"]] == ["san_marcos_springs"]


def _write_layer(repo, name, **changes):
    text = (repo / "layers" / "demo_landmarks.yaml").read_text()
    for old, new in changes.items():
        text = text.replace(old, new)
    (repo / "layers" / f"{name}.yaml").write_text(text)


def test_rejects_unknown_adapter(repo):
    _write_layer(repo, "bad_source", **{"id: demo_landmarks": "id: bad_source",
                                         "source: demo_points": "source: no_such_adapter"})
    with pytest.raises(ManifestError, match="no_such_adapter"):
        registry.compile_registry()


def test_rejects_style_that_does_not_fit_geometry(repo):
    _write_layer(repo, "bad_style", **{"id: demo_landmarks": "id: bad_style", "type: circle": "type: fill"})
    with pytest.raises(ManifestError, match="does not fit geometry"):
        registry.compile_registry()


def test_rejects_id_file_name_mismatch(repo):
    _write_layer(repo, "other_name")  # id inside still says demo_landmarks
    with pytest.raises(ManifestError, match="must match the file name"):
        registry.compile_registry()


def test_rejects_unknown_fields(repo):
    _write_layer(repo, "typo_field", **{"id: demo_landmarks": "id: typo_field",
                                         "order: 900": "order: 900\ncolour: red"})
    with pytest.raises(ManifestError, match="colour"):
        registry.compile_registry()


def test_shared_bundle_is_one_file(repo):
    _write_layer(repo, "demo_a", **{"id: demo_landmarks": "id: demo_a", "order: 900": "order: 900\ndata_bundle: demo_bundle"})
    _write_layer(repo, "demo_b", **{"id: demo_landmarks": "id: demo_b", "order: 900": "order: 900\ndata_bundle: demo_bundle"})
    runner.run("demo_points", mode="fixture")
    reg = registry.compile_registry()
    urls = {l.id: l.data_url for l in reg.layers if l.id in ("demo_a", "demo_b")}
    assert urls == {"demo_a": "data/layers/demo_bundle.geojson", "demo_b": "data/layers/demo_bundle.geojson"}
    files = {p.name for p in (repo / "web/public/data/layers").iterdir()}
    assert "demo_bundle.geojson" in files and not {"demo_a.geojson", "demo_b.geojson"} & files


def test_rejects_bundle_named_like_a_layer(repo):
    _write_layer(repo, "demo_a", **{"id: demo_landmarks": "id: demo_a", "order: 900": "order: 900\ndata_bundle: demo_landmarks"})
    with pytest.raises(ManifestError, match="same name as a layer id"):
        registry.compile_registry()


def test_schema_export(repo):
    written = registry.export_schemas()
    assert "schemas/registry.schema.json" in written
    schema = json.loads((repo / "schemas/registry.schema.json").read_text())
    assert schema["title"] == "Registry"


def test_committed_schemas_are_current(tmp_path, monkeypatch):
    """schemas/ in the repo matches the models (run `mm schema` after changing them)."""
    from conftest import REPO

    monkeypatch.setenv("MM_ROOT", str(tmp_path))
    registry.export_schemas()
    for p in (tmp_path / "schemas").glob("*.json"):
        assert p.read_text() == (REPO / "schemas" / p.name).read_text(), f"run `mm schema`: {p.name}"
