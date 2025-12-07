# seed_lassa_products.py
#
# Run from project root with:
#   source venv/bin/activate   (if not already active)
#   python seed_lassa_products.py
#
# This will insert Lassa AG products into the SAME tire_simulator.db used by FastAPI.

import re

from app.main import SessionLocal, Product  # IMPORTANT: from app.main
from app.utils import (
    estimate_geometry_and_cbm,
    estimate_units_per_container,
)


RAW_LASSA_LIST = """
250/85R24 — Radial
280/70R16 — Radial
280/70R18 — Radial
280/70R20 — Radial
280/85R20 (11.2R20) — Radial
280/85R24 (11.2R24) — Radial
280/85R28 — Radial
300/70R20 — Radial
320/70R24 — Radial
320/85R20 — Radial
320/85R24 (12.4R24) — Radial
320/85R28 — Radial
320/85R36 — Radial
340/85R24 (13.6R24) — Radial
340/85R28 (13.6R28) — Radial
340/85R36 (13.6R36) — Radial
340/85R38 — Radial
360/70R20 — Radial
360/70R24 — Radial
360/70R28 — Radial
380/70R24 — Radial
380/70R28 — Radial
380/85R24 — Radial
380/85R28 (14.9R28) — Radial
380/85R30 (14.9R30) — Radial
380/85R38 (14.9R38) — Radial
420/70R24 — Radial
420/70R28 — Radial
420/70R30 — Radial
420/85R28 — Radial
420/85R30 (16.9R30) — Radial
420/85R34 (16.9R34) — Radial
420/85R38 — Radial
460/85R30 (18.4R30) — Radial
460/85R34 (18.4R34) — Radial
460/85R38 (18.4R38) — Radial
480/70R24 — Radial
480/70R34 — Radial
480/70R38 — Radial

11.2-24 — Bias
12.4/11-24 (6PR) — Bias
12.4/11-24 (8PR) — Bias
12.4/11-28 (6PR) — Bias
12.4/11-28 (8PR) — Bias
13.6/12-28 (6PR) — Bias
13.6/12-28 (8PR) — Bias
13.6/12-36 (8PR) — Bias
13.6/12-38 (6PR) — Bias
13.6/12-38 (8PR) — Bias
14.9/13-28 (6PR) — Bias
14.9/13-28 (8PR) — Bias
14.9/13-30 (6PR) — Bias
14.9/13-30 (8PR) — Bias
16.9/14-30 (6PR) — Bias
16.9/14-30 (8PR) — Bias
16.9/14-38 (8PR) — Bias
18.4/15-30 (8PR) — Bias
18.4/15-30 (14PR) — Bias

9.5-24 — Bias (Front)
5.50-16 (6PR) — Bias (Front)
5.50-16 (8PR) — Bias (Front)
6.00-16 (6PR) — Bias (Front)
6.00-16 (8PR) — Bias (Front)
6.00-19 (6PR) — Bias (Front)
6.00-19 (8PR) — Bias (Front)
6.50-16 (6PR) — Bias (Front)
6.50-16 (8PR) — Bias (Front)
7.50-16 (6PR) — Bias (Front)
7.50-16 (8PR) — Bias (Front)
7.50-18 (8PR) — Bias (Front)

7.50-16 (12PR) — Trailer / Implement
"""


def classify_line(line: str):
    """
    Parse a single line like:
      '280/85R20 (11.2R20) — Radial'
      '12.4/11-24 (6PR) — Bias'
      '7.50-16 (12PR) — Trailer / Implement'
    Return a dict with fields for Product().
    """
    # Split left/right by em-dash (—). If that fails, try double hyphen.
    if "—" in line:
        left, right = line.split("—", 1)
    elif "--" in line:
        left, right = line.split("--", 1)
    else:
        left, right = line, ""

    left = left.strip()
    right = right.strip()

    # size_string = first token on the left (before any space)
    size_string = left.split()[0]

    # ply rating if present, e.g. (6PR) or (14PR)
    ply_match = re.search(r"(\d+PR)", left)
    ply_rating = ply_match.group(1) if ply_match else ""

    right_lower = right.lower()

    # Construction & category rules
    if "radial" in right_lower:
        radial_or_bias = "Radial"
        category = "Tractor Rear"
    elif "trailer / implement" in right_lower:
        radial_or_bias = "Bias"
        category = "Implement"
    elif "bias (front)" in right_lower:
        radial_or_bias = "Bias"
        category = "Tractor Front"
    elif "bias" in right_lower:
        radial_or_bias = "Bias"
        category = "Tractor Rear"
    else:
        radial_or_bias = "Bias"
        category = "Tractor Rear"

    return {
        "size_string": size_string,
        "radial_or_bias": radial_or_bias,
        "category": category,
        "ply_rating": ply_rating,
    }


def seed_lassa_products():
    db = SessionLocal()
    created = 0
    skipped = 0

    try:
        for raw_line in RAW_LASSA_LIST.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            data = classify_line(line)

            # Check if this product already exists (avoid duplicates)
            existing = (
                db.query(Product)
                .filter(
                    Product.brand == "Lassa",
                    Product.size_string == data["size_string"],
                    Product.radial_or_bias == data["radial_or_bias"],
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

            # --- NEW: compute geometry + cbm + container loading ---
            geo = estimate_geometry_and_cbm(data["size_string"])
            units_20, units_40 = estimate_units_per_container(geo["cbm_per_tire"])

            p = Product(
                brand="Lassa",
                model_name="",           # pattern name can be added later
                size_string=data["size_string"],
                segment="AG",            # agricultural line
                category=data["category"],
                radial_or_bias=data["radial_or_bias"],
                load_index="",           # unknown here
                speed_rating="",         # unknown here
                ply_rating=data["ply_rating"],
                currency="USD",          # default for now

                # cost fields (placeholders for now)
                exw_price=0.0,
                packing_cost=0.0,
                tire_weight_kg=0.0,

                # OLD: if you still use tire_cbm, keep it in sync with estimate
                tire_cbm=geo["cbm_per_tire"] or 0.0,

                duty_percent=0.0,
                source_country="Turkiye",

                # NEW logistics fields from models.py
                section_width_mm=geo["section_width_mm"],
                aspect_ratio=geo["aspect_ratio"],
                rim_diameter_inch=geo["rim_diameter_inch"],
                overall_diameter_mm=geo["overall_diameter_mm"],
                cbm_per_tire_estimated=geo["cbm_per_tire"],
                units_per_20dc_estimated=units_20,
                units_per_40hc_estimated=units_40,
            )
            db.add(p)
            created += 1

        db.commit()
        print(f"Done. Created {created} products, skipped {skipped} already existing.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_lassa_products()
