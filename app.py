from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html import escape
from io import BytesIO
import hmac
import mimetypes
import os
import re
import time    

from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st
from requests.auth import HTTPBasicAuth, HTTPDigestAuth


# =============================================================================
# Configuration
# =============================================================================

APP_TITLE = "Performance KPIs"
APP_DIR = Path(__file__).resolve().parent
DEFAULT_BACKGROUND_IMAGE = APP_DIR / ""
ODATA_ENDPOINT = "https://online.marorka.com/Odata/v1/ODataService.svc/ReportData"
MAX_ODATA_PAGES = 250
API_CACHE_TTL_SECONDS = 21600  # 6 hours; KPI filters use local data and do not refetch.
UI_DATE_INPUT_FORMAT = "DD/MM/YYYY"
DISPLAY_DATETIME_FORMAT = "%d/%m/%Y %H:%M"
API_FULL_START_DATE = date(2026, 1, 1)
TABLE_PREVIEW_ROW_LIMIT = 500
CALCULATION_SCHEMA_VERSION = "2026-06-25-dynamic-lub-oil-consumption-sample-v1"



EXCLUDED_REPORT_TYPES = [
    "Intake Report",
    "Fuel Change Report",
]

SOURCE_COLUMNS = [
    "ReportId",
    "ShipName",
    "ReportType",
    "StartDateTimeGMT",
    "EndDateTimeGMT",
    "LapTime",
    "StateName",
    "ValueDescription",
    "ReportedValue",
]

# Required API values only. The API request remains simple; these are applied locally
# after the data is downloaded, mimicking the stable working reefer app pattern.
VALUE_ALIASES = {
    "Engine Distance [nm]": [
        "Engine Distance [nm]",
    ],
    "Distance Over Ground [nm]": [
        "Distance Over Ground [nm]",
    ],
    "Steaming Time Since Last Report [hh:mm]": [
        "Steaming Time Since Last Report [hh:mm]",
        "Steaming Time Since Last Report",
    ],
    "ME Load [%MCR]": [
        "ME Load [%MCR]",
        "ME Load [% MCR]",
    ],
    "Power from Torque Meter [kW]": [
        "Power from Torque Meter [kW]",
        "Total Shaft Power [kW] (kW)",
        "Total Shaft Power [kW]",
    ],
    "Total DG Power [kW]": [
        "Total DG Power [kW]",
        "Total DG Power [kW] (kW)",
        "Total Daily Average Power [kW]",
    ],
    "DG1 Running Hours [hh:mm]": [
        "DG1 Running Hours [hh:mm]",
        "DG 1 Running Hours [hh:mm]",
        "DG1 Running Hours",
        "DG 1 Running Hours",
        "Diesel Generator 1 Running Hours [hh:mm]",
        "Diesel Generator 1 Running Hours",
    ],
    "DG2 Running Hours [hh:mm]": [
        "DG2 Running Hours [hh:mm]",
        "DG 2 Running Hours [hh:mm]",
        "DG2 Running Hours",
        "DG 2 Running Hours",
        "Diesel Generator 2 Running Hours [hh:mm]",
        "Diesel Generator 2 Running Hours",
    ],
    "DG3 Running Hours [hh:mm]": [
        "DG3 Running Hours [hh:mm]",
        "DG 3 Running Hours [hh:mm]",
        "DG3 Running Hours",
        "DG 3 Running Hours",
        "Diesel Generator 3 Running Hours [hh:mm]",
        "Diesel Generator 3 Running Hours",
    ],
    "DG4 Running Hours [hh:mm]": [
        "DG4 Running Hours [hh:mm]",
        "DG 4 Running Hours [hh:mm]",
        "DG4 Running Hours",
        "DG 4 Running Hours",
        "Diesel Generator 4 Running Hours [hh:mm]",
        "Diesel Generator 4 Running Hours",
    ],
    "MELO ROB [ltr]": ["MELO ROB [ltr]"],
    "MELO Received [ltr]": ["MELO Received [ltr]"],
    "Cylinder Oil 1 ROB [ltr]": ["Cylinder Oil 1 ROB [ltr]"],
    "Cylinder Oil 1 Received [ltr]": ["Cylinder Oil 1 Received [ltr]"],
    "Cylinder Oil 2 ROB [ltr]": ["Cylinder Oil 2 ROB [ltr]"],
    "Cylinder Oil 2 Received [ltr]": ["Cylinder Oil 2 Received [ltr]"],
    "GELO ROB [ltr]": [
        "GELO ROB [ltr]",
        "GELO Grade ROB [ltr]",
    ],
    "GELO Received [ltr]": ["GELO Received [ltr]"],
    "Main Engine - HSHFO": ["Main Engine - HSHFO"],
    "Main Engine - HSLFO": ["Main Engine - HSLFO"],
    "Main Engine - MGO": ["Main Engine - MGO"],
    "Main Engine - ULSHFO": ["Main Engine - ULSHFO"],
    "Main Engine - ULSLFO": ["Main Engine - ULSLFO"],
    "Main Engine - VLSHFO": ["Main Engine - VLSHFO"],
    "Main Engine - VLSLFO": ["Main Engine - VLSLFO"],
    "Boiler - HSHFO": ["Boiler - HSHFO"],
    "Boiler - HSLFO": ["Boiler - HSLFO"],
    "Boiler - MGO": ["Boiler - MGO"],
    "Boiler - ULSHFO": ["Boiler - ULSHFO"],
    "Boiler - ULSLFO": ["Boiler - ULSLFO"],
    "Boiler - VLSHFO": ["Boiler - VLSHFO"],
    "Boiler - VLSLFO": ["Boiler - VLSLFO"],
}

ME_FUEL_COLUMNS = [
    "Main Engine - HSHFO",
    "Main Engine - HSLFO",
    "Main Engine - MGO",
    "Main Engine - ULSHFO",
    "Main Engine - ULSLFO",
    "Main Engine - VLSHFO",
    "Main Engine - VLSLFO",
]

BOILER_FUEL_COLUMNS = [
    "Boiler - HSHFO",
    "Boiler - HSLFO",
    "Boiler - MGO",
    "Boiler - ULSHFO",
    "Boiler - ULSLFO",
    "Boiler - VLSHFO",
    "Boiler - VLSLFO",
]

MELO_DENSITY_KG_PER_LTR = 0.89
CYLO_DENSITY_KG_PER_LTR = 0.93
GELO_DENSITY_KG_PER_LTR = 0.89

MELO_COLUMNS = [
    "MELO ROB [ltr]",
    "MELO Received [ltr]",
]

CYLINDER_OIL_COLUMNS = [
    "Cylinder Oil 1 ROB [ltr]",
    "Cylinder Oil 1 Received [ltr]",
    "Cylinder Oil 2 ROB [ltr]",
    "Cylinder Oil 2 Received [ltr]",
]

GELO_COLUMNS = [
    "GELO ROB [ltr]",
    "GELO Received [ltr]",
]

DG_RUNNING_HOUR_COLUMNS = [
    "DG1 Running Hours [hh:mm]",
    "DG2 Running Hours [hh:mm]",
    "DG3 Running Hours [hh:mm]",
    "DG4 Running Hours [hh:mm]",
]

DISPLAY_COLUMNS = [
    "ShipName",
    "ReportType",
    "StartDateTimeGMT",
    "EndDateTimeGMT",
    "LapTime",
    "Steaming Time Since Last Report [hh:mm]",
    "StateName",
    "Engine Distance [nm]",
    "Distance Over Ground [nm]",
    "Calculated Slip",
    "ME Load [%MCR]",
    "Power from Torque Meter [kW]",
    "Consumption ME 24 Hours [MT]",
    "SFOC [g/kWh]",
    "Boiler Sum",
    "Total DG Power [kW]",
    "DG1 Running Hours [hh:mm]",
    "DG2 Running Hours [hh:mm]",
    "DG3 Running Hours [hh:mm]",
    "DG4 Running Hours [hh:mm]",
    "Total DG Running Hours [hh:mm]",
    "MELO ROB [ltr]",
    "MELO Received [ltr]",
    "MELO Consumption [ltr]",
    "MELO Consumption [ltr/day]",
    "Cylinder Oil 1 ROB [ltr]",
    "Cylinder Oil 1 Received [ltr]",
    "Cylinder Oil 2 ROB [ltr]",
    "Cylinder Oil 2 Received [ltr]",
    "Cylinder Oil Consumption [ltr]",
    "CYLO SLOC [g/kWh]",
    "GELO ROB [ltr]",
    "GELO Received [ltr]",
    "GELO Consumption [ltr]",
    "GELO Consumption [ltr/day]",
]

VESSEL_GROUPS = {
    "Fleet 1": ["ATETI", "CMA CGM THALASSA", "CZECH", "DOLPHIN II", "GSL CHRISTEL ELISABETH", "GSL VINIA", "ORCA I", "MYNY", "SYDNEY EXPRESS"],
    "Fleet 2": ["AGIOS DIMITRIOS", "CONSTANTINOS P II", "ELENI T", "MAIRA", "MELINA", "NEWYORKER", "NIKOLAS", "TORRANCE"],
    "Fleet 3": ["BREMERHAVEN EXPRESS", "CMA CGM ALCAZAR", "GSL ALICE", "GSL CHATEAU D'IF", "GSL ELEFTHERIA", "GSL MAREN", "GSL MELINA", "ISTANBUL EXPRESS"],
    "Fleet 4": ["ANTHEA Y", "COLOMBIA EXPRESS", "COSTA RICA EXPRESS", "JAMAICA EXPRESS", "MEXICO EXPRESS", "NICARAGUA EXPRESS", "PANAMA EXPRESS", "ZIM NORFOLK", "ZIM XIAMEN"],
    "Fleet 9": ["CMA CGM AMERICA", "CMA CGM SAMBHAR", "GSL ELENI", "GSL GRANIA", "GSL KALLIOPI", "GSL NINGBO", "MSC QINGDAO", "MSC TIANJIN"],
    "Fleet 10": ["CAPTAIN THANASIS I", "CMA CGM JAMAICA", "GSL CHRISTEN", "GSL NICOLETTA", "GSL VALERIE", "JULIE", "KUMASI", "MANET"],
    "Fleet 11": ["ATHENA", "EPAMINONDAS", "IAN H", "MARIANNA I", "MSC ROMA", "TINA I"],
    "Fleet 12": ["GSL DOROTHEA", "GSL KITHIRA", "GSL MARIA", "GSL MELITA", "GSL SYROS", "GSL TEGEA", "GSL TINOS", "GSL TRIPOLI"],
    "Fleet 14": ["GSL CHLOE", "GSL ELIZABETH", "GSL LALO", "GSL MAMITSA", "GSL MERCER", "GSL ROSSI", "GSL SUSAN", "TONSBERG"],
    "Fleet 15": ["GSL ALEXANDRA", "GSL ARCADIA", "GSL EFFIE", "GSL LYDIA", "GSL MYNY", "GSL SOFIA", "GSL VIOLETTA", "KOSTAS K", "MARIA Y"],
}

VESSEL_OPTIONS = sorted({v for vessels in VESSEL_GROUPS.values() for v in vessels})

# Default KPI filters matching the Power Query reporting logic.
# These are applied on first load only; if the user edits them, their choices
# stay in session_state across API refreshes, vessel changes, and date changes.
DEFAULT_PERFORMANCE_FILTER_COLUMNS = [
    "StateName",
    "Steaming Time Since Last Report [hh:mm]",
    "ME Load [%MCR]",
    "Calculated Slip",
    "SFOC [g/kWh]",
]

DEFAULT_BOILER_FILTER_COLUMNS = [
    "StateName",
    "Steaming Time Since Last Report [hh:mm]",
]

DEFAULT_PERFORMANCE_NUMERIC_FILTERS = {
    "Steaming Time Since Last Report [hh:mm]": {"min": "5", "max": "", "min_op": ">", "max_op": "<="},
    "ME Load [%MCR]": {"min": "0.10", "max": "1", "min_op": ">", "max_op": "<="},
    "Calculated Slip": {"min": "-0.15", "max": "0.35", "min_op": ">=", "max_op": "<="},
    "SFOC [g/kWh]": {"min": "150", "max": "250", "min_op": ">=", "max_op": "<="},
}

DEFAULT_BOILER_NUMERIC_FILTERS = {
    "Steaming Time Since Last Report [hh:mm]": {"min": "5", "max": "", "min_op": ">", "max_op": "<="},
}

DEFAULT_PERFORMANCE_CATEGORICAL_FILTERS = {
    "StateName": ["Sea Passage"],
}

DEFAULT_BOILER_CATEGORICAL_FILTERS = {
    "StateName": ["Sea Passage"],
}


st.set_page_config(page_title=APP_TITLE, layout="wide")


# =============================================================================
# Styling
# =============================================================================


def apply_custom_css() -> None:
    background_image_url = dashboard_background_image_url()
    background_image_layer = dashboard_background_image_layer(background_image_url)
    hero_background = dashboard_hero_background(has_background_image=bool(background_image_url))
    hero_backdrop_filter = dashboard_hero_backdrop_filter(has_background_image=bool(background_image_url))
    hero_box_shadow = dashboard_hero_box_shadow(has_background_image=bool(background_image_url))
    metric_background = dashboard_metric_background(has_background_image=bool(background_image_url))
    metric_backdrop_filter = dashboard_metric_backdrop_filter(has_background_image=bool(background_image_url))
    metric_box_shadow = dashboard_metric_box_shadow(has_background_image=bool(background_image_url))
    st.markdown(
        """
        <style>
        :root {
            --bg: #050505;
            --panel: #0F0F0B;
            --panel-soft: #18150C;
            --border: rgba(245, 200, 75, 0.24);
            --border-strong: rgba(255, 216, 74, 0.70);
            --text-soft: #B8B29F;
            --cyan: #FFD84A;
            --green: #FFB000;
            --red-muted: rgba(207, 95, 95, 0.24);
        }

        .stApp {
            background:
                __BACKGROUND_IMAGE_LAYER__
                radial-gradient(circle at 18% 10%, rgba(255, 216, 74, 0.11), transparent 31rem),
                radial-gradient(circle at 86% 8%, rgba(255, 176, 0, 0.08), transparent 28rem),
                linear-gradient(180deg, rgba(255, 216, 74, 0.035), transparent 19rem),
                var(--bg);
            background-position: center center;
            background-size: cover;
            background-attachment: fixed;
        }

        header[data-testid="stHeader"] {
            background: transparent !important;
            border-bottom: 0 !important;
            box-shadow: none !important;
            backdrop-filter: none;
        }

        header[data-testid="stHeader"] > div {
            background: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
        }

        div[data-testid="stToolbar"] {
            background: transparent !important;
        }

        div[data-testid="stDecoration"] {
            background: transparent !important;
            height: 0 !important;
        }

        div[data-testid="stAlert"],
        div[data-testid="stAlert"] > div,
        div[data-testid="stAlert"] [role="alert"],
        div[data-testid="stAlertContentInfo"],
        div[data-testid="stAlertContentWarning"],
        div[data-testid="stAlertContentError"],
        div[data-testid="stAlertContentSuccess"] {
            background: transparent !important;
            background-color: transparent !important;
            background-image: none !important;
            border: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            color: #FFFBEA !important;
            backdrop-filter: none;
        }

        div[data-testid="stAlert"] {
            padding-left: 0 !important;
            padding-right: 0 !important;
        }

        div[data-testid="stAlert"] * {
            background: transparent !important;
            background-color: transparent !important;
            background-image: none !important;
            border: 0 !important;
            box-shadow: none !important;
        }

        div[data-testid="stAlert"] svg {
            display: none !important;
        }

        div[data-testid="stAlert"] div,
        div[data-testid="stAlert"] p {
            color: #FFFBEA !important;
            font-weight: 700 !important;
            text-shadow: 0 2px 12px rgba(0,0,0,0.92);
        }

        .block-container {
            padding-top: 2.15rem;
            padding-bottom: 3rem;
            max-width: 1240px;
        }

        section[data-testid="stSidebar"] {
            background:
                radial-gradient(circle at top left, rgba(255, 216, 74, 0.08), transparent 18rem),
                linear-gradient(180deg, #121008 0%, #050505 100%);
            border-right: 1px solid var(--border);
        }

        section[data-testid="stSidebar"] > div {
            padding-bottom: 8rem !important;
        }

        section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 0.7rem;
        }

        section[data-testid="stSidebar"] div[data-baseweb="select"] > div {
            overflow: visible !important;
        }

        section[data-testid="stSidebar"] [data-testid="stExpander"] {
            margin-bottom: 0.45rem;
        }

        section[data-testid="stSidebar"] label {
            color: #F5EFD8 !important;
            font-weight: 700 !important;
        }

        /* Inputs: calm by default; one homogeneous gold outline only on focus. */
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div {
            background-color: rgba(13, 13, 9, 0.88) !important;
            border: 1px solid rgba(255, 216, 74, 0.16) !important;
            border-radius: 14px !important;
            box-shadow: none !important;
            outline: none !important;
            overflow: hidden !important;
            transition: border-color 140ms ease, box-shadow 140ms ease, background-color 140ms ease !important;
        }

        /* Keep the actual inner input flat so BaseWeb does not draw a second rectangle. */
        div[data-baseweb="input"] input,
        [data-testid="stTextInput"] input,
        [data-testid="stDateInput"] input,
        textarea {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            box-shadow: none !important;
            outline: none !important;
            caret-color: #FFD84A !important;
        }

        div[data-baseweb="select"] > div:hover,
        div[data-baseweb="input"] > div:hover {
            border-color: rgba(255, 216, 74, 0.24) !important;
            box-shadow: none !important;
        }

        div[data-baseweb="select"] > div:focus-within,
        div[data-baseweb="input"] > div:focus-within,
        div[data-baseweb="input"]:focus-within > div {
            border-color: rgba(255, 216, 74, 0.88) !important;
            box-shadow: 0 0 0 1px rgba(255, 216, 74, 0.64) !important;
            outline: none !important;
        }

        div[data-baseweb="input"] input:focus,
        div[data-baseweb="input"] input:focus-visible,
        [data-testid="stTextInput"] input:focus,
        [data-testid="stTextInput"] input:focus-visible,
        [data-testid="stDateInput"] input:focus,
        [data-testid="stDateInput"] input:focus-visible,
        textarea:focus,
        textarea:focus-visible {
            border: 0 !important;
            outline: none !important;
            box-shadow: none !important;
        }

        /* Make the password-eye/button area part of the same input surface. */
        div[data-baseweb="input"] button,
        [data-testid="stTextInput"] button,
        div[data-baseweb="input"] [role="button"],
        [data-testid="stTextInput"] [role="button"] {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-left: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            outline: none !important;
            color: #FFF7CC !important;
        }

        div[data-baseweb="input"] button:focus,
        div[data-baseweb="input"] button:focus-visible,
        [data-testid="stTextInput"] button:focus,
        [data-testid="stTextInput"] button:focus-visible,
        div[data-baseweb="input"] [role="button"]:focus,
        div[data-baseweb="input"] [role="button"]:focus-visible,
        [data-testid="stTextInput"] [role="button"]:focus,
        [data-testid="stTextInput"] [role="button"]:focus-visible {
            border: 0 !important;
            outline: none !important;
            box-shadow: none !important;
        }

        /* Suppress Streamlit/BaseWeb validation rings without adding a second outline. */
        div[data-baseweb="input"] > div[aria-invalid="true"],
        div[data-baseweb="input"][aria-invalid="true"] > div,
        div[data-baseweb="input"] > div[data-invalid="true"],
        div[data-baseweb="input"][data-invalid="true"] > div,
        [data-testid="stTextInput"] [aria-invalid="true"],
        [data-testid="stDateInput"] [aria-invalid="true"] {
            border-color: rgba(255, 216, 74, 0.18) !important;
            box-shadow: none !important;
            outline: none !important;
        }

        div[data-baseweb="input"] > div[aria-invalid="true"]:focus-within,
        div[data-baseweb="input"][aria-invalid="true"] > div:focus-within,
        div[data-baseweb="input"] > div[data-invalid="true"]:focus-within,
        div[data-baseweb="input"][data-invalid="true"] > div:focus-within,
        [data-testid="stTextInput"] [aria-invalid="true"]:focus-within,
        [data-testid="stDateInput"] [aria-invalid="true"]:focus-within {
            border-color: rgba(255, 216, 74, 0.88) !important;
            box-shadow: 0 0 0 1px rgba(255, 216, 74, 0.64) !important;
            outline: none !important;
        }

        div[data-baseweb="input"],
        div[data-baseweb="input"] *,
        [data-testid="stTextInput"],
        [data-testid="stTextInput"] *,
        [data-testid="stDateInput"],
        [data-testid="stDateInput"] * {
            --focus-color: #FFD84A !important;
            --input-border-color: rgba(255, 216, 74, 0.18) !important;
            --error-color: #FFD84A !important;
            outline-color: transparent !important;
        }

        div[data-baseweb="input"] svg,
        [data-testid="stTextInput"] svg {
            color: #FFF7CC !important;
        }

        [data-baseweb="tag"] {
            background: linear-gradient(135deg, rgba(255, 216, 74, 0.22), rgba(255, 176, 0, 0.14)) !important;
            border: 1px solid rgba(255, 216, 74, 0.38) !important;
            color: #FFF7CC !important;
            border-radius: 999px !important;
        }
        [data-baseweb="tag"] span { color: #FFF7CC !important; }
        [data-baseweb="tag"] svg { color: #FFF7CC !important; }

        .dashboard-hero {
            padding: 1.35rem 1.55rem;
            border: 1px solid rgba(255, 216, 74, 0.30);
            border-radius: 8px;
            background: __HERO_BACKGROUND__;
            box-shadow: __HERO_BOX_SHADOW__;
            backdrop-filter: __HERO_BACKDROP_FILTER__;
            margin-bottom: 0.85rem;
        }

        .eyebrow {
            color: var(--cyan);
            text-transform: uppercase;
            letter-spacing: 0.16em;
            font-size: 0.78rem;
            font-weight: 800;
            margin-bottom: 0.35rem;
        }

        .dashboard-title {
            font-size: clamp(2.05rem, 3vw, 3.1rem);
            line-height: 1.02;
            font-weight: 900;
            color: #FFFBEA;
            margin: 0;
            text-shadow: 0 3px 16px rgba(0,0,0,0.88);
        }

        .dashboard-subtitle {
            color: var(--text-soft);
            font-size: 1rem;
            margin-top: 0.8rem;
            text-shadow: 0 2px 10px rgba(0,0,0,0.82);
        }

        .section-title {
            font-size: 1.45rem;
            font-weight: 850;
            color: #FFFBEA;
            margin: 1.25rem 0 0.55rem 0;
        }

        .section-note {
            color: var(--text-soft);
            font-size: 0.92rem;
            font-weight: 650;
            margin: -0.15rem 0 1rem 0;
        }

        div[data-testid="stMetric"] {
            position: relative;
            background: __METRIC_BACKGROUND__ !important;
            border: 1px solid rgba(255, 216, 74, 0.56) !important;
            border-radius: 20px !important;
            padding: 1.05rem 1.1rem !important;
            box-shadow: __METRIC_BOX_SHADOW__ !important;
            backdrop-filter: __METRIC_BACKDROP_FILTER__;
            min-height: 124px;
            overflow: hidden;
        }

        .kpi-grid {
            display: grid;
            gap: 1rem;
            margin: 0.7rem 0 0.95rem 0;
        }

        .kpi-grid-four {
            grid-template-columns: repeat(4, minmax(0, 1fr));
        }

        .kpi-grid-three {
            grid-template-columns: repeat(3, minmax(0, 1fr));
        }

        .kpi-card {
            position: relative;
            min-height: 112px;
            padding: 1.05rem 1.1rem;
            border: 1px solid var(--border-strong);
            border-radius: 8px;
            background:
                linear-gradient(135deg, rgba(255, 216, 74, 0.10), rgba(255, 176, 0, 0.035) 42%, rgba(5, 5, 5, 0.94)),
                linear-gradient(180deg, rgba(25, 22, 12, 0.98), rgba(9, 9, 6, 0.98));
            box-shadow: 0 18px 42px rgba(0,0,0,0.42), 0 0 24px rgba(255,176,0,0.08), inset 0 1px 0 rgba(255,216,74,0.16);
            overflow: hidden;
        }

        .kpi-card::before {
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            background: radial-gradient(circle at 18% 12%, rgba(255,216,74,0.10), transparent 12rem);
        }

        .kpi-label {
            position: relative;
            color: #E8DDAF;
            font-size: 0.82rem;
            font-weight: 800;
            line-height: 1.25;
            margin-bottom: 0.42rem;
        }

        .kpi-value {
            position: relative;
            color: #FFFBEA;
            font-size: clamp(1.9rem, 2.5vw, 2.7rem);
            line-height: 1;
            font-weight: 950;
            letter-spacing: 0;
            text-shadow: 0 3px 18px rgba(0,0,0,0.98);
            overflow-wrap: anywhere;
        }

        .kpi-footnote {
            position: relative;
            color: #B8B29F;
            font-size: 0.78rem;
            font-weight: 650;
            margin-top: 0.65rem;
        }

        .support-card {
            min-height: 96px;
            padding: 0.92rem 1rem;
            border: 1px solid rgba(255, 216, 74, 0.18);
            border-radius: 8px;
            background: rgba(15, 14, 9, 0.82);
            box-shadow: inset 0 1px 0 rgba(255,216,74,0.10);
        }

        .support-row {
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.16rem 0;
        }

        .support-label {
            color: #B8B29F;
            font-size: 0.79rem;
            font-weight: 700;
            line-height: 1.25;
        }

        .support-value {
            color: #FFD84A;
            font-size: 0.86rem;
            font-weight: 850;
            text-align: right;
            white-space: nowrap;
        }

        .sloc-card {
            min-height: 202px;
            padding: 1.08rem;
        }

        .sloc-detail-panel {
            position: relative;
            margin-top: 1rem;
            padding: 0.8rem 0.92rem;
            border: 1px solid rgba(255, 216, 74, 0.18);
            border-radius: 8px;
            background: rgba(7, 7, 5, 0.46);
        }

        .sloc-detail-row {
            display: grid;
            grid-template-columns: 0.85rem 1fr auto;
            gap: 0.55rem;
            align-items: baseline;
            padding: 0.25rem 0;
        }

        .sloc-dot {
            width: 0.42rem;
            height: 0.42rem;
            border-radius: 99px;
            background: #FFD84A;
            box-shadow: 0 0 14px rgba(255, 216, 74, 0.65);
            margin-top: 0.28rem;
        }

        .sloc-detail-label {
            color: #FFD84A;
            font-size: 0.80rem;
            font-weight: 800;
            line-height: 1.25;
        }

        .sloc-detail-value {
            color: #FFFBEA;
            font-size: 0.82rem;
            font-weight: 780;
            text-align: right;
            white-space: nowrap;
        }

        @media (max-width: 1100px) {
            .kpi-grid-four,
            .kpi-grid-three {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }

        @media (max-width: 760px) {
            .kpi-grid-four,
            .kpi-grid-three {
                grid-template-columns: 1fr;
            }
        }

        div[data-testid="stMetric"]::before {
            content: "";
            position: absolute;
            top: 0;
            left: 1rem;
            right: 1rem;
            height: 2px;
            background: linear-gradient(90deg, rgba(255,216,74,0), rgba(255,216,74,0.92), rgba(255,176,0,0));
        }

        div[data-testid="stMetricLabel"] p {
            color: #F5EFD8 !important;
            font-weight: 800 !important;
            font-size: 0.82rem !important;
            line-height: 1.25 !important;
            text-shadow: 0 2px 12px rgba(0,0,0,0.96), 0 0 18px rgba(0,0,0,0.70);
        }

        div[data-testid="stMetricValue"] {
            color: #FFFBEA !important;
            font-size: clamp(1.85rem, 2.2vw, 2.45rem) !important;
            line-height: 1 !important;
            font-weight: 950 !important;
            letter-spacing: 0 !important;
            text-shadow: 0 3px 18px rgba(0,0,0,0.98), 0 0 22px rgba(0,0,0,0.78);
            white-space: normal !important;
            overflow-wrap: anywhere !important;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--border);
            border-radius: 18px;
            overflow: hidden;
            box-shadow: 0 14px 36px rgba(0,0,0,0.30);
        }

        button[data-baseweb="tab"] {
            color: #CFC6A5 !important;
            font-weight: 750 !important;
        }

        button[data-baseweb="tab"][aria-selected="true"] {
            color: #FFD84A !important;
        }

        div[data-baseweb="tab-highlight"] {
            background-color: #FFD84A !important;
        }

        .stDownloadButton button, .stButton button {
            border-radius: 8px !important;
            border: 1px solid rgba(255, 216, 74, 0.45) !important;
            background: linear-gradient(135deg, rgba(255, 216, 74, 0.98), rgba(255, 176, 0, 0.86)) !important;
            color: #121008 !important;
            font-weight: 850 !important;
        }
        
        /* Sidebar refresh button compact sizing */
        section[data-testid="stSidebar"] .stButton button {
            width: auto !important;
            min-width: 145px !important;
            max-width: 165px !important;
        
            padding: 0.45rem 0.85rem !important;
            font-size: 0.90rem !important;
            min-height: 38px !important;
        
            margin-bottom: 0.85rem !important;
        }


        /* Final unified input styling: one calm surface, one yellow focus line, no orange/red rings. */
        :root {
            --mn-input-bg: rgba(13, 13, 9, 0.90);
            --mn-input-border: rgba(255, 216, 74, 0.18);
            --mn-input-border-hover: rgba(255, 216, 74, 0.28);
            --mn-input-border-focus: rgba(255, 216, 74, 0.92);
        }

        /* Put the single visible border on the BaseWeb input shell. */
        div[data-baseweb="input"],
        [data-testid="stTextInput"] div[data-baseweb="input"],
        [data-testid="stDateInput"] div[data-baseweb="input"],
        [data-testid="stNumberInput"] div[data-baseweb="input"] {
            background: var(--mn-input-bg) !important;
            background-color: var(--mn-input-bg) !important;
            border: 1px solid var(--mn-input-border) !important;
            border-radius: 14px !important;
            box-shadow: none !important;
            outline: none !important;
            overflow: hidden !important;
            transition: border-color 140ms ease, background-color 140ms ease !important;
        }

        div[data-baseweb="input"]:hover,
        [data-testid="stTextInput"] div[data-baseweb="input"]:hover,
        [data-testid="stDateInput"] div[data-baseweb="input"]:hover,
        [data-testid="stNumberInput"] div[data-baseweb="input"]:hover {
            border-color: var(--mn-input-border-hover) !important;
            box-shadow: none !important;
        }

        div[data-baseweb="input"]:focus-within,
        div[data-baseweb="input"]:has(input:focus),
        div[data-baseweb="input"]:has(input:focus-visible),
        [data-testid="stTextInput"] div[data-baseweb="input"]:focus-within,
        [data-testid="stDateInput"] div[data-baseweb="input"]:focus-within,
        [data-testid="stNumberInput"] div[data-baseweb="input"]:focus-within {
            border-color: var(--mn-input-border-focus) !important;
            box-shadow: none !important;
            outline: none !important;
        }

        /* Remove every inner rectangle so the field reads as one homogeneous tab. */
        div[data-baseweb="input"] > div,
        div[data-baseweb="input"] > div > div,
        div[data-baseweb="input"] > div > div > div,
        div[data-baseweb="input"] [data-baseweb="base-input"],
        div[data-baseweb="input"] [data-testid="stBaseInput"],
        [data-testid="stTextInput"] div[data-baseweb="input"] > div,
        [data-testid="stDateInput"] div[data-baseweb="input"] > div,
        [data-testid="stNumberInput"] div[data-baseweb="input"] > div {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-color: transparent !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            outline: none !important;
        }

        div[data-baseweb="input"] input,
        div[data-baseweb="input"] input:hover,
        div[data-baseweb="input"] input:focus,
        div[data-baseweb="input"] input:focus-visible,
        div[data-baseweb="input"] input:invalid,
        div[data-baseweb="input"] input:user-invalid,
        [data-testid="stTextInput"] input,
        [data-testid="stDateInput"] input,
        [data-testid="stNumberInput"] input {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-color: transparent !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            outline: none !important;
            caret-color: #FFD84A !important;
        }

        /* Make the password eye area the same surface as the input; no black patch and no separate outline. */
        div[data-baseweb="input"] button,
        div[data-baseweb="input"] button:hover,
        div[data-baseweb="input"] button:focus,
        div[data-baseweb="input"] button:focus-visible,
        div[data-baseweb="input"] [role="button"],
        div[data-baseweb="input"] [role="button"]:hover,
        div[data-baseweb="input"] [role="button"]:focus,
        div[data-baseweb="input"] [role="button"]:focus-visible,
        div[data-baseweb="input"] svg,
        [data-testid="stTextInput"] button,
        [data-testid="stTextInput"] [role="button"] {
            background: transparent !important;
            background-color: transparent !important;
            border: 0 !important;
            border-left: 0 !important;
            border-radius: 0 !important;
            box-shadow: none !important;
            outline: none !important;
            color: #FFF7CC !important;
        }

        /* Streamlit/BaseWeb invalid states sometimes inject orange/red borders; force them back to theme. */
        div[data-baseweb="input"][aria-invalid="true"],
        div[data-baseweb="input"][data-invalid="true"],
        div[data-baseweb="input"]:has(input[aria-invalid="true"]),
        div[data-baseweb="input"]:has(input:invalid),
        [data-testid="stTextInput"] div[aria-invalid="true"],
        [data-testid="stDateInput"] div[aria-invalid="true"],
        [data-testid="stNumberInput"] div[aria-invalid="true"] {
            border-color: var(--mn-input-border) !important;
            box-shadow: none !important;
            outline: none !important;
        }

        div[data-baseweb="input"][aria-invalid="true"]:focus-within,
        div[data-baseweb="input"][data-invalid="true"]:focus-within,
        div[data-baseweb="input"]:has(input[aria-invalid="true"]:focus),
        div[data-baseweb="input"]:has(input:invalid:focus),
        [data-testid="stTextInput"] div[aria-invalid="true"]:focus-within,
        [data-testid="stDateInput"] div[aria-invalid="true"]:focus-within,
        [data-testid="stNumberInput"] div[aria-invalid="true"]:focus-within {
            border-color: var(--mn-input-border-focus) !important;
            box-shadow: none !important;
            outline: none !important;
        }
        /* Timeline slider: theme-driven yellow/gold styling */
        div[data-testid="stSlider"] [role="slider"] {
            background-color: #FFD84A !important;
            border-color: #FFD84A !important;
            box-shadow: 0 0 0 2px rgba(255, 216, 74, 0.35) !important;
        }
        
        div[data-testid="stSlider"] [data-testid="stTickBar"] {
            color: #FFD84A !important;
        }
        
        div[data-testid="stSlider"] {
            accent-color: #FFD84A !important;
        }

        .api-load-caption {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            margin: -0.35rem 0 1.05rem 0;
            padding: 0.38rem 0.72rem;
            border: 1px solid rgba(255, 216, 74, 0.22);
            border-radius: 999px;
            background: rgba(13, 13, 9, 0.46);
            color: #B8B29F;
            font-size: 0.80rem;
            font-weight: 650;
            backdrop-filter: blur(6px);
        }

        .api-load-caption span {
            color: #FFF7CC;
            font-weight: 800;
        }
        </style>
        """
        .replace("__BACKGROUND_IMAGE_LAYER__", background_image_layer)
        .replace("__HERO_BACKGROUND__", hero_background)
        .replace("__HERO_BACKDROP_FILTER__", hero_backdrop_filter)
        .replace("__HERO_BOX_SHADOW__", hero_box_shadow)
        .replace("__METRIC_BACKGROUND__", metric_background)
        .replace("__METRIC_BACKDROP_FILTER__", metric_backdrop_filter)
        .replace("__METRIC_BOX_SHADOW__", metric_box_shadow),
        unsafe_allow_html=True,
    )

def dashboard_background_image_layer(image_url: str) -> str:
    if not image_url:
        return ""

    safe_url = image_url.replace("\\", "\\\\").replace("'", "\\'")
    return (
        "linear-gradient(rgba(5, 5, 5, 0.78), rgba(5, 5, 5, 0.88)),\n"
        f"                url('{safe_url}'),\n"
    )

def dashboard_hero_background(*, has_background_image: bool) -> str:
    if has_background_image:
        return "transparent"

    return (
        "linear-gradient(135deg, rgba(20, 18, 10, 0.98), rgba(5, 5, 5, 0.82)), "
        "linear-gradient(90deg, rgba(255, 216, 74, 0.12), transparent)"
    )


def dashboard_hero_backdrop_filter(*, has_background_image: bool) -> str:
    return "none" if has_background_image else "blur(12px)"


def dashboard_hero_box_shadow(*, has_background_image: bool) -> str:
    if has_background_image:
        return "inset 0 1px 0 rgba(255,216,74,0.20)"

    return "0 24px 70px rgba(0,0,0,0.38), inset 0 1px 0 rgba(255,216,74,0.18)"


def dashboard_metric_background(*, has_background_image: bool) -> str:
    if has_background_image:
        return "transparent"

    return (
        "linear-gradient(135deg, rgba(255, 216, 74, 0.12), rgba(255, 176, 0, 0.04) 42%, rgba(5, 5, 5, 0.94)), "
        "linear-gradient(180deg, rgba(28, 25, 14, 0.98), rgba(8, 8, 5, 0.98))"
    )


def dashboard_metric_backdrop_filter(*, has_background_image: bool) -> str:
    return "none" if has_background_image else "blur(10px)"


def dashboard_metric_box_shadow(*, has_background_image: bool) -> str:
    if has_background_image:
        return "inset 0 1px 0 rgba(255,216,74,0.22)"

    return (
        "0 18px 42px rgba(0,0,0,0.42), "
        "0 0 28px rgba(255,176,0,0.08), "
        "inset 0 1px 0 rgba(255,216,74,0.18)"
    )


def dashboard_background_image_url() -> str:
    source = read_secret("DASHBOARD_BACKGROUND_IMAGE")
    if source and re.match(r"^(https?://|data:)", source, flags=re.IGNORECASE):
        return source

    image_path = Path(source).expanduser() if source else DEFAULT_BACKGROUND_IMAGE
    if not image_path.is_absolute():
        image_path = APP_DIR / image_path
    if source and not image_path.is_file():
        image_path = DEFAULT_BACKGROUND_IMAGE

    if not image_path.is_file():
        return ""

    mime_type = mimetypes.guess_type(image_path.name)[0] or "image/png"
    encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded_image}"


def render_header(selected_group: str, selected_vessels: list[str]) -> None:
    vessel_text = "All selected vessels" if len(selected_vessels) != 1 else selected_vessels[0]
    st.markdown(
        f"""
        <div class="dashboard-hero">
            <div class="eyebrow">Marorka performance monitoring</div>
            <h1 class="dashboard-title">Performance KPIs</h1>
            <div class="dashboard-subtitle">
                {escape(selected_group)} | {escape(vessel_text)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )




def render_api_load_caption(metadata: dict[str, Any] | None) -> None:
    """Render one small, discrete last-load indicator below the dashboard hero."""
    metadata = metadata or {}
    last_load = metadata.get("loaded_at_local") or metadata.get("loaded_at_utc") or "-"

    last_load_display = str(last_load).replace(" EEST", "").replace(" EET", "")

    st.markdown(
        f"""
        <div class="api-load-caption">
            Last API load: <span>{escape(last_load_display)} LT</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

# =============================================================================
# Secrets/auth/API helpers
# =============================================================================


class MarorkaConfigError(RuntimeError):
    pass


def read_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, os.getenv(name, default))
    except Exception:
        value = os.getenv(name, default)
    return str(value).strip() if value is not None else default




def app_timezone() -> ZoneInfo:
    timezone_name = read_secret("APP_TIMEZONE", "Europe/Athens")
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        return ZoneInfo("Europe/Athens")


def local_time_label(dt_utc: datetime | None = None) -> str:
    dt_utc = dt_utc or datetime.now(timezone.utc)
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    local_dt = dt_utc.astimezone(app_timezone())
    return local_dt.strftime("%d-%m-%Y %H:%M:%S %Z")


def get_query_param(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
    except Exception:
        value = st.experimental_get_query_params().get(name, [default])

    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value) if value is not None else default


def is_warmup_request() -> bool:
    return get_query_param("warmup", "0") == "1"


def warmup_token_is_valid() -> bool:
    expected_token = read_secret("WARMUP_TOKEN")
    provided_token = get_query_param("token", "")
    return bool(expected_token) and hmac.compare_digest(provided_token, expected_token)


def require_dashboard_password() -> None:
    dashboard_password = read_secret("DASHBOARD_PASSWORD")
    if not dashboard_password:
        return

    if st.session_state.get("dashboard_authenticated"):
        return

    apply_custom_css()
    st.markdown(
        """
        <div class="dashboard-hero">
            <div class="eyebrow">Secure access</div>
            <h1 class="dashboard-title">Performance KPIs</h1>
            <div class="dashboard-subtitle">Enter your dashboard password to continue.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    entered_password = st.text_input("Password", type="password")

    if st.button("Sign in", type="primary"):
        if hmac.compare_digest(entered_password, dashboard_password):
            st.session_state["dashboard_authenticated"] = True
            st.rerun()
        st.error("Invalid password.")

    st.stop()


def request_auth(username: str, password: str, auth_method: str) -> Any:
    method = auth_method.lower()
    if method == "basic":
        return HTTPBasicAuth(username, password)
    if method == "digest":
        return HTTPDigestAuth(username, password)
    if method == "bearer":
        return None
    if method in {"none", "anonymous", ""}:
        return None
    raise MarorkaConfigError("Unsupported MARORKA_AUTH_METHOD. Use basic, digest, bearer, or none.")


def request_headers(token: str, auth_method: str) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if auth_method.lower() == "bearer":
        if not token:
            raise MarorkaConfigError("MARORKA_TOKEN is required for bearer auth.")
        headers["Authorization"] = f"Bearer {token}"
    return headers


def default_report_window(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()

    start_month = today.month - 2
    start_year = today.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1

    start_date = date(start_year, start_month, 1)

    if today.month == 12:
        end_date = date(today.year, 12, 31)
    else:
        end_date = date(today.year, today.month + 1, 1) - timedelta(days=1)

    return start_date, end_date


def build_odata_url(start_date: date) -> str:
    start_text = start_date.strftime("%Y-%m-%d")
    params = {
        "$filter": f"StartDateTimeGMT gt DateTime'{start_text}'",
        "$select": ",".join(SOURCE_COLUMNS),
    }
    return f"{ODATA_ENDPOINT}?{urlencode(params)}"


def extract_odata_page(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(payload, list):
        return payload, None

    if not isinstance(payload, dict):
        raise ValueError("Could not parse OData response payload.")

    rows = payload.get("value")
    next_link = payload.get("@odata.nextLink") or payload.get("odata.nextLink")

    if rows is None and isinstance(payload.get("d"), dict):
        data = payload["d"]
        rows = data.get("results")
        next_link = next_link or data.get("__next")

    if rows is None:
        raise ValueError("Could not find OData rows in the API response.")

    return rows, next_link


def rows_to_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "__metadata" in df.columns:
        df = df.drop(columns=["__metadata"])
    for column in SOURCE_COLUMNS:
        if column not in df.columns:
            df[column] = pd.NA
    return df[SOURCE_COLUMNS]


def compact_odata_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted_keys = wanted_value_keys()
    compact_rows: list[dict[str, Any]] = []

    for row in rows:
        value_description = row.get("ValueDescription")
        if value_description is None:
            continue
        if normalize_text(value_description) not in wanted_keys:
            continue
        if row.get("ReportType") in EXCLUDED_REPORT_TYPES:
            continue
        compact_rows.append({column: row.get(column) for column in SOURCE_COLUMNS})

    return compact_rows


def fetch_report_data(
    username: str,
    password: str,
    token: str,
    auth_method: str,
    start_date: date,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    started_at = time.perf_counter()
    next_url = build_odata_url(start_date)
    kept_rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    pages = 0
    total_bytes = 0
    scanned_rows = 0
    first_url = next_url
    auth = request_auth(username, password, auth_method)
    headers = request_headers(token, auth_method)

    with requests.Session() as session:
        session.headers.update(headers)
        for _ in range(MAX_ODATA_PAGES):
            if next_url in seen_urls:
                break
            seen_urls.add(next_url)

            response = session.get(
                next_url,
                auth=auth,
                timeout=90,
            )
            total_bytes += len(response.content)
            response.raise_for_status()
            pages += 1

            page_rows, next_link = extract_odata_page(response.json())
            scanned_rows += len(page_rows)
            kept_rows.extend(compact_odata_rows(page_rows))

            if not next_link:
                break
            next_url = urljoin(next_url, next_link)

    loaded_at_utc = datetime.now(timezone.utc)
    metadata = {
        "loaded_at_utc": loaded_at_utc.strftime("%d-%m-%Y %H:%M:%S UTC"),
        "loaded_at_local": local_time_label(loaded_at_utc),
        "rows": len(kept_rows),
        "kept_rows": len(kept_rows),
        "scanned_rows": scanned_rows,
        "discarded_rows": max(scanned_rows - len(kept_rows), 0),
        "pages": pages,
        "downloaded_mb": round(total_bytes / 1024 / 1024, 2),
        "fetch_seconds": round(time.perf_counter() - started_at, 2),
        "first_url": first_url,
        "hit_page_limit": pages >= MAX_ODATA_PAGES,
    }
    return rows_to_dataframe(kept_rows), metadata

@st.cache_data(ttl=API_CACHE_TTL_SECONDS, show_spinner=False)
def cached_fetch_report_data(
    username: str,
    password: str,
    token: str,
    auth_method: str,
    start_date: date,
    cache_marker: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    return fetch_report_data(
        username=username,
        password=password,
        token=token,
        auth_method=auth_method,
        start_date=start_date,
    )


@st.cache_data(ttl=API_CACHE_TTL_SECONDS, show_spinner=False)
def cached_transform_report_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    return transform_report_data(raw_df)

# =============================================================================
# Transform helpers
# =============================================================================


def normalize_text(value: Any) -> str:
    text = str(value).lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def wanted_value_keys() -> set[str]:
    return {normalize_text(alias) for aliases in VALUE_ALIASES.values() for alias in aliases}


def parse_datetime_series(series: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(series, errors="coerce", utc=True)
    missing_mask = parsed.isna()

    if missing_mask.any():
        date_text = series.astype("string")
        dotnet_millis = date_text.str.extract(r"/Date\((-?\d+)").iloc[:, 0]
        dotnet_parsed = pd.to_datetime(
            pd.to_numeric(dotnet_millis, errors="coerce"),
            errors="coerce",
            unit="ms",
            utc=True,
        )
        parsed = parsed.mask(missing_mask, dotnet_parsed)

    return parsed


def parse_numeric_value(value: Any) -> Any:
    if pd.isna(value):
        return pd.NA

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return pd.NA

    duration_match = re.fullmatch(r"(-?\d+):([0-5]?\d)(?::([0-5]?\d))?", text)
    if duration_match:
        hours = int(duration_match.group(1))
        sign = -1 if hours < 0 else 1
        minutes = int(duration_match.group(2))
        seconds = int(duration_match.group(3) or 0)
        return sign * (abs(hours) + minutes / 60 + seconds / 3600)

    numeric_text = text.replace(" ", "")
    if re.fullmatch(r"-?\d+,\d+", numeric_text):
        numeric_text = numeric_text.replace(",", ".")
    else:
        numeric_text = numeric_text.replace(",", "")

    numeric_text = re.sub(r"[^0-9.\-]", "", numeric_text)
    if numeric_text in {"", "-", ".", "-."}:
        return pd.NA

    try:
        return float(numeric_text)
    except ValueError:
        return pd.NA


def parse_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.map(parse_numeric_value), errors="coerce")


def first_non_null(series: pd.Series) -> Any:
    values = series.dropna()
    if values.empty:
        return pd.NA
    return values.iloc[0]


def last_non_null(series: pd.Series) -> Any:
    values = series.dropna()
    if values.empty:
        return pd.NA
    return values.iloc[-1]


def match_selected_vessels(raw_ship_names: pd.Series, selected_vessels: list[str]) -> pd.Series:
    selected_keys = {normalize_text(vessel) for vessel in selected_vessels}
    return raw_ship_names.map(normalize_text).isin(selected_keys)


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    numerator = pd.to_numeric(numerator, errors="coerce")
    denominator = pd.to_numeric(denominator, errors="coerce")
    denominator = denominator.mask(denominator == 0)
    return numerator / denominator


def sum_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    available_columns = [column for column in columns if column in df.columns]
    if not available_columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")
    return df[available_columns].apply(pd.to_numeric, errors="coerce").sum(axis=1, min_count=1)


def build_report_rows(df: pd.DataFrame) -> pd.DataFrame:
    group_keys = ["ReportId", "ShipName", "EndDateTimeGMT"]
    available_group_keys = [key for key in group_keys if key in df.columns]
    if not available_group_keys:
        available_group_keys = ["ShipName", "EndDateTimeGMT"]

    sorted_df = df.sort_values("_source_order")
    base_columns = [
        column
        for column in ["ReportType", "StartDateTimeGMT", "LapTime", "StateName"]
        if column in sorted_df.columns
    ]

    report_df = (
        sorted_df
        .groupby(available_group_keys, sort=False, dropna=False)[base_columns]
        .agg(last_non_null)
        .reset_index()
    )

    alias_to_column = {
        normalize_text(alias): column
        for column, aliases in VALUE_ALIASES.items()
        for alias in aliases
    }
    value_rows = sorted_df.loc[
        sorted_df["_value_key"].isin(alias_to_column) & sorted_df["ParsedValue"].notna(),
        [*available_group_keys, "_value_key", "_source_order", "ParsedValue"],
    ].copy()

    if not value_rows.empty:
        value_rows["_canonical_column"] = value_rows["_value_key"].map(alias_to_column)
        value_rows = value_rows.drop_duplicates(
            [*available_group_keys, "_canonical_column"],
            keep="last",
        )
        value_table = (
            value_rows
            .pivot(index=available_group_keys, columns="_canonical_column", values="ParsedValue")
            .reset_index()
        )
        report_df = report_df.merge(value_table, on=available_group_keys, how="left")

    for column in VALUE_ALIASES:
        if column not in report_df.columns:
            report_df[column] = pd.NA

    return report_df


def transform_report_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    missing_columns = sorted(set(SOURCE_COLUMNS).difference(raw_df.columns))
    if missing_columns:
        raise ValueError(f"Missing expected API columns: {', '.join(missing_columns)}")

    df = raw_df.copy()
    df["StartDateTimeGMT"] = parse_datetime_series(df["StartDateTimeGMT"])
    df["EndDateTimeGMT"] = parse_datetime_series(df["EndDateTimeGMT"])
    df["LapTime"] = parse_numeric_series(df["LapTime"])
    df["ParsedValue"] = parse_numeric_series(df["ReportedValue"])
    df["_value_key"] = df["ValueDescription"].map(normalize_text)
    df["_source_order"] = range(len(df))

    df = df[
        df["ValueDescription"].notna()
        & df["_value_key"].isin(wanted_value_keys())
        & ~df["ReportType"].isin(EXCLUDED_REPORT_TYPES)
    ].copy()

    if df.empty:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)

    report_df = build_report_rows(df)
    if report_df.empty:
        return pd.DataFrame(columns=DISPLAY_COLUMNS)

    report_df = report_df.sort_values(["ShipName", "EndDateTimeGMT", "ReportId"], na_position="last")
    report_df = add_calculations(report_df)
    return report_df


def filter_reports_for_selection(
    report_df: pd.DataFrame,
    selected_vessels: list[str],
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    if report_df.empty:
        return report_df

    filtered = report_df.copy()
    start_timestamp = pd.Timestamp(start_date, tz="UTC")
    end_timestamp = pd.Timestamp(end_date + timedelta(days=1), tz="UTC")
    start_values = pd.to_datetime(filtered["StartDateTimeGMT"], errors="coerce", utc=True)

    filtered = filtered[
        match_selected_vessels(filtered["ShipName"], selected_vessels)
        & start_values.ge(start_timestamp)
        & start_values.lt(end_timestamp)
    ].copy()
    return filtered


def calculate_interval_consumption_ltr(
    df: pd.DataFrame,
    rob_column: str,
    received_column: str,
) -> pd.Series:
    if rob_column not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")

    current_rob = pd.to_numeric(df[rob_column], errors="coerce")
    previous_rob = current_rob.groupby(df["ShipName"]).shift(1)
    received = pd.to_numeric(df.get(received_column, 0), errors="coerce").fillna(0)

    consumption = previous_rob + received - current_rob
    consumption = consumption.where(previous_rob.notna() & current_rob.notna())
    consumption = consumption.where(consumption >= 0)
    return consumption


def calculate_sloc_g_per_kwh(
    consumption_ltr: pd.Series,
    power_kw: pd.Series,
    lap_time_hours: pd.Series,
    density_kg_per_ltr: float,
) -> pd.Series:
    energy_kwh = pd.to_numeric(power_kw, errors="coerce") * pd.to_numeric(lap_time_hours, errors="coerce")
    energy_kwh = energy_kwh.mask(energy_kwh <= 0)

    # API oil quantities are in liters. Convert liters -> kg with density,
    # then kg -> grams so SLOC is directly comparable with SFOC [g/kWh].
    consumption_grams = (
        pd.to_numeric(consumption_ltr, errors="coerce")
        * density_kg_per_ltr
        * 1000
    )
    return safe_divide(consumption_grams, energy_kwh)


def calculate_consumption_ltr_per_day(
    consumption_ltr: pd.Series,
    running_hours: pd.Series,
) -> pd.Series:
    running_hours = pd.to_numeric(running_hours, errors="coerce")
    running_hours = running_hours.mask(running_hours <= 0)
    return safe_divide(pd.to_numeric(consumption_ltr, errors="coerce") * 24, running_hours)


def add_calculations(report_df: pd.DataFrame) -> pd.DataFrame:
    df = report_df.copy()
    lap_time = pd.to_numeric(df.get("LapTime"), errors="coerce")
    engine_distance = pd.to_numeric(df.get("Engine Distance [nm]"), errors="coerce")
    distance_over_ground = pd.to_numeric(df.get("Distance Over Ground [nm]"), errors="coerce")
    power = pd.to_numeric(df.get("Power from Torque Meter [kW]"), errors="coerce")

    df["Calculated Slip"] = (1 - safe_divide(distance_over_ground, engine_distance)).round(3)

    if "ME Load [%MCR]" in df.columns:
        df["ME Load [%MCR]"] = pd.to_numeric(df["ME Load [%MCR]"], errors="coerce") / 100

    me_sum = sum_numeric_columns(df, ME_FUEL_COLUMNS)
    df["Consumption ME 24 Hours [MT]"] = safe_divide(me_sum * 24, lap_time).round(3)

    sfoc_values = (
        safe_divide(df["Consumption ME 24 Hours [MT]"], power) / 0.000024
    ).round(3).fillna(0)
    # Keep the legacy internal column and the cleaner display-label alias.
    # This prevents old session/cache data or older filter settings from losing SFOC.
    df["SFOC [gr/Kwh]"] = sfoc_values
    df["SFOC [g/kWh]"] = sfoc_values

    df["Boiler Sum"] = sum_numeric_columns(df, BOILER_FUEL_COLUMNS).round(3)

    df["MELO Consumption [ltr]"] = calculate_interval_consumption_ltr(
        df,
        "MELO ROB [ltr]",
        "MELO Received [ltr]",
    ).round(3)

    cylinder_oil_1_consumption = calculate_interval_consumption_ltr(
        df,
        "Cylinder Oil 1 ROB [ltr]",
        "Cylinder Oil 1 Received [ltr]",
    )
    cylinder_oil_2_consumption = calculate_interval_consumption_ltr(
        df,
        "Cylinder Oil 2 ROB [ltr]",
        "Cylinder Oil 2 Received [ltr]",
    )
    df["Cylinder Oil Consumption [ltr]"] = (
        pd.concat([cylinder_oil_1_consumption, cylinder_oil_2_consumption], axis=1)
        .sum(axis=1, min_count=1)
        .round(3)
    )

    df["GELO Consumption [ltr]"] = calculate_interval_consumption_ltr(
        df,
        "GELO ROB [ltr]",
        "GELO Received [ltr]",
    ).round(3)

    dg_power = pd.to_numeric(df.get("Total DG Power [kW]"), errors="coerce")
    df["Total DG Running Hours [hh:mm]"] = sum_numeric_columns(df, DG_RUNNING_HOUR_COLUMNS).round(3)
    steaming_hours = pd.to_numeric(df.get("Steaming Time Since Last Report [hh:mm]"), errors="coerce")
    df["MELO Consumption [ltr/day]"] = calculate_consumption_ltr_per_day(
        df["MELO Consumption [ltr]"],
        steaming_hours,
    ).round(3)
    df["CYLO SLOC [g/kWh]"] = calculate_sloc_g_per_kwh(
        df["Cylinder Oil Consumption [ltr]"],
        power,
        lap_time,
        CYLO_DENSITY_KG_PER_LTR,
    ).round(3)
    df["GELO Consumption [ltr/day]"] = calculate_consumption_ltr_per_day(
        df["GELO Consumption [ltr]"],
        df["Total DG Running Hours [hh:mm]"],
    ).round(3)

    return df




def recalculate_lub_oil_for_sample(df: pd.DataFrame) -> pd.DataFrame:
    """Recalculate ROB-based lub-oil consumption inside the final selected KPI sample.

    The base dataset calculates consumption against the previous report in the full
    chronological vessel dataset. KPI filters intentionally define a smaller sample,
    so the KPI cards and KPI Excel export should calculate MELO/CYLO/GELO intervals
    against the previous row that remains in that selected sample.
    """
    if df.empty:
        return df.copy()

    sample = df.copy()
    original_order = pd.Series(range(len(sample)), index=sample.index)
    sample["_sample_original_order"] = original_order

    sort_columns = [column for column in ["ShipName", "EndDateTimeGMT", "ReportId"] if column in sample.columns]
    if sort_columns:
        sample = sample.sort_values(sort_columns, na_position="last")

    sample["MELO Consumption [ltr]"] = calculate_interval_consumption_ltr(
        sample,
        "MELO ROB [ltr]",
        "MELO Received [ltr]",
    ).round(3)

    cylinder_oil_1_consumption = calculate_interval_consumption_ltr(
        sample,
        "Cylinder Oil 1 ROB [ltr]",
        "Cylinder Oil 1 Received [ltr]",
    )
    cylinder_oil_2_consumption = calculate_interval_consumption_ltr(
        sample,
        "Cylinder Oil 2 ROB [ltr]",
        "Cylinder Oil 2 Received [ltr]",
    )
    sample["Cylinder Oil Consumption [ltr]"] = (
        pd.concat([cylinder_oil_1_consumption, cylinder_oil_2_consumption], axis=1)
        .sum(axis=1, min_count=1)
        .round(3)
    )

    sample["GELO Consumption [ltr]"] = calculate_interval_consumption_ltr(
        sample,
        "GELO ROB [ltr]",
        "GELO Received [ltr]",
    ).round(3)

    running_hours = pd.to_numeric(sample.get("Steaming Time Since Last Report [hh:mm]"), errors="coerce")
    power = pd.to_numeric(sample.get("Power from Torque Meter [kW]"), errors="coerce")
    lap_time = pd.to_numeric(sample.get("LapTime"), errors="coerce")

    if all(column in sample.columns for column in DG_RUNNING_HOUR_COLUMNS):
        sample["Total DG Running Hours [hh:mm]"] = sum_numeric_columns(sample, DG_RUNNING_HOUR_COLUMNS).round(3)

    sample["MELO Consumption [ltr/day]"] = calculate_consumption_ltr_per_day(
        sample["MELO Consumption [ltr]"],
        running_hours,
    ).round(3)
    sample["CYLO SLOC [g/kWh]"] = calculate_sloc_g_per_kwh(
        sample["Cylinder Oil Consumption [ltr]"],
        power,
        lap_time,
        CYLO_DENSITY_KG_PER_LTR,
    ).round(3)
    sample["GELO Consumption [ltr/day]"] = calculate_consumption_ltr_per_day(
        sample["GELO Consumption [ltr]"],
        sample.get("Total DG Running Hours [hh:mm]", pd.Series(pd.NA, index=sample.index)),
    ).round(3)

    sample = sample.sort_values("_sample_original_order").drop(columns=["_sample_original_order"])
    return sample

# =============================================================================
# Display/export helpers
# =============================================================================


def format_value(value: Any, decimals: int = 2, suffix: str = "") -> str:
    if pd.isna(value):
        return "-"
    if isinstance(value, str):
        return value
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:,.{decimals}f}{suffix}"


def format_percentage(value: Any) -> str:
    if pd.isna(value):
        return "-"
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "-"


def format_datetime(value: Any) -> str:
    if pd.isna(value):
        return "-"
    return pd.Timestamp(value).strftime(DISPLAY_DATETIME_FORMAT)


def make_display_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    columns = [column for column in DISPLAY_COLUMNS if column in df.columns]
    display_df = df[columns].copy()
    for column in ["StartDateTimeGMT", "EndDateTimeGMT"]:
        if column in display_df.columns:
            display_df[column] = pd.to_datetime(display_df[column], errors="coerce").dt.strftime(DISPLAY_DATETIME_FORMAT)
    for column in ["Calculated Slip", "ME Load [%MCR]"]:
        if column in display_df.columns:
            display_df[column] = pd.to_numeric(display_df[column], errors="coerce").map(
                lambda value: "-" if pd.isna(value) else f"{value:.2%}"
            )
    numeric_columns = [
        column for column in display_df.columns
        if column not in {"Calculated Slip", "ME Load [%MCR]", "ReportType", "ShipName", "StateName", "StartDateTimeGMT", "EndDateTimeGMT"}
    ]
    for column in numeric_columns:
        values = pd.to_numeric(display_df[column], errors="coerce")
        display_df[column] = values.map(lambda value: "-" if pd.isna(value) else f"{value:,.2f}")
    return display_df.fillna("-")


@st.cache_data(show_spinner=False)
def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    safe_df = df.copy()
    for column in safe_df.columns:
        if pd.api.types.is_datetime64_any_dtype(safe_df[column]):
            safe_df[column] = pd.to_datetime(safe_df[column], errors="coerce").dt.tz_localize(None)
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        safe_df.to_excel(writer, index=False, sheet_name="Fleet Performance")
        worksheet = writer.sheets["Fleet Performance"]
        for column_cells in worksheet.columns:
            max_length = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column_cells)
            worksheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 45)
    return output.getvalue()


def filter_specs_to_text(specs: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []

    for spec in specs:
        column = spec.get("column", "-")
        kind = spec.get("kind")

        if kind == "numeric":
            parts = []
            if spec.get("min") is not None:
                parts.append(f"{spec.get('min_op', '>=')} {spec.get('min')}")
            if spec.get("max") is not None:
                parts.append(f"{spec.get('max_op', '<=')} {spec.get('max')}")
            lines.append(f"{column}: {' and '.join(parts) if parts else 'No limit'}")
            continue

        if kind == "categorical":
            values = spec.get("values") or []
            lines.append(f"{column}: {', '.join(map(str, values)) if values else 'All values'}")
            continue

        if kind == "datetime":
            parts = []
            from_value = spec.get("from")
            to_value = spec.get("to")
            if from_value is not None:
                parts.append(f"from {pd.Timestamp(from_value).strftime('%d/%m/%Y')}")
            if to_value is not None:
                parts.append(f"to {pd.Timestamp(to_value).strftime('%d/%m/%Y')}")
            lines.append(f"{column}: {' '.join(parts) if parts else 'No limit'}")
            continue

        lines.append(f"{column}: No filter details")

    return lines or ["No filters enabled"]


def vessel_fleet_name(vessel: str) -> str:
    for fleet, vessels in VESSEL_GROUPS.items():
        if vessel in vessels:
            return fleet
    return "-"


def to_kpi_excel_bytes(
    selected_group: str,
    selected_vessels: list[str],
    selected_start: date,
    selected_end: date,
    slip_kpi_df: pd.DataFrame,
    me_sfoc_kpi_df: pd.DataFrame,
    boiler_kpi_df: pd.DataFrame,
    slip_period: tuple[date, date],
    me_sfoc_period: tuple[date, date],
    boiler_period: tuple[date, date],
    performance_filter_specs: list[dict[str, Any]],
    boiler_filter_specs: list[dict[str, Any]],
) -> bytes:
    output = BytesIO()

    if selected_group == "Single vessel" and selected_vessels:
        report_title = selected_vessels[0]
    elif selected_group == "All fleets":
        report_title = "All fleets"
    else:
        report_title = selected_group

    def vessel_mask(df: pd.DataFrame, vessel: str) -> pd.Series:
        if df.empty or "ShipName" not in df.columns:
            return pd.Series(False, index=df.index)
        return match_selected_vessels(df["ShipName"], [vessel])

    rows: list[dict[str, str]] = []
    for vessel in selected_vessels:
        vessel_slip_df = slip_kpi_df.loc[vessel_mask(slip_kpi_df, vessel)]
        vessel_me_sfoc_df = me_sfoc_kpi_df.loc[vessel_mask(me_sfoc_kpi_df, vessel)]
        vessel_boiler_df = boiler_kpi_df.loc[vessel_mask(boiler_kpi_df, vessel)]
        vessel_lub_oil_df = recalculate_lub_oil_for_sample(vessel_me_sfoc_df)

        slip = numeric_series(vessel_slip_df, "Calculated Slip").mean()
        me_load = numeric_series(vessel_me_sfoc_df, "ME Load [%MCR]").mean()
        sfoc = numeric_series_any(vessel_me_sfoc_df, ["SFOC [g/kWh]", "SFOC [gr/Kwh]"]).replace(0, pd.NA).mean()
        boiler = numeric_series(vessel_boiler_df, "Boiler Sum").sum(min_count=1)
        melo_consumption_day = weighted_melo_ltr_per_running_day(vessel_lub_oil_df)
        cylo_sloc = weighted_sloc_g_per_kwh(
            vessel_lub_oil_df,
            "Cylinder Oil Consumption [ltr]",
            "Power from Torque Meter [kW]",
            CYLO_DENSITY_KG_PER_LTR,
        )
        gelo_consumption_day = weighted_gelo_ltr_per_running_day(vessel_lub_oil_df)

        rows.append(
            {
                "Vessels included": vessel,
                "Fleet": vessel_fleet_name(vessel),
                "Average Calculated Slip": format_percentage(slip),
                "Average ME Load [%MCR]": format_percentage(me_load),
                "Average SFOC [g/kWh]": format_value(sfoc, 2),
                "Boiler Sum": format_value(boiler, 2),
                "MELO Consumption [ltr/running day]": format_value(melo_consumption_day, 2),
                "CYLO SLOC [g/kWh]": format_value(cylo_sloc, 2),
                "GELO Consumption [ltr/DG running day]": format_value(gelo_consumption_day, 2),
            }
        )

    kpi_df = pd.DataFrame(rows)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # Leave rows 1-2 for title and period. The KPI table starts on row 3.
        kpi_df.to_excel(writer, index=False, sheet_name="KPI Report", startrow=3)
        worksheet = writer.sheets["KPI Report"]

        worksheet["A1"] = report_title
        worksheet["A1"].font = worksheet["A1"].font.copy(bold=True, underline="single", size=14)

        worksheet["A2"] = f"API Period: {selected_start.strftime('%d/%m/%Y')} to {selected_end.strftime('%d/%m/%Y')}"
        worksheet["A2"].font = worksheet["A2"].font.copy(italic=True)

        # Add a grouped KPI heading above the KPI value columns.
        
        worksheet["A3"].font = worksheet["A3"].font.copy(bold=True)
        worksheet["C3"] = "KPIs"
        worksheet["C3"].font = worksheet["C3"].font.copy(bold=True)
        worksheet.merge_cells(start_row=3, start_column=3, end_row=3, end_column=9)

        header_row = 4
        for cell in worksheet[header_row]:
            cell.font = cell.font.copy(bold=True)

        filter_start_row = header_row + len(kpi_df) + 3
        worksheet[f"A{filter_start_row}"] = "KPI filters used"
        worksheet[f"A{filter_start_row}"].font = worksheet[f"A{filter_start_row}"].font.copy(bold=True)

        row = filter_start_row + 1
        worksheet[f"A{row}"] = "KPI date periods"
        worksheet[f"A{row}"].font = worksheet[f"A{row}"].font.copy(bold=True)
        row += 1
        worksheet[f"A{row}"] = f"Average Calculated Slip: {slip_period[0].strftime('%d/%m/%Y')} to {slip_period[1].strftime('%d/%m/%Y')}"
        row += 1
        worksheet[f"A{row}"] = f"Average ME Load / SFOC / Lub Oil: {me_sfoc_period[0].strftime('%d/%m/%Y')} to {me_sfoc_period[1].strftime('%d/%m/%Y')}"
        row += 1
        worksheet[f"A{row}"] = f"Boiler Sum: {boiler_period[0].strftime('%d/%m/%Y')} to {boiler_period[1].strftime('%d/%m/%Y')}"
        row += 2

        worksheet[f"A{row}"] = "Performance KPI filters"
        worksheet[f"A{row}"].font = worksheet[f"A{row}"].font.copy(bold=True)
        row += 1
        for line in filter_specs_to_text(performance_filter_specs):
            worksheet[f"A{row}"] = line
            row += 1

        row += 1
        worksheet[f"A{row}"] = "Boiler KPI filters"
        worksheet[f"A{row}"].font = worksheet[f"A{row}"].font.copy(bold=True)
        row += 1
        for line in filter_specs_to_text(boiler_filter_specs):
            worksheet[f"A{row}"] = line
            row += 1

        worksheet.column_dimensions["A"].width = 36
        worksheet.column_dimensions["B"].width = 16
        worksheet.column_dimensions["C"].width = 24
        worksheet.column_dimensions["D"].width = 24
        worksheet.column_dimensions["E"].width = 24
        worksheet.column_dimensions["F"].width = 16
        worksheet.column_dimensions["G"].width = 24
        worksheet.column_dimensions["H"].width = 24
        worksheet.column_dimensions["I"].width = 24

    return output.getvalue()

def numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(dtype="float64")
    return pd.to_numeric(df[column], errors="coerce")


def numeric_series_any(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    for column in columns:
        if column in df.columns:
            return pd.to_numeric(df[column], errors="coerce")
    return pd.Series(dtype="float64")


def weighted_melo_ltr_per_running_day(df: pd.DataFrame) -> Any:
    consumption = numeric_series(df, "MELO Consumption [ltr]").sum(min_count=1)
    running_hours = numeric_series(df, "Steaming Time Since Last Report [hh:mm]").sum(min_count=1)
    if pd.isna(consumption) or pd.isna(running_hours) or running_hours <= 0:
        return pd.NA
    return consumption / running_hours * 24


def weighted_gelo_ltr_per_running_day(df: pd.DataFrame) -> Any:
    consumption = numeric_series(df, "GELO Consumption [ltr]").sum(min_count=1)
    dg_running_hours = numeric_series(df, "Total DG Running Hours [hh:mm]").sum(min_count=1)
    if pd.isna(consumption) or pd.isna(dg_running_hours) or dg_running_hours <= 0:
        return pd.NA
    return consumption / dg_running_hours * 24


def weighted_sloc_g_per_kwh(
    df: pd.DataFrame,
    consumption_column: str,
    power_column: str,
    density_kg_per_ltr: float,
) -> Any:
    consumption_ltr = numeric_series(df, consumption_column).sum(min_count=1)
    energy_kwh = (
        numeric_series(df, power_column)
        * numeric_series(df, "LapTime")
    ).sum(min_count=1)
    if pd.isna(consumption_ltr) or pd.isna(energy_kwh) or energy_kwh <= 0:
        return pd.NA
    return consumption_ltr * density_kg_per_ltr * 1000 / energy_kwh


def numeric_sum(df: pd.DataFrame, column: str) -> Any:
    return numeric_series(df, column).sum(min_count=1)


def energy_sum(df: pd.DataFrame, power_column: str) -> Any:
    if df.empty or power_column not in df.columns:
        return pd.NA
    energy = numeric_series(df, power_column) * numeric_series(df, "LapTime")
    return energy.sum(min_count=1)


def kpi_card_html(label: str, value: str, footnote: Any = "", extra_class: str = "") -> str:
    if isinstance(footnote, list):
        detail_html = "\n".join(
            f'<div class="support-row">'
            f'<div class="support-label">{escape(str(detail_label))}</div>'
            f'<div class="support-value">{escape(str(detail_value))}</div>'
            "</div>"
            for detail_label, detail_value in footnote
        )
        footnote_html = f'<div class="sloc-detail-panel">{detail_html}</div>'
    else:
        footnote_html = f'<div class="kpi-footnote">{escape(str(footnote))}</div>' if footnote else ""
    return (
        f'<div class="kpi-card {escape(extra_class)}">'
        f'<div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{escape(value)}</div>'
        f"{footnote_html}"
        "</div>"
    )


def support_card_html(rows: list[tuple[str, str]]) -> str:
    rows_html = "\n".join(
        f'<div class="support-row">'
        f'<div class="support-label">{escape(label)}</div>'
        f'<div class="support-value">{escape(value)}</div>'
        "</div>"
        for label, value in rows
    )
    return f'<div class="support-card">{rows_html}</div>'


def sloc_card_html(
    label: str,
    value: str,
    detail_rows: list[tuple[str, str]],
) -> str:
    detail_html = "\n".join(
        f'<div class="sloc-detail-row">'
        '<div class="sloc-dot"></div>'
        f'<div class="sloc-detail-label">{escape(detail_label)}</div>'
        f'<div class="sloc-detail-value">{escape(detail_value)}</div>'
        "</div>"
        for detail_label, detail_value in detail_rows
    )
    return (
        '<div class="kpi-card sloc-card">'
        f'<div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{escape(value)}</div>'
        f'<div class="sloc-detail-panel">{detail_html}</div>'
        "</div>"
    )


def render_card_grid(cards: list[str], grid_class: str) -> None:
    st.markdown(
        f'<div class="kpi-grid {escape(grid_class)}">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )


def render_kpis(slip_df: pd.DataFrame, me_sfoc_df: pd.DataFrame, boiler_df: pd.DataFrame) -> None:
    lub_oil_df = recalculate_lub_oil_for_sample(me_sfoc_df)

    slip = numeric_series(slip_df, "Calculated Slip").mean()
    me_load = numeric_series(me_sfoc_df, "ME Load [%MCR]").mean()
    sfoc = numeric_series_any(me_sfoc_df, ["SFOC [g/kWh]", "SFOC [gr/Kwh]"]).replace(0, pd.NA).mean()
    boiler = numeric_series(boiler_df, "Boiler Sum").sum(min_count=1)
    melo_consumption_day = weighted_melo_ltr_per_running_day(lub_oil_df)
    cylo_sloc = weighted_sloc_g_per_kwh(
        lub_oil_df,
        "Cylinder Oil Consumption [ltr]",
        "Power from Torque Meter [kW]",
        CYLO_DENSITY_KG_PER_LTR,
    )
    gelo_consumption_day = weighted_gelo_ltr_per_running_day(lub_oil_df)

    running_hours = numeric_sum(me_sfoc_df, "Steaming Time Since Last Report [hh:mm]")
    if pd.isna(running_hours):
        running_hours = numeric_sum(me_sfoc_df, "LapTime")
    running_days = pd.NA if pd.isna(running_hours) else running_hours / 24
    slip_engine_distance = numeric_sum(slip_df, "Engine Distance [nm]")
    slip_distance_over_ground = numeric_sum(slip_df, "Distance Over Ground [nm]")
    me_fuel_total = sum_numeric_columns(me_sfoc_df, ME_FUEL_COLUMNS).sum(min_count=1)
    me_fuel_total_g = pd.NA if pd.isna(me_fuel_total) else me_fuel_total * 1_000_000
    boiler_hours = numeric_sum(boiler_df, "Steaming Time Since Last Report [hh:mm]")
    if pd.isna(boiler_hours):
        boiler_hours = numeric_sum(boiler_df, "LapTime")
    torque_energy = energy_sum(me_sfoc_df, "Power from Torque Meter [kW]")
    gelo_running_hours = numeric_sum(lub_oil_df, "Total DG Running Hours [hh:mm]")
    gelo_running_days = pd.NA if pd.isna(gelo_running_hours) else gelo_running_hours / 24
    melo_total = numeric_sum(lub_oil_df, "MELO Consumption [ltr]")
    cylo_total_ltr = numeric_sum(lub_oil_df, "Cylinder Oil Consumption [ltr]")
    gelo_total_ltr = numeric_sum(lub_oil_df, "GELO Consumption [ltr]")
    cylo_total_g = pd.NA if pd.isna(cylo_total_ltr) else cylo_total_ltr * CYLO_DENSITY_KG_PER_LTR * 1000

    render_card_grid(
        [
            kpi_card_html(
                "Average Calculated Slip",
                format_percentage(slip),
                [
                    ("Total Distance Over Ground", format_value(slip_distance_over_ground, 2, " nm")),
                    ("Total Engine Distance", format_value(slip_engine_distance, 2, " nm")),
                ],
            ),
            kpi_card_html(
                "Average ME Load [%MCR]",
                format_percentage(me_load),
                [
                    ("Total Running Hours", format_value(running_hours, 2, " hrs")),
                    ("Running Days", format_value(running_days, 2, " days")),
                ],
            ),
            kpi_card_html(
                "Average SFOC [g/kWh]",
                format_value(sfoc, 2),
                [
                    ("Total Fuel Consumption (ME)", format_value(me_fuel_total, 2, " MT")),
                    ("Total Fuel Consumption (ME)", format_value(me_fuel_total_g, 0, " g")),
                    ("Total Energy (Torque Meter)", format_value(torque_energy, 0, " kWh")),
                ],
            ),
            kpi_card_html(
                "Boiler Sum",
                format_value(boiler, 2),
                [
                    ("Total Fuel Consumption (Boiler)", format_value(boiler, 2, " MT")),
                    ("Total Boiler Hours", format_value(boiler_hours, 2, " hrs")),
                ],
            ),
        ],
        "kpi-grid-four",
    )

    render_card_grid(
        [
            sloc_card_html(
                "MELO Consumption [ltr/running day]",
                format_value(melo_consumption_day, 2),
                [
                    ("Total MELO Consumption", format_value(melo_total, 2, " ltr")),
                    ("Total Running Hours", format_value(running_hours, 2, " hrs")),
                    ("Running Days", format_value(running_days, 2, " days")),
                ],
            ),
            sloc_card_html(
                "CYLO SLOC [g/kWh]",
                format_value(cylo_sloc, 2),
                [
                    ("Total CYLO Consumption", format_value(cylo_total_ltr, 2, " ltr")),
                    ("Total CYLO Consumption", format_value(cylo_total_g, 2, " g")),
                    ("Total Energy (Torque Meter)", format_value(torque_energy, 0, " kWh")),
                ],
            ),
            sloc_card_html(
                "GELO Consumption [ltr/DG running day]",
                format_value(gelo_consumption_day, 2),
                [
                    ("Total GELO Consumption", format_value(gelo_total_ltr, 2, " ltr")),
                    ("Total DG Running Hours", format_value(gelo_running_hours, 2, " hrs")),
                    ("DG Running Days", format_value(gelo_running_days, 2, " days")),
                ],
            ),
        ],
        "kpi-grid-three",
    )



def latest_by_vessel(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "ShipName" not in df.columns:
        return df
    return df.sort_values("EndDateTimeGMT").groupby("ShipName", as_index=False, dropna=False).tail(1).sort_values("ShipName")


# =============================================================================
# Excel-like KPI filters
# =============================================================================


def unique_display_values(series: pd.Series, limit: int = 500) -> list[str]:
    values = series.astype("string").fillna("(Blank)").drop_duplicates().tolist()
    values = sorted(values, key=lambda value: value.casefold())
    return values[:limit]


def parse_optional_float(value: str) -> tuple[float | None, bool]:
    text = str(value or "").strip()
    if not text:
        return None, True
    normalized = text.replace(" ", "").replace(",", "")
    try:
        return float(normalized), True
    except ValueError:
        return None, False


def parse_optional_date(value: str) -> tuple[pd.Timestamp | None, bool]:
    text = str(value or "").strip()
    if not text:
        return None, True
    parsed = pd.to_datetime(text, dayfirst=True, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None, False
    return parsed, True


def filterable_columns(df: pd.DataFrame) -> list[str]:
    preferred = [column for column in DISPLAY_COLUMNS if column in df.columns]
    remaining = [column for column in df.columns if column not in preferred]
    return preferred + remaining


def is_numeric_like(series: pd.Series) -> bool:
    values = pd.to_numeric(series, errors="coerce")
    return values.notna().any()


def filter_digest(column: str) -> str:
    return sha256(column.encode("utf-8")).hexdigest()[:10]


def seed_filter_defaults(
    *,
    key_prefix: str,
    default_columns: list[str] | None = None,
    default_numeric_filters: dict[str, dict[str, str]] | None = None,
    default_categorical_filters: dict[str, list[str]] | None = None,
) -> None:
    selected_key = f"{key_prefix}_columns"
    if selected_key not in st.session_state and default_columns:
        st.session_state[selected_key] = list(default_columns)

    for column, bounds in (default_numeric_filters or {}).items():
        digest = filter_digest(column)
        min_key = f"{key_prefix}_{digest}_min"
        max_key = f"{key_prefix}_{digest}_max"
        if min_key not in st.session_state:
            st.session_state[min_key] = bounds.get("min", "")
        if max_key not in st.session_state:
            st.session_state[max_key] = bounds.get("max", "")

    for column, values in (default_categorical_filters or {}).items():
        value_key = f"{key_prefix}_{filter_digest(column)}_values"
        if value_key not in st.session_state:
            st.session_state[value_key] = list(values)


def render_excel_like_filters(
    df: pd.DataFrame,
    *,
    key_prefix: str,
    label: str,
    default_columns: list[str] | None = None,
    default_numeric_filters: dict[str, dict[str, str]] | None = None,
    default_categorical_filters: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    seed_filter_defaults(
        key_prefix=key_prefix,
        default_columns=default_columns,
        default_numeric_filters=default_numeric_filters,
        default_categorical_filters=default_categorical_filters,
    )

    current_options = filterable_columns(df)
    selected_key = f"{key_prefix}_columns"
    previous_columns = st.session_state.get(selected_key, [])
    if not isinstance(previous_columns, list):
        previous_columns = []

    # Keep previously chosen filters available even if the current vessel/date
    # selection has fewer columns. This makes the filter setup stable across
    # reruns, vessel changes, and date-window changes.
    options = []
    for column in [*previous_columns, *current_options]:
        if column not in options:
            options.append(column)

    selected_columns = st.multiselect(
        label,
        options=options,
        key=selected_key,
        help="Choose columns to filter. Numeric columns use Min/Max text boxes; text columns use value selection.",
    )

    specs: list[dict[str, Any]] = []
    for column in selected_columns:
        if column not in df.columns:
            st.caption(f"{column}: retained, but not present in the currently loaded data.")
            continue

        st.caption(f"Filter: {column}")
        series = df[column]

        if pd.api.types.is_datetime64_any_dtype(series):
            digest = filter_digest(column)
            from_key = f"{key_prefix}_{digest}_from"
            to_key = f"{key_prefix}_{digest}_to"
            left, right = st.columns(2)
            from_text = left.text_input("From", key=from_key, placeholder="dd/mm/yyyy")
            to_text = right.text_input("To", key=to_key, placeholder="dd/mm/yyyy")
            from_value, from_ok = parse_optional_date(from_text)
            to_value, to_ok = parse_optional_date(to_text)
            if not from_ok or not to_ok:
                st.warning(f"{column}: enter dates as dd/mm/yyyy or yyyy-mm-dd.")
            specs.append({"column": column, "kind": "datetime", "from": from_value, "to": to_value})
            continue

        if is_numeric_like(series):
            values = pd.to_numeric(series, errors="coerce").dropna()
            if not values.empty:
                st.caption(f"Loaded range: {format_value(values.min(), 3)} to {format_value(values.max(), 3)}")
            digest = filter_digest(column)
            min_key = f"{key_prefix}_{digest}_min"
            max_key = f"{key_prefix}_{digest}_max"
            default_rule = (default_numeric_filters or {}).get(column, {})
            min_op = default_rule.get("min_op", ">=")
            max_op = default_rule.get("max_op", "<=")
            left, right = st.columns(2)
            min_text = left.text_input("Min", key=min_key, placeholder="no minimum")
            max_text = right.text_input("Max", key=max_key, placeholder="no maximum")
            minimum, min_ok = parse_optional_float(min_text)
            maximum, max_ok = parse_optional_float(max_text)
            if not min_ok or not max_ok:
                st.warning(f"{column}: enter numeric Min/Max values only.")
            if minimum is not None and maximum is not None and minimum > maximum:
                minimum, maximum = maximum, minimum
                min_op, max_op = ">=", "<="
            specs.append({
                "column": column,
                "kind": "numeric",
                "min": minimum,
                "max": maximum,
                "min_op": min_op,
                "max_op": max_op,
            })
            continue

        value_key = f"{key_prefix}_{filter_digest(column)}_values"
        previous_values = st.session_state.get(value_key, [])
        if not isinstance(previous_values, list):
            previous_values = []
        value_options = []
        for value in [*previous_values, *unique_display_values(series)]:
            if value not in value_options:
                value_options.append(value)
        selected_values = st.multiselect(
            "Values",
            options=value_options,
            key=value_key,
            help="Leave blank to include all values for this column.",
        )
        specs.append({"column": column, "kind": "categorical", "values": selected_values})

    return specs


def apply_excel_like_filters(df: pd.DataFrame, specs: list[dict[str, Any]]) -> pd.DataFrame:
    filtered = df.copy()

    for spec in specs:
        column = spec.get("column")
        if column not in filtered.columns:
            continue

        kind = spec.get("kind")
        if kind == "numeric":
            values = pd.to_numeric(filtered[column], errors="coerce")
            minimum = spec.get("min")
            maximum = spec.get("max")
            min_op = spec.get("min_op", ">=")
            max_op = spec.get("max_op", "<=")
            if minimum is not None:
                if min_op == ">":
                    filtered = filtered[values > minimum]
                else:
                    filtered = filtered[values >= minimum]
                values = pd.to_numeric(filtered[column], errors="coerce")
            if maximum is not None:
                if max_op == "<":
                    filtered = filtered[values < maximum]
                else:
                    filtered = filtered[values <= maximum]

        elif kind == "datetime":
            values = pd.to_datetime(filtered[column], errors="coerce", utc=True)
            from_value = spec.get("from")
            to_value = spec.get("to")
            if from_value is not None:
                filtered = filtered[values >= from_value]
                values = pd.to_datetime(filtered[column], errors="coerce", utc=True)
            if to_value is not None:
                # Include the full selected day.
                filtered = filtered[values < (to_value + pd.Timedelta(days=1))]

        elif kind == "categorical":
            selected_values = spec.get("values") or []
            if selected_values:
                values = filtered[column].astype("string").fillna("(Blank)")
                filtered = filtered[values.isin(selected_values)]

    return filtered


# =============================================================================
# Sidebar
# =============================================================================


def selected_vessel_controls() -> tuple[str, list[str]]:
    group_options = ["Single vessel", "All fleets"] + list(VESSEL_GROUPS.keys())
    selected_group = st.sidebar.selectbox("Fleet group", options=group_options)

    if selected_group == "Single vessel":
        vessel = st.sidebar.selectbox("Vessel to include", options=VESSEL_OPTIONS)
        return selected_group, [vessel]

    if selected_group == "All fleets":
        group_vessels = VESSEL_OPTIONS
    else:
        group_vessels = VESSEL_GROUPS[selected_group]

    vessels = st.sidebar.multiselect(
        "Vessels to include",
        options=group_vessels,
        default=group_vessels,
        help=(
            "This controls the dashboard display and KPI calculations only. "
            "The API data has already been loaded broadly for the selected date window."
        ),
    )

    if not vessels:
        st.sidebar.caption(
            "No vessels selected manually, so all vessels in this fleet group are included."
        )
        vessels = group_vessels

    return selected_group, vessels


def sidebar_controls() -> tuple[date, date, str, list[str], bool]:
    api_start_date = API_FULL_START_DATE
    api_end_date = date.today()

    refresh_requested = st.sidebar.button("Refresh API data", use_container_width=False)
    if refresh_requested:
        st.session_state["confirm_api_refresh"] = True

    refresh = False
    if st.session_state.get("confirm_api_refresh"):
        metadata = st.session_state.get("loaded_metadata") or {}
        last_load = metadata.get("loaded_at_local") or metadata.get("loaded_at_utc") or "-"
        last_load_display = str(last_load).replace(" EEST", "").replace(" EET", "")

        st.sidebar.warning(
            f"Refresh will call the API and may take a while.\n\n"
        	f"Last updated data was on: {last_load_display} LT")
        
        col1, col2 = st.sidebar.columns(2)
        
        if col1.button("Confirm"):
            refresh = True
            st.session_state["confirm_api_refresh"] = False
                
        if col2.button("Cancel"):
        	st.session_state["confirm_api_refresh"] = False
        	st.rerun()

    group, vessels = selected_vessel_controls()

    return api_start_date, api_end_date, group, vessels, refresh





def render_dashboard_date_slicer(df: pd.DataFrame) -> tuple[pd.DataFrame, date, date]:
    if df.empty or "StartDateTimeGMT" not in df.columns:
        today = date.today()
        return df, today, today

    dates = pd.to_datetime(df["StartDateTimeGMT"], errors="coerce", utc=True).dt.date.dropna()
    if dates.empty:
        today = date.today()
        return df, today, today

    min_date = max(dates.min(), API_FULL_START_DATE)
    max_date = min(dates.max(), date.today())

    st.markdown('<div class="section-title">Performance Period</div>', unsafe_allow_html=True)
    st.caption("Drag the handles to choose the time period used by the KPIs and dashboard tables.")

    if min_date >= max_date:
        st.caption(f"Available data period: {min_date.strftime('%d/%m/%Y')}")
        selected_start, selected_end = min_date, max_date
    else:
        selected_start, selected_end = st.slider(
            "Timeline slicer",
            min_value=min_date,
            max_value=max_date,
            value=(min_date, max_date),
            format="DD/MM/YYYY",
            key="dashboard_timeline_slicer",
            label_visibility="collapsed",
        )

    start_timestamp = pd.Timestamp(selected_start, tz="UTC")
    end_timestamp = pd.Timestamp(selected_end + timedelta(days=1), tz="UTC")
    date_values = pd.to_datetime(df["StartDateTimeGMT"], errors="coerce", utc=True)
    filtered_df = df[date_values.ge(start_timestamp) & date_values.lt(end_timestamp)].copy()

    st.caption(
        f"Selected period: {selected_start.strftime('%d/%m/%Y')} to {selected_end.strftime('%d/%m/%Y')} "
        f"({len(filtered_df):,} of {len(df):,} reports)"
    )
    return filtered_df, selected_start, selected_end


def dataframe_date_window(df: pd.DataFrame) -> tuple[date, date]:
    if df.empty or "StartDateTimeGMT" not in df.columns:
        today = date.today()
        return today, today

    dates = pd.to_datetime(df["StartDateTimeGMT"], errors="coerce", utc=True).dt.date.dropna()
    if dates.empty:
        today = date.today()
        return today, today

    return max(dates.min(), API_FULL_START_DATE), min(dates.max(), date.today())


def filter_dataframe_by_date_range(df: pd.DataFrame, selected_start: date, selected_end: date) -> pd.DataFrame:
    if df.empty or "StartDateTimeGMT" not in df.columns:
        return df

    start_timestamp = pd.Timestamp(selected_start, tz="UTC")
    end_timestamp = pd.Timestamp(selected_end + timedelta(days=1), tz="UTC")
    date_values = pd.to_datetime(df["StartDateTimeGMT"], errors="coerce", utc=True)
    return df[date_values.ge(start_timestamp) & date_values.lt(end_timestamp)].copy()


def render_kpi_date_slicer(
    df: pd.DataFrame,
    *,
    label: str,
    key: str,
) -> tuple[pd.DataFrame, date, date]:
    if df.empty or "StartDateTimeGMT" not in df.columns:
        today = date.today()
        st.caption(f"{label}: no available reports.")
        return df, today, today

    dates = pd.to_datetime(df["StartDateTimeGMT"], errors="coerce", utc=True).dt.date.dropna()
    if dates.empty:
        today = date.today()
        st.caption(f"{label}: no valid report dates.")
        return df, today, today

    current_min_date = max(dates.min(), API_FULL_START_DATE)
    current_max_date = min(dates.max(), date.today())

    # Keep one stable slider range per KPI for the whole user session.
    # This prevents vessel/fleet changes from rewriting the user's selected
    # KPI period just because the newly selected vessel has a narrower data
    # window. On first app launch, the stored range is the full period available
    # after the default KPI filters are applied. Later selections can expand
    # the stored range, but they do not shrink it.
    bounds_key = f"{key}_stable_bounds"
    previous_bounds = st.session_state.get(bounds_key)
    if isinstance(previous_bounds, tuple) and len(previous_bounds) == 2:
        stored_min_date, stored_max_date = previous_bounds
        min_date = min(stored_min_date, current_min_date)
        max_date = max(stored_max_date, current_max_date)
    else:
        min_date, max_date = current_min_date, current_max_date
    st.session_state[bounds_key] = (min_date, max_date)

    desired_key = f"{key}_desired_period"
    previous_value = st.session_state.get(desired_key)

    if isinstance(previous_value, tuple) and len(previous_value) == 2:
        previous_start, previous_end = previous_value
        selected_start = max(min(previous_start, max_date), min_date)
        selected_end = max(min(previous_end, max_date), min_date)
        if selected_start > selected_end:
            selected_start, selected_end = min_date, max_date
    else:
        selected_start, selected_end = min_date, max_date

    st.caption(label)
    if min_date >= max_date:
        selected_start, selected_end = min_date, max_date
        st.session_state[desired_key] = (selected_start, selected_end)
        st.caption(f"Available period: {selected_start.strftime('%d/%m/%Y')}")
    else:
        selected_start, selected_end = st.slider(
            label,
            min_value=min_date,
            max_value=max_date,
            value=(selected_start, selected_end),
            format="DD/MM/YYYY",
            key=key,
            label_visibility="collapsed",
        )
        st.session_state[desired_key] = (selected_start, selected_end)

    filtered_df = filter_dataframe_by_date_range(df, selected_start, selected_end)
    st.caption(
        f"Selected period: {selected_start.strftime('%d/%m/%Y')} to {selected_end.strftime('%d/%m/%Y')} "
        f"({len(filtered_df):,} of {len(df):,} filtered reports)"
    )
    return filtered_df, selected_start, selected_end



def render_table_date_slicer(
    df: pd.DataFrame,
    *,
    label: str = "Filtered Report Table period",
    key: str = "filtered_report_table_period_slicer",
) -> tuple[pd.DataFrame, date, date]:
    if df.empty or "StartDateTimeGMT" not in df.columns:
        today = date.today()
        return df, today, today

    dates = pd.to_datetime(df["StartDateTimeGMT"], errors="coerce", utc=True).dt.date.dropna()
    if dates.empty:
        today = date.today()
        return df, today, today

    min_date = max(dates.min(), API_FULL_START_DATE)
    max_date = min(dates.max(), date.today())

    st.caption(label)

    if min_date >= max_date:
        selected_start, selected_end = min_date, max_date
        st.caption(f"Available period: {selected_start.strftime('%d/%m/%Y')}")
    else:
        default_value = st.session_state.get(key)
        if isinstance(default_value, tuple) and len(default_value) == 2:
            default_start, default_end = default_value
            default_start = max(min(default_start, max_date), min_date)
            default_end = max(min(default_end, max_date), min_date)
            if default_start > default_end:
                default_start, default_end = min_date, max_date
            default_value = (default_start, default_end)
        else:
            default_value = (min_date, max_date)
        selected_start, selected_end = st.slider(
            label,
            min_value=min_date,
            max_value=max_date,
            value=default_value,
            format="DD/MM/YYYY",
            key=key,
            label_visibility="collapsed",
        )

    filtered_df = filter_dataframe_by_date_range(df, selected_start, selected_end)
    st.caption(
        f"Selected table period: {selected_start.strftime('%d/%m/%Y')} to {selected_end.strftime('%d/%m/%Y')} "
        f"({len(filtered_df):,} of {len(df):,} reports)"
    )
    return filtered_df, selected_start, selected_end

# =============================================================================
# Session-state data  helpers
# =============================================================================


def raw_value_alias_signature() -> str:
    alias_text = "|".join(
        f"{column}:{','.join(aliases)}"
        for column, aliases in sorted(VALUE_ALIASES.items())
    )
    return sha256(alias_text.encode("utf-8")).hexdigest()[:12]


def request_signature(
    username: str,
    auth_method: str,
    start_date: date,
) -> dict[str, Any]:
    return {
        "endpoint": ODATA_ENDPOINT,
        "username_hash": sha256(username.encode("utf-8")).hexdigest()[:12],
        "auth_method": auth_method.lower(),
        "start_date": start_date.isoformat(),
        # This matters because raw API rows are compacted by VALUE_ALIASES.
        # If aliases change, old compact raw data may not contain newly added API values.
        "raw_value_alias_signature": raw_value_alias_signature(),
    }


def transform_signature(raw_signature: dict[str, Any]) -> dict[str, Any]:
    schema_text = "|".join([
        CALCULATION_SCHEMA_VERSION,
        *VALUE_ALIASES.keys(),
        *DISPLAY_COLUMNS,
    ])
    return {
        **raw_signature,
        "value_signature": sha256(schema_text.encode("utf-8")).hexdigest()[:12],
    }


def view_signature(
    raw_signature: dict[str, Any],
    selected_vessels: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, Any]:
    schema_text = "|".join([
        CALCULATION_SCHEMA_VERSION,
        *VALUE_ALIASES.keys(),
        *DISPLAY_COLUMNS,
    ])
    return {
        **raw_signature,
        "selected_vessels": tuple(selected_vessels),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "value_signature": sha256(schema_text.encode("utf-8")).hexdigest()[:12],
    }


def get_loaded_state() -> tuple[pd.DataFrame | None, pd.DataFrame | None, dict[str, Any] | None]:
    raw_df = st.session_state.get("loaded_raw_df")
    transformed_df = st.session_state.get("loaded_transformed_df")
    metadata = st.session_state.get("loaded_metadata")
    return raw_df, transformed_df, metadata


def set_loaded_raw_state(
    raw_df: pd.DataFrame,
    metadata: dict[str, Any],
    signature: dict[str, Any],
) -> None:
    metadata = metadata.copy()
    metadata.setdefault("loaded_at_utc", datetime.now(timezone.utc).strftime("%d-%m-%Y %H:%M:%S UTC"))
    metadata.setdefault("loaded_at_local", local_time_label())
    metadata["loaded_start_date"] = signature["start_date"]
    st.session_state["loaded_raw_df"] = raw_df
    st.session_state["loaded_metadata"] = metadata
    st.session_state["loaded_request_signature"] = signature
    # The raw data changed, so any transformed data from the previous raw pull is stale.
    st.session_state.pop("loaded_transformed_df", None)
    st.session_state.pop("loaded_transform_signature", None)


def set_loaded_transform_state(df: pd.DataFrame, signature: dict[str, Any]) -> None:
    st.session_state["loaded_transformed_df"] = df
    st.session_state["loaded_transform_signature"] = signature



def raw_data_covers_request(
    loaded_signature: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
    requested_signature: dict[str, Any],
    requested_start_date: date,
) -> bool:
    if not loaded_signature or not metadata:
        return False

    # If the same API/user/auth data was fetched from an earlier start date, it
    # also covers later start-date selections. No new API call is needed.
    for key in ["endpoint", "username_hash", "auth_method", "raw_value_alias_signature"]:
        if loaded_signature.get(key) != requested_signature.get(key):
            return False

    loaded_start_text = metadata.get("loaded_start_date") or loaded_signature.get("start_date")
    try:
        loaded_start_date = date.fromisoformat(str(loaded_start_text))
    except ValueError:
        return False

    return loaded_start_date <= requested_start_date

# =============================================================================
# Main app
# =============================================================================



def run_warmup_if_requested() -> None:
    """Warm up API/cache via a secret-token URL without showing the normal dashboard UI."""
    if not is_warmup_request():
        return

    apply_custom_css()

    if not warmup_token_is_valid():
        st.error("Invalid or missing warmup token.")
        st.stop()

    username = read_secret("MARORKA_USERNAME")
    password = read_secret("MARORKA_PASSWORD")
    token = read_secret("MARORKA_TOKEN")
    auth_method = read_secret("MARORKA_AUTH_METHOD", "basic")
    start_date = API_FULL_START_DATE

    if auth_method.lower() in {"basic", "digest"} and (not username or not password):
        st.error("Warmup failed: MARORKA_USERNAME and MARORKA_PASSWORD are required.")
        st.stop()

    if get_query_param("force", "0") == "1":
        cached_fetch_report_data.clear()
        cached_transform_report_data.clear()

    try:
        with st.spinner("Warming up API..."):
            raw_df, metadata = cached_fetch_report_data(
                username=username,
                password=password,
                token=token,
                auth_method=auth_method,
                start_date=start_date,
                cache_marker=raw_value_alias_signature(),
            )
            all_df = cached_transform_report_data(raw_df)
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        st.error(f"Warmup failed: Marorka API request failed with status {status}.")
        st.stop()
    except (MarorkaConfigError, ValueError, requests.RequestException) as exc:
        st.error(f"Warmup failed: {exc}")
        st.stop()

    metadata = metadata.copy()
    metadata["transformed_rows"] = int(len(all_df))

    st.success("Warmup OK.")
    st.write(
        {
            "last_api_load_local": metadata.get("loaded_at_local"),
            "compact_api_rows": int(len(raw_df)),
            "dashboard_rows": int(len(all_df)),
            "force_refresh": get_query_param("force", "0") == "1",
        }
    )
    st.stop()


def main() -> None:
    run_warmup_if_requested()
    require_dashboard_password()
    apply_custom_css()

    username = read_secret("MARORKA_USERNAME")
    password = read_secret("MARORKA_PASSWORD")
    token = read_secret("MARORKA_TOKEN")
    auth_method = read_secret("MARORKA_AUTH_METHOD", "basic")

    if auth_method.lower() in {"basic", "digest"} and (not username or not password):
        st.info("Add MARORKA_USERNAME and MARORKA_PASSWORD to .streamlit/secrets.toml.")
        st.stop()

    start_date, end_date, selected_group, selected_vessels, refresh = sidebar_controls()
    render_header(selected_group, selected_vessels)

    raw_signature = request_signature(username, auth_method, start_date)
    current_raw_signature = st.session_state.get("loaded_request_signature")
    raw_df, df, metadata = get_loaded_state()

    needs_raw_load = (
        refresh
        or raw_df is None
        or metadata is None
        or not raw_data_covers_request(current_raw_signature, metadata, raw_signature, start_date)
    )

    if needs_raw_load:
        if refresh:
            cached_fetch_report_data.clear()
            cached_transform_report_data.clear()

        try:
            spinner_text = (
                "Refreshing API..."
                if refresh
                else "Loading API..."
            )
            with st.spinner(spinner_text):
                raw_df, metadata = cached_fetch_report_data(
                    username=username,
                    password=password,
                    token=token,
                    auth_method=auth_method,
                    start_date=start_date,
                    cache_marker=raw_signature["raw_value_alias_signature"],
                )
            set_loaded_raw_state(raw_df, metadata, raw_signature)
            df = None
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            st.error(f"Marorka API request failed with status {status}.")
            st.caption("If credentials are correct, try MARORKA_AUTH_METHOD = 'digest'.")
            if exc.response is not None and exc.response.request is not None:
                st.code(exc.response.request.url, language="text")
            st.stop()
        except (MarorkaConfigError, ValueError, requests.RequestException) as exc:
            st.error(str(exc))
            st.stop()

    transform_sig = transform_signature(raw_signature)
    current_transform_sig = st.session_state.get("loaded_transform_signature")
    all_df = st.session_state.get("loaded_transformed_df")
    metadata = st.session_state.get("loaded_metadata")
    raw_df = st.session_state.get("loaded_raw_df")

    if raw_df is None or metadata is None:
        st.info("Loading Marorka data automatically. Use **Refresh API data** to force a new API pull.")
        st.stop()

    if all_df is None or current_transform_sig != transform_sig:
        try:
            transform_started_at = time.perf_counter()
            all_df = cached_transform_report_data(raw_df)
            set_loaded_transform_state(all_df, transform_sig)
            metadata = st.session_state.get("loaded_metadata")
            if isinstance(metadata, dict):
                metadata["transform_seconds"] = round(time.perf_counter() - transform_started_at, 2)
                metadata["transformed_rows"] = int(len(all_df))
                st.session_state["loaded_metadata"] = metadata
        except (ValueError, TypeError) as exc:
            st.error(str(exc))
            st.stop()

    view_sig = view_signature(raw_signature, selected_vessels, start_date, end_date)
    df = filter_reports_for_selection(all_df, selected_vessels, start_date, end_date)

    if df.empty:
        st.warning("No matching performance report values were returned for the selected fleet/date window.")
        st.stop()

    render_api_load_caption(metadata)

    tab_dashboard, tab_diagnostics, tab_data = st.tabs(["Dashboard", "API Diagnostics", "Dataset"])

    if metadata.get("hit_page_limit"):
        st.warning(
            "The API refresh reached the page safety limit. The loaded dataset may be incomplete. "
            "Check API Diagnostics before using the report."
        )

    dashboard_df = df.copy()
    dashboard_start_date, dashboard_end_date = dataframe_date_window(dashboard_df)

    if dashboard_df.empty:
        st.warning("No reports match the selected vessel/fleet selection.")
        st.stop()

    with st.sidebar.expander("KPI Filters: Slip / ME Load / SFOC / Lub Oil", expanded=False):
        st.caption("These filters affect Average Calculated Slip, Average ME Load, Average SFOC, MELO Consumption, and the Lub Oil KPIs.")
        performance_filter_specs = render_excel_like_filters(
            dashboard_df,
            key_prefix="performance_kpi_filter",
            label="Columns to filter",
            default_columns=DEFAULT_PERFORMANCE_FILTER_COLUMNS,
            default_numeric_filters=DEFAULT_PERFORMANCE_NUMERIC_FILTERS,
            default_categorical_filters=DEFAULT_PERFORMANCE_CATEGORICAL_FILTERS,
        )

    with st.sidebar.expander("KPI Filters: Boiler Sum", expanded=False):
        st.caption("These filters affect only the Boiler Sum KPI.")
        boiler_filter_specs = render_excel_like_filters(
            dashboard_df,
            key_prefix="boiler_kpi_filter",
            label="Columns to filter",
            default_columns=DEFAULT_BOILER_FILTER_COLUMNS,
            default_numeric_filters=DEFAULT_BOILER_NUMERIC_FILTERS,
            default_categorical_filters=DEFAULT_BOILER_CATEGORICAL_FILTERS,
        )

    performance_kpi_base_df = apply_excel_like_filters(dashboard_df, 
                                                       performance_filter_specs)
    boiler_kpi_base_df = apply_excel_like_filters(dashboard_df, boiler_filter_specs)

    with st.sidebar.expander("KPI Periods", expanded=True):
        st.caption("These periods control the KPI cards without changing the loaded dataset.")
        slip_kpi_df, slip_start_date, slip_end_date = render_kpi_date_slicer(
            performance_kpi_base_df,
            label="Average Calculated Slip period",
            key="calculated_slip_kpi_period_slicer",
        )
        me_sfoc_kpi_df, me_sfoc_start_date, me_sfoc_end_date = render_kpi_date_slicer(
            performance_kpi_base_df,
            label="Average ME Load / SFOC / Lub Oil period",
            key="me_load_sfoc_kpi_period_slicer",
        )
        boiler_kpi_df, boiler_start_date, boiler_end_date = render_kpi_date_slicer(
            boiler_kpi_base_df,
            label="Boiler Sum period",
            key="boiler_sum_kpi_period_slicer",
        )

    with st.sidebar.expander("Filtered Report Table Filters", expanded=False):
        st.caption("These controls affect only the Filtered Report Table below. They do not change KPI cards or Latest Report By Vessel.")
        table_period_df, table_start_date, table_end_date = render_table_date_slicer(
            dashboard_df,
            label="Table period",
            key="filtered_report_table_period_slicer",
        )
        table_filter_specs = render_excel_like_filters(
            table_period_df,
            key_prefix="filtered_report_table_filter",
            label="Columns to filter",
        )
        table_df = apply_excel_like_filters(table_period_df, table_filter_specs)
        st.caption(
            f"Table rows after filters: {len(table_df):,} of {len(dashboard_df):,} selected-vessel reports."
        )

    with tab_dashboard:
        st.markdown('<div class="section-title">Fleet KPIs</div>', unsafe_allow_html=True)
        render_kpis(slip_kpi_df, me_sfoc_kpi_df, boiler_kpi_df)

        kpi_excel_bytes = to_kpi_excel_bytes(
            selected_group=selected_group,
            selected_vessels=selected_vessels,
            selected_start=dashboard_start_date,
            selected_end=dashboard_end_date,
            slip_kpi_df=slip_kpi_df,
            me_sfoc_kpi_df=me_sfoc_kpi_df,
            boiler_kpi_df=boiler_kpi_df,
            slip_period=(slip_start_date, slip_end_date),
            me_sfoc_period=(me_sfoc_start_date, me_sfoc_end_date),
            boiler_period=(boiler_start_date, boiler_end_date),
            performance_filter_specs=performance_filter_specs,
            boiler_filter_specs=boiler_filter_specs,
        )
        st.download_button(
            "Download KPI summary Excel",
            data=kpi_excel_bytes,
            file_name="kpi_summary_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        if (
            len(slip_kpi_df) != len(dashboard_df)
            or len(me_sfoc_kpi_df) != len(dashboard_df)
            or len(boiler_kpi_df) != len(dashboard_df)
        ):
            st.caption(
                f"Calculated Slip uses {len(slip_kpi_df):,} reports. "
                f"ME Load / SFOC uses {len(me_sfoc_kpi_df):,} reports. "
                f"Lub Oil uses {len(me_sfoc_kpi_df):,} reports. "
                f"Boiler Sum uses {len(boiler_kpi_df):,} reports."
            )

        st.markdown('<div class="section-title">Latest Report By Vessel</div>', unsafe_allow_html=True)
        st.dataframe(make_display_dataframe(latest_by_vessel(dashboard_df)), use_container_width=True, hide_index=True)

        st.markdown('<div class="section-title">Filtered Report Table</div>', unsafe_allow_html=True)
        st.caption(
            f"Table period: {table_start_date.strftime('%d/%m/%Y')} to {table_end_date.strftime('%d/%m/%Y')} "
            f"({len(table_df):,} rows after table filters)."
        )
        sorted_dashboard_df = table_df.sort_values("EndDateTimeGMT", ascending=False)
        preview_dashboard_df = sorted_dashboard_df.head(TABLE_PREVIEW_ROW_LIMIT)
        display_df = make_display_dataframe(preview_dashboard_df)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        if len(sorted_dashboard_df) > TABLE_PREVIEW_ROW_LIMIT:
            st.caption(
                f"Showing first {TABLE_PREVIEW_ROW_LIMIT:,} of {len(sorted_dashboard_df):,} rows. "
                "Use the Dataset tab and Excel export for the full selected dataset."
            )

    with tab_diagnostics:
        st.markdown('<div class="section-title">Diagnostics</div>', unsafe_allow_html=True)
        diagnostics = pd.DataFrame(
            {
                "Metric": [
                    "Selected vessels",
                    "API start date",
                    "API end date",
                    "Dashboard selected start",
                    "Dashboard selected end",
                    "API loaded at",
                    "API loaded local time",
                    "API loaded from start date",
                    "Selected-vessel reports",
                    "All-vessel transformed reports",
                    "Kept compact raw rows",
                    "Original API rows scanned",
                    "Discarded irrelevant rows",
                    "API pages",
                    "Downloaded MB",
                    "API fetch seconds",
                    "Transform seconds",
                    "Hit API page limit",
                ],
                "Value": [
                    ", ".join(selected_vessels),
                    start_date.isoformat(),
                    end_date.isoformat(),
                    dashboard_start_date.isoformat(),
                    dashboard_end_date.isoformat(),
                    metadata.get("loaded_at_utc", "-"),
                    metadata.get("loaded_at_local", "-"),
                    metadata.get("loaded_start_date", "-"),
                    f"{len(df):,}",
                    f"{len(all_df):,}",
                    f"{metadata.get('kept_rows', metadata.get('rows', 0)):,}",
                    f"{metadata.get('scanned_rows', 0):,}",
                    f"{metadata.get('discarded_rows', 0):,}",
                    f"{metadata['pages']:,}",
                    metadata["downloaded_mb"],
                    metadata.get("fetch_seconds", "-"),
                    metadata.get("transform_seconds", "-"),
                    str(metadata.get("hit_page_limit", "-")),
                ],
            }
        )
        st.dataframe(diagnostics, use_container_width=True, hide_index=True)

        with st.expander("First API URL", expanded=False):
            st.code(metadata.get("first_url", "-"), language="text")

        st.markdown('<div class="section-title">Compact Raw ValueDescription Counts</div>', unsafe_allow_html=True)
        if st.button("Calculate raw value counts"):
            value_counts = raw_df.get("ValueDescription", pd.Series(dtype="object")).value_counts(dropna=False).reset_index()
            value_counts.columns = ["ValueDescription", "Compact raw rows"]
            st.dataframe(value_counts.head(200), use_container_width=True, hide_index=True)
        else:
            st.caption("Raw value counts are calculated on demand so diagnostics do not slow normal loads.")

    with tab_data:
        export_df = df.sort_values(["ShipName", "EndDateTimeGMT"], ascending=[True, False])
        export_ready = (
            st.session_state.get("fleet_export_signature") == view_sig
            and "fleet_export_bytes" in st.session_state
        )

        if st.button("Prepare Excel download", type="primary"):
            with st.spinner("Preparing Excel file..."):
                st.session_state["fleet_export_bytes"] = to_excel_bytes(export_df)
                st.session_state["fleet_export_signature"] = view_sig
            export_ready = True

        if export_ready:
            st.download_button(
                "Download fleet performance Excel",
                data=st.session_state["fleet_export_bytes"],
                file_name="fleet_performance_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        else:
            st.caption("Excel generation is prepared on demand so normal dashboard loads stay faster.")

        preview_export_df = export_df.head(TABLE_PREVIEW_ROW_LIMIT)
        st.dataframe(make_display_dataframe(preview_export_df), use_container_width=True, hide_index=True)
        if len(export_df) > TABLE_PREVIEW_ROW_LIMIT:
            st.caption(
                f"Showing first {TABLE_PREVIEW_ROW_LIMIT:,} of {len(export_df):,} selected rows. "
                "The Excel download includes the full selected dataset."
            )


if __name__ == "__main__":
    main()
