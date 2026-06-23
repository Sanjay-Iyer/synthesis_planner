from app.modules.risk.engine import lookup_suggested_origins

def test_pet_reagents_origins():
    """Verify that all target PET reagents now have origins."""
    reagents = [
        {"name": "Germanium dioxide catalyst"},
        {"name": "PET Intermediate (Oligomer)"},
        {"name": "High-Performance UV Stabilizer"},
        {"name": "Manganese(II) acetate"},
        {"name": "Antimony trioxide catalyst"},
        {"name": "Nitrogen Gas (UHP Grade)"}
    ]
    
    results = lookup_suggested_origins(reagents)
    
    print("\nTest Results for PET Reagents:")
    print("-" * 40)
    for i, r in enumerate(reagents):
        res = results[i]
        print(f"{r['name']}: {res['primary']} (HS6: {res['hs6']})")
        if res["primary"] == "Unknown":
            print(f"  Warning: {r['name']} still has Unknown origin (Trade data missing in DB)")
    print("-" * 40)

if __name__ == "__main__":
    test_pet_reagents_origins()
