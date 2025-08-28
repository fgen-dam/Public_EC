import streamlit as st
import requests
import pandas as pd
from datetime import datetime, time, timezone, timedelta
import json

# --- Page and Session State Configuration ---
st.set_page_config(page_title="Edge API Data Downloader", layout="wide")

# --- Helper Function for Logging ---
def log_error(error_message):
    """Prints a timestamped error message to the console/log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # On Streamlit Cloud, print statements will appear in the log viewer.
    print(f"{timestamp} - ERROR: {error_message}")

# Initialize session state for login status if it doesn't exist
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

def logout():
    """Callback function to reset login state."""
    st.session_state.logged_in = False
    st.rerun()

# --- Login Logic ---
if not st.session_state.logged_in:
    st.title("Edge API Data Downloader")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            # More robust check for secrets configuration
            if "credentials" not in st.secrets:
                st.error("Missing [credentials] section in your secrets.toml file.")
            elif "usernames" not in st.secrets["credentials"] or "passwords" not in st.secrets["credentials"]:
                st.error("Missing 'usernames' or 'passwords' under [credentials] in your secrets.toml file.")
            else:
                try:
                    if (username in st.secrets["credentials"]["usernames"] and
                        password in st.secrets["credentials"]["passwords"]):
                        st.session_state.logged_in = True
                        st.rerun()
                    else:
                        st.error("Incorrect username or password")
                except Exception as e:
                    error_msg = f"An error occurred while reading secrets: {e}"
                    log_error(error_msg)
                    st.error(error_msg)

# --- Main Application ---
if st.session_state.logged_in:
    st.title("Edge API Data Downloader")
    st.write("This app fetches data from the Edge API and allows you to download it as a CSV file.")

    # --- Sidebar Configuration ---
    st.sidebar.header("Endpoint Selection")

    endpoints = {
        "Devices": {
            "path": "/devices",
            "description": "Returns device details based on the API Key and optional device serial ID.",
            "params": ["device_serialid"],
            "required_params": [] 
        },
        "Events Interval": {
            "path": "/events/interval/",
            "description": "Returns event details based on the device_serialid provided within the time stamps.",
            "params": ["device_serialid", "dates"],
            "required_params": ["device_serialid"]
        },
        "Power Quality Live": {
            "path": "/powerquality/live/",
            "description": "Returns live power quality based on the serialid provided.",
            "params": ["device_serialid"],
            "required_params": ["device_serialid"]
        },
        "Power Quality Interval": {
            "path": "/powerquality/interval/",
            "description": "Returns power quality data based on the provided serialid and the time stamps.",
            "params": ["device_serialid", "dates", "granularity"],
            "required_params": ["device_serialid", "granularity"]
        },
        "Power Quality Aggregated": {
            "path": "/powerquality/aggregated/",
            "description": "Returns aggregated power quality data based on the provided serialid and the time stamps.",
            "params": ["device_serialid", "dates", "granularity"],
            "required_params": ["device_serialid", "granularity"]
        }
    }

    selected_endpoint_name = st.sidebar.selectbox("Choose an API endpoint", list(endpoints.keys()))
    st.sidebar.write("---")
    st.sidebar.button("Logout", on_click=logout)

    selected_endpoint = endpoints[selected_endpoint_name]
    st.info(f"**Description:** {selected_endpoint['description']}")

    # --- Dynamic Input Parameters ---
    st.header("Input Parameters")
    params = {}
    base_url = "https://v3.edgezeroapi.com/pienergy"
    full_url = ""
    device_serialid = ""

    if "device_serialid" in selected_endpoint["params"]:
        label = "Device Serial ID"
        if "device_serialid" not in selected_endpoint["required_params"]:
            label += " (Optional)"
        device_serialid = st.text_input(label, "EXXXXXXXXXXXX")
        
        if selected_endpoint_name not in ["Devices"]:
            full_url = f"{base_url}{selected_endpoint['path']}{device_serialid}"
        else:
            full_url = f"{base_url}{selected_endpoint['path']}"
            if device_serialid:
                 params['device_serialid'] = device_serialid

    if "dates" in selected_endpoint["params"]:
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.now().date())
            start_dt_utc = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            params['starttime'] = int(start_dt_utc.timestamp())
            st.caption(f"Epoch: {params['starttime']}")

        with col2:
            end_date = st.date_input("End Date", datetime.now().date())
            end_dt_utc = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
            params['endtime'] = int(end_dt_utc.timestamp())
            st.caption(f"Epoch: {params['endtime']}")
    
    if "granularity" in selected_endpoint["params"]:
        if 'start_date' in locals() and 'end_date' in locals():
            date_range_days = (end_date - start_date).days

            granularity_options = []
            if date_range_days < 1:
                granularity_options = ["1m", "5m", "15m", "1h", "daily"]
            elif 1 <= date_range_days <= 7:
                granularity_options = ["15m", "1h", "daily"]
            else:
                granularity_options = ["1h", "daily"]
                
            params['granularity'] = st.selectbox("Granularity", granularity_options)


    # --- Data Fetching Logic ---
    if st.button(f"Fetch Data from '{selected_endpoint_name}'"):
        validation_passed = True
        for param in selected_endpoint.get("required_params", []):
            if param == 'device_serialid' and not device_serialid:
                error_msg = "Device Serial ID is a required parameter for this endpoint."
                log_error(error_msg)
                st.error(error_msg)
                validation_passed = False

        if validation_passed:
            try:
                if "edgeapi" not in st.secrets or "api_key" not in st.secrets["edgeapi"]:
                    error_msg = "API Key not found in Streamlit secrets."
                    log_error(error_msg)
                    st.error(error_msg)
                    st.stop()
                
                api_key = st.secrets["edgeapi"]["api_key"]
                
                with st.spinner("Fetching data from Edge API..."):
                    headers = {"X-Api-Key": api_key, "accept": "*/*"}
                    response = requests.get(full_url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()

                if isinstance(data, dict) and 'error-code' in data:
                    error_msg = f"API Error {data.get('error-code')}: {data.get('message')}"
                    log_error(error_msg)
                    st.error(error_msg)
                elif not data:
                    st.info("The API returned no data for the given parameters.")
                else:
                    st.success("Data fetched successfully!")
                    df = pd.json_normalize(data)

                    for col in df.columns:
                        if 'time' in col or 'date' in col or 'epoch' in col:
                            if pd.api.types.is_numeric_dtype(df[col]):
                                df[f'{col}_readable'] = pd.to_datetime(df[col], unit='s', errors='coerce')

                    csv = df.to_csv(index=False).encode('utf-8')
                    filename = f"{selected_endpoint_name.replace(' ', '_').lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    st.download_button(
                        label="Download data as CSV",
                        data=csv,
                        file_name=filename,
                        mime='text/csv',
                    )
            
            except requests.exceptions.HTTPError as e:
                error_msg = f"HTTP Error: {e}"
                log_error(error_msg)
                st.error(error_msg)
                try:
                    error_json = e.response.json()
                    api_message = error_json.get('message', e.response.text)
                    api_response_error = f"API Response: {api_message}"
                    log_error(api_response_error)
                    st.error(api_response_error)
                except json.JSONDecodeError:
                    api_response_error = f"API Response: {e.response.text}"
                    log_error(api_response_error)
                    st.error(api_response_error)
                except Exception:
                    pass
            except Exception as e:
                error_msg = f"An unexpected error occurred: {e}"
                log_error(error_msg)
                st.error(error_msg)
