"""Explicit HS6 survives routes and joins WITS independently of chemical names."""

import json
import sqlite3
import asyncio

import pandas as pd
import pytest

from app.hs6 import normalize_hs6
from app.modules.database import db as route_db
from app.modules.database.models import RouteReagentInput, SaveRouteRequest
from app.modules.extraction.schemas import DraftReagent
from app.modules.risk import engine, hs6_mapping
from app.modules.risk.engine import ReagentRiskInput, run_risk_assessment
from app.modules.risk.scenario import compute_scenario, items_from_assessment
from app.modules.synthesis.engine import ReagentInput, SynthesisProject, calculate_engine
from app.modules.trade_data import db as trade_db
from app.modules.trade_data.wits_ingest import ingest, parse_wits_file


def write_wits(path, code="282580", quantities=None):
    pd.DataFrame({
        "Reporter": ["China", "Belgium", "United States"],
        "TradeFlow": ["Export"] * 3, "Partner": ["World"] * 3,
        "ProductCode": [code] * 3,
        "Product Description": ["Antimony oxides"] * 3,
        "Year": [2024] * 3, "Quantity Unit": ["Kg"] * 3,
        "Quantity": quantities or [600, 250, 150], "Trade Value 1000USD": [60, 25, 15],
    }).to_excel(path, sheet_name="By-HS6Product", index=False)


@pytest.fixture
def antimony_trade(tmp_path, monkeypatch, usitc_folder, isolated_db):
    workbook = tmp_path / "antimony.xlsx"
    database = tmp_path / "wits.json"
    write_wits(workbook)
    ingest(str(workbook), str(database))
    loaded = trade_db.load(str(database))
    monkeypatch.setattr(trade_db, "load", lambda: loaded)
    monkeypatch.setattr(hs6_mapping, "_load_hs6_map", lambda: {
        "test": {"hs6_code": "282580", "name_hint": "Antimony trioxide"}
    })
    monkeypatch.setattr(engine, "load_reagent_mapping", lambda: pd.DataFrame())
    monkeypatch.setattr(engine, "load_country_stability", lambda: pd.DataFrame({
        "Country": ["China", "Belgium", "United States"],
        "Stability_Score": [40, 80, 70],
    }))
    return loaded


@pytest.mark.parametrize("name", [
    "Antimony trioxide catalyst", "antimony oxides", "antiomy oxides", "Sb2O3"
])
def test_explicit_code_matches_without_renaming(name, antimony_trade):
    row = run_risk_assessment([ReagentRiskInput(name=name, hs6=" 282580 ", cost=100)])['reagents'][0]
    assert row['name'] == name
    assert row['hs6'] == row['hs_code'] == '282580'
    assert row['trade_status'] == 'MATCHED'
    assert row['provenance']['hs6_mapping']['match_method'] == 'user_input'
    assert row['primary_origin'] == 'China'
    assert row['primary_origin_share_pct'] == 60
    assert row['secondary_origin_share_pct'] == 25
    assert row['breakdown']['geographic'] == 60
    assert row['concentration']['top_supplier_share'] == 60
    assert row['concentration']['tier'] == 'HIGH'
    assert len(row['supplier_shares']) == 3
    assert row['supply_chain_data']['top_exporters'][0]['trade_value_1000_usd'] == 60
    scenario = compute_scenario(items_from_assessment([row]), {'type': 'dominant_supplier_loss'})
    assert scenario['reagents'][0]['hs6'] == '282580'
    assert scenario['reagents'][0]['trade_status'] == 'MATCHED'
    assert scenario['reagents'][0]['exposure_share_pct'] == 60


def test_no_explicit_code_uses_resolver(antimony_trade):
    row = run_risk_assessment([ReagentRiskInput(name='Antimony trioxide')])['reagents'][0]
    assert row['hs6'] == '282580'
    assert row['trade_status'] == 'MATCHED'
    assert row['provenance']['hs6_mapping']['match_method'] == 'name_hint'


def test_explicit_code_does_not_require_working_name_registry(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Explicit HS6 should bypass automatic chemical identity resolution')
    monkeypatch.setattr(hs6_mapping, '_load_hs6_map', forbidden)
    resolved = hs6_mapping.resolve_hs6('arbitrary name', hs6_input='282580', conn=object())
    assert resolved['hs6'] == '282580'
    assert resolved['match_method'] == 'user_input'


def test_hs6_only_row_can_lookup_origins(antimony_trade):
    result = engine.lookup_suggested_origins([{'name': '', 'hs6': '282580'}])[0]
    assert result['primary'] == 'China'
    assert result['secondary'] == 'Belgium'
    assert result['trade_status'] == 'MATCHED'
    assert result['product_description'] == 'Antimony oxides'


@pytest.mark.parametrize('code,status', [('070951', 'NO WITS DATA'), ('ABC123', 'INVALID HS6'), (None, 'HS6 MISSING')])
def test_unmatched_lookup_does_not_invent_product_description(code, status, antimony_trade):
    result = engine.lookup_suggested_origins([{'name': '', 'hs6': code}])[0]
    assert result['trade_status'] == status
    assert result['product_description'] is None


def test_unknown_has_no_false_association(antimony_trade):
    row = run_risk_assessment([ReagentRiskInput(name='Example Unknown Chemical')])['reagents'][0]
    assert row['hs6'] is None
    assert row['trade_status'] == 'HS6 MISSING'
    assert not row['supplier_shares']


@pytest.mark.parametrize('origin,expected', [('United States', 15), ('USA', 15), ('Peru', None)])
def test_displayed_origin_share_follows_user_country_not_top_rank(origin, expected, antimony_trade):
    row = run_risk_assessment([ReagentRiskInput(name='oxides', hs6='282580', origin=origin)])['reagents'][0]
    assert row['primary_origin'] == origin
    assert row['primary_origin_share_pct'] == expected
    assert row['concentration']['top_supplier_share'] == 60


def test_98_percent_china_exports_are_tracked_as_high_concentration(antimony_trade, tmp_path, monkeypatch):
    workbook, database = tmp_path / 'high.xlsx', tmp_path / 'high.json'
    write_wits(workbook, quantities=[980, 20, 0])
    # Fixture replaces load for assessment; restore file loading for ingestion.
    loaded = trade_db.empty_db()
    monkeypatch.setattr(trade_db, 'load', lambda *args: loaded)
    ingest(str(workbook), str(database))
    row = run_risk_assessment([ReagentRiskInput(name='oxides', hs6='282580')])['reagents'][0]
    assert row['primary_origin_share_pct'] == 98
    assert row['secondary_origin_share_pct'] == 2
    assert row['concentration']['tier'] == 'HIGH'
    assert row['breakdown']['concentration'] == 98
    assert row['provenance']['share_basis'] == 'share_of_listed'


def test_valid_code_without_trade_remains_visible(antimony_trade):
    row = run_risk_assessment([ReagentRiskInput(name='Antimony trioxide', hs6='070951')])['reagents'][0]
    assert row['hs6'] == '070951'
    assert row['trade_status'] == 'NO WITS DATA'
    assert not row['supplier_shares']


@pytest.mark.parametrize('code', ['ABC123', '28258', '2825800', '282580.0', '2.8258e5', '2825.80', 282580.0])
def test_invalid_explicit_code_blocks_fallback_and_trade(code, antimony_trade, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Invalid HS6 must not attempt trade matching')
    monkeypatch.setattr(engine, 'get_supply_chain_concentration', forbidden)
    row = run_risk_assessment([ReagentRiskInput(name='Antimony trioxide', hs6=code)])['reagents'][0]
    assert row['hs6'] == str(code)
    assert row['hs_code'] is None
    assert row['trade_status'] == 'INVALID HS6'
    assert row['provenance']['status'] == 'invalid_hs6'
    assert 'Invalid HS6' in row['data_quality']['reasons'][0]
    assert not row['supplier_shares']


@pytest.mark.parametrize('code,expected', [(' 282580 ', '282580'), (282580, '282580'), ('07 0951', '070951'), (None, None), (' ', None)])
def test_normalization_across_models(code, expected):
    assert normalize_hs6(code) == expected
    for model, required in [
        (ReagentRiskInput, {}), (DraftReagent, {}),
        (ReagentInput, {'mw': 1, 'equivalents': 1}),
        (RouteReagentInput, {'mw': 1, 'equivalents': 1, 'mass': 1}),
    ]:
        item = model(name='unchanged', hs6=code, **required)
        assert item.model_dump()['hs6'] == expected


@pytest.mark.parametrize('code', [' 282580 ', 282580, '070951'])
def test_wits_productcode_normalization(tmp_path, code):
    path = tmp_path / 'wits.xlsx'
    write_wits(path, code)
    assert parse_wits_file(str(path))[0]['hs6_code'] == normalize_hs6(code)


@pytest.mark.parametrize('code', ['ABC123', '28258', '2825800', '282580.0', '2.8258e5'])
def test_invalid_wits_codes_fail_without_saving(tmp_path, code):
    path, database = tmp_path / 'wits.xlsx', tmp_path / 'wits.json'
    write_wits(path, code)
    with pytest.raises(ValueError, match='Invalid HS6.*ProductCode'):
        ingest(str(path), str(database))
    assert not database.exists()


def test_route_save_load_hash_and_estimate_preserve_hs6(isolated_db):
    request = SaveRouteRequest(
        route_label='A', route={'steps': [{
            'step_id': 1, 'name': 'test', 'product_mw': 100,
            'reagents': [{'name': 'antiomy oxides', 'hs6': '070951', 'mw': 100,
                          'equivalents': 1, 'mass': 1}]
        }]}, analysis_results={'total_cost': 1, 'cost_per_kg': 1, 'e_factor': 1})
    definition = request.route.model_dump()
    code_hash = route_db.compute_route_hash(definition, 'test')
    definition['steps'][0]['reagents'][0]['hs6'] = None
    legacy_hash = route_db.compute_route_hash(definition, 'test')
    del definition['steps'][0]['reagents'][0]['hs6']
    assert route_db.compute_route_hash(definition, 'test') == legacy_hash
    assert code_hash != legacy_hash
    with route_db.connect_db() as conn:
        result = route_db.save_route_transaction(conn, request)
        row = conn.execute('SELECT hs6, raw_reagent_json FROM step_reagents').fetchone()
        assert row[0] == json.loads(row[1])['hs6'] == '070951'
    from app.modules.database.router import api_get_route_detail
    assert asyncio.run(api_get_route_detail(result['route_uuid']))['steps'][0]['reagents'][0]['hs6'] == '070951'
    estimate = calculate_engine(SynthesisProject(**request.route.model_dump()))
    assert estimate['steps'][0]['reagents'][0]['hs6'] == '070951'


def test_additive_migration_keeps_historical_rows(tmp_path, monkeypatch):
    path = tmp_path / 'legacy.db'
    monkeypatch.setattr(route_db, 'DB_PATH', path)
    route_db.init_db()
    with sqlite3.connect(path) as conn:
        conn.execute('ALTER TABLE step_reagents DROP COLUMN hs6')
        conn.execute("INSERT INTO step_reagents (uuid, step_uuid, route_uuid, name) VALUES ('r', 's', 'old', 'old name')")
    route_db.init_db()
    route_db.init_db()
    with sqlite3.connect(path) as conn:
        assert conn.execute('SELECT name, hs6 FROM step_reagents').fetchone() == ('old name', None)
