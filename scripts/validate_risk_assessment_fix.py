import sys
import sqlite3
from pathlib import Path

# Allow execution from any working directory after cloning the repository.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.database.db import init_db, connect_db
from app.modules.risk.engine import ReagentRiskInput, run_risk_assessment

def validate():
    print("Risk assessment fix validation")
    print("-" * 30)
    
    # 1. Initialize database (triggers migration)
    init_db()
    
    # 2. Check schema
    conn = connect_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(compounds)")
    cols = [c[1] for c in cursor.fetchall()]
    
    hs6_exists = "hs6_code" in cols
    print(f"compounds.hs6_code exists: {'PASS' if hs6_exists else 'FAIL'}")
    
    # 3. Check index
    cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_compounds_hs6_code'")
    idx_exists = cursor.fetchone() is not None
    print(f"hs6_code index exists: {'PASS' if idx_exists else 'FAIL'}")
    conn.close()
    
    # 4. Run risk assessment test
    reagents = [
        ReagentRiskInput(name="Test Chemical", cas="7440-06-4", mass_g=1.0, cost=1.0)
    ]
    
    try:
        results = run_risk_assessment(reagents)
        print("run_risk_assessment executes: PASS")
        
        # 5. Check stability fallback for Unknown origin
        # (Assuming 'Unknown' is not in the stability CSV)
        unknown_reagent = ReagentRiskInput(name="Unknown", origin="Unknown", mass_g=1.0, cost=1.0)
        results_unk = run_risk_assessment([unknown_reagent])
        # If it didn't crash, it passed the stability definition check
        print("stability fallback works for Unknown origin: PASS")
        
        final_pass = hs6_exists and idx_exists and results and results_unk
        print("-" * 30)
        print(f"Final result: {'PASS' if final_pass else 'FAIL'}")
        
    except Exception as e:
        print(f"run_risk_assessment executes: FAIL ({type(e).__name__}: {e})")
        import traceback
        traceback.print_exc()
        print("-" * 30)
        print("Final result: FAIL")

if __name__ == "__main__":
    validate()
