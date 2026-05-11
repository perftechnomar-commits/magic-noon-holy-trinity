from __future__ import annotations

from datetime import date, timedelta
from hashlib import sha256
from io import BytesIO
from time import perf_counter
from urllib.parse import urljoin

import pandas as pd
import requests
import streamlit as st
from requests.adapters import HTTPAdapter
from requests.auth import HTTPBasicAuth
from urllib3.util.retry import Retry


APP_TITLE = "Fleet Performance Dashboard"
BASE_URL = "https://online.marorka.com/Odata/v1/ODataService.svc/ReportData"

DEFAULT_DAYS_BACK = 30
DEFAULT_START_DATE = "2026-01-01"
PAGE_SAFETY_LIMIT = 2000
SAMPLE_ROW_LIMIT = 100
METRIC_QUERY_CHUNK_SIZE = 1
QUERY_DATE_CHUNK_DAYS = 7

UI_DATE_INPUT_FORMAT = "DD/MM/YYYY"
DISPLAY_DATETIME_FORMAT = "%d/%m/%Y %H:%M"

DATE_LITERAL_FORMATS = {
    "Date only": "%Y-%m-%d",
    "Date and time": "%Y-%m-%dT00:00:00",
}

REPORT_TYPES_TO_EXCLUDE = [
    "Intake Report",
    "Fuel Change Report",
]

INDEX_COLUMNS = [
    "ReportId",
    "ShipName",
    "ReportType",
    "StartDateTimeGMT",
    "EndDateTimeGMT",
    "LapTime",
    "StateName",
]

VESSEL_DISCOVERY_VALUES = [
    "Steaming Time Since Last Report [hh:mm]",
    "Draft Forward [m] (m)",
    "Draft Aft [m] (m)",
    "Engine Distance [nm]",
    "Shaft 1 RPM (rpm)",
]

DEFAULT_VALUES = [
    # Calculated Slip
    "Engine Distance [nm]",
    "Distance Over Ground [nm]",

    # ME Load [%MCR]
    "ME Load [%MCR]",

    # SFOC [gr/Kwh]
    "Power from Torque Meter [kW]",
    "Main Engine - HSHFO",
    "Main Engine - HSLFO",
    "Main Engine - MGO",
    "Main Engine - ULSHFO",
    "Main Engine - ULSLFO",
    "Main Engine - VLSHFO",
    "Main Engine - VLSLFO",

    # Boiler Sum
    "Boiler - HSHFO",
    "Boiler - HSLFO",
    "Boiler - MGO",
    "Boiler - ULSHFO",
    "Boiler - ULSLFO",
    "Boiler - VLSHFO",
    "Boiler - VLSLFO",
]

VESSEL_GROUPS = {
    "Fleet 1": ["ATETI", "CMA CGM THALASSA", "CZECH", "DOLPHIN II", "GSL CHRISTEL ELISABETH", "GSL VINIA", "MYNY", "SYDNEY EXPRESS"],
    "Fleet 2": ["AGIOS DIMITRIOS", "ELENI T", "MAIRA", "MELINA", "NEWYORKER", "NIKOLAS", "TORRANCE"],
    "Fleet 3": ["BREMERHAVEN EXPRESS", "CMA CGM ALCAZAR", "GSL ALICE", "GSL CHATEAU D'IF", "GSL ELEFTHERIA", "GSL MAREN", "GSL MELINA", "ISTANBUL EXPRESS"],
    "Fleet 4": ["ANTHEA Y", "COLOMBIA EXPRESS", "COSTA RICA EXPRESS", "JAMAICA EXPRESS", "MEXICO EXPRESS", "NICARAGUA EXPRESS", "PANAMA EXPRESS", "ZIM NORFOLK", "ZIM XIAMEN"],
    "Fleet 9": ["CMA CGM AMERICA", "CMA CGM SAMBHAR", "GSL ELENI", "GSL GRANIA", "GSL KALLIOPI", "GSL NINGBO", "MSC QINGDAO", "MSC TIANJIN"],
    "Fleet 10": ["CAPTAIN THANASIS I", "CMA CGM JAMAICA", "GSL CHRISTEN", "GSL NICOLETTA", "GSL VALERIE", "JULIE", "KUMASI", "MANET"],
    "Fleet 11": ["ATHENA", "EPAMINONDAS", "IAN H", "MARIANNA I", "MSC ROMA", "TINA I"],
    "Fleet 12": ["GSL DOROTHEA", "GSL KITHIRA", "GSL MARIA", "GSL MELITA", "GSL SYROS", "GSL TEGEA", "GSL TINOS", "GSL TRIPOLI"],
    "Fleet 14": ["GSL CHLOE", "GSL ELIZABETH", "GSL MAMITSA", "GSL MERCER", "GSL ROSSI", "GSL SUSAN", "TONSBERG"],
    "Fleet 15": ["GSL ALEXANDRA", "GSL ARCADIA", "GSL EFFIE", "GSL LYDIA", "GSL MYNY", "GSL SOFIA", "GSL VIOLETTA", "KOSTAS K", "MARIA Y"],
}

VESSEL_OPTIONS = sorted({vessel for vessels in VESSEL_GROUPS.values() for vessel in vessels})
VESSEL_QUERY_CHUNK_SIZE = 1

COLUMN_ALIASES = {
    "Diesel Generators - HSHFO": "Diesel Generator - HSHFO",
    "Diesel Generators - HSLFO": "Diesel Generator - HSLFO",
    "Diesel Generators - MGO": "Diesel Generator - MGO",
    "Diesel Generators - ULSHFO": "Diesel Generator - ULSHFO",
    "Diesel Generators - ULSLFO": "Diesel Generator - ULSLFO",
    "Diesel Generators - VLSHFO": "Diesel Generator - VLSHFO",
    "Diesel Generators - VLSLFO": "Diesel Generator - VLSLFO",
    "Total DG Power [kW] (kW)": "Total Electric Load [kW]",
    "Total Shaft Power [kW] (kW)": "Power from Torque Meter [kW]",
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

DG_FUEL_COLUMNS = [
    "Diesel Generator - HSHFO",
    "Diesel Generator - HSLFO",
    "Diesel Generator - MGO",
    "Diesel Generator - ULSHFO",
    "Diesel Generator - ULSLFO",
    "Diesel Generator - VLSHFO",
    "Diesel Generator - VLSLFO",
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

DEFAULT_TABLE_COLUMNS = [
    "ShipName",
    "ReportType",
    "StartDateTimeGMT",
    "EndDateTimeGMT",
    "LapTime",
    "StateName",
    "Average Draft [m]",
    "Calculated Slip",
    "Shaft 1 RPM (rpm)",
    "Corrected Speed for 7% Slip",
    "Engine Distance [nm]",
    "Distance Over Ground [nm]",
    "Speed over ground [kn GPS] (kn)",
    "Water speed [kn Log] (kn)",
    "Current Speed Calculated [kn]",
    "ME Load [%MCR]",
    "Consumption ME 24 Hours [MT]",
    "Consumption DGs 24 Hours [MT]",
    "Boiler Sum",
    "Consumption Boiler 24 Hours [MT]",
    "Total Consumption 24 Hours [MT]",
    "HFO Consumption Equivalent [MT]",
    "Total Electric Load [kW]",
    "Load per Generator [% MCR]",
    "Power from Torque Meter [kW]",
    "SFOC [gr/Kwh]",
    "Total Number Reefer Units (20 and 40ft)",
    "Reefers Onboard 20ft Equivalent",
    "Estimated Reefer Load",
    "Reefer Power [kW]",
    "Average Power per Reefer [kW]",
]

KEY_METRICS = [
    ("Lap Time", "LapTime"),
    ("Average Draft", "Average Draft [m]"),
    ("Calculated Slip", "Calculated Slip"),
    ("Corrected Speed", "Corrected Speed for 7% Slip"),
    ("Engine Distance", "Engine Distance [nm]"),
    ("Distance Over Ground", "Distance Over Ground [nm]"),
    ("Water Speed", "Water speed [kn Log] (kn)"),
    ("SOG", "Speed over ground [kn GPS] (kn)"),
    ("ME Load", "ME Load [%MCR]"),
    ("ME 24h Consumption", "Consumption ME 24 Hours [MT]"),
    ("Total 24h Consumption", "Total Consumption 24 Hours [MT]"),
    ("SFOC", "SFOC [gr/Kwh]"),
    ("Torque Power", "Power from Torque Meter [kW]"),
    ("Total DG Power", "Total Electric Load [kW]"),
    ("Reefer Power", "Reefer Power [kW]"),
    ("Average Power / Reefer", "Average Power per Reefer [kW]"),
]

REPORT_SECTIONS = {
    "Navigation": [
        "Steaming Time Since Last Report [hh:mm]",
        "Engine Distance [nm]",
        "Distance Over Ground [nm]",
        "Distance Through Water [nm]",
        "Water speed [kn Log] (kn)",
        "Speed over ground [kn GPS] (kn)",
        "Current Speed [kn]",
        "Speed Ordered by the Charterers [kn]",
    ],
    "Draft And Propulsion": [
        "Draft Forward [m] (m)",
        "Draft Aft [m] (m)",
        "Average Draft [m]",
        "Shaft 1 RPM (rpm)",
        "ME Rev Since Last Report",
        "ME Load [%MCR]",
        "Power from Torque Meter [kW]",
    ],
    "Electrical And Reefers": [
        "Total Electric Load [kW]",
        "Shaft Generator Power [kW]",
        "Load per Generator Calculated",
        "Load per Generator [% MCR]",
        "20ft Reefer Units",
        "40ft Reefer Units",
        "Reefers Onboard 20ft Equivalent",
        "Estimated Reefer Load",
        "Reefer Power [kW]",
        "Reefer Energy [kWh]",
        "Average Power per Reefer [kW]",
        "Sea Load [kW]",
        "Load from AMS [kW]",
    ],
    "Generator Running Hours And Load": [
        "DG1 Running Hours [hh:mm]",
        "DG2 Running Hours [hh:mm]",
        "DG3 Running Hours [hh:mm]",
        "DG4 Running Hours [hh:mm]",
        "Shaft Generator Running Hours [hh:mm]",
        "DG1 Load [% MCR]",
        "DG2 Load [% MCR]",
        "DG3 Load [% MCR]",
        "DG4 Load [% MCR]",
    ],
    "Fuel Consumption": [
        "Consumption ME 24 Hours [MT]",
        "Consumption DGs 24 Hours [MT]",
        "Boiler Sum",
        "Consumption Boiler 24 Hours [MT]",
        "Total Consumption 24 Hours [MT]",
        "HFO Consumption Equivalent [MT]",
        "SFOC [gr/Kwh]",
        *ME_FUEL_COLUMNS,
        *DG_FUEL_COLUMNS,
        *BOILER_FUEL_COLUMNS,
    ],
    "Performance Calculations": [
        "Calculated Slip",
        "Corrected Speed for 7% Slip",
        "Engine Miles Calculated [RPM]",
        "Engine Miles Calculated [Rev]",
        "Current Speed Calculated [kn]",
        "For Corrected Speed CP Consumption is",
        "Difference from Actual",
        "Difference Percentage",
        "For Corrected Speed with + 0.5 kn for on about CP Consumption is",
        "Difference from Actual2",
        "Difference Percentage2",
        "For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is",
        "Difference from Actual3",
        "Difference Percentage3",
    ],
    "Fresh Water And Waste": [
        "Bilge Water Produced [cbm]",
        "Bilge Water Disposed Through OWS [cbm]",
        "FW Consumed [cbm]",
        "Sludge Produced [cbm]",
        "FW Produced [cbm]",
        "FW Received [cbm]",
        "Air Cooler Air Press Drop [mmWC]",
    ],
}


st.set_page_config(page_title=APP_TITLE, layout="wide")


def inject_app_css() -> None:
    st.markdown(
        """
        <style>
        :root {
            --page-bg: #0b1018;
            --panel-bg: #111827;
            --panel-soft: #162033;
            --sidebar-bg: #0f1724;
            --border-soft: rgba(148, 163, 184, 0.22);
            --text-soft: #9ca3af;
            --text-strong: #f8fafc;
            --accent: #00d1ff;
            --accent-strong: #00b8d9;
            --accent-muted: rgba(0, 209, 255, 0.14);
            --green: #00d48d;
        }

        .stApp {
            background: linear-gradient(180deg, #101827 0%, var(--page-bg) 40%, #080d14 100%);
        }

        .block-container {
            max-width: 1280px;
            padding-top: 2.8rem;
            padding-bottom: 3rem;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, var(--sidebar-bg) 0%, #0b1018 100%);
            border-right: 1px solid var(--border-soft);
        }

        [data-testid="stHeader"] {
            background: rgba(11, 16, 24, 0.88);
            backdrop-filter: blur(8px);
        }

        h1 {
            font-size: 2.6rem;
            font-weight: 850;
            line-height: 1.06;
            margin: 0;
            color: var(--text-strong);
        }

        h2, h3 {
            font-weight: 800;
            color: var(--text-strong);
        }

        .app-header {
            padding: 1.65rem 1.9rem;
            border: 1px solid var(--border-soft);
            border-radius: 8px;
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.88));
            box-shadow: 0 20px 54px rgba(0, 0, 0, 0.30);
            margin-bottom: 1.25rem;
        }

        .app-eyebrow {
            color: var(--accent);
            text-transform: uppercase;
            font-size: 0.78rem;
            font-weight: 850;
            margin-bottom: 0.55rem;
        }

        .app-subtitle {
            color: var(--text-soft);
            font-size: 0.95rem;
            max-width: 880px;
            margin-top: 0.8rem;
        }

        .kpi-card {
            border: 1px solid var(--border-soft);
            border-top: 3px solid var(--accent);
            border-radius: 8px;
            padding: 1rem 1.05rem;
            min-height: 128px;
            background: linear-gradient(180deg, rgba(22, 32, 51, 0.98), rgba(17, 24, 39, 0.98));
            box-shadow: 0 14px 34px rgba(0, 0, 0, 0.24);
        }

        .kpi-label {
            color: #aeb8c7;
            font-size: 0.78rem;
            font-weight: 800;
            margin-bottom: 0.45rem;
        }

        .kpi-value {
            color: var(--text-strong);
            font-size: 1.9rem;
            font-weight: 850;
            line-height: 1.15;
            overflow-wrap: anywhere;
        }

        .kpi-footnote {
            color: var(--text-soft);
            font-size: 0.74rem;
            margin-top: 0.45rem;
        }

        .tone-good { --accent: #00d48d; }
        .tone-watch { --accent: #d8a545; }
        .tone-alert { --accent: #cf5f5f; }
        .tone-info { --accent: #00d1ff; }
        .tone-neutral { --accent: #9a8fcb; }

        [data-testid="stMetric"] {
            border: 1px solid var(--border-soft);
            border-top: 3px solid var(--accent);
            border-radius: 8px;
            padding: 0.95rem 1rem;
            background: linear-gradient(180deg, rgba(22, 32, 51, 0.98), rgba(17, 24, 39, 0.98));
            min-height: 104px;
            box-shadow: 0 12px 28px rgba(0, 0, 0, 0.22);
        }

        [data-testid="stMetricLabel"] p {
            color: #aeb8c7;
            font-size: 0.78rem;
            font-weight: 750;
        }

        [data-testid="stMetricValue"] {
            color: var(--text-strong);
            font-size: 1.55rem;
            font-weight: 850;
            white-space: normal;
            overflow-wrap: anywhere;
        }

        .section-note {
            color: var(--text-soft);
            font-size: 0.88rem;
            margin-top: -0.35rem;
            margin-bottom: 0.8rem;
        }

        .stDataFrame {
            border: 1px solid var(--border-soft);
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 14px 32px rgba(0, 0, 0, 0.24);
        }

        div.stButton > button {
            border-radius: 8px;
            font-weight: 800;
        }

        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--accent-strong), var(--green));
            border-color: rgba(0, 209, 255, 0.40);
            color: #061018;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header() -> None:
    st.markdown(
        """
        <div class="app-header">
            <div class="app-eyebrow">Marorka performance monitoring</div>
            <h1>Fleet Performance Dashboard</h1>
            <div class="app-subtitle">Selected vessel analysis | live API snapshot | Power Query aligned calculations</div>
        </div>
        """,
        unsafe_allow_html=True,
    )



def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(name, default) or "")
    except Exception:
        return default


def get_int_secret(name: str, default: int) -> int:
    try:
        return int(get_secret(name, str(default)))
    except ValueError:
        return default


def get_default_start_date() -> date:
    configured_start_date = get_secret("MARORKA_START_DATE")
    if configured_start_date:
        parsed = pd.to_datetime(configured_start_date, errors="coerce")
        if pd.notna(parsed):
            return parsed.date()

    configured_days_back = get_int_secret("MARORKA_DAYS_BACK", DEFAULT_DAYS_BACK)
    if configured_days_back > 0:
        return date.today() - timedelta(days=configured_days_back)

    return pd.to_datetime(DEFAULT_START_DATE).date()


def default_report_window(today: date | None = None) -> tuple[date, date]:
    """Default monthly report window: first day two months back through current month end.

    Example: any date in May 2026 -> 01/03/2026 to 31/05/2026.
    """
    today = today or date.today()

    start_month = today.month - 2
    start_year = today.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1

    start_date_value = date(start_year, start_month, 1)

    if today.month == 12:
        end_date_value = date(today.year, 12, 31)
    else:
        end_date_value = date(today.year, today.month + 1, 1) - timedelta(days=1)

    return start_date_value, end_date_value


def require_dashboard_password() -> bool:
    expected_password = get_secret("DASHBOARD_PASSWORD")
    if not expected_password:
        render_app_header()
        st.error("DASHBOARD_PASSWORD is not configured in Streamlit secrets.")
        return False

    if st.session_state.get("dashboard_authenticated"):
        return True

    render_app_header()
    entered_password = st.text_input("Dashboard password", type="password")
    if st.button("Open dashboard", type="primary"):
        if entered_password == expected_password:
            st.session_state.dashboard_authenticated = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value)
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            result.append(text)
    return result


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def date_chunks(start_date_value: date, end_date_value: date, chunk_days: int = QUERY_DATE_CHUNK_DAYS) -> list[tuple[date, date]]:
    ranges: list[tuple[date, date]] = []
    chunk_start = start_date_value
    while chunk_start <= end_date_value:
        chunk_end = min(chunk_start + timedelta(days=chunk_days - 1), end_date_value)
        ranges.append((chunk_start, chunk_end))
        chunk_start = chunk_end + timedelta(days=1)
    return ranges



def escape_odata_text(value: str) -> str:
    return value.replace("'", "''")


def build_value_filter(values: list[str]) -> str:
    return " or ".join(f"ValueDescription eq '{escape_odata_text(value)}'" for value in values)


def build_report_type_filter(report_types: list[str]) -> str:
    return " ".join(f"and ReportType ne '{escape_odata_text(report_type)}'" for report_type in report_types)


def build_ship_filter(ship_names: str | list[str]) -> str:
    if isinstance(ship_names, str):
        names = [ship_names.strip()] if ship_names.strip() else []
    else:
        names = [str(name).strip() for name in ship_names if str(name).strip()]

    names = unique_preserve_order(names)
    if not names:
        return ""
    if len(names) == 1:
        return f"ShipName eq '{escape_odata_text(names[0])}'"
    return "(" + " or ".join(f"ShipName eq '{escape_odata_text(name)}'" for name in names) + ")"


def build_query_params(
    start_date_value: date,
    end_date_value: date,
    values: list[str] | None,
    *,
    include_date_filter: bool,
    include_value_filter: bool,
    date_literal_format: str,
    ship_name: str | list[str] = "",
    date_operator: str = "ge",
    order_by_start_desc: bool = False,
    top_limit: int | None = None,
) -> dict[str, str]:
    start_datetime = start_date_value.strftime(date_literal_format)
    end_exclusive_datetime = (end_date_value + timedelta(days=1)).strftime(date_literal_format)
    filters = ["ValueDescription ne null"]

    ship_filter = build_ship_filter(ship_name)
    if ship_filter:
        filters.insert(0, ship_filter)

    if include_date_filter:
        filters.append(f"StartDateTimeGMT {date_operator} DateTime'{start_datetime}'")
        filters.append(f"StartDateTimeGMT lt DateTime'{end_exclusive_datetime}'")

    report_type_filter = build_report_type_filter(REPORT_TYPES_TO_EXCLUDE)
    if report_type_filter:
        filters.append(report_type_filter.removeprefix("and "))

    if include_value_filter and values:
        filters.append(f"({build_value_filter(values)})")

    params = {
        "$format": "json",
        "$select": ",".join(INDEX_COLUMNS + ["ValueDescription", "ReportedValue"]),
        "$filter": " and ".join(filters),
    }

    if top_limit:
        params["$top"] = str(top_limit)
    if order_by_start_desc:
        params["$orderby"] = "StartDateTimeGMT desc"

    return params


def build_vessel_query_params(start_date_value: date, end_date_value: date, date_literal_format: str) -> dict[str, str]:
    start_datetime = start_date_value.strftime(date_literal_format)
    end_exclusive_datetime = (end_date_value + timedelta(days=1)).strftime(date_literal_format)
    filters = [
        "ValueDescription ne null",
        f"StartDateTimeGMT gt DateTime'{start_datetime}'",
        f"StartDateTimeGMT lt DateTime'{end_exclusive_datetime}'",
    ]

    report_type_filter = build_report_type_filter(REPORT_TYPES_TO_EXCLUDE)
    if report_type_filter:
        filters.append(report_type_filter.removeprefix("and "))

    filters.append(f"({build_value_filter(VESSEL_DISCOVERY_VALUES)})")

    return {
        "$format": "json",
        "$select": "ShipName",
        "$filter": " and ".join(filters),
    }


def build_value_description_query_params(
    start_date_value: date,
    end_date_value: date,
    date_literal_format: str,
    ship_name: str,
) -> dict[str, str]:
    start_datetime = start_date_value.strftime(date_literal_format)
    end_exclusive_datetime = (end_date_value + timedelta(days=1)).strftime(date_literal_format)
    filters = [
        "ValueDescription ne null",
        f"ShipName eq '{escape_odata_text(ship_name)}'",
        f"StartDateTimeGMT ge DateTime'{start_datetime}'",
        f"StartDateTimeGMT lt DateTime'{end_exclusive_datetime}'",
    ]

    report_type_filter = build_report_type_filter(REPORT_TYPES_TO_EXCLUDE)
    if report_type_filter:
        filters.append(report_type_filter.removeprefix("and "))

    return {
        "$format": "json",
        "$select": "ValueDescription",
        "$filter": " and ".join(filters),
    }


def build_parameter_sets(
    start_date_value: date,
    end_date_value: date,
    values: list[str],
    date_literal_format: str,
    ship_name: str | list[str],
    query_mode: str = "Dashboard metric pull",
) -> list[dict[str, str]]:
    if query_mode == "Connection test":
        return [
            build_query_params(
                start_date_value,
                end_date_value,
                None,
                include_date_filter=False,
                include_value_filter=False,
                date_literal_format=date_literal_format,
                ship_name=ship_name,
                top_limit=10,
            )
        ]

    if query_mode == "Date sample":
        return [
            build_query_params(
                start_date_value,
                end_date_value,
                None,
                include_date_filter=True,
                include_value_filter=False,
                date_literal_format=date_literal_format,
                ship_name=ship_name,
                order_by_start_desc=True,
                top_limit=SAMPLE_ROW_LIMIT,
            )
        ]

    if query_mode == "Excel-style full pull":
        return [
            build_query_params(
                chunk_start,
                chunk_end,
                None,
                include_date_filter=True,
                include_value_filter=False,
                date_literal_format=date_literal_format,
                ship_name=ship_name,
                order_by_start_desc=True,
            )
            for chunk_start, chunk_end in date_chunks(start_date_value, end_date_value)
        ]

    ship_name_chunks = chunks(ship_name, VESSEL_QUERY_CHUNK_SIZE) if isinstance(ship_name, list) else [ship_name]
    return [
        build_query_params(
            chunk_start,
            chunk_end,
            value_chunk,
            include_date_filter=True,
            include_value_filter=True,
            date_literal_format=date_literal_format,
            ship_name=ship_name_chunk,
            order_by_start_desc=False,
        )
        for ship_name_chunk in ship_name_chunks
        for chunk_start, chunk_end in date_chunks(start_date_value, end_date_value)
        for value_chunk in chunks(values, METRIC_QUERY_CHUNK_SIZE)
    ]


def prepared_url(base_url: str, parameters: dict[str, str]) -> str:
    request = requests.Request("GET", base_url, params=parameters)
    return request.prepare().url or base_url


def make_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def extract_rows(payload: dict) -> tuple[list[dict], str | None]:
    if "d" in payload and isinstance(payload["d"], dict):
        return payload["d"].get("results", []), payload["d"].get("__next")
    return payload.get("value", []), payload.get("@odata.nextLink")


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_vessel_options(
    base_url: str,
    parameters: dict[str, str],
    page_safety_limit: int,
    auth_signature: str,
    _username: str,
    _password: str,
) -> tuple[list[str], dict[str, int | float | bool]]:
    vessels: list[str] = []
    metadata = fetch_single_field_values(
        base_url=base_url,
        parameters=parameters,
        page_safety_limit=page_safety_limit,
        username=_username,
        password=_password,
        field_name="ShipName",
        collector=vessels,
    )
    return sorted(unique_preserve_order(vessels), key=str.casefold), metadata


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_value_descriptions(
    base_url: str,
    parameters: dict[str, str],
    page_safety_limit: int,
    auth_signature: str,
    _username: str,
    _password: str,
) -> tuple[list[str], dict[str, int | float | bool]]:
    values: list[str] = []
    metadata = fetch_single_field_values(
        base_url=base_url,
        parameters=parameters,
        page_safety_limit=page_safety_limit,
        username=_username,
        password=_password,
        field_name="ValueDescription",
        collector=values,
    )
    return sorted(unique_preserve_order(values), key=str.casefold), metadata


def fetch_single_field_values(
    *,
    base_url: str,
    parameters: dict[str, str],
    page_safety_limit: int,
    username: str,
    password: str,
    field_name: str,
    collector: list[str],
) -> dict[str, int | float | bool]:
    total_pages = 0
    total_bytes = 0
    started_at = perf_counter()
    stopped_by_page_limit = False
    session = make_session()
    next_url: str | None = base_url
    local_params = parameters.copy()

    while next_url:
        total_pages += 1
        response = session.get(
            next_url,
            params=local_params if total_pages == 1 else None,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "application/json"},
            timeout=120,
        )
        total_bytes += len(response.content)
        response.raise_for_status()

        page_rows, next_link = extract_rows(response.json())
        for row in page_rows:
            value = str(row.get(field_name) or "").strip()
            if value:
                collector.append(value)

        if total_pages >= page_safety_limit and next_link:
            stopped_by_page_limit = True
            break

        next_url = urljoin(base_url, next_link) if next_link else None
        local_params = {}

    return {
        "rows": len(collector),
        "unique_values": len(set(collector)),
        "pages": total_pages,
        "downloaded_mb": round(total_bytes / 1024 / 1024, 2),
        "elapsed_seconds": round(perf_counter() - started_at, 2),
        "stopped_by_page_limit": stopped_by_page_limit,
    }


@st.cache_data(ttl=600, show_spinner=False)
def fetch_all_data(
    base_url: str,
    parameter_sets: list[dict[str, str]],
    page_safety_limit: int,
    auth_signature: str,
    _username: str,
    _password: str,
) -> tuple[pd.DataFrame, dict[str, int | float | bool]]:
    rows: list[dict] = []
    total_pages = 0
    total_bytes = 0
    started_at = perf_counter()
    stopped_by_page_limit = False
    session = make_session()

    for query_number, parameters in enumerate(parameter_sets, start=1):
        next_url: str | None = base_url
        local_params = parameters.copy()
        query_page = 0

        while next_url:
            query_page += 1
            total_pages += 1
            response = session.get(
                next_url,
                params=local_params if query_page == 1 else None,
                auth=HTTPBasicAuth(_username, _password),
                headers={"Accept": "application/json"},
                timeout=120,
            )
            total_bytes += len(response.content)
            response.raise_for_status()

            page_rows, next_link = extract_rows(response.json())
            for row in page_rows:
                row["_QueryNumber"] = query_number
            rows.extend(page_rows)

            if query_page >= page_safety_limit and next_link:
                stopped_by_page_limit = True
                break

            next_url = urljoin(base_url, next_link) if next_link else None
            local_params = {}

    metadata = {
        "rows": len(rows),
        "queries": len(parameter_sets),
        "pages": total_pages,
        "downloaded_mb": round(total_bytes / 1024 / 1024, 2),
        "elapsed_seconds": round(perf_counter() - started_at, 2),
        "stopped_by_page_limit": stopped_by_page_limit,
    }
    return pd.DataFrame(rows), metadata


def parse_datetime_column(series: pd.Series) -> pd.Series:
    text = series.astype("string")
    odata_ms = text.str.extract(r"/Date\((-?\d+)").iloc[:, 0]
    parsed_odata = pd.to_datetime(odata_ms, unit="ms", utc=True, errors="coerce")
    parsed_normal = pd.to_datetime(text, utc=True, errors="coerce")
    return parsed_normal.fillna(parsed_odata)


def prepare_raw_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    cleaned = df.copy()
    for column in INDEX_COLUMNS:
        if column not in cleaned.columns:
            cleaned[column] = pd.NA

    for column in ["StartDateTimeGMT", "EndDateTimeGMT"]:
        cleaned[column] = parse_datetime_column(cleaned[column])

    if "ReportedValue" not in cleaned.columns:
        cleaned["ReportedValue"] = pd.NA
    if "ValueDescription" not in cleaned.columns:
        cleaned["ValueDescription"] = pd.NA

    cleaned["ReportedValueNumeric"] = pd.to_numeric(cleaned["ReportedValue"], errors="coerce")
    return cleaned


def pivot_report_data(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    pivoted = (
        df.pivot_table(
            index=INDEX_COLUMNS,
            columns="ValueDescription",
            values="ReportedValue",
            aggfunc="first",
            dropna=False,
        )
        .reset_index()
        .sort_values(["ShipName", "EndDateTimeGMT", "ReportId"], na_position="last")
    )
    pivoted.columns.name = None
    return pivoted


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    for old_name, canonical_name in COLUMN_ALIASES.items():
        if old_name in result.columns and canonical_name not in result.columns:
            result = result.rename(columns={old_name: canonical_name})
        elif old_name in result.columns and canonical_name in result.columns:
            result[canonical_name] = result[canonical_name].fillna(result[old_name])
            result = result.drop(columns=[old_name])
    return result


def numeric_column(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")
    return pd.to_numeric(df[column], errors="coerce")


def first_numeric_column(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    result = pd.Series(pd.NA, index=df.index, dtype="Float64")
    for column in columns:
        if column in df.columns:
            result = result.fillna(numeric_column(df, column))
    return result


def sum_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.Series:
    available_columns = [column for column in columns if column in df.columns]
    if not available_columns:
        return pd.Series(pd.NA, index=df.index, dtype="Float64")
    numeric_values = df[available_columns].apply(pd.to_numeric, errors="coerce")
    return numeric_values.sum(axis=1, min_count=1)


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.replace(0, pd.NA)
    return numerator / denominator


def round_series(series: pd.Series, digits: int = 3) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").round(digits)


def add_power_query_calculations(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    result = normalize_columns(df)

    lap_time = numeric_column(result, "LapTime")
    draft_forward = numeric_column(result, "Draft Forward [m] (m)")
    draft_aft = numeric_column(result, "Draft Aft [m] (m)")
    engine_distance = numeric_column(result, "Engine Distance [nm]")
    distance_over_ground = numeric_column(result, "Distance Over Ground [nm]")
    shaft_rpm = numeric_column(result, "Shaft 1 RPM (rpm)")
    me_revolutions = numeric_column(result, "ME Rev Since Last Report")

    result["Average Draft [m]"] = round_series(
        pd.concat([draft_forward, draft_aft], axis=1).mean(axis=1, skipna=True)
    )
    result["Calculated Slip"] = round_series(1 - safe_divide(distance_over_ground, engine_distance))

    result["Corrected Speed for 7% Slip"] = round_series(shaft_rpm * 0.030123 * 8.3280)

    result["Consumption ME 24 Hours [MT]"] = round_series(
        safe_divide(sum_numeric_columns(result, ME_FUEL_COLUMNS) * 24, lap_time)
    )
    result["Consumption DGs 24 Hours [MT]"] = round_series(
        safe_divide(sum_numeric_columns(result, DG_FUEL_COLUMNS) * 24, lap_time)
    )
    result["Boiler Sum"] = round_series(sum_numeric_columns(result, BOILER_FUEL_COLUMNS))
    result["Consumption Boiler 24 Hours [MT]"] = round_series(
        safe_divide(sum_numeric_columns(result, BOILER_FUEL_COLUMNS) * 24, lap_time)
    )
    result["Total Consumption 24 Hours [MT]"] = round_series(
        sum_numeric_columns(
            result,
            [
                "Consumption ME 24 Hours [MT]",
                "Consumption DGs 24 Hours [MT]",
                "Consumption Boiler 24 Hours [MT]",
            ],
        )
    )

    shaft_power = first_numeric_column(result, ["Power from Torque Meter [kW]", "Total Shaft Power [kW] (kW)"])
    result["SFOC [gr/Kwh]"] = round_series(
        safe_divide(result["Consumption ME 24 Hours [MT]"], shaft_power) / 0.000024
    ).fillna(0)

    hfo_columns = [
        "Main Engine - HSHFO",
        "Diesel Generator - HSHFO",
        "Boiler - HSHFO",
        "Main Engine - VLSHFO",
        "Diesel Generator - VLSHFO",
        "Boiler - VLSHFO",
        "Main Engine - ULSHFO",
        "Diesel Generator - ULSHFO",
        "Boiler - ULSHFO",
    ]
    lfo_columns = [
        "Main Engine - HSLFO",
        "Diesel Generator - HSLFO",
        "Boiler - HSLFO",
        "Main Engine - VLSLFO",
        "Diesel Generator - VLSLFO",
        "Boiler - VLSLFO",
        "Main Engine - ULSLFO",
        "Diesel Generator - ULSLFO",
        "Boiler - ULSLFO",
    ]
    mgo_columns = [
        "Main Engine - MGO",
        "Diesel Generator - MGO",
        "Boiler - MGO",
    ]

    total_hfo = sum_numeric_columns(result, hfo_columns)
    total_lfo = safe_divide(sum_numeric_columns(result, lfo_columns), pd.Series(0.9481, index=result.index))
    total_mgo = safe_divide(sum_numeric_columns(result, mgo_columns), pd.Series(0.9415, index=result.index))
    result["HFO Consumption Equivalent [MT]"] = round_series(
        pd.concat([total_hfo, total_lfo, total_mgo], axis=1).sum(axis=1, min_count=1)
    )

    result["Engine Miles Calculated [RPM]"] = round_series(
        shaft_rpm * 0.032397 * lap_time * 8.3280
    ).fillna(0)
    result["Engine Miles Calculated [Rev]"] = round_series(
        safe_divide(me_revolutions, pd.Series(1852, index=result.index)) * 8.3280
    )

    speed_through_water = numeric_column(result, "Water speed [kn Log] (kn)")
    speed_over_ground = numeric_column(result, "Speed over ground [kn GPS] (kn)")
    current_speed = speed_through_water - speed_over_ground
    result["Current Speed Calculated [kn]"] = round_series(
        current_speed.where(result.get("StateName", "") == "Sea Passage")
    ).fillna(0)

    generator_hours = sum_numeric_columns(
        result,
        [
            "DG1 Running Time [h] (h)",
            "DG2 Running Time [h] (h)",
            "DG3 Running Time [h] (h)",
            "DG4 Running Time [h] (h)",
            "DG1 Running Hours [hh:mm]",
            "DG2 Running Hours [hh:mm]",
            "DG3 Running Hours [hh:mm]",
            "DG4 Running Hours [hh:mm]",
            "Shaft Generator Running Hours [hh:mm]",
        ],
    )
    total_electric_load = first_numeric_column(result, ["Total Electric Load [kW]", "Total DG Power [kW] (kW)"])
    result["Load per Generator Calculated"] = round_series(
        safe_divide(total_electric_load, generator_hours) * lap_time
    )
    result["Load per Generator [% MCR]"] = round_series(
        safe_divide(result["Load per Generator Calculated"], pd.Series(2900, index=result.index))
    )

    reefer_20 = numeric_column(result, "20ft Reefer Units")
    reefer_40 = numeric_column(result, "40ft Reefer Units")
    result["Reefers Onboard 20ft Equivalent"] = round_series((reefer_20 + reefer_40) * 1.66).fillna(0)
    result["Estimated Reefer Load"] = round_series(result["Reefers Onboard 20ft Equivalent"] * 3)

    corrected_speed = numeric_column(result, "Corrected Speed for 7% Slip")

    cp_consumption = (
        corrected_speed.pow(3) * 0.0141024
        + corrected_speed.pow(2) * -0.1092988
        + corrected_speed * 1.6175387
    )
    result["For Corrected Speed CP Consumption is"] = round_series(cp_consumption).fillna(0)
    result["Difference from Actual"] = round_series(
        result["For Corrected Speed CP Consumption is"] - result["Consumption ME 24 Hours [MT]"]
    )
    result["Difference Percentage"] = round_series(
        (1 - safe_divide(result["For Corrected Speed CP Consumption is"], result["Consumption ME 24 Hours [MT]"]))
        .where(result["For Corrected Speed CP Consumption is"] > 0)
    ).replace(0, pd.NA)

    corrected_speed_plus = corrected_speed + 0.5
    cp_consumption_plus = (
        corrected_speed_plus.pow(3) * 0.0141024
        + corrected_speed_plus.pow(2) * -0.1092988
        + corrected_speed_plus * 1.6175387
    )
    result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"] = round_series(
        cp_consumption_plus
    ).fillna(0)
    result["Difference from Actual2"] = round_series(
        result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"]
        - result["Consumption ME 24 Hours [MT]"]
    )
    result["Difference Percentage2"] = round_series(
        (
            1
            - safe_divide(
                result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"],
                result["Consumption ME 24 Hours [MT]"],
            )
        ).where(result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"] > 0)
    ).replace(0, pd.NA)

    result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"] = round_series(
        result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"] * 1.05
    )
    result["Difference from Actual3"] = round_series(
        result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"]
        - result["Consumption ME 24 Hours [MT]"]
    )
    result["Difference Percentage3"] = round_series(
        (
            1
            - safe_divide(
                result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"],
                result["Total Consumption 24 Hours [MT]"],
            )
        ).where(result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"] > 0)
    ).replace(0, pd.NA)

    percentage_columns = [
        "Slip Average [%]",
        "ME Load [%MCR]",
        "DG1 Load [% MCR]",
        "DG2 Load [% MCR]",
        "DG3 Load [% MCR]",
        "DG4 Load [% MCR]",
        "Bending Moments [%]",
        "Shearing Forces [%]",
        "Torsional Moments [%]",
    ]
    for column in percentage_columns:
        if column in result.columns:
            result[column] = numeric_column(result, column) / 100

    return result


@st.cache_data(ttl=1800, show_spinner=False)
def transform_report_data(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared_raw = prepare_raw_data(raw_df)
    pivoted = pivot_report_data(prepared_raw)
    pivoted = normalize_columns(pivoted)
    calculated = add_power_query_calculations(pivoted)
    return prepared_raw, calculated


def format_value(value: object) -> str:
    if pd.isna(value):
        return "-"
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.notna(numeric_value):
        if abs(numeric_value) >= 100:
            return f"{numeric_value:,.0f}"
        return f"{numeric_value:,.2f}"
    return str(value)


def format_datetime(value: object) -> str:
    if pd.isna(value):
        return "-"
    return pd.Timestamp(value).strftime(DISPLAY_DATETIME_FORMAT)


def format_percentage(value: object) -> str:
    if pd.isna(value):
        return "-"
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return "-"
    return f"{numeric_value:.1%}"


def numeric_delta(current_value: object, previous_value: object) -> str | None:
    current_numeric = pd.to_numeric(pd.Series([current_value]), errors="coerce").iloc[0]
    previous_numeric = pd.to_numeric(pd.Series([previous_value]), errors="coerce").iloc[0]
    if pd.isna(current_numeric) or pd.isna(previous_numeric):
        return None
    delta = current_numeric - previous_numeric
    if abs(delta) >= 100:
        return f"{delta:+,.0f}"
    return f"{delta:+,.2f}"


def make_excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    safe = df.copy()
    for column in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[column]):
            safe[column] = pd.to_datetime(safe[column], errors="coerce").dt.tz_localize(None)
    return safe


def latest_by_vessel(pivoted: pd.DataFrame) -> pd.DataFrame:
    if pivoted.empty or "ShipName" not in pivoted.columns:
        return pivoted
    sort_column = "EndDateTimeGMT" if "EndDateTimeGMT" in pivoted.columns else "ReportId"
    return pivoted.sort_values(sort_column).groupby("ShipName", as_index=False, dropna=False).tail(1).sort_values("ShipName")


def make_excel_file(pivoted: pd.DataFrame, raw: pd.DataFrame, latest: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        make_excel_safe(pivoted).to_excel(writer, sheet_name="Pivoted Data", index=False)
        make_excel_safe(latest).to_excel(writer, sheet_name="Latest By Vessel", index=False)
        make_excel_safe(raw).to_excel(writer, sheet_name="Raw Data", index=False)
    return output.getvalue()


def render_downloads(pivoted: pd.DataFrame, raw: pd.DataFrame, latest: pd.DataFrame, key_prefix: str) -> None:
    csv_column, excel_column = st.columns(2)
    csv_column.download_button(
        "Download pivoted CSV",
        data=pivoted.to_csv(index=False).encode("utf-8"),
        file_name="marorka_pivoted_data.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"{key_prefix}_pivoted_csv",
    )
    excel_column.download_button(
        "Download Excel workbook",
        data=make_excel_file(pivoted, raw, latest),
        file_name="marorka_dashboard_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"{key_prefix}_excel_workbook",
    )


def format_report_table_for_display(table_df: pd.DataFrame) -> pd.DataFrame:
    display_df = table_df.copy()
    percentage_columns = [
        "Calculated Slip",
        "ME Load [%MCR]",
        "Load per Generator [% MCR]",
        "Difference Percentage",
        "Difference Percentage2",
        "Difference Percentage3",
    ]

    for column in display_df.columns:
        if pd.api.types.is_datetime64_any_dtype(display_df[column]):
            display_df[column] = pd.to_datetime(display_df[column], errors="coerce").dt.strftime(DISPLAY_DATETIME_FORMAT)

    for column in percentage_columns:
        if column in display_df.columns:
            values = pd.to_numeric(display_df[column], errors="coerce")
            display_df[column] = values.map(lambda value: "-" if pd.isna(value) else f"{value:.1%}")

    numeric_columns = [
        column for column in display_df.select_dtypes(include="number").columns if column not in percentage_columns
    ]
    for column in numeric_columns:
        values = pd.to_numeric(display_df[column], errors="coerce")
        display_df[column] = values.map(lambda value: "-" if pd.isna(value) else f"{value:,.3f}")

    return display_df.fillna("-")


def display_report_table(table_df: pd.DataFrame) -> None:
    st.dataframe(format_report_table_for_display(table_df), use_container_width=True, hide_index=True)



def numeric_scalar(value: object) -> float | None:
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return None
    return float(numeric_value)


def tone_for_slip(value: object) -> str:
    numeric_value = numeric_scalar(value)
    if numeric_value is None:
        return "tone-neutral"
    if numeric_value <= 0.10:
        return "tone-good"
    if numeric_value <= 0.20:
        return "tone-watch"
    return "tone-alert"


def tone_for_me_load(value: object) -> str:
    numeric_value = numeric_scalar(value)
    if numeric_value is None:
        return "tone-neutral"
    if 0.30 <= numeric_value <= 0.85:
        return "tone-good"
    if 0.10 <= numeric_value < 0.30 or 0.85 < numeric_value <= 0.95:
        return "tone-watch"
    return "tone-alert"


def tone_for_sfoc(value: object) -> str:
    numeric_value = numeric_scalar(value)
    if numeric_value is None:
        return "tone-neutral"
    if numeric_value <= 185:
        return "tone-good"
    if numeric_value <= 205:
        return "tone-watch"
    return "tone-alert"


def tone_for_boiler(value: object) -> str:
    numeric_value = numeric_scalar(value)
    if numeric_value is None:
        return "tone-neutral"
    if numeric_value <= 0:
        return "tone-good"
    if numeric_value <= 1:
        return "tone-watch"
    return "tone-alert"


def render_kpi_card(column, label: str, value: str, footnote: str, tone: str) -> None:
    column.markdown(
        f"""
        <div class="kpi-card {tone}">
            <div class="kpi-label">{label}</div>
            <div class="kpi-value">{value}</div>
            <div class="kpi-footnote">{footnote}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def mean_metric(df: pd.DataFrame, column: str) -> object:
    if column not in df.columns:
        return pd.NA
    return pd.to_numeric(df[column], errors="coerce").mean()


def sum_metric(df: pd.DataFrame, column: str) -> object:
    if column not in df.columns:
        return pd.NA
    return pd.to_numeric(df[column], errors="coerce").sum(min_count=1)


def filter_by_numeric_range(df: pd.DataFrame, column: str, value_range: tuple[float, float] | None) -> pd.DataFrame:
    if value_range is None or column not in df.columns:
        return df
    values = pd.to_numeric(df[column], errors="coerce")
    minimum_value, maximum_value = value_range
    return df[(values >= minimum_value) & (values <= maximum_value)]


def apply_dashboard_filters(
    df: pd.DataFrame,
    selected_vessels: list[str],
    selected_report_types: list[str],
    selected_states: list[str],
    numeric_ranges: dict[str, tuple[float, float] | None],
    search_text: str,
    start_date_filter: date | None = None,
    end_date_filter: date | None = None,
) -> pd.DataFrame:
    filtered = df.copy()

    if start_date_filter is not None and "EndDateTimeGMT" in filtered.columns:
        filtered = filtered[filtered["EndDateTimeGMT"] >= pd.Timestamp(start_date_filter, tz="UTC")]
    if end_date_filter is not None and "EndDateTimeGMT" in filtered.columns:
        filtered = filtered[filtered["EndDateTimeGMT"] < pd.Timestamp(end_date_filter + timedelta(days=1), tz="UTC")]
    if selected_vessels:
        filtered = filtered[filtered["ShipName"].isin(selected_vessels)]
    if selected_report_types:
        filtered = filtered[filtered["ReportType"].isin(selected_report_types)]
    if selected_states:
        filtered = filtered[filtered["StateName"].isin(selected_states)]

    for column, value_range in numeric_ranges.items():
        filtered = filter_by_numeric_range(filtered, column, value_range)

    if search_text.strip():
        search_value = search_text.strip().casefold()
        searchable = filtered.astype("string").apply(
            lambda column: column.str.casefold().str.contains(search_value, na=False)
        )
        filtered = filtered[searchable.any(axis=1)]

    return filtered


def stable_widget_key(prefix: str, column: str) -> str:
    digest = sha256(column.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def numeric_filter_columns(df: pd.DataFrame) -> list[str]:
    excluded_columns = {"ReportId", "_QueryNumber"}
    options: list[str] = []
    for column in df.columns:
        if column in excluded_columns or pd.api.types.is_datetime64_any_dtype(df[column]):
            continue
        if pd.to_numeric(df[column], errors="coerce").notna().any():
            options.append(column)
    return options


def slider_step(minimum_value: float, maximum_value: float) -> float:
    value_range = maximum_value - minimum_value
    if value_range <= 2:
        return 0.01
    if value_range <= 100:
        return 0.1
    return 1.0


def render_numeric_range_filters(
    df: pd.DataFrame,
    *,
    key_prefix: str,
    label: str = "Numeric columns",
) -> dict[str, tuple[float, float] | None]:
    numeric_options = numeric_filter_columns(df)
    selected_key = f"{key_prefix}_columns"
    previous_columns = st.session_state.get(selected_key, [])
    if not isinstance(previous_columns, list):
        previous_columns = []
    numeric_options = unique_preserve_order(previous_columns + numeric_options)

    selected_columns = st.multiselect(
        label,
        options=numeric_options,
        default=[],
        key=selected_key,
        help="Choose any numeric column loaded from the API or calculated by the dashboard.",
    )

    ranges: dict[str, tuple[float, float] | None] = {}
    for column in selected_columns:
        if column not in df.columns:
            st.caption(f"{column}: kept, but not returned in the current loaded data.")
            continue

        numeric_values = pd.to_numeric(df[column], errors="coerce").dropna()
        if numeric_values.empty:
            st.caption(f"{column}: kept, but no numeric values are available in the current loaded data.")
            continue

        minimum_value = float(numeric_values.min())
        maximum_value = float(numeric_values.max())
        step = slider_step(minimum_value, maximum_value)
        key = stable_widget_key(key_prefix, column)

        st.caption(f"{column}: loaded range {format_value(minimum_value)} to {format_value(maximum_value)}")
        low_column, high_column = st.columns(2)
        low_value = low_column.number_input(
            "Min",
            value=float(st.session_state.get(f"{key}_min", minimum_value)),
            step=step,
            format="%.3f",
            key=f"{key}_min",
            help=f"Minimum {column}",
        )
        high_value = high_column.number_input(
            "Max",
            value=float(st.session_state.get(f"{key}_max", maximum_value)),
            step=step,
            format="%.3f",
            key=f"{key}_max",
            help=f"Maximum {column}",
        )

        low_value = float(low_value)
        high_value = float(high_value)
        if low_value > high_value:
            low_value, high_value = high_value, low_value
        ranges[column] = (low_value, high_value)

    return ranges


def render_dashboard_kpis(filtered_df: pd.DataFrame, boiler_df: pd.DataFrame) -> None:
    latest_value = filtered_df["EndDateTimeGMT"].max() if "EndDateTimeGMT" in filtered_df.columns and not filtered_df.empty else pd.NA
    slip_value = mean_metric(filtered_df, "Calculated Slip")
    me_load_value = mean_metric(filtered_df, "ME Load [%MCR]")
    sfoc_value = mean_metric(filtered_df, "SFOC [gr/Kwh]")
    boiler_value = sum_metric(boiler_df, "Boiler Sum")

    kpi_columns = st.columns(4)
    render_kpi_card(kpi_columns[0], "Average of Calculated Slip", format_percentage(slip_value), "Main filters", tone_for_slip(slip_value))
    render_kpi_card(kpi_columns[1], "Average of ME Load [%MCR]", format_percentage(me_load_value), "Main filters", tone_for_me_load(me_load_value))
    render_kpi_card(kpi_columns[2], "Average of SFOC [gr/Kwh]", format_value(sfoc_value), "Main filters", tone_for_sfoc(sfoc_value))
    render_kpi_card(kpi_columns[3], "Sum of Boiler Sum", format_value(boiler_value), "Independent boiler filters", tone_for_boiler(boiler_value))

    context_columns = st.columns(3)
    context_columns[0].metric("Filtered reports", f"{filtered_df['ReportId'].nunique():,}")
    context_columns[1].metric("Filtered vessels", f"{filtered_df['ShipName'].nunique():,}")
    context_columns[2].metric("Latest GMT", format_datetime(latest_value))

    if len(boiler_df) != len(filtered_df):
        st.caption(
            f"Boiler KPI uses {len(boiler_df):,} rows from its independent filter set; "
            f"the other KPIs use {len(filtered_df):,} rows from the main filters."
        )


def render_dashboard_table(filtered_df: pd.DataFrame, visible_columns: list[str]) -> None:
    available_columns = [column for column in visible_columns if column in filtered_df.columns]
    if not available_columns:
        available_columns = filtered_df.columns.tolist()
    table_df = filtered_df.sort_values("EndDateTimeGMT", ascending=False)[available_columns]
    display_report_table(table_df)


def render_operational_dashboard(filtered_df: pd.DataFrame, boiler_df: pd.DataFrame, visible_columns: list[str]) -> None:
    if filtered_df.empty:
        st.warning("No reports match the current filters.")
        return

    st.markdown("### Fleet KPIs")
    st.markdown(
        '<div class="section-note">Slip, ME load, and SFOC use the main dashboard filters. Boiler uses its own independent filter set.</div>',
        unsafe_allow_html=True,
    )
    render_dashboard_kpis(filtered_df, boiler_df)

    st.markdown("### Latest Report By Vessel")
    latest_columns = [column for column in DEFAULT_TABLE_COLUMNS if column in filtered_df.columns]
    display_report_table(latest_by_vessel(filtered_df)[latest_columns])

    st.markdown("### Filtered Report Table")
    render_dashboard_table(filtered_df, visible_columns)


def report_selector(pivot_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series | None]:
    vessel_options = sorted(pivot_df["ShipName"].dropna().unique().tolist())
    selected_vessel = st.selectbox("Report vessel", vessel_options)
    vessel_df = pivot_df[pivot_df["ShipName"] == selected_vessel].sort_values("EndDateTimeGMT", ascending=False)

    report_options = [
        {
            "ReportId": row["ReportId"],
            "Label": f"{format_datetime(row['EndDateTimeGMT'])} GMT | {row.get('ReportType', '-')} | {row.get('StateName', '-')}",
        }
        for _, row in vessel_df.iterrows()
    ]

    selected_label = st.selectbox("Report date/time", [option["Label"] for option in report_options])
    selected_report_id = next(option["ReportId"] for option in report_options if option["Label"] == selected_label)
    selected_index = vessel_df.index[vessel_df["ReportId"] == selected_report_id][0]
    selected_row = vessel_df.loc[selected_index]

    chronological = vessel_df.sort_values("EndDateTimeGMT")
    previous_rows = chronological[chronological["EndDateTimeGMT"] < selected_row["EndDateTimeGMT"]]
    previous_row = previous_rows.iloc[-1] if not previous_rows.empty else None
    return vessel_df, selected_row, previous_row


def render_metric_cards(row: pd.Series, previous_row: pd.Series | None) -> None:
    available_metrics = [(label, column) for label, column in KEY_METRICS if column in row.index]
    for chunk_start in range(0, len(available_metrics), 5):
        columns = st.columns(min(5, len(available_metrics) - chunk_start))
        for metric_column, (label, source_column) in zip(columns, available_metrics[chunk_start : chunk_start + 5]):
            delta = None
            if previous_row is not None and source_column in previous_row.index:
                delta = numeric_delta(row[source_column], previous_row[source_column])
            metric_column.metric(label, format_value(row[source_column]), delta=delta)


def section_dataframe(row: pd.Series, section_columns: list[str]) -> pd.DataFrame:
    records = []
    for column in section_columns:
        if column in row.index and pd.notna(row[column]):
            records.append({"Parameter": column, "Value": format_value(row[column])})
    return pd.DataFrame(records)


def render_report_presentation(pivot_df: pd.DataFrame) -> None:
    st.markdown("### Single Report Detail")
    st.markdown(
        '<div class="section-note">Select one vessel and report timestamp to review calculated performance, consumption, and operating data.</div>',
        unsafe_allow_html=True,
    )
    vessel_df, selected_row, previous_row = report_selector(pivot_df)

    header_columns = st.columns([2, 1, 1, 1])
    header_columns[0].markdown(f"### {selected_row.get('ShipName', '-')}")
    header_columns[1].metric("Report Type", selected_row.get("ReportType", "-"))
    header_columns[2].metric("State", selected_row.get("StateName", "-"))
    header_columns[3].metric("Report ID", selected_row.get("ReportId", "-"))

    time_columns = st.columns(3)
    time_columns[0].metric("Start GMT", format_datetime(selected_row.get("StartDateTimeGMT")))
    time_columns[1].metric("End GMT", format_datetime(selected_row.get("EndDateTimeGMT")))
    time_columns[2].metric("Lap Time", format_value(selected_row.get("LapTime")))

    st.markdown("### Key Metrics")
    render_metric_cards(selected_row, previous_row)
    st.caption("Deltas compare against the previous report for the same vessel when numeric values are available.")

    st.markdown("### Report Sections")
    section_names = list(REPORT_SECTIONS.keys())
    for chunk_start in range(0, len(section_names), 2):
        columns = st.columns(2)
        for section_column, section_name in zip(columns, section_names[chunk_start : chunk_start + 2]):
            with section_column:
                section = section_dataframe(selected_row, REPORT_SECTIONS[section_name])
                st.subheader(section_name)
                if section.empty:
                    st.info("No returned values for this section.")
                else:
                    st.dataframe(section, use_container_width=True, hide_index=True)

    trend_columns = [
        "Engine Distance [nm]",
        "Distance Over Ground [nm]",
        "Power from Torque Meter [kW]",
        "Total Electric Load [kW]",
        "Reefer Power [kW]",
    ]
    available_trends = [column for column in trend_columns if column in vessel_df.columns]
    if available_trends:
        st.subheader("Recent Numeric Trend")
        trend_df = vessel_df.sort_values("EndDateTimeGMT")[["EndDateTimeGMT"] + available_trends].copy()
        for column in available_trends:
            trend_df[column] = pd.to_numeric(trend_df[column], errors="coerce")
        trend_df = trend_df.set_index("EndDateTimeGMT").dropna(how="all")
        if not trend_df.empty:
            st.line_chart(trend_df)


def render_data_tables(filtered_pivot: pd.DataFrame, filtered_raw: pd.DataFrame, latest_df: pd.DataFrame) -> None:
    render_downloads(filtered_pivot, filtered_raw, latest_df, key_prefix="export_tab")

    st.subheader("Pivoted Data")
    st.dataframe(filtered_pivot.sort_values("EndDateTimeGMT", ascending=False), use_container_width=True, hide_index=True)

    st.subheader("Raw Data")
    raw_sort_columns = [column for column in ["ShipName", "EndDateTimeGMT"] if column in filtered_raw.columns]
    if raw_sort_columns:
        filtered_raw = filtered_raw.sort_values(raw_sort_columns, ascending=[True, False][: len(raw_sort_columns)])
    st.dataframe(filtered_raw, use_container_width=True, hide_index=True)


def render_validation_table(pivot_df: pd.DataFrame) -> None:
    st.markdown("### Power Query Logic Validation")
    st.caption("Checks key calculated fields for missing values, ranges, and formula consistency.")

    checks: list[dict[str, str]] = []

    def add_check(name: str, condition: bool, detail: str) -> None:
        checks.append({"Check": name, "Status": "OK" if condition else "Review", "Detail": detail})

    required_columns = [
        "Average Draft [m]",
        "Calculated Slip",
        "Corrected Speed for 7% Slip",
        "Consumption ME 24 Hours [MT]",
        "Consumption DGs 24 Hours [MT]",
        "Consumption Boiler 24 Hours [MT]",
        "Total Consumption 24 Hours [MT]",
        "HFO Consumption Equivalent [MT]",
        "SFOC [gr/Kwh]",
        "For Corrected Speed CP Consumption is",
    ]

    for column in required_columns:
        add_check(column, column in pivot_df.columns, "Column present" if column in pivot_df.columns else "Column missing")

    if "Corrected Speed for 7% Slip" in pivot_df.columns:
        values = pd.to_numeric(pivot_df["Corrected Speed for 7% Slip"], errors="coerce")
        non_null = values.dropna()
        add_check(
            "Corrected speed range",
            non_null.empty or non_null.between(0, 35).all(),
            "No numeric values" if non_null.empty else f"Loaded range: {non_null.min():.3f} to {non_null.max():.3f}",
        )

    if "Calculated Slip" in pivot_df.columns:
        values = pd.to_numeric(pivot_df["Calculated Slip"], errors="coerce")
        non_null = values.dropna()
        add_check(
            "Calculated slip range",
            non_null.empty or non_null.between(-0.5, 0.8).all(),
            "No numeric values" if non_null.empty else f"Loaded range: {non_null.min():.3%} to {non_null.max():.3%}",
        )

    total_columns = [
        "Consumption ME 24 Hours [MT]",
        "Consumption DGs 24 Hours [MT]",
        "Consumption Boiler 24 Hours [MT]",
        "Total Consumption 24 Hours [MT]",
    ]
    if set(total_columns).issubset(pivot_df.columns):
        expected_total = (
            pd.to_numeric(pivot_df["Consumption ME 24 Hours [MT]"], errors="coerce")
            + pd.to_numeric(pivot_df["Consumption DGs 24 Hours [MT]"], errors="coerce")
            + pd.to_numeric(pivot_df["Consumption Boiler 24 Hours [MT]"], errors="coerce")
        ).round(3)
        actual_total = pd.to_numeric(pivot_df["Total Consumption 24 Hours [MT]"], errors="coerce").round(3)
        max_diff = (expected_total - actual_total).abs().max()
        add_check(
            "Total consumption formula",
            pd.isna(max_diff) or max_diff <= 0.001,
            "No comparable values" if pd.isna(max_diff) else f"Max difference: {max_diff:.6f}",
        )

    if {"Shaft 1 RPM (rpm)", "Corrected Speed for 7% Slip"}.issubset(pivot_df.columns):
        expected_speed = round_series(pd.to_numeric(pivot_df["Shaft 1 RPM (rpm)"], errors="coerce") * 0.030123 * 8.3280)
        actual_speed = pd.to_numeric(pivot_df["Corrected Speed for 7% Slip"], errors="coerce").round(3)
        max_diff = (expected_speed - actual_speed).abs().max()
        add_check(
            "Corrected speed formula uses Power Query constant 8.3280",
            pd.isna(max_diff) or max_diff <= 0.001,
            "No comparable values" if pd.isna(max_diff) else f"Max difference: {max_diff:.6f}",
        )

    if "For Corrected Speed CP Consumption is" in pivot_df.columns and "Corrected Speed for 7% Slip" in pivot_df.columns:
        speed = pd.to_numeric(pivot_df["Corrected Speed for 7% Slip"], errors="coerce")
        expected_cp = round_series(speed.pow(3) * 0.0141024 + speed.pow(2) * -0.1092988 + speed * 1.6175387)
        actual_cp = pd.to_numeric(pivot_df["For Corrected Speed CP Consumption is"], errors="coerce").round(3)
        max_diff = (expected_cp - actual_cp).abs().max()
        add_check(
            "CP consumption formula uses Power Query coefficients",
            pd.isna(max_diff) or max_diff <= 0.001,
            "No comparable values" if pd.isna(max_diff) else f"Max difference: {max_diff:.6f}",
        )

    st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)

    st.markdown("### Column Diagnostics")
    diagnostics = pd.DataFrame(
        {
            "Column": pivot_df.columns,
            "Non-null values": [pivot_df[column].notna().sum() for column in pivot_df.columns],
            "Null values": [pivot_df[column].isna().sum() for column in pivot_df.columns],
        }
    )
    st.dataframe(diagnostics, use_container_width=True, hide_index=True)


def main() -> None:
    inject_app_css()

    if not require_dashboard_password():
        st.stop()

    render_app_header()

    with st.sidebar:
        username = get_secret("MARORKA_USERNAME")
        password = get_secret("MARORKA_PASSWORD")
        api_base_url = get_secret("MARORKA_BASE_URL", BASE_URL).strip() or BASE_URL
        page_safety_limit = get_int_secret("MARORKA_PAGE_SAFETY_LIMIT", PAGE_SAFETY_LIMIT)
        query_mode = "Dashboard metric pull"
        date_format_label = "Date only"

        st.header("Data Window")
        default_start_date, default_end_date = default_report_window()
        start_date_input = st.date_input("Start date", value=default_start_date, format=UI_DATE_INPUT_FORMAT)
        end_date_input = st.date_input("End date", value=default_end_date, format=UI_DATE_INPUT_FORMAT)
        st.caption("Date format: DD/MM/YYYY")

        if end_date_input < start_date_input:
            st.warning("End date must be on or after start date.")
            st.stop()

        if not username or not password:
            st.error("Marorka API credentials are not configured. Add MARORKA_USERNAME and MARORKA_PASSWORD in Streamlit secrets.")
            st.stop()

        auth_signature = sha256(f"{username}:{password}".encode("utf-8")).hexdigest()

        refresh_api = st.button("Refresh API data", use_container_width=True)
        if refresh_api:
            fetch_vessel_options.clear()
            fetch_value_descriptions.clear()
            fetch_all_data.clear()
            transform_report_data.clear()

        selected_group = st.selectbox(
            "Vessel group",
            options=["Single vessel"] + list(VESSEL_GROUPS.keys()),
            key="api_vessel_group_select",
        )

        if selected_group == "Single vessel":
            single_vessel = st.selectbox(
                "Vessel to load",
                options=[""] + VESSEL_OPTIONS,
                key="api_ship_name_select",
            )
            api_selected_vessels = [single_vessel] if single_vessel else []
        else:
            api_selected_vessels = st.multiselect(
                "Vessels to load",
                options=VESSEL_GROUPS[selected_group],
                default=VESSEL_GROUPS[selected_group],
                key="api_vessels_multiselect",
            )

        api_ship_name = ", ".join(api_selected_vessels)
        selected_values = DEFAULT_VALUES
        st.caption(
            f"Dashboard will load {len(selected_values):,} required API variables for "
            f"{len(api_selected_vessels):,} vessel(s)."
        )
        load_fetch = st.button("Load dashboard data", type="primary", use_container_width=True, disabled=not bool(api_selected_vessels))

    active_request = {
        "start_date": start_date_input.isoformat(),
        "end_date": end_date_input.isoformat(),
        "vessels": "|".join(api_selected_vessels),
        "values_signature": sha256("|".join(selected_values).encode("utf-8")).hexdigest(),
    }

    if load_fetch:
        if not api_selected_vessels:
            st.warning("Select at least one vessel before loading dashboard data.")
            st.stop()
        st.session_state.active_api_request = active_request

    if refresh_api and api_selected_vessels:
        st.session_state.active_api_request = active_request

    if not api_selected_vessels:
        st.info("Select a date range and at least one vessel, then click Load dashboard data.")
        st.stop()

    if st.session_state.get("active_api_request") != active_request:
        st.info("Click Load dashboard data to pull Marorka reports for the selected date range and vessel.")
        st.stop()

    parameter_sets = build_parameter_sets(
        start_date_input,
        end_date_input,
        selected_values,
        DATE_LITERAL_FORMATS[date_format_label],
        api_selected_vessels,
        query_mode=query_mode,
    )

    try:
        with st.spinner("Loading dashboard data from Marorka..."):
            raw_df, fetch_metadata = fetch_all_data(
                api_base_url,
                parameter_sets,
                page_safety_limit,
                auth_signature,
                username,
                password,
            )
    except requests.HTTPError as exc:
        response_text = exc.response.text[:1000] if exc.response is not None else str(exc)
        status_code = exc.response.status_code if exc.response is not None else "unknown"
        st.error(f"Marorka API returned HTTP {status_code}: {response_text}")
        if exc.response is not None and exc.response.request is not None:
            failed_url = exc.response.request.url
            st.caption(f"Failed request URL length: {len(failed_url):,} characters")
            with st.expander("Failed request URL", expanded=False):
                st.code(failed_url, language="text")
        st.stop()
    except Exception as exc:
        st.error(f"Could not load Marorka data: {exc}")
        st.stop()

    raw_df, pivot_df = transform_report_data(raw_df)

    if pivot_df.empty:
        st.warning("No data returned for the selected date and metric filters.")
        st.stop()

    with st.sidebar:
        st.header("Dashboard Filters")
        vessel_options = sorted(pivot_df["ShipName"].dropna().unique().tolist())
        raw_vessel_options = sorted(raw_df["ShipName"].dropna().unique().tolist()) if "ShipName" in raw_df.columns else []
        loaded_start_date = start_date_input
        loaded_end_date = end_date_input
        selected_vessels: list[str] = []

        with st.expander("Loaded data coverage"):
            st.metric("API rows", f"{len(raw_df):,}")
            st.metric("Reports", f"{pivot_df['ReportId'].nunique():,}")
            st.metric("Vessels", f"{len(vessel_options):,}")
            st.metric("API queries/pages", f"{fetch_metadata['queries']}/{fetch_metadata['pages']}")
            st.metric("Downloaded MB", fetch_metadata["downloaded_mb"])
            st.metric("Elapsed sec", fetch_metadata["elapsed_seconds"])
            if fetch_metadata.get("stopped_by_page_limit"):
                st.warning("The API fetch reached the safety page limit before Marorka finished paging.")

            vessel_lookup = st.text_input("Find loaded vessel", key="coverage_vessel_lookup")
            if vessel_lookup.strip():
                needle = vessel_lookup.strip().casefold()
                matches = [vessel for vessel in raw_vessel_options if needle in vessel.casefold()]
                if matches:
                    st.write(", ".join(matches[:20]))
                else:
                    st.warning("No matching vessel name was returned by the API for this data window.")

        if vessel_options:
            st.caption(f"Loaded vessel: {', '.join(vessel_options)}")

        report_type_options = sorted(pivot_df["ReportType"].dropna().unique().tolist())
        selected_report_types = st.multiselect("Report types", options=report_type_options, default=[], key="filter_report_types")

        state_options = sorted(pivot_df["StateName"].dropna().unique().tolist())
        selected_states = st.multiselect("States", options=state_options, default=[], key="filter_states")

        search_text = st.text_input("Table search", key="filter_search_text")

        with st.expander("Numeric filters"):
            numeric_ranges = render_numeric_range_filters(pivot_df, key_prefix="filter_numeric", label="Columns to filter")

        with st.expander("Boiler KPI Filters"):
            st.caption("These filters affect only the Sum of Boiler Sum KPI.")
            boiler_vessels: list[str] = []
            boiler_date_range = st.date_input(
                "Boiler date range",
                value=(loaded_start_date, loaded_end_date),
                format=UI_DATE_INPUT_FORMAT,
                key="filter_boiler_date_range",
            )
            if isinstance(boiler_date_range, tuple) and len(boiler_date_range) == 2:
                boiler_start_date, boiler_end_date = boiler_date_range
            else:
                boiler_start_date, boiler_end_date = loaded_start_date, loaded_end_date

            boiler_report_types = st.multiselect("Boiler report types", options=report_type_options, default=[], key="filter_boiler_report_types")
            boiler_states = st.multiselect("Boiler states", options=state_options, default=[], key="filter_boiler_states")
            boiler_numeric_ranges = render_numeric_range_filters(pivot_df, key_prefix="filter_boiler_numeric", label="Boiler KPI numeric columns")

        with st.expander("Table columns"):
            default_visible_columns = [column for column in DEFAULT_TABLE_COLUMNS if column in pivot_df.columns]
            visible_columns = st.multiselect(
                "Visible columns",
                options=pivot_df.columns.tolist(),
                default=default_visible_columns,
                key="filter_visible_columns",
            )

    filtered_pivot = apply_dashboard_filters(
        pivot_df,
        selected_vessels,
        selected_report_types,
        selected_states,
        numeric_ranges,
        search_text,
    )

    boiler_filtered_pivot = apply_dashboard_filters(
        pivot_df,
        boiler_vessels,
        boiler_report_types,
        boiler_states,
        boiler_numeric_ranges,
        "",
        boiler_start_date,
        boiler_end_date,
    )

    dashboard_tab, report_tab, data_tab, validation_tab = st.tabs([
        "Dashboard",
        "Single Report",
        "Data Export",
        "Validation",
    ])

    with dashboard_tab:
        render_operational_dashboard(filtered_pivot, boiler_filtered_pivot, visible_columns)

    with report_tab:
        if filtered_pivot.empty:
            st.warning("No reports match the current filters.")
        else:
            render_report_presentation(filtered_pivot)

    with data_tab:
        latest_df = latest_by_vessel(filtered_pivot)
        filtered_raw = raw_df
        if "ReportId" in raw_df.columns and "ReportId" in filtered_pivot.columns:
            filtered_raw = raw_df[raw_df["ReportId"].isin(filtered_pivot["ReportId"].unique())]
        render_data_tables(filtered_pivot, filtered_raw, latest_df)

    with validation_tab:
        render_validation_table(pivot_df)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        st.error("App crashed during startup.")
        st.code(traceback.format_exc())
        raise exc
