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


APP_TITLE = "Magic Noon alla Mantalos"
BASE_URL = "https://online.marorka.com/Odata/v1/ODataService.svc/ReportData"
DEFAULT_DAYS_BACK = 30
DEFAULT_START_DATE = "2026-01-01"
DEFAULT_API_SHIP_FILTER = ""
PAGE_SAFETY_LIMIT = 2000
SAMPLE_ROW_LIMIT = 100
METRIC_QUERY_CHUNK_SIZE = 8

QUERY_MODES = [
    "Excel-style full pull",
    "Connection test",
    "Date sample",
    "Selected metric pull",
]

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

DEFAULT_VALUES = [
    "Steaming Time Since Last Report [hh:mm]",
    "Draft Forward [m] (m)",
    "Draft Aft [m] (m)",
    "Engine Distance [nm]",
    "Distance Over Ground [nm]",
    "Shaft 1 RPM (rpm)",
    "ME Rev Since Last Report",
    "Water speed [kn Log] (kn)",
    "Speed over ground [kn GPS] (kn)",
    "Current Speed [kn]",
    "ME Load [%MCR]",
    "Power from Torque Meter [kW]",
    "Main Engine - HSHFO",
    "Main Engine - HSLFO",
    "Main Engine - MGO",
    "Main Engine - ULSHFO",
    "Main Engine - ULSLFO",
    "Main Engine - VLSHFO",
    "Main Engine - VLSLFO",
    "Diesel Generators - HSHFO",
    "Diesel Generators - HSLFO",
    "Diesel Generators - MGO",
    "Diesel Generators - ULSHFO",
    "Diesel Generators - ULSLFO",
    "Diesel Generators - VLSHFO",
    "Diesel Generators - VLSLFO",
    "Boiler - HSHFO",
    "Boiler - HSLFO",
    "Boiler - MGO",
    "Boiler - ULSHFO",
    "Boiler - ULSLFO",
    "Boiler - VLSHFO",
    "Boiler - VLSLFO",
    "Total DG Power [kW] (kW)",
    "DG1 Running Hours [hh:mm]",
    "DG2 Running Hours [hh:mm]",
    "DG3 Running Hours [hh:mm]",
    "DG4 Running Hours [hh:mm]",
    "Shaft Generator Running Hours [hh:mm]",
    "DG1 Load [% MCR]",
    "DG2 Load [% MCR]",
    "DG3 Load [% MCR]",
    "DG4 Load [% MCR]",
    "Speed Ordered by the Charterers [kn]",
    "Shaft Generator Power [kW]",
    "Reefer Power [kW]",
    "Reefer Energy [kWh]",
    "Average Power per Reefer [kW]",
    "Bilge Water Produced [cbm]",
    "Bilge Water Disposed Through OWS [cbm]",
    "FW Consumed [cbm]",
    "Sludge Produced [cbm]",
    "FW Produced [cbm]",
    "FW Received [cbm]",
    "Air Cooler Air Press Drop [mmWC]",
    "Sea Load [kW]",
    "Load from AMS [kW]",
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
    ("Torque Power", "Total Shaft Power [kW] (kW)"),
    ("Total DG Power", "Total DG Power [kW] (kW)"),
    ("Reefer Power", "Reefer Power [kW]"),
    ("Average Power / Reefer", "Average Power per Reefer [kW]"),
]

REPORT_SECTIONS = {
    "Navigation": [
        "Steaming Time Since Last Report [hh:mm]",
        "Engine Distance [nm]",
        "Distance Over Ground [nm]",
        "Water speed [kn Log] (kn)",
        "Speed over ground [kn GPS] (kn)",
        "Current Speed [kn]",
        "Speed Ordered by the Charterers [kn]",
    ],
    "Draft And Propulsion": [
        "Draft Forward [m] (m)",
        "Draft Aft [m] (m)",
        "Shaft 1 RPM (rpm)",
        "ME Rev Since Last Report",
        "ME Load [%MCR]",
        "Power from Torque Meter [kW]",
    ],
    "Electrical And Reefers": [
        "Total DG Power [kW] (kW)",
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
        "Main Engine - HSHFO",
        "Main Engine - HSLFO",
        "Main Engine - MGO",
        "Main Engine - ULSHFO",
        "Main Engine - ULSLFO",
        "Main Engine - VLSHFO",
        "Main Engine - VLSLFO",
        "Diesel Generators - HSHFO",
        "Diesel Generators - HSLFO",
        "Diesel Generators - MGO",
        "Diesel Generators - ULSHFO",
        "Diesel Generators - ULSLFO",
        "Diesel Generators - VLSHFO",
        "Diesel Generators - VLSLFO",
        "Boiler - HSHFO",
        "Boiler - HSLFO",
        "Boiler - MGO",
        "Boiler - ULSHFO",
        "Boiler - ULSLFO",
        "Boiler - VLSHFO",
        "Boiler - VLSLFO",
    ],
    "Performance Calculations": [
        "Average Draft [m]",
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
    "Total DG Power [kW] (kW)",
    "Load per Generator [% MCR]",
    "Total Shaft Power [kW] (kW)",
    "SFOC [gr/Kwh]",
    "Total Number Reefer Units (20 and 40ft)",
    "Reefers Onboard 20ft Equivalent",
    "Estimated Reefer Load",
    "Reefer Power [kW]",
    "Average Power per Reefer [kW]",
]

NUMERIC_FILTER_COLUMNS = [
    ("ME Load >= ", "ME Load [%MCR]"),
    ("Total Consumption 24h >= ", "Total Consumption 24 Hours [MT]"),
    ("ME Consumption 24h >= ", "Consumption ME 24 Hours [MT]"),
    ("DG Load >= ", "Load per Generator [% MCR]"),
    ("Reefer Power >= ", "Reefer Power [kW]"),
    ("SOG >= ", "Speed over ground [kn GPS] (kn)"),
]

BOILER_FILTER_COLUMNS = [
    ("Boiler Sum >= ", "Boiler Sum"),
    ("Boiler 24h Consumption >= ", "Consumption Boiler 24 Hours [MT]"),
]


st.set_page_config(page_title=APP_TITLE, layout="wide")


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


def require_dashboard_password() -> bool:
    expected_password = get_secret("DASHBOARD_PASSWORD")
    if not expected_password:
        st.title(APP_TITLE)
        st.error("DASHBOARD_PASSWORD is not configured in Streamlit secrets.")
        return False

    if st.session_state.get("dashboard_authenticated"):
        return True

    st.title(APP_TITLE)
    entered_password = st.text_input("Dashboard password", type="password")
    if st.button("Open dashboard", type="primary"):
        if entered_password == expected_password:
            st.session_state.dashboard_authenticated = True
            st.rerun()
        st.error("Incorrect password.")
    return False


def escape_odata_text(value: str) -> str:
    return value.replace("'", "''")


def build_value_filter(values: list[str]) -> str:
    return " or ".join(
        f"ValueDescription eq '{escape_odata_text(value)}'" for value in values
    )


def build_report_type_filter(report_types: list[str]) -> str:
    return " ".join(
        f"and ReportType ne '{escape_odata_text(report_type)}'"
        for report_type in report_types
    )


def chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def build_query_params(
    start_date_value: date,
    end_date_value: date,
    values: list[str] | None,
    *,
    include_date_filter: bool,
    include_value_filter: bool,
    date_literal_format: str,
    ship_name: str = "",
    date_operator: str = "ge",
    order_by_start_desc: bool = False,
    top_limit: int | None = None,
) -> dict[str, str]:
    start_datetime = start_date_value.strftime(date_literal_format)
    end_exclusive_datetime = (end_date_value + timedelta(days=1)).strftime(date_literal_format)
    report_type_filter = build_report_type_filter(REPORT_TYPES_TO_EXCLUDE)
    filters = ["ValueDescription ne null"]

    if ship_name.strip():
        filters.insert(0, f"ShipName eq '{escape_odata_text(ship_name.strip())}'")

    if include_date_filter:
        filters.append(f"StartDateTimeGMT {date_operator} DateTime'{start_datetime}'")
        filters.append(f"StartDateTimeGMT lt DateTime'{end_exclusive_datetime}'")

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


def build_parameter_sets(
    query_mode: str,
    start_date_value: date,
    end_date_value: date,
    values: list[str],
    date_literal_format: str,
    ship_name: str,
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
                start_date_value,
                end_date_value,
                None,
                include_date_filter=True,
                include_value_filter=False,
                date_literal_format=date_literal_format,
                ship_name=ship_name,
                date_operator="gt",
                order_by_start_desc=True,
            )
        ]

    return [
        build_query_params(
            start_date_value,
            end_date_value,
            value_chunk,
            include_date_filter=True,
            include_value_filter=True,
            date_literal_format=date_literal_format,
            ship_name=ship_name,
            order_by_start_desc=True,
        )
        for value_chunk in chunks(values, METRIC_QUERY_CHUNK_SIZE)
    ]


def prepared_url(base_url: str, parameters: dict[str, str]) -> str:
    request = requests.Request("GET", base_url, params=parameters)
    return request.prepare().url or base_url


def extract_rows(payload: dict) -> tuple[list[dict], str | None]:
    if "d" in payload and isinstance(payload["d"], dict):
        rows = payload["d"].get("results", [])
        next_link = payload["d"].get("__next")
        return rows, next_link

    rows = payload.get("value", [])
    next_link = payload.get("@odata.nextLink")
    return rows, next_link


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
    session = make_session()
    stopped_by_page_limit = False

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

    cleaned["ReportedValueNumeric"] = pd.to_numeric(
        cleaned["ReportedValue"], errors="coerce"
    )
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
        )
        .reset_index()
        .sort_values(["ShipName", "EndDateTimeGMT", "ReportId"], na_position="last")
    )
    pivoted.columns.name = None
    return pivoted


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

    result = df.copy()
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
    result["Calculated Slip"] = round_series(
        1 - safe_divide(distance_over_ground, engine_distance)
    )
    result["Corrected Speed for 7% Slip"] = round_series(
        shaft_rpm * 0.030123 * 8.2220
    )

    me_fuel_columns = [
        "Main Engine - HSHFO",
        "Main Engine - HSLFO",
        "Main Engine - MGO",
        "Main Engine - ULSHFO",
        "Main Engine - ULSLFO",
        "Main Engine - VLSHFO",
        "Main Engine - VLSLFO",
    ]
    dg_fuel_columns = [
        "Diesel Generators - HSHFO",
        "Diesel Generators - HSLFO",
        "Diesel Generators - MGO",
        "Diesel Generators - ULSHFO",
        "Diesel Generators - ULSLFO",
        "Diesel Generators - VLSHFO",
        "Diesel Generators - VLSLFO",
    ]
    boiler_fuel_columns = [
        "Boiler - HSHFO",
        "Boiler - HSLFO",
        "Boiler - MGO",
        "Boiler - ULSHFO",
        "Boiler - ULSLFO",
        "Boiler - VLSHFO",
        "Boiler - VLSLFO",
    ]

    result["Consumption ME 24 Hours [MT]"] = round_series(
        safe_divide(sum_numeric_columns(result, me_fuel_columns) * 24, lap_time)
    )
    result["Consumption DGs 24 Hours [MT]"] = round_series(
        safe_divide(sum_numeric_columns(result, dg_fuel_columns) * 24, lap_time)
    )
    result["Consumption Boiler 24 Hours [MT]"] = round_series(
        safe_divide(sum_numeric_columns(result, boiler_fuel_columns) * 24, lap_time)
    )
    result["Boiler Sum"] = round_series(sum_numeric_columns(result, boiler_fuel_columns))
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

    shaft_power = first_numeric_column(
        result,
        ["Total Shaft Power [kW] (kW)", "Power from Torque Meter [kW]"],
    )
    result["SFOC [gr/Kwh]"] = round_series(
        safe_divide(result["Consumption ME 24 Hours [MT]"], shaft_power) / 0.000024
    ).fillna(0)

    hfo_columns = [
        "Main Engine - HSHFO",
        "Diesel Generators - HSHFO",
        "Boiler - HSHFO",
        "Main Engine - VLSHFO",
        "Diesel Generators - VLSHFO",
        "Boiler - VLSHFO",
        "Main Engine - ULSHFO",
        "Diesel Generators - ULSHFO",
        "Boiler - ULSHFO",
    ]
    lfo_columns = [
        "Main Engine - HSLFO",
        "Diesel Generators - HSLFO",
        "Boiler - HSLFO",
        "Main Engine - VLSLFO",
        "Diesel Generators - VLSLFO",
        "Boiler - VLSLFO",
        "Main Engine - ULSLFO",
        "Diesel Generators - ULSLFO",
        "Boiler - ULSLFO",
    ]
    mgo_columns = [
        "Main Engine - MGO",
        "Diesel Generators - MGO",
        "Boiler - MGO",
    ]
    total_hfo = sum_numeric_columns(result, hfo_columns)
    total_lfo = safe_divide(sum_numeric_columns(result, lfo_columns), pd.Series(0.9481, index=result.index))
    total_mgo = safe_divide(sum_numeric_columns(result, mgo_columns), pd.Series(0.9415, index=result.index))
    result["HFO Consumption Equivalent [MT]"] = round_series(
        pd.concat([total_hfo, total_lfo, total_mgo], axis=1).sum(axis=1, min_count=1)
    )

    result["Engine Miles Calculated [RPM]"] = (
        round_series(shaft_rpm * 0.032397 * lap_time * 8.2220).fillna(0)
    )
    result["Engine Miles Calculated [Rev]"] = round_series(
        safe_divide(me_revolutions, pd.Series(1852, index=result.index)) * 8.2220
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
    total_dg_power = numeric_column(result, "Total DG Power [kW] (kW)")
    result["Load per Generator Calculated"] = round_series(
        safe_divide(total_dg_power, generator_hours) * lap_time
    )
    result["Load per Generator [% MCR]"] = round_series(
        safe_divide(result["Load per Generator Calculated"], pd.Series(2900, index=result.index))
    )

    reefer_20 = numeric_column(result, "20ft Reefer Units")
    reefer_40 = numeric_column(result, "40ft Reefer Units")
    result["Reefers Onboard 20ft Equivalent"] = round_series(
        (reefer_20 + reefer_40) * 1.66
    ).fillna(0)
    result["Estimated Reefer Load"] = round_series(
        result["Reefers Onboard 20ft Equivalent"] * 3
    )

    corrected_speed = numeric_column(result, "Corrected Speed for 7% Slip")
    cp_consumption = (
        corrected_speed.pow(3) * -0.002695939
        + corrected_speed.pow(2) * 0.38073932
        + corrected_speed * -1.884501436
    )
    result["For Corrected Speed CP Consumption is"] = round_series(cp_consumption).fillna(0)
    result["Difference from Actual"] = (
        result["For Corrected Speed CP Consumption is"]
        - result["Consumption ME 24 Hours [MT]"]
    )
    result["Difference Percentage"] = (
        1
        - safe_divide(
            result["For Corrected Speed CP Consumption is"],
            result["Consumption ME 24 Hours [MT]"],
        )
    ).where(result["For Corrected Speed CP Consumption is"] > 0)

    corrected_speed_plus = corrected_speed + 0.5
    cp_consumption_plus = (
        corrected_speed_plus.pow(3) * -0.002695939
        + corrected_speed_plus.pow(2) * 0.38073932
        + corrected_speed_plus * -1.884501436
    )
    result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"] = (
        round_series(cp_consumption_plus).fillna(0)
    )
    result["Difference from Actual2"] = (
        result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"]
        - result["Consumption ME 24 Hours [MT]"]
    )
    result["Difference Percentage2"] = (
        1
        - safe_divide(
            result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"],
            result["Consumption ME 24 Hours [MT]"],
        )
    ).where(result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"] > 0)

    result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"] = (
        round_series(
            result["For Corrected Speed with + 0.5 kn for on about CP Consumption is"] * 1.05
        )
    )
    result["Difference from Actual3"] = round_series(
        result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"]
        - result["Consumption ME 24 Hours [MT]"]
    )
    result["Difference Percentage3"] = (
        1
        - safe_divide(
            result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"],
            result["Total Consumption 24 Hours [MT]"],
        )
    ).where(
        result["For Corrected Speed with + 0.5 kn + 5% for both on abouts CP Consumption is"] > 0
    )

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

    for column in ["Difference Percentage", "Difference Percentage2", "Difference Percentage3"]:
        result[column] = round_series(result[column]).replace(0, pd.NA)

    return result


@st.cache_data(ttl=1800, show_spinner=False)
def transform_report_data(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    prepared_raw = prepare_raw_data(raw_df)
    pivoted = pivot_report_data(prepared_raw)
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
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M")


def numeric_delta(current_value: object, previous_value: object) -> str | None:
    current_numeric = pd.to_numeric(pd.Series([current_value]), errors="coerce").iloc[0]
    previous_numeric = pd.to_numeric(pd.Series([previous_value]), errors="coerce").iloc[0]
    if pd.isna(current_numeric) or pd.isna(previous_numeric):
        return None
    delta = current_numeric - previous_numeric
    if abs(delta) >= 100:
        return f"{delta:+,.0f}"
    return f"{delta:+,.2f}"


def latest_by_vessel(pivoted: pd.DataFrame) -> pd.DataFrame:
    if pivoted.empty or "ShipName" not in pivoted.columns:
        return pivoted

    sort_column = "EndDateTimeGMT" if "EndDateTimeGMT" in pivoted.columns else "ReportId"
    return (
        pivoted.sort_values(sort_column)
        .groupby("ShipName", as_index=False, dropna=False)
        .tail(1)
        .sort_values("ShipName")
    )


def make_excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    safe = df.copy()
    for column in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[column]):
            safe[column] = pd.to_datetime(safe[column], errors="coerce").dt.tz_localize(None)
    return safe


def make_excel_file(
    pivoted: pd.DataFrame,
    raw: pd.DataFrame,
    latest: pd.DataFrame,
) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        make_excel_safe(pivoted).to_excel(writer, sheet_name="Pivoted Data", index=False)
        make_excel_safe(latest).to_excel(writer, sheet_name="Latest By Vessel", index=False)
        make_excel_safe(raw).to_excel(writer, sheet_name="Raw Data", index=False)
    return output.getvalue()


def render_downloads(
    pivoted: pd.DataFrame,
    raw: pd.DataFrame,
    latest: pd.DataFrame,
    key_prefix: str,
) -> None:
    csv_data = pivoted.to_csv(index=False).encode("utf-8")
    excel_data = make_excel_file(pivoted, raw, latest)

    csv_column, excel_column = st.columns(2)
    csv_column.download_button(
        "Download pivoted CSV",
        data=csv_data,
        file_name="marorka_pivoted_data.csv",
        mime="text/csv",
        use_container_width=True,
        key=f"{key_prefix}_pivoted_csv",
    )
    excel_column.download_button(
        "Download Excel workbook",
        data=excel_data,
        file_name="marorka_dashboard_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=f"{key_prefix}_excel_workbook",
    )


def render_query_preview(
    parameter_sets: list[dict[str, str]],
    max_pages: int,
    query_mode: str,
    base_url: str,
) -> None:
    st.subheader("API Test Setup")
    st.write("Use this first to confirm credentials, date range, pagination, and returned fields.")
    first_url = prepared_url(base_url, parameter_sets[0])
    st.code(first_url, language="text")
    if len(first_url) > 1800:
        st.warning(
            f"The first request URL is {len(first_url):,} characters. "
            "Long OData URLs can be rejected by IIS as HTTP 404. "
            "Use Connection test or Date sample first, or reduce selected metrics."
        )
    st.json(
        {
            "query_mode": query_mode,
            "query_count": len(parameter_sets),
            "max_pages": max_pages,
            "first_request_url_length": len(first_url),
            "first_parameters": parameter_sets[0],
        }
    )


def render_api_test(
    raw_df: pd.DataFrame,
    pivot_df: pd.DataFrame,
    metadata: dict[str, int | float | bool],
    parameter_sets: list[dict[str, str]],
    max_pages: int,
    query_mode: str,
    base_url: str,
) -> None:
    st.subheader("Fetch Result")
    if metadata.get("stopped_by_page_limit"):
        st.warning(
            "The fetch stopped at the selected max-page limit. Increase max pages "
            "when you are ready to test the full API pull."
        )

    metric_columns = st.columns(6)
    metric_columns[0].metric("Raw rows", f"{len(raw_df):,}")
    metric_columns[1].metric("Reports", f"{pivot_df['ReportId'].nunique():,}")
    metric_columns[2].metric("Vessels", f"{pivot_df['ShipName'].nunique():,}")
    metric_columns[3].metric("API queries/pages", f"{metadata['queries']}/{metadata['pages']}")
    metric_columns[4].metric("Downloaded MB", metadata["downloaded_mb"])
    metric_columns[5].metric("Elapsed sec", metadata["elapsed_seconds"])

    if "EndDateTimeGMT" in pivot_df.columns:
        min_date = pivot_df["EndDateTimeGMT"].min()
        max_date = pivot_df["EndDateTimeGMT"].max()
        if pd.notna(min_date) and pd.notna(max_date):
            st.caption(
                f"Loaded report window: {min_date:%Y-%m-%d %H:%M} "
                f"to {max_date:%Y-%m-%d %H:%M} GMT"
            )

    with st.expander("Exact API request settings", expanded=False):
        render_query_preview(parameter_sets, max_pages, query_mode, base_url)

    left_column, right_column = st.columns(2)
    with left_column:
        st.subheader("Rows By Report Type")
        st.dataframe(
            raw_df["ReportType"].value_counts(dropna=False).rename_axis("ReportType").reset_index(name="Rows"),
            use_container_width=True,
            hide_index=True,
        )

    with right_column:
        st.subheader("Rows By Vessel")
        st.dataframe(
            raw_df["ShipName"].value_counts(dropna=False).rename_axis("ShipName").reset_index(name="Rows"),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Value Descriptions Returned")
    value_counts = (
        raw_df["ValueDescription"]
        .value_counts(dropna=False)
        .rename_axis("ValueDescription")
        .reset_index(name="Rows")
    )
    st.dataframe(value_counts, use_container_width=True, hide_index=True)

    st.subheader("Latest Report By Vessel")
    latest_columns = [
        "ShipName",
        "ReportType",
        "StartDateTimeGMT",
        "EndDateTimeGMT",
        "LapTime",
        "StateName",
        "ReportId",
    ]
    st.dataframe(
        latest_by_vessel(pivot_df)[latest_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Raw Sample")
    st.dataframe(raw_df.head(100), use_container_width=True, hide_index=True)


def report_selector(pivot_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series | None]:
    vessel_options = sorted(pivot_df["ShipName"].dropna().unique().tolist())
    selected_vessel = st.selectbox("Report vessel", vessel_options)
    vessel_df = pivot_df[pivot_df["ShipName"] == selected_vessel].sort_values(
        "EndDateTimeGMT", ascending=False
    )

    report_options = []
    for _, row in vessel_df.iterrows():
        report_options.append(
            {
                "ReportId": row["ReportId"],
                "Label": (
                    f"{format_datetime(row['EndDateTimeGMT'])} GMT"
                    f" | {row.get('ReportType', '-')}"
                    f" | {row.get('StateName', '-')}"
                ),
            }
        )

    selected_label = st.selectbox(
        "Report date/time",
        [option["Label"] for option in report_options],
    )
    selected_report_id = next(
        option["ReportId"] for option in report_options if option["Label"] == selected_label
    )

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
        for metric_column, (label, source_column) in zip(
            columns, available_metrics[chunk_start : chunk_start + 5]
        ):
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
    st.subheader("Report Presentation")
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

    st.divider()
    render_metric_cards(selected_row, previous_row)
    st.caption("Deltas compare against the previous report for the same vessel when numeric values are available.")

    st.divider()
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
        "Total DG Power [kW] (kW)",
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


def render_data_tables(
    filtered_pivot: pd.DataFrame,
    filtered_raw: pd.DataFrame,
    latest_df: pd.DataFrame,
) -> None:
    render_downloads(filtered_pivot, filtered_raw, latest_df, key_prefix="export_tab")

    st.subheader("Pivoted Data")
    st.dataframe(
        filtered_pivot.sort_values("EndDateTimeGMT", ascending=False),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Raw Data")
    st.dataframe(
        filtered_raw.sort_values(["ShipName", "EndDateTimeGMT"], ascending=[True, False]),
        use_container_width=True,
        hide_index=True,
    )


def filter_by_numeric_min(df: pd.DataFrame, column: str, minimum_value: float | None) -> pd.DataFrame:
    if minimum_value is None or column not in df.columns:
        return df
    values = pd.to_numeric(df[column], errors="coerce")
    return df[values >= minimum_value]


def apply_dashboard_filters(
    df: pd.DataFrame,
    selected_vessels: list[str],
    selected_report_types: list[str],
    selected_states: list[str],
    numeric_minimums: dict[str, float | None],
    search_text: str,
    start_date_filter: date | None = None,
    end_date_filter: date | None = None,
) -> pd.DataFrame:
    filtered = df.copy()

    if start_date_filter is not None and "EndDateTimeGMT" in filtered.columns:
        start_timestamp = pd.Timestamp(start_date_filter, tz="UTC")
        filtered = filtered[filtered["EndDateTimeGMT"] >= start_timestamp]
    if end_date_filter is not None and "EndDateTimeGMT" in filtered.columns:
        end_timestamp = pd.Timestamp(end_date_filter + timedelta(days=1), tz="UTC")
        filtered = filtered[filtered["EndDateTimeGMT"] < end_timestamp]

    if selected_vessels:
        filtered = filtered[filtered["ShipName"].isin(selected_vessels)]
    if selected_report_types:
        filtered = filtered[filtered["ReportType"].isin(selected_report_types)]
    if selected_states:
        filtered = filtered[filtered["StateName"].isin(selected_states)]

    for column, minimum_value in numeric_minimums.items():
        filtered = filter_by_numeric_min(filtered, column, minimum_value)

    if search_text.strip():
        search_value = search_text.strip().casefold()
        searchable = filtered.astype("string").apply(
            lambda column: column.str.casefold().str.contains(search_value, na=False)
        )
        filtered = filtered[searchable.any(axis=1)]

    return filtered


def format_percentage(value: object) -> str:
    if pd.isna(value):
        return "-"
    numeric_value = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric_value):
        return "-"
    return f"{numeric_value:.1%}"


def parse_optional_float(value: str) -> float | None:
    if not value.strip():
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def mean_metric(df: pd.DataFrame, column: str) -> object:
    if column not in df.columns:
        return pd.NA
    return pd.to_numeric(df[column], errors="coerce").mean()


def sum_metric(df: pd.DataFrame, column: str) -> object:
    if column not in df.columns:
        return pd.NA
    return pd.to_numeric(df[column], errors="coerce").sum(min_count=1)


def render_dashboard_kpis(filtered_df: pd.DataFrame, boiler_df: pd.DataFrame) -> None:
    def latest_value() -> object:
        if "EndDateTimeGMT" not in filtered_df.columns or filtered_df.empty:
            return pd.NA
        return filtered_df["EndDateTimeGMT"].max()

    kpi_columns = st.columns(4)
    kpi_columns[0].metric(
        "Average of Calculated Slip",
        format_percentage(mean_metric(filtered_df, "Calculated Slip")),
    )
    kpi_columns[1].metric(
        "Average of ME Load [%MCR]",
        format_percentage(mean_metric(filtered_df, "ME Load [%MCR]")),
    )
    kpi_columns[2].metric(
        "Average of SFOC [gr/Kwh]",
        format_value(mean_metric(filtered_df, "SFOC [gr/Kwh]")),
    )
    kpi_columns[3].metric(
        "Sum of Boiler Sum",
        format_value(sum_metric(boiler_df, "Boiler Sum")),
        help="This KPI uses the independent Boiler KPI Filters, not the main KPI/table filters.",
    )

    context_columns = st.columns(3)
    context_columns[0].metric("Filtered reports", f"{filtered_df['ReportId'].nunique():,}")
    context_columns[1].metric("Filtered vessels", f"{filtered_df['ShipName'].nunique():,}")
    context_columns[2].metric("Latest GMT", format_datetime(latest_value()))

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
    st.dataframe(table_df, use_container_width=True, hide_index=True)


def render_operational_dashboard(
    filtered_df: pd.DataFrame,
    boiler_df: pd.DataFrame,
    visible_columns: list[str],
) -> None:
    if filtered_df.empty:
        st.warning("No reports match the current filters.")
        return

    render_dashboard_kpis(filtered_df, boiler_df)

    st.subheader("Latest report by vessel")
    latest_columns = [column for column in DEFAULT_TABLE_COLUMNS if column in filtered_df.columns]
    st.dataframe(
        latest_by_vessel(filtered_df)[latest_columns],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Filtered report table")
    render_dashboard_table(filtered_df, visible_columns)


if not require_dashboard_password():
    st.stop()

st.title(APP_TITLE)
st.caption("Fleet performance dashboard powered by cached Marorka data and Excel-equivalent calculations.")

with st.sidebar:
    username = get_secret("MARORKA_USERNAME")
    password = get_secret("MARORKA_PASSWORD")

    api_base_url = get_secret("MARORKA_BASE_URL", BASE_URL).strip() or BASE_URL
    query_mode = "Excel-style full pull"
    api_ship_name = get_secret("MARORKA_SHIP_NAME", DEFAULT_API_SHIP_FILTER).strip()
    date_format_label = "Date only"
    selected_values = DEFAULT_VALUES
    page_safety_limit = get_int_secret("MARORKA_PAGE_SAFETY_LIMIT", PAGE_SAFETY_LIMIT)

    st.header("Data Window")
    start_date_input = st.date_input("Start date", value=get_default_start_date())
    end_date_input = st.date_input("End date", value=date.today())

    refresh_fetch = st.button("Refresh API data", type="primary", use_container_width=True)

if refresh_fetch:
    fetch_all_data.clear()
    transform_report_data.clear()
    st.rerun()

if end_date_input < start_date_input:
    st.warning("End date must be on or after start date.")
    st.stop()

parameter_sets = build_parameter_sets(
    query_mode,
    start_date_input,
    end_date_input,
    selected_values,
    DATE_LITERAL_FORMATS[date_format_label],
    api_ship_name,
)

if not username or not password:
    st.error(
        "Marorka API credentials are not configured. Add MARORKA_USERNAME and "
        "MARORKA_PASSWORD in Streamlit secrets."
    )
    st.stop()

auth_signature = sha256(f"{username}:{password}".encode("utf-8")).hexdigest()

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
    st.info(
        "For HTTP 404, first try API request type = Connection test. "
        "If that works, try Date sample. If only Selected metric pull fails, "
        "the metric filter is likely too large or one ValueDescription is invalid."
    )
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
    loaded_start_date = pivot_df["EndDateTimeGMT"].min().date()
    loaded_end_date = pivot_df["EndDateTimeGMT"].max().date()

    main_date_range = st.date_input(
        "KPI/table date range",
        value=(loaded_start_date, loaded_end_date),
        min_value=loaded_start_date,
        max_value=loaded_end_date,
        key="filter_main_date_range",
    )
    if isinstance(main_date_range, tuple) and len(main_date_range) == 2:
        main_start_date, main_end_date = main_date_range
    else:
        main_start_date, main_end_date = loaded_start_date, loaded_end_date

    selected_vessels = st.multiselect(
        "Vessels",
        options=vessel_options,
        default=[],
        key="filter_vessels",
        help="Leave blank to include all vessels.",
    )

    report_type_options = sorted(pivot_df["ReportType"].dropna().unique().tolist())
    selected_report_types = st.multiselect(
        "Report types",
        options=report_type_options,
        default=[],
        key="filter_report_types",
        help="Leave blank to include all report types.",
    )

    state_options = sorted(pivot_df["StateName"].dropna().unique().tolist())
    selected_states = st.multiselect(
        "States",
        options=state_options,
        default=[],
        key="filter_states",
        help="Leave blank to include all states.",
    )

    search_text = st.text_input(
        "Table search",
        key="filter_search_text",
        help="Searches across the filtered table.",
    )

    with st.expander("Numeric filters"):
        numeric_minimums = {}
        for label, column in NUMERIC_FILTER_COLUMNS:
            if column in pivot_df.columns:
                text_value = st.text_input(
                    label,
                    key=f"filter_min_{column}",
                    help="Blank means no minimum. Example: ME Load >= 0.1 keeps load above 10%.",
                )
                parsed_value = parse_optional_float(text_value)
                if text_value.strip() and parsed_value is None:
                    st.warning(f"Ignoring invalid number for {label.strip()}.")
                numeric_minimums[column] = parsed_value

    with st.expander("Boiler KPI Filters"):
        st.caption("These filters affect only the Sum of Boiler Sum KPI.")
        boiler_date_range = st.date_input(
            "Boiler date range",
            value=(loaded_start_date, loaded_end_date),
            min_value=loaded_start_date,
            max_value=loaded_end_date,
            key="filter_boiler_date_range",
        )
        if isinstance(boiler_date_range, tuple) and len(boiler_date_range) == 2:
            boiler_start_date, boiler_end_date = boiler_date_range
        else:
            boiler_start_date, boiler_end_date = loaded_start_date, loaded_end_date

        boiler_vessels = st.multiselect(
            "Boiler vessels",
            options=vessel_options,
            default=[],
            key="filter_boiler_vessels",
            help="Leave blank to include all vessels for the boiler KPI.",
        )
        boiler_report_types = st.multiselect(
            "Boiler report types",
            options=report_type_options,
            default=[],
            key="filter_boiler_report_types",
            help="Leave blank to include all report types for the boiler KPI.",
        )
        boiler_states = st.multiselect(
            "Boiler states",
            options=state_options,
            default=[],
            key="filter_boiler_states",
            help="Leave blank to include all states for the boiler KPI.",
        )

        boiler_numeric_minimums = {}
        for label, column in BOILER_FILTER_COLUMNS:
            if column in pivot_df.columns:
                text_value = st.text_input(
                    label,
                    key=f"filter_boiler_min_{column}",
                    help="Blank means no minimum.",
                )
                parsed_value = parse_optional_float(text_value)
                if text_value.strip() and parsed_value is None:
                    st.warning(f"Ignoring invalid boiler number for {label.strip()}.")
                boiler_numeric_minimums[column] = parsed_value

    with st.expander("Table columns"):
        default_visible_columns = [
            column for column in DEFAULT_TABLE_COLUMNS if column in pivot_df.columns
        ]
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
    numeric_minimums,
    search_text,
    main_start_date,
    main_end_date,
)

boiler_filtered_pivot = apply_dashboard_filters(
    pivot_df,
    boiler_vessels,
    boiler_report_types,
    boiler_states,
    boiler_numeric_minimums,
    "",
    boiler_start_date,
    boiler_end_date,
)

dashboard_tab, report_tab = st.tabs(["Dashboard", "Single Report"])

with dashboard_tab:
    st.subheader("Dashboard")
    render_operational_dashboard(filtered_pivot, boiler_filtered_pivot, visible_columns)

with report_tab:
    if filtered_pivot.empty:
        st.warning("No reports match the current filters.")
    else:
        render_report_presentation(filtered_pivot)
