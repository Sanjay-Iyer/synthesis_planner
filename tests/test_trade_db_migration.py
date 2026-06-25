import pytest
import os
import json
import uuid
import asyncio
from app.modules.trade_data import db


def test_detects_legacy_schema():
    legacy = {"schema_version": 1, "trade_data": {}}
    assert db.is_legacy_trade_db(legacy) is True


def test_migrates_trade_data_to_products():
    legacy = {
        "last_updated": "2026-05-13T17:00:13+00:00",
        "trade_data": {
            "291735": {
                "product_description": "Phthalic anhydride",
                "years": {
                    "2024": {
                        "trade_flow": "Export",
                        "partner": "World",
                        "top_exporters": [{"reporter": "China", "quantity": 100}],
                        "concentration_top1_pct": 30.19,
                    }
                },
            }
        },
    }
    migrated = db.migrate_trade_db_to_v1_1(legacy)
    assert "products" in migrated
    assert "291735" in migrated["products"]
    assert migrated["metadata"]["schema_version"] == "1.1.0"


def test_generates_record_uuid():
    legacy = {"trade_data": {"291735": {"years": {"2024": {"top_exporters": []}}}}}
    migrated = db.migrate_trade_db_to_v1_1(legacy)
    record = migrated["products"]["291735"]["records"]["2024_export_world"]
    assert "record_uuid" in record
    assert len(record["record_uuid"]) == 36  # UUID length


def test_computes_concentration_score():
    def get_score(pct):
        legacy = {
            "trade_data": {
                "HS": {
                    "years": {
                        "2024": {"concentration_top1_pct": pct, "top_exporters": []}
                    }
                }
            }
        }
        migrated = db.migrate_trade_db_to_v1_1(legacy)
        return migrated["products"]["HS"]["records"]["2024_export_world"][
            "risk_summary"
        ]["concentration_score"]

    assert get_score(60) == "High"
    assert get_score(30) == "Medium"
    assert get_score(10) == "Low"


def test_load_auto_migration(tmp_path):
    # Create a legacy file
    p = tmp_path / "legacy_db.json"
    legacy = {
        "last_updated": "2026-05-13T17:00:13+00:00",
        "trade_data": {
            "291735": {
                "product_description": "Phthalic anhydride",
                "years": {
                    "2024": {
                        "trade_flow": "Export",
                        "partner": "World",
                        "top_exporters": [{"reporter": "China", "quantity": 100}],
                        "concentration_top1_pct": 30.19,
                    }
                },
            }
        },
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(legacy, f)

    # Loading it should auto-migrate
    loaded = db.load(str(p))
    assert "products" in loaded
    assert "trade_data" not in loaded
    assert loaded["metadata"]["schema_version"] == "1.1.0"

    # Should have been saved back to disk
    with open(p, "r", encoding="utf-8") as f:
        on_disk = json.load(f)
    assert on_disk["metadata"]["schema_version"] == "1.1.0"


def test_record_uuid_stability():
    legacy = {"trade_data": {"291735": {"years": {"2024": {"top_exporters": []}}}}}
    migrated = db.migrate_trade_db_to_v1_1(legacy)
    record1 = migrated["products"]["291735"]["records"]["2024_export_world"]
    uuid1 = record1["record_uuid"]

    # Second migration of the same data should keep the same UUID if we started from the migrated one
    # But migrate_trade_db_to_v1_1 is designed to migrate LEGACY.
    # If we call it on already migrated, it returns as-is.
    remigrated = db.migrate_trade_db_to_v1_1(migrated)
    assert (
        remigrated["products"]["291735"]["records"]["2024_export_world"]["record_uuid"]
        == uuid1
    )


def test_future_import_writes_v1_1(tmp_path):
    from app.modules.trade_data import wits_ingest

    db_p = tmp_path / "new_db.json"

    # Mock some parsed results
    mock_results = [
        {
            "hs6_code": "123456",
            "product_description": "Test Product",
            "year": 2024,
            "trade_flow": "Export",
            "partner": "World",
            "quantity_unit": "Kg",
            "top_n_actual": 1,
            "top_exporters": [
                {
                    "rank": 1,
                    "reporter": "A",
                    "quantity": 10,
                    "trade_value_1000_usd": 100,
                    "share_of_top5_pct": 100,
                }
            ],
            "totals": {
                "total_top5_quantity": 10,
                "total_top5_trade_value_1000_usd": 100,
            },
            "risk_summary": {
                "concentration_score": "High",
                "concentration_top1_pct": 100,
            },
            "excluded_rows": {"missing_quantity": []},
            "warnings": [],
        }
    ]

    # We need to monkeypatch parse_wits_file to return our mock results
    import app.modules.trade_data.wits_ingest as wi

    original_parse = wi.parse_wits_file
    wi.parse_wits_file = lambda x: mock_results

    try:
        wits_ingest.ingest("fake.xlsx", str(db_p))

        with open(db_p, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "products" in data
        assert data["metadata"]["schema_version"] == "1.1.0"
        assert "123456" in data["products"]
    finally:
        wi.parse_wits_file = original_parse


def test_api_summary_v1_1():
    from app.modules.trade_data.router import get_trade_summary

    # This requires mocking db.load
    import app.modules.trade_data.db as trade_db

    original_load = trade_db.load

    mock_db = {
        "metadata": {"schema_version": "1.1.0"},
        "products": {
            "123": {
                "records": {
                    "2024_export_world": {
                        "year": 2024,
                        "risk_summary": {"concentration_score": "High"},
                        "source": {"ingested_at": "2026-01-01"},
                    }
                }
            }
        },
    }
    trade_db.load = lambda: mock_db

    try:
        summary = asyncio.run(get_trade_summary())
        assert summary["product_count"] == 1
        assert summary["high_concentration_count"] == 1
        assert summary["schema_version"] == "1.1.0"
    finally:
        trade_db.load = original_load
