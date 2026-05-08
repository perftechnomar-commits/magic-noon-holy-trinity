import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
import time

# Configure the Streamlit page
st.set_page_config(page_title="Magic Noon alla Mantalos", layout="wide")

# Display title and instructions
st.title("Magic Noon alla Mantalos")
st.markdown("Choose a start date to fetch all-vessel data. Credentials are read from Streamlit secrets.")

# Read credentials from secrets rather than prompting the user.  If these
# entries are not set in `.streamlit/secrets.toml`, the app will show an
# error when attempting to fetch data.  A date input is still provided
# to allow the user to select the reporting window.
username = st.secrets.get("MARORKA_USERNAME")
password = st.secrets.get("MARORKA_PASSWORD")
start_date_input = st.date_input("Start Date", value=pd.to_datetime("2026-01-01"))

# Convert date input to string for OData filter
start_date_str = start_date_input.strftime("%Y-%m-%d")

# Base URL for the ReportData entity
BASE_URL = "https://online.marorka.com/Odata/v1/ODataService.svc/ReportData"

# Define the list of metrics to include in the pivot
wanted_values = [
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

# Build the value filter string for the OData query
value_filter = " or ".join([
    f"ValueDescription eq '{v.replace("'", "''")}'" for v in wanted_values
])

# Build the OData parameters dictionary
params = {
    "$format": "json",
    "$select": (
        "ReportId,ShipName,ReportType,StartDateTimeGMT,"
        "EndDateTimeGMT,LapTime,StateName,ValueDescription,ReportedValue"
    ),
    "$filter": (
        f"StartDateTimeGMT gt DateTime'{start_date_str}' "
        "and ValueDescription ne null "
        "and ReportType ne 'Intake Report' "
        "and ReportType ne 'Fuel Change Report' "
        f"and ({value_filter})"
    ),
}

def extract_rows(payload: dict):
    """Extract rows and next link from an OData response payload."""
    if "d" in payload and "results" in payload["d"]:
        return payload["d"]["results"], payload["d"].get("__next")
    if "value" in payload:
        return payload["value"], payload.get("@odata.nextLink")
    return [], None

def fetch_all_data(base_url: str, parameters: dict) -> tuple[pd.DataFrame, int]:
    """
    Fetch all pages of OData results using the given base URL and parameters.

    Returns a DataFrame of results and the total number of bytes downloaded.
    """
    rows = []
    next_url = base_url
    local_params = parameters.copy()
    page = 1
    total_bytes = 0
    while next_url:
        resp = requests.get(
            next_url,
            params=local_params if page == 1 else None,
            auth=HTTPBasicAuth(username, password),
            headers={"Accept": "application/json"},
            timeout=120,
        )
        total_bytes += len(resp.content)
        if resp.status_code != 200:
            st.error(f"HTTP {resp.status_code}: {resp.text}")
            return pd.DataFrame(), total_bytes
        payload = resp.json()
        page_rows, next_link = extract_rows(payload)
        rows.extend(page_rows)
        next_url = next_link
        local_params = None  # parameters only needed for first call
        page += 1
    return pd.DataFrame(rows), total_bytes

if st.button("Load Data"):
    # Ensure credentials are available; if not, instruct the user to configure secrets
    if not username or not password:
        st.error(
            "API credentials are not configured. Please set 'MARORKA_USERNAME' "
            "and 'MARORKA_PASSWORD' in your `.streamlit/secrets.toml` file."
        )
    else:
        start_time = time.time()
        df, bytes_downloaded = fetch_all_data(BASE_URL, params)
        elapsed = time.time() - start_time
        st.subheader("Fetch Summary")
        st.metric("Rows", len(df))
        st.metric("Columns", len(df.columns))
        st.metric("Downloaded MB", round(bytes_downloaded / 1024 / 1024, 2))
        st.metric("Elapsed Seconds", round(elapsed, 2))
        st.subheader("Raw Results (first 50 rows)")
        if not df.empty:
            st.dataframe(df.head(50), use_container_width=True)
            pivot_df = df.pivot_table(
                index=[
                    "ReportId",
                    "ShipName",
                    "ReportType",
                    "StartDateTimeGMT",
                    "EndDateTimeGMT",
                    "LapTime",
                    "StateName",
                ],
                columns="ValueDescription",
                values="ReportedValue",
                aggfunc="first",
            ).reset_index()
            st.subheader("Pivoted Data (first 50 rows)")
            st.dataframe(pivot_df.head(50), use_container_width=True)
            csv_bytes = pivot_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Pivoted CSV",
                data=csv_bytes,
                file_name="marorka_global_pivot.csv",
                mime="text/csv",
            )
        else:
            st.write("No data returned from the API.")
