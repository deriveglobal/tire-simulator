{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 # app/utils.py\
import re\
from math import pi\
from typing import Optional, Tuple\
\
\
def parse_tire_size(size_string: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:\
    """\
    Try to parse a tire size string and return:\
      (section_width_mm, aspect_ratio, rim_diameter_inch)\
\
    Supports:\
      - Metric radial: 420/85R28, 420/85 R 28\
      - Imperial AG:   18.4-30 (assumes ~80 aspect ratio)\
    Returns (None, None, None) if it can't parse.\
    """\
    if not size_string:\
        return None, None, None\
\
    s = size_string.strip().upper()\
\
    # Pattern 1: metric radial, e.g. "420/85R28" or "420/85 R 28"\
    m = re.match(r"^\\s*(\\d\{3\})\\s*/\\s*(\\d\{2\})\\s*R?\\s*(\\d\{2\})\\s*$", s)\
    if m:\
        width_mm = float(m.group(1))      # 420\
        aspect_ratio = float(m.group(2))  # 85\
        rim_inch = float(m.group(3))      # 28\
        return width_mm, aspect_ratio, rim_inch\
\
    # Pattern 2: imperial AG, e.g. "18.4-30"\
    m = re.match(r"^\\s*(\\d\{2\})\\.(\\d)\\s*-\\s*(\\d\{2\})\\s*$", s)\
    if m:\
        section_inch = float(f"\{m.group(1)\}.\{m.group(2)\}")  # 18.4\
        rim_inch = float(m.group(3))                        # 30\
        # Common AG rule of thumb: aspect ratio ~ 80\
        width_mm = section_inch * 25.4\
        aspect_ratio = 80.0\
        return width_mm, aspect_ratio, rim_inch\
\
    # If nothing matched:\
    return None, None, None\
\
\
def estimate_geometry_and_cbm(size_string: str) -> dict:\
    """\
    Use the parsed size to estimate geometry + volume (CBM) per tire.\
\
    This is a rough cylinder-based approximation with a packing factor.\
    Good enough for planning. You can override later with manual units.\
    """\
    width_mm, aspect_ratio, rim_inch = parse_tire_size(size_string)\
    if width_mm is None:\
        return \{\
            "section_width_mm": None,\
            "aspect_ratio": None,\
            "rim_diameter_inch": None,\
            "overall_diameter_mm": None,\
            "cbm_per_tire": None,\
        \}\
\
    # Overall diameter in mm:\
    overall_diameter_mm = (2 * width_mm * (aspect_ratio / 100.0)) + (rim_inch * 25.4)\
\
    # Approximate volume as a cylinder:\
    radius_m = (overall_diameter_mm / 1000.0) / 2.0\
    height_m = width_mm / 1000.0\
\
    volume_m3 = pi * (radius_m ** 2) * height_m\
\
    # Packing factor for voids / inefficiency:\
    packing_factor = 1.25\
    cbm_per_tire = volume_m3 * packing_factor\
\
    return \{\
        "section_width_mm": width_mm,\
        "aspect_ratio": aspect_ratio,\
        "rim_diameter_inch": rim_inch,\
        "overall_diameter_mm": overall_diameter_mm,\
        "cbm_per_tire": cbm_per_tire,\
    \}\
\
\
def estimate_units_per_container(\
    cbm_per_tire: Optional[float],\
    usable_cbm_20dc: float = 28.0,\
    usable_cbm_40hc: float = 68.0,\
) -> tuple[Optional[int], Optional[int]]:\
    """\
    Very rough estimate of how many tires fit in 20DC and 40HC containers.\
    """\
    if not cbm_per_tire or cbm_per_tire <= 0:\
        return None, None\
\
    units_20 = int(usable_cbm_20dc // cbm_per_tire)\
    units_40 = int(usable_cbm_40hc // cbm_per_tire)\
    return units_20, units_40\
}