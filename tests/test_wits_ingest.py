import pytest
import pandas as pd
import os
import json
import tempfile
from pathlib import Path
from app.modules.trade_data.wits_ingest import parse_wits_file, ingest
from app.modules.trade_data import db

_TMP = Path(tempfile.gettempdir())
TEST_DB_PATH = str(_TMP / "test_wits_exports.json")
TEST_XLSX_PATH = str(_TMP / "test_wits_data.xlsx")

@pytest.fixture
def clean_env():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    if os.path.exists(TEST_XLSX_PATH):
        os.remove(TEST_XLSX_PATH)
    yield
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    if os.path.exists(TEST_XLSX_PATH):
        os.remove(TEST_XLSX_PATH)

def create_mock_excel(data, path=TEST_XLSX_PATH):
    df = pd.DataFrame(data)
    with pd.ExcelWriter(path) as writer:
        df.to_excel(writer, sheet_name='By-HS6Product', index=False)
        pd.DataFrame().to_excel(writer, sheet_name='Sheet1', index=False)

def test_strings_preserve_leading_zero_hs6(clean_env):
    data = {
        'Reporter': ['Saudi Arabia'],
        'TradeFlow': ['Export'],
        'ProductCode': ['070951'],
        'Product Description': ['Test Product'],
        'Year': [2024],
        'Partner': [' World'],
        'Trade Value 1000USD': [100.0],
        'Quantity': [1000.0],
        'Quantity Unit': ['Kg']
    }
    create_mock_excel(data)
    results = parse_wits_file(TEST_XLSX_PATH)
    assert results[0]['hs6_code'] == "070951"

def test_filter_drops_imports_and_bilateral(clean_env):
    data = {
        'Reporter': ['SA', 'US', 'CN'],
        'TradeFlow': ['Export', 'Import', 'Export'],
        'ProductCode': ['291611', '291611', '291611'],
        'Product Description': ['P', 'P', 'P'],
        'Year': [2024, 2024, 2024],
        'Partner': [' World', ' World', 'US'],
        'Trade Value 1000USD': [100, 200, 300],
        'Quantity': [1000, 2000, 3000],
        'Quantity Unit': ['Kg', 'Kg', 'Kg']
    }
    create_mock_excel(data)
    results = parse_wits_file(TEST_XLSX_PATH)
    assert len(results) == 1
    assert results[0]['top_exporters'][0]['reporter'] == 'SA'

def test_missing_quantity_goes_to_excluded(clean_env):
    data = {
        'Reporter': ['SA', 'CN'],
        'TradeFlow': ['Export', 'Export'],
        'ProductCode': ['291611', '291611'],
        'Product Description': ['P', 'P'],
        'Year': [2024, 2024],
        'Partner': [' World', ' World'],
        'Trade Value 1000USD': [100, 500],
        'Quantity': [1000, None],
        'Quantity Unit': ['Kg', 'Kg']
    }
    create_mock_excel(data)
    results = parse_wits_file(TEST_XLSX_PATH)
    assert len(results[0]['top_exporters']) == 1
    assert results[0]['top_exporters'][0]['reporter'] == 'SA'
    assert len(results[0]['excluded_no_quantity']) == 1
    assert results[0]['excluded_no_quantity'][0]['reporter'] == 'CN'

def test_top5_by_quantity_not_value(clean_env):
    # Saudi has lower value but higher quantity
    data = {
        'Reporter': ['SA', 'CN', 'US', 'DE', 'JP', 'UK'],
        'TradeFlow': ['Export'] * 6,
        'ProductCode': ['291611'] * 6,
        'Product Description': ['P'] * 6,
        'Year': [2024] * 6,
        'Partner': [' World'] * 6,
        'Trade Value 1000USD': [100, 1000, 800, 700, 600, 500],
        'Quantity': [10000, 5000, 4000, 3000, 2000, 1000],
        'Quantity Unit': ['Kg'] * 6
    }
    create_mock_excel(data)
    results = parse_wits_file(TEST_XLSX_PATH)
    top_reporters = [e['reporter'] for e in results[0]['top_exporters']]
    assert top_reporters == ['SA', 'CN', 'US', 'DE', 'JP']

def test_idempotent_reingest(clean_env):
    data = {
        'Reporter': ['SA'], 'TradeFlow': ['Export'], 'ProductCode': ['291611'],
        'Product Description': ['P'], 'Year': [2024], 'Partner': [' World'],
        'Trade Value 1000USD': [100], 'Quantity': [1000], 'Quantity Unit': ['Kg']
    }
    create_mock_excel(data)
    ingest(TEST_XLSX_PATH, TEST_DB_PATH)
    with open(TEST_DB_PATH, 'r', encoding='utf-8') as f:
        db1 = json.load(f)

    ingest(TEST_XLSX_PATH, TEST_DB_PATH)
    with open(TEST_DB_PATH, 'r', encoding='utf-8') as f:
        db2 = json.load(f)
    
    # Ignore last_updated and ingested_at in comparison
    db1.pop('last_updated')
    db2.pop('last_updated')
    for hs6 in db1['trade_data']:
        for year in db1['trade_data'][hs6]['years']:
            db1['trade_data'][hs6]['years'][year].pop('ingested_at')
            db2['trade_data'][hs6]['years'][year].pop('ingested_at')
    assert db1 == db2

def test_two_years_coexist(clean_env):
    data24 = {
        'Reporter': ['SA'], 'TradeFlow': ['Export'], 'ProductCode': ['291611'],
        'Product Description': ['P'], 'Year': [2024], 'Partner': [' World'],
        'Trade Value 1000USD': [100], 'Quantity': [1000], 'Quantity Unit': ['Kg']
    }
    create_mock_excel(data24)
    ingest(TEST_XLSX_PATH, TEST_DB_PATH)
    
    data25 = {
        'Reporter': ['SA'], 'TradeFlow': ['Export'], 'ProductCode': ['291611'],
        'Product Description': ['P'], 'Year': [2025], 'Partner': [' World'],
        'Trade Value 1000USD': [110], 'Quantity': [1100], 'Quantity Unit': ['Kg']
    }
    create_mock_excel(data25)
    ingest(TEST_XLSX_PATH, TEST_DB_PATH)
    
    final_db = db.load(TEST_DB_PATH)
    years = final_db['trade_data']['291611']['years']
    assert '2024' in years
    assert '2025' in years

def test_unknown_quantity_unit_preserved(clean_env):
    data = {
        'Reporter': ['SA'], 'TradeFlow': ['Export'], 'ProductCode': ['291611'],
        'Product Description': ['P'], 'Year': [2024], 'Partner': [' World'],
        'Trade Value 1000USD': [100], 'Quantity': [1000], 'Quantity Unit': ['m3']
    }
    create_mock_excel(data)
    results = parse_wits_file(TEST_XLSX_PATH)
    assert results[0]['quantity_unit'] == 'm3'

def test_warning_when_excluded_outranks_top5_smallest(clean_env):
    # CN has 500 value but no qty. UK has 100 value and 1000 qty.
    # CN (excluded) outranks UK (top-5) by value.
    data = {
        'Reporter': ['UK', 'CN'],
        'TradeFlow': ['Export', 'Export'],
        'ProductCode': ['291611', '291611'],
        'Product Description': ['P', 'P'],
        'Year': [2024, 2024],
        'Partner': [' World', ' World'],
        'Trade Value 1000USD': [100, 500],
        'Quantity': [1000, None],
        'Quantity Unit': ['Kg', 'Kg']
    }
    create_mock_excel(data)
    summary = ingest(TEST_XLSX_PATH, TEST_DB_PATH)
    assert any("CN excluded but has higher trade value" in w for w in summary['warnings'])
