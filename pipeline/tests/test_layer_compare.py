"""Display-only comparison contracts and the complete P1-12 manifest table."""
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from pydantic import ValidationError

from mm.schemas import LayerManifest

ROOT = Path(__file__).resolve().parents[2]
RATIO = [.67, .9, 1.1, 1.5]


def base():
    return yaml.safe_load((ROOT / 'layers/safety_agency_rate.yaml').read_text())


def test_optional_compare_and_default_benchmark_field():
    doc = base()
    doc.pop('compare')
    assert LayerManifest.model_validate(doc).compare is None
    doc['compare'] = dict(field='rate_part1', method='ratio', breaks=RATIO, direction='neutral')
    c = LayerManifest.model_validate(doc).compare
    assert c.benchmark_field is None and c.unit == ''


@pytest.mark.parametrize('changes,match', [
    ({'breaks': [1, 1, 2, 3]}, 'strictly increasing'),
    ({'breaks': [1, 3, 2, 4]}, 'strictly increasing'),
    ({'breaks': [1, 2, 3, float('inf')]}, 'finite'),
    ({'breaks': [1, 2, 3, float('nan')]}, 'finite'),
    ({'breaks': [1, 2, 3]}, 'at least 4'),
    ({'breaks': [1, 2, 3, 4, 5]}, 'at most 4'),
    ({'method': 'difference', 'breaks': [-10, -2, 3, 10]}, 'symmetric'),
    ({'method': 'difference', 'breaks': [1, 2, 3, 4]}, 'symmetric'),
    ({'field': 'not_in_popup'}, 'popup'),
    ({'direction': 'higher'}, 'Input should be'),
])
def test_compare_rejections(changes, match):
    doc = base()
    doc['compare'].update(changes)
    with pytest.raises(ValidationError, match=match):
        LayerManifest.model_validate(doc)


def test_demographic_and_nonpublished_guards():
    doc = base()
    doc['demographic'] = True
    with pytest.raises(ValidationError, match='neutral'):
        LayerManifest.model_validate(doc)
    doc['compare']['direction'] = 'neutral'
    LayerManifest.model_validate(doc)
    doc.update(publish='none', geometry='none', style=None)
    with pytest.raises(ValidationError, match='publish: none'):
        LayerManifest.model_validate(doc)


def expected_table():
    table = {}
    def add(identity, field, method='ratio', breaks=RATIO, direction='lower_is_better', unit='', benchmark=None):
        table[identity] = dict(field=field, benchmark_field=benchmark, method=method,
                              breaks=breaks, direction=direction, unit=unit)
    add('safety_agency_rate', 'rate_part1')
    for name, field in [('apd_part1_rate', 'rate_part1'), ('apd_violent_rate', 'rate_violent'), ('apd_part1_density', 'density_part1')]:
        add(name, field)
    for name, scope in [('school_campuses', 'campus'), ('school_district_ratings', 'district')]:
        add(name, 'overall_score', 'difference', [-10,-3,3,10], 'higher_is_better', 'points', scope+'_overall_score')
    for mode in ('walk', 'bike'):
        for dest in ('grocery', 'park', 'school', 'basket'):
            add(f'access_{dest}_{mode}', f'{mode}_{dest}')
    add('access_transit', 'transit_per_hour', direction='higher_is_better')
    # Derive the ACS families from the native metric contract, while asserting rules independently.
    import importlib.util
    spec = importlib.util.spec_from_file_location('compare_metrics', ROOT/'adapters/acs/metrics.py')
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    for field, (_, fmt, *_) in metrics.METRICS.items():
        if field == 'population':
            continue
        method, cuts, unit = ('ratio', RATIO, '') if fmt == 'currency' else (
            'difference', [-5,-2,2,5] if field == 'median_age' else [-15,-5,5,15] if field == 'median_year_built' else [-.1,-.03,.03,.1],
            'pp' if fmt == 'percent' else 'years')
        for scale in ('bg', 'tract'):
            add(f'acs_{field}_{scale}', field, method, cuts, 'neutral', unit, field)
    add('elections_turnout_2024', 'turnout_2024', 'difference', [-.1,-.03,.03,.1], 'neutral', 'pp')
    add('elections_president_2024', 'pres_2024_margin', 'difference', [-.2,-.05,.05,.2], 'neutral', 'pts')
    return table


def test_every_manifest_matches_task_table():
    expected = expected_table()
    actual = {}
    for path in (ROOT/'layers').glob('*.yaml'):
        layer = LayerManifest.model_validate(yaml.safe_load(path.read_text()))
        if layer.compare:
            actual[layer.id] = layer.compare.model_dump()
            assert not layer.demographic or layer.compare.direction == 'neutral'
    assert actual == expected  # also excludes population, flood, boundaries, metadata and school_districts


@pytest.mark.parametrize('source', ['acs', 'access', 'elections'])
def test_generated_manifests_are_current(source, tmp_path):
    # Run each generator in an isolated minimal tree; never rewrite the checkout in tests.
    import shutil
    shutil.copytree(ROOT/'adapters'/source, tmp_path/'adapters'/source)
    (tmp_path/'layers').mkdir()
    subprocess.run([sys.executable, str(tmp_path/'adapters'/source/'make_layers.py')], check=True)
    produced = list((tmp_path/'layers').glob('*.yaml'))
    assert produced
    for path in produced:
        assert path.read_text() == (ROOT/'layers'/path.name).read_text(), path.name
