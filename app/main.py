from collections import Counter, defaultdict
from typing import Optional
from fastapi import FastAPI, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, Session, declarative_base, relationship
import re
import httpx
import csv
import io
import json
import math

# Safe import for local run and Render
try:
    # when app is run as a package: uvicorn app.main:app
    from .scrapers import scrape_all_sources, ScrapedOffer
except ImportError:
    # when main.py is run directly: uvicorn main:app
    from scrapers import scrape_all_sources, ScrapedOffer


# ---------------------------
# Google Custom Search config
# ---------------------------
GOOGLE_API_KEY = "AIzaSyCCpdvPIquVvmlUrxxD3ZEZ_a0MGyQOgy0"
GOOGLE_CX = "f57f45f72644c493d"

DATABASE_URL = "sqlite:///tire_simulator.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Approx container volumes (very rough, useful for “how many pcs”)
CONTAINER_20FT_CBM = 33.0
CONTAINER_40FT_CBM = 67.0

# ---------------------------
# Dropdown option definitions
# ---------------------------

SEGMENT_CHOICES = [
    "AG",      # Agricultural
    "TBR",     # Truck & Bus Radial
    "PCR",     # Passenger Car Radial
    "LT",      # Light Truck
    "OTR",     # Off-the-Road
    "IND",     # Industrial
]

COUNTRY_CHOICES = [
    "Turkiye",
    "United States",
    "Canada",
    "Mexico",
    "Brazil",
    "United Kingdom",
    "Germany",
    "France",
    "Italy",
    "Spain",
    "Netherlands",
    "Belgium",
    "Poland",
    "Czech Republic",
    "Russia",
    "China",
    "India",
    "Japan",
    "South Korea",
    "Thailand",
    "Vietnam",
    "Indonesia",
    "Malaysia",
    "Singapore",
    "Australia",
    "New Zealand",
    "South Africa",
    "Egypt",
    "United Arab Emirates",
    "Saudi Arabia",
]

CATEGORY_CHOICES_BY_SEGMENT = {
    "AG": [
        "Tractor Front",
        "Tractor Rear",
        "Implement",
        "Harvester Front",
        "Harvester Rear",
        "Flotation",
        "Row Crop",
    ],
    "TBR": [
        "Steer",
        "Drive",
        "Trailer",
        "All-Position",
        "Mixed Service",
    ],
    "PCR": [
        "Touring",
        "UHP (Ultra High Performance)",
        "Winter",
        "All-Season",
        "SUV / CUV",
    ],
    "LT": [
        "Highway",
        "All-Terrain",
        "Mud-Terrain",
        "Commercial Van",
    ],
    "OTR": [
        "Loader / Dozer",
        "Grader",
        "Dump Truck",
        "Crane",
    ],
    "IND": [
        "Forklift",
        "Skid Steer",
        "Port / Terminal",
        "Solid Tire",
    ],
}

RADIAL_BIAS_CHOICES = ["Radial", "Bias"]
SPEED_RATING_CHOICES = [
    "A8", "B", "C", "D", "E", "F", "G",
    "J", "K", "L", "M", "N", "P", "Q",
    "R", "S", "T", "H", "V", "W", "Y"
]

CURRENCY_SYMBOLS = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
}


def extract_price_from_text(text: str):
    """
    Look for the first occurrence of something like:
    $1,234.56 / €900 / £750 in the given text.

    Returns (price_float, currency_code) or (None, None).
    """
    if not text:
        return None, None

    pattern = re.compile(r"(\$|€|£)\s*([0-9][0-9,\.]*)")
    match = pattern.search(text)
    if not match:
        return None, None

    symbol, number_str = match.groups()
    cleaned = number_str.replace(",", "")

    try:
        price_value = float(cleaned)
    except ValueError:
        return None, None

    currency = CURRENCY_SYMBOLS.get(symbol, "USD")
    return price_value, currency


def calculate_tire_cbm(size_string: str):
    """
    Estimate tire volume in CBM from size_string.

    Supports:
      - Metric radial:  480/70R28
      - Imperial bias:  14.9-28

    Returns a float in m³, or None if format isn't recognized.
    """
    if not size_string:
        return None

    s = size_string.replace(" ", "").upper()

    # Metric pattern: 480/70R28
    metric = re.match(r"(\d{3})/(\d{2})R(\d{2})", s)
    if metric:
        width_mm = int(metric.group(1))            # mm
        aspect = int(metric.group(2)) / 100.0      # 70 -> 0.70
        rim_inch = int(metric.group(3))
        rim_mm = rim_inch * 25.4

        sidewall = width_mm * aspect
        diameter_mm = rim_mm + 2 * sidewall

    else:
        # Imperial pattern: 14.9-28 (or 12.4-28, 18.4-30, etc.)
        imperial = re.match(r"(\d{1,2}(\.\d)?)-(\d{2})", s)
        if imperial:
            width_inch = float(imperial.group(1))
            rim_inch = int(imperial.group(3))

            width_mm = width_inch * 25.4
            rim_mm = rim_inch * 25.4

            # Default aspect ratio for bias tires (assumption)
            aspect = 0.85
            sidewall = width_mm * aspect
            diameter_mm = rim_mm + 2 * sidewall
        else:
            # Unsupported / weird format
            return None

    radius_mm = diameter_mm / 2.0

    # Cylinder volume in mm³
    volume_mm3 = math.pi * (radius_mm ** 2) * width_mm

    # Convert to m³
    volume_m3 = volume_mm3 / 1_000_000_000.0

    return round(volume_m3, 3)


# ---------------------------
# DATABASE MODELS
# ---------------------------
class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, nullable=False)
    model_name = Column(String)
    size_string = Column(String, nullable=False)
    segment = Column(String)
    category = Column(String)
    radial_or_bias = Column(String)
    load_index = Column(String)
    speed_rating = Column(String)
    ply_rating = Column(String)

    # Professional cost structure
    currency = Column(String, default="USD")
    exw_price = Column(Float, default=0.0)
    packing_cost = Column(Float, default=0.0)
    tire_weight_kg = Column(Float, default=0.0)
    tire_cbm = Column(Float, default=0.0)
    duty_percent = Column(Float, default=0.0)

    # Source country, default Turkiye
    source_country = Column(String, default="Turkiye")

    competitor_prices = relationship(
        "CompetitorPrice",
        back_populates="product",
        cascade="all, delete-orphan",
    )


class CompetitorPrice(Base):
    __tablename__ = "competitor_prices"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    source_name = Column(String, nullable=False)   # e.g. “Tyres Int.”
    region = Column(String)                        # e.g. “US East”
    competitor_brand = Column(String)
    competitor_model = Column(String)
    competitor_size = Column(String)
    selling_price = Column(Float, default=0.0)
    currency = Column(String, default="USD")
    url = Column(String)
    in_stock = Column(Boolean, default=True)
    notes = Column(String)

    product = relationship("Product", back_populates="competitor_prices")


Base.metadata.create_all(bind=engine)

# ---------------------------
# FASTAPI SETUP
# ---------------------------
app = FastAPI()
templates = Jinja2Templates(directory="templates")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------
# HOME & SIMPLE SIMULATOR
# ---------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return templates.TemplateResponse(
        "home.html",
        {
            "request": request,
            "products": products,
        },
    )


@app.post("/simulate", response_class=HTMLResponse)
def simulate(
    request: Request,
    lassa_exw: float = Form(...),
    freight_total: float = Form(...),
    duty_percent: float = Form(...),
    other_costs: float = Form(0.0),
    target_margin_percent: float = Form(...),
):
    base_cost = lassa_exw + freight_total + other_costs
    duty_amount = base_cost * (duty_percent / 100.0)
    landed_cost = base_cost + duty_amount
    suggested_selling_price = landed_cost * (1 + target_margin_percent / 100.0)

    return templates.TemplateResponse(
        "results.html",
        {
            "request": request,
            "landed_cost": round(landed_cost, 2),
            "suggested_selling_price": round(suggested_selling_price, 2),
        },
    )


# ---------------------------
# PRODUCT CRUD
# ---------------------------
@app.get("/products", response_class=HTMLResponse)
def list_products(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()
    return templates.TemplateResponse(
        "products.html",
        {
            "request": request,
            "products": products,
            "segment_choices": SEGMENT_CHOICES,
            "category_choices_by_segment": CATEGORY_CHOICES_BY_SEGMENT,
            "radial_bias_choices": RADIAL_BIAS_CHOICES,
            "speed_rating_choices": SPEED_RATING_CHOICES,
            "country_choices": COUNTRY_CHOICES,
        },
    )


@app.post("/products")
def create_product(
    request: Request,
    brand: str = Form(...),
    model_name: str = Form(""),
    size_string: str = Form(...),
    segment: str = Form(""),
    category: str = Form(""),
    radial_or_bias: str = Form(""),
    load_index: str = Form(""),
    speed_rating: str = Form(""),
    ply_rating: str = Form(""),
    currency: str = Form("USD"),
    exw_price: float = Form(0.0),
    packing_cost: float = Form(0.0),
    tire_weight_kg: float = Form(0.0),
    tire_cbm: float = Form(0.0),
    duty_percent: float = Form(0.0),
    source_country: str = Form("Turkiye"),
    db: Session = Depends(get_db),
):
    # If CBM not supplied or zero, auto-calculate from size_string
    auto_cbm = calculate_tire_cbm(size_string)
    if (tire_cbm is None or tire_cbm == 0.0) and auto_cbm is not None:
        tire_cbm = auto_cbm

    product = Product(
        brand=brand,
        model_name=model_name,
        size_string=size_string,
        segment=segment,
        category=category,
        radial_or_bias=radial_or_bias,
        load_index=load_index,
        speed_rating=speed_rating,
        ply_rating=ply_rating,
        currency=currency,
        exw_price=exw_price,
        packing_cost=packing_cost,
        tire_weight_kg=tire_weight_kg,
        tire_cbm=tire_cbm,
        duty_percent=duty_percent,
        source_country=source_country or "Turkiye",
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return RedirectResponse(url="/products", status_code=303)


@app.post("/products/import_csv")
def import_products_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Bulk import products from a CSV file.
    """
    raw_bytes = file.file.read()
    try:
        text = raw_bytes.decode("utf-8-sig")
    except Exception:
        text = raw_bytes.decode("utf-8", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))

    created = 0
    skipped = 0

    for row in reader:
        brand = (row.get("brand") or "").strip()
        size_string = (row.get("size_string") or "").strip()

        if not brand or not size_string:
            skipped += 1
            continue

        # Handle CBM from CSV or auto-calc
        raw_cbm = row.get("tire_cbm")
        try:
            tire_cbm_val = float(raw_cbm) if raw_cbm not in (None, "",) else 0.0
        except ValueError:
            tire_cbm_val = 0.0

        if tire_cbm_val == 0.0:
            auto_cbm = calculate_tire_cbm(size_string)
            if auto_cbm is not None:
                tire_cbm_val = auto_cbm

        product = Product(
            brand=brand,
            model_name=(row.get("model_name") or "").strip(),
            size_string=size_string,
            segment=(row.get("segment") or "").strip(),
            category=(row.get("category") or "").strip(),
            radial_or_bias=(row.get("radial_or_bias") or "").strip(),
            load_index=(row.get("load_index") or "").strip(),
            speed_rating=(row.get("speed_rating") or "").strip(),
            ply_rating=(row.get("ply_rating") or "").strip(),
            currency=(row.get("currency") or "USD").strip() or "USD",
            exw_price=float(row.get("exw_price") or 0.0),
            packing_cost=float(row.get("packing_cost") or 0.0),
            tire_weight_kg=float(row.get("tire_weight_kg") or 0.0),
            tire_cbm=tire_cbm_val,
            duty_percent=float(row.get("duty_percent") or 0.0),
            source_country=(row.get("source_country") or "Turkiye").strip() or "Turkiye",
        )

        db.add(product)
        created += 1

    db.commit()
    print(f"CSV import complete: created={created}, skipped={skipped}")
    return RedirectResponse(url="/products", status_code=303)


@app.get("/products/sample_csv")
def download_sample_csv():
    content = """brand,model_name,size_string,segment,category,radial_or_bias,load_index,speed_rating,ply_rating,currency,exw_price,packing_cost,tire_weight_kg,tire_cbm,duty_percent,source_country
Lassa,IMP-700,280/70R16,AG,Tractor Rear,Radial,115,A8,8 PR,USD,100,5,45,0.25,4,Turkiye
Mitas,AC85,380/85R28,AG,Tractor Rear,Radial,142,A8,10 PR,USD,150,6,52,0.30,4,Turkey
BKT,TR135,12.4-28,AG,Tractor Rear,Bias,,A8,8 PR,USD,120,5,48,0.28,4,India
"""
    return StreamingResponse(
        io.StringIO(content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=products_sample.csv"},
    )


@app.get("/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(url="/products", status_code=303)
    return templates.TemplateResponse(
        "edit_product.html",
        {
            "request": request,
            "product": product,
            "country_choices": COUNTRY_CHOICES,
        },
    )


@app.post("/products/{product_id}/edit")
def update_product(
    product_id: int,
    request: Request,
    brand: str = Form(...),
    model_name: str = Form(""),
    size_string: str = Form(...),
    segment: str = Form(""),
    category: str = Form(""),
    radial_or_bias: str = Form(""),
    load_index: str = Form(""),
    speed_rating: str = Form(""),
    ply_rating: str = Form(""),
    currency: str = Form("USD"),
    exw_price: float = Form(0.0),
    packing_cost: float = Form(0.0),
    tire_weight_kg: float = Form(0.0),
    tire_cbm: float = Form(0.0),
    duty_percent: float = Form(0.0),
    source_country: str = Form("Turkiye"),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(url="/products", status_code=303)

    # Auto-calc CBM if zero
    auto_cbm = calculate_tire_cbm(size_string)
    if (tire_cbm is None or tire_cbm == 0.0) and auto_cbm is not None:
        tire_cbm = auto_cbm

    product.brand = brand
    product.model_name = model_name
    product.size_string = size_string
    product.segment = segment
    product.category = category
    product.radial_or_bias = radial_or_bias
    product.load_index = load_index
    product.speed_rating = speed_rating
    product.ply_rating = ply_rating
    product.currency = currency
    product.exw_price = exw_price
    product.packing_cost = packing_cost
    product.tire_weight_kg = tire_weight_kg
    product.tire_cbm = tire_cbm
    product.duty_percent = duty_percent
    product.source_country = source_country or "Turkiye"

    db.commit()
    db.refresh(product)
    return RedirectResponse(url="/products", status_code=303)


@app.post("/products/{product_id}/delete")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        db.delete(product)
        db.commit()
    return RedirectResponse(url="/products", status_code=303)


# ---------------------------
# COMPETITOR CRUD
# ---------------------------
@app.get("/competitors", response_class=HTMLResponse)
def competitors_page(
    request: Request,
    product_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    if product_id is not None:
        product = db.query(Product).filter(Product.id == product_id).first()
        competitors = (
            db.query(CompetitorPrice)
            .filter(CompetitorPrice.product_id == product_id)
            .all()
        )
    else:
        product = None
        competitors = []

    return templates.TemplateResponse(
        "competitors.html",
        {
            "request": request,
            "product": product,
            "competitors": competitors,
        },
    )


@app.post("/competitors")
def create_competitor(
    request: Request,
    product_id: int = Form(...),
    source_name: str = Form(...),
    region: str = Form(""),
    competitor_brand: str = Form(""),
    competitor_model: str = Form(""),
    competitor_size: str = Form(""),
    selling_price: float = Form(0.0),
    currency: str = Form("USD"),
    url: str = Form(""),
    in_stock: bool = Form(True),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    competitor = CompetitorPrice(
        product_id=product_id,
        source_name=source_name,
        region=region,
        competitor_brand=competitor_brand,
        competitor_model=competitor_model,
        competitor_size=competitor_size,
        selling_price=selling_price,
        currency=currency,
        url=url,
        in_stock=in_stock,
        notes=notes,
    )
    db.add(competitor)
    db.commit()

    return RedirectResponse(url=f"/competitors?product_id={product_id}", status_code=303)


@app.get("/competitors/{competitor_id}/edit", response_class=HTMLResponse)
def edit_competitor(
    competitor_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    competitor = (
        db.query(CompetitorPrice)
        .filter(CompetitorPrice.id == competitor_id)
        .first()
    )
    if not competitor:
        return RedirectResponse(url="/products", status_code=303)

    return templates.TemplateResponse(
        "edit_competitor.html",
        {
            "request": request,
            "competitor": competitor,
        },
    )


@app.post("/competitors/{competitor_id}/edit")
def update_competitor(
    competitor_id: int,
    request: Request,
    product_id: int = Form(...),
    source_name: str = Form(...),
    region: str = Form(""),
    competitor_brand: str = Form(""),
    competitor_model: str = Form(""),
    competitor_size: str = Form(""),
    selling_price: float = Form(0.0),
    currency: str = Form("USD"),
    url: str = Form(""),
    in_stock: bool = Form(True),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    competitor = (
        db.query(CompetitorPrice)
        .filter(CompetitorPrice.id == competitor_id)
        .first()
    )
    if not competitor:
        return RedirectResponse(url="/products", status_code=303)

    competitor.product_id = product_id
    competitor.source_name = source_name
    competitor.region = region
    competitor.competitor_brand = competitor_brand
    competitor.competitor_model = competitor_model
    competitor.competitor_size = competitor_size
    competitor.selling_price = selling_price
    competitor.currency = currency
    competitor.url = url
    competitor.in_stock = in_stock
    competitor.notes = notes

    db.commit()

    return RedirectResponse(url=f"/competitors?product_id={product_id}", status_code=303)


@app.post("/competitors/{competitor_id}/delete")
def delete_competitor(
    competitor_id: int,
    db: Session = Depends(get_db),
):
    competitor = (
        db.query(CompetitorPrice)
        .filter(CompetitorPrice.id == competitor_id)
        .first()
    )
    if competitor:
        product_id = competitor.product_id
        db.delete(competitor)
        db.commit()
        return RedirectResponse(url=f"/competitors?product_id={product_id}", status_code=303)
    return RedirectResponse(url="/products", status_code=303)


@app.post("/competitors/import_from_search")
def import_competitor_from_search(
    request: Request,
    product_id: int = Form(...),
    competitor_brand: str = Form(""),
    competitor_model: str = Form(...),
    competitor_size: str = Form(""),
    selling_price: float = Form(...),
    currency: str = Form("USD"),
    url: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse(url="/products", status_code=303)

    if not competitor_size:
        competitor_size = product.size_string

    competitor = CompetitorPrice(
        product_id=product_id,
        source_name="Google Search",
        region="",
        competitor_brand=competitor_brand,
        competitor_model=competitor_model[:200],
        competitor_size=competitor_size,
        selling_price=selling_price,
        currency=currency or (product.currency or "USD"),
        url=url,
        in_stock=True,
        notes=notes[:300],
    )

    db.add(competitor)
    db.commit()
    db.refresh(competitor)

    return RedirectResponse(url=f"/competitors?product_id={product_id}", status_code=303)


# ---------------------------
# OPPORTUNITY ANALYSIS
# ---------------------------
@app.get("/analysis", response_class=HTMLResponse)
def analysis(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).order_by(Product.brand, Product.size_string).all()
    rows = []

    # approximate usable CBM per container
    CBM_20 = 28.0   # adjust later if you want
    CBM_40 = 68.0

    for p in products:
        offers = p.competitor_prices or []
        valid_offers = [o for o in offers if (o.selling_price or 0) > 0]

        if valid_offers:
            best_offer = min(valid_offers, key=lambda o: o.selling_price)
            best_comp_name = best_offer.competitor_brand or best_offer.source_name
            best_comp_region = best_offer.region or ""
            best_price = best_offer.selling_price
            best_currency = best_offer.currency
            offers_count = len(valid_offers)
            any_in_stock = any(o.in_stock for o in valid_offers)
        else:
            best_offer = None
            best_comp_name = None
            best_comp_region = ""
            best_price = None
            best_currency = None
            offers_count = 0
            any_in_stock = False

        factory_cost = (p.exw_price or 0.0) + (p.packing_cost or 0.0)

        profit_per_tire = None
        margin_percent = None
        if best_price is not None and best_price > 0:
            if not best_currency or best_currency == (p.currency or "USD"):
                profit_per_tire = best_price - factory_cost
                if best_price != 0:
                    margin_percent = (profit_per_tire / best_price) * 100.0

        # --- CBM + container units ---
        cbm = p.tire_cbm
        if not cbm or cbm <= 0:
            cbm = calculate_tire_cbm(p.size_string) or 0.0

        units_20 = int(CBM_20 / cbm) if cbm > 0 else 0
        units_40 = int(CBM_40 / cbm) if cbm > 0 else 0

        rows.append(
            {
                "product": p,
                "offers_count": offers_count,
                "best_comp_name": best_comp_name,
                "best_comp_region": best_comp_region,
                "best_currency": best_currency,
                "best_price": best_price,
                "factory_cost": factory_cost,
                "profit_per_tire": profit_per_tire,
                "margin_percent": margin_percent,
                "any_in_stock": any_in_stock,
                "cbm_per_tire": cbm,
                "units_20": units_20,
                "units_40": units_40,
            }
        )

    return templates.TemplateResponse(
        "analysis.html",
        {
            "request": request,
            "rows": rows,
        },
    )



# ---------------------------
# DASHBOARD (CHARTS)
# ---------------------------
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    products = db.query(Product).all()

    # --- BASIC COUNTS ---

    # Products by segment
    segment_counts = Counter(p.segment or "Unspecified" for p in products)

    # Products by source country
    country_counts = Counter(p.source_country or "Unspecified" for p in products)

    # --- AVERAGE EXW PRICE BY SEGMENT ---
    price_sum = defaultdict(float)
    price_count = defaultdict(int)

    for p in products:
        seg = p.segment or "Unspecified"
        if p.exw_price and p.exw_price > 0:
            price_sum[seg] += p.exw_price
            price_count[seg] += 1

    segment_avg_price = {
        seg: (price_sum[seg] / price_count[seg])
        for seg in price_sum
        if price_count[seg] > 0
    }

    # Prepare simple arrays for Chart.js
    segment_labels = list(segment_counts.keys())
    segment_values = list(segment_counts.values())

    country_labels = list(country_counts.keys())
    country_values = list(country_counts.values())

    avg_seg_labels = list(segment_avg_price.keys())
    avg_seg_values = [round(v, 2) for v in segment_avg_price.values()]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "segment_labels_json": json.dumps(segment_labels),
            "segment_values_json": json.dumps(segment_values),
            "country_labels_json": json.dumps(country_labels),
            "country_values_json": json.dumps(country_values),
            "avg_seg_labels_json": json.dumps(avg_seg_labels),
            "avg_seg_values_json": json.dumps(avg_seg_values),
        },
    )


# ---------------------------
# AUTO FETCH PRICES (SCRAPERS)
# ---------------------------
@app.get("/products/{product_id}/auto_fetch_prices", response_class=HTMLResponse)
def auto_fetch_prices(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/products", status_code=303)

    offers = scrape_all_sources(
        size_string=product.size_string,
        segment=product.segment or "",
        brand=product.brand or "",
    )

    priced_offers = [o for o in offers if o.price is not None]

    return templates.TemplateResponse(
        "competitor_scraped_offers.html",
        {
            "request": request,
            "product": product,
            "offers": priced_offers,
        },
    )


# ---------------------------
# AUTO GOOGLE COMPETITOR SEARCH
# ---------------------------
@app.get("/products/{product_id}/find_competitors", response_class=HTMLResponse)
def find_competitors(
    product_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/products", status_code=303)

    query = f"{product.size_string} tractor tire -{product.brand}"

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX,
        "q": query,
        "num": 10,
    }

    response = httpx.get(url, params=params)
    data = response.json()
    items = data.get("items", [])

    return templates.TemplateResponse(
        "competitor_search_results.html",
        {
            "request": request,
            "query": query,
            "results": items,
        },
    )
