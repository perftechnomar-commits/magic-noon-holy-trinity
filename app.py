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
DEFAULT_MAX_PAGES = 5
ABSOLUTE_MAX_PAGES = 500

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
    ("Engine Distance", "Engine Distance [nm]"),
    ("Distance Over Ground", "Distance Over Ground [nm]"),
    ("Water Speed", "Water speed [kn Log] (kn)"),
    ("SOG", "Speed over ground [kn GPS] (kn)"),
    ("ME Load", "ME Load [%MCR]"),
    ("Torque Power", "Power from Torque Meter [kW]"),
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


def require_dashboard_password() -> bool:
    expected_password = get_secret("DASHBOARD_PASSWORD")
    if not expected_password:
        return True

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


def build_query_params(start_date_value: date, values: list[str]) -> dict[str, str]:
    start_datetime = start_date_value.strftime("%Y-%m-%dT00:00:00")
    value_filter = build_value_filter(values)
    report_type_filter = build_report_type_filter(REPORT_TYPES_TO_EXCLUDE)

    return {
        "$format": "json",
        "$select": ",".join(INDEX_COLUMNS + ["ValueDescription", "ReportedValue"]),
        "$filter": (
            f"StartDateTimeGMT ge DateTime'{start_datetime}' "
            "and ValueDescription ne null "
            f"{report_type_filter} "
            f"and ({value_filter})"
        ),
    }


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
    parameters: dict[str, str],
    max_pages: int,
    auth_signature: str,
    _username: str,
    _password: str,
) -> tuple[pd.DataFrame, dict[str, int | float | bool]]:
    rows: list[dict] = []
    next_url: str | None = base_url
    local_params = parameters.copy()
    page = 0
    total_bytes = 0
    started_at = perf_counter()
    session = make_session()
    stopped_by_page_limit = False

    while next_url:
        page += 1
        response = session.get(
            next_url,
            params=local_params if page == 1 else None,
            auth=HTTPBasicAuth(_username, _password),
            headers={"Accept": "application/json"},
            timeout=120,
        )
        total_bytes += len(response.content)
        response.raise_for_status()

        page_rows, next_link = extract_rows(response.json())
        rows.extend(page_rows)

        if page >= max_pages and next_link:
            stopped_by_page_limit = True
            break

        next_url = urljoin(base_url, next_link) if next_link else None
        local_params = {}

    metadata = {
        "rows": len(rows),
        "pages": page,
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


def render_downloads(pivoted: pd.DataFrame, raw: pd.DataFrame, latest: pd.DataFrame) -> None:
    csv_data = pivoted.to_csv(index=False).encode("utf-8")
    excel_data = make_excel_file(pivoted, raw, latest)

    csv_column, excel_column = st.columns(2)
    csv_column.download_button(
        "Download pivoted CSV",
        data=csv_data,
        file_name="marorka_pivoted_data.csv",
        mime="text/csv",
        use_container_width=True,
    )
    excel_column.download_button(
        "Download Excel workbook",
        data=excel_data,
        file_name="marorka_dashboard_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


def render_query_preview(query_params: dict[str, str], max_pages: int) -> None:
    st.subheader("API Test Setup")
    st.write("Use this first to confirm credentials, date range, pagination, and returned fields.")
    st.code(BASE_URL, language="text")
    st.json(
        {
            "max_pages": max_pages,
            "parameters": query_params,
        }
    )


def render_api_test(
    raw_df: pd.DataFrame,
    pivot_df: pd.DataFrame,
    metadata: dict[str, int | float | bool],
    query_params: dict[str, str],
    max_pages: int,
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
    metric_columns[3].metric("API pages", metadata["pages"])
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
        render_query_preview(query_params, max_pages)

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
    render_downloads(filtered_pivot, filtered_raw, latest_df)

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


if not require_dashboard_password():
    st.stop()

st.title(APP_TITLE)
st.caption("Stage 1: test the API pull. Stage 2: review the report presentation from the same data.")

with st.sidebar:
    st.header("API Credentials")

    secret_username = get_secret("MARORKA_USERNAME")
    secret_password = get_secret("MARORKA_PASSWORD")
    use_secrets = bool(secret_username and secret_password)

    if use_secrets:
        username = secret_username
        password = secret_password
        st.success("Using Marorka credentials from Streamlit secrets.")
        if st.checkbox("Override credentials"):
            username = st.text_input("Username", value=secret_username)
            password = st.text_input("Password", type="password")
    else:
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

    st.header("API Test Controls")
    configured_days_back = get_int_secret("MARORKA_DAYS_BACK", DEFAULT_DAYS_BACK)
    default_start_date = date.today() - timedelta(days=configured_days_back)
    start_date_input = st.date_input("Start date", value=default_start_date)

    configured_max_pages = get_int_secret("MARORKA_MAX_PAGES", DEFAULT_MAX_PAGES)
    max_pages = st.number_input(
        "Max OData pages",
        min_value=1,
        max_value=ABSOLUTE_MAX_PAGES,
        value=min(configured_max_pages, ABSOLUTE_MAX_PAGES),
        step=1,
    )

    with st.expander("Metric filter"):
        selected_values = st.multiselect(
            "Value descriptions",
            options=DEFAULT_VALUES,
            default=DEFAULT_VALUES,
        )

    run_fetch = st.button("Run API test", type="primary", use_container_width=True)
    refresh_fetch = st.button("Refresh and rerun", use_container_width=True)

if run_fetch:
    st.session_state.load_requested = True
if refresh_fetch:
    fetch_all_data.clear()
    st.session_state.load_requested = True
    st.rerun()

if not selected_values:
    st.warning("Select at least one value description.")
    st.stop()

query_params = build_query_params(start_date_input, selected_values)

if not st.session_state.get("load_requested"):
    render_query_preview(query_params, int(max_pages))
    st.info("Click Run API test in the sidebar when you are ready to call Marorka.")
    st.stop()

if not username or not password:
    st.info("Enter Marorka credentials in the sidebar to load data.")
    st.stop()

auth_signature = sha256(f"{username}:{password}".encode("utf-8")).hexdigest()

try:
    with st.spinner("Fetching Marorka OData pages..."):
        raw_df, fetch_metadata = fetch_all_data(
            BASE_URL,
            query_params,
            int(max_pages),
            auth_signature,
            username,
            password,
        )
except requests.HTTPError as exc:
    response_text = exc.response.text[:1000] if exc.response is not None else str(exc)
    status_code = exc.response.status_code if exc.response is not None else "unknown"
    st.error(f"Marorka API returned HTTP {status_code}: {response_text}")
    st.stop()
except Exception as exc:
    st.error(f"Could not load Marorka data: {exc}")
    st.stop()

raw_df = prepare_raw_data(raw_df)
pivot_df = pivot_report_data(raw_df)

if pivot_df.empty:
    st.warning("No data returned for the selected date and metric filters.")
    st.stop()

with st.sidebar:
    st.header("Report Filters")
    vessel_options = sorted(pivot_df["ShipName"].dropna().unique().tolist())
    selected_vessel = st.selectbox("Vessel", ["All vessels"] + vessel_options)

    report_type_options = sorted(pivot_df["ReportType"].dropna().unique().tolist())
    selected_report_types = st.multiselect(
        "Report type",
        options=report_type_options,
        default=report_type_options,
    )

filtered_pivot = pivot_df.copy()
if selected_vessel != "All vessels":
    filtered_pivot = filtered_pivot[filtered_pivot["ShipName"] == selected_vessel]
if selected_report_types:
    filtered_pivot = filtered_pivot[filtered_pivot["ReportType"].isin(selected_report_types)]
else:
    filtered_pivot = filtered_pivot.iloc[0:0]

filtered_report_ids = set(filtered_pivot["ReportId"].dropna().tolist())
filtered_raw = raw_df[raw_df["ReportId"].isin(filtered_report_ids)].copy()
latest_df = latest_by_vessel(filtered_pivot)

api_tab, report_tab, tables_tab = st.tabs(
    ["API Test", "Report Presentation", "Data Tables And Export"]
)

with api_tab:
    render_api_test(raw_df, pivot_df, fetch_metadata, query_params, int(max_pages))

with report_tab:
    if filtered_pivot.empty:
        st.warning("No reports match the current report filters.")
    else:
        render_report_presentation(filtered_pivot)

with tables_tab:
    if filtered_pivot.empty:
        st.warning("No reports match the current report filters.")
    else:
        render_data_tables(filtered_pivot, filtered_raw, latest_df)
