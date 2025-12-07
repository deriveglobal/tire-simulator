from sqlalchemy import Column, Integer, String, Float, ForeignKey, Date
from sqlalchemy.orm import relationship
from .db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    # BASIC IDENTITY / CATALOG FIELDS
    brand = Column(String, index=True)              # e.g. "Lassa"
    model_name = Column(String, index=True)         # e.g. "Imperial", pattern name, etc.
    size_string = Column(String, index=True)        # e.g. "420/85R28", "18.4-30"
    segment = Column(String, index=True)            # e.g. "Agricultural", "PCR", "TBR"
    category = Column(String, index=True)           # e.g. "Tractor Rear", "Implement"
    radial_or_bias = Column(String, index=True)     # e.g. "Radial" / "Bias"
    load_index = Column(String, nullable=True)      # e.g. "139A8/B"

    # === GEOMETRY (PARSED / COMPUTED FROM SIZE STRING) ===
    # These are filled by helper functions when you create/import products.
    section_width_mm = Column(Float, nullable=True)     # e.g. 420
    aspect_ratio = Column(Float, nullable=True)         # e.g. 85
    rim_diameter_inch = Column(Float, nullable=True)    # e.g. 28
    overall_diameter_mm = Column(Float, nullable=True)  # computed OD

    # === LOGISTICS: VOLUME & CONTAINER LOADING (ESTIMATED) ===
    # cbm_per_tire_estimated: rough volume including packing factor.
    cbm_per_tire_estimated = Column(Float, nullable=True)

    # Estimated maximum units per container based on geometry/CBM.
    units_per_20dc_estimated = Column(Integer, nullable=True)
    units_per_40hc_estimated = Column(Integer, nullable=True)

    # === LOGISTICS: MANUAL OVERRIDES ===
    # When you have REAL loading data from shipments, set these.
    # Your cost calculations should prefer manual values if present.
    units_per_20dc_manual = Column(Integer, nullable=True)
    units_per_40hc_manual = Column(Integer, nullable=True)

    # === RELATIONSHIPS ===
    competitor_prices = relationship(
        "CompetitorPrice",
        back_populates="product",
        cascade="all, delete-orphan",
    )

    # === CONVENIENCE PROPERTIES (NOT COLUMNS) ===
    @property
    def effective_units_per_20dc(self) -> int | None:
        """
        Use manual override if available, otherwise fall back to estimate.
        """
        if self.units_per_20dc_manual is not None:
            return self.units_per_20dc_manual
        return self.units_per_20dc_estimated

    @property
    def effective_units_per_40hc(self) -> int | None:
        """
        Use manual override if available, otherwise fall back to estimate.
        """
        if self.units_per_40hc_manual is not None:
            return self.units_per_40hc_manual
        return self.units_per_40hc_estimated


class CompetitorPrice(Base):
    __tablename__ = "competitor_prices"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), index=True)

    competitor_name = Column(String, index=True)    # e.g. "Firestone", "BKT", "Dealer A"
    price_usd = Column(Float, nullable=False)       # normalized to USD for now
    source = Column(String, nullable=True)          # URL or "scraped", "manual"
    observed_at = Column(Date, nullable=True)       # date when this price was observed

    product = relationship("Product", back_populates="competitor_prices")
