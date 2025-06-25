import streamlit as st
import requests
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
import st_folium
from streamlit_folium import folium

# Constants
MAX_ELEVATION_M = 2400  # ~8,000 feet


def geocode_address(address):
    geolocator = Nominatim(user_agent="ev_feasibility_checker_v2")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    location = geocode(address)
    if location:
        return location.latitude, location.longitude
    return None, None


def get_elevation(lat, lon):
    url = f"https://api.open-elevation.com/api/v1/lookup?locations={lat},{lon}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        results = response.json().get('results', [])
        if results:
            elevation = results[0].get('elevation', None)
            st.write(f"Elevation at {lat},{lon} is {elevation} m")
            return elevation
    except Exception as e:
        st.warning(f"Elevation API error: {e}")
    return None

def is_not_in_heat_warning_zone(lat, lon):
    """
    Based on the map showing % of days > 45°C, returns True if the site is in a high-heat area.
    Rough bounds drawn from Furnace Creek / southwest heat zones.
    """
    # Approx bounding box for high-temp zone
    # Covers parts of SE California, SW Arizona, S Nevada
    if 33 <= lat <= 37 and -118 <= lon <= -112:
        return False
    return True

def get_fema_fld_zone(lat, lon):
    """
    Returns the FEMA flood zone designation (e.g., 'AE', 'X') for a given point,
    or None if outside known zones or no coverage.
    """
    url = "http://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/0/query"
    params = {
        "where": "1=1",
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelWithin",
        "outFields": "FLD_ZONE",
        "returnGeometry": "false",
        "f": "pjson"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        features = data.get("features", [])
        if features:
            fld = features[0]["attributes"].get("FLD_ZONE")
            return fld
        return None
    except Exception as e:
        st.warning(f"FEMA flood zone query error: {e}")
        return None

def is_in_flood_zone(lat, lon):
    zone = get_fema_fld_zone(lat, lon)
    if zone:
        st.write(f"⚠️ FEMA Flood Zone: {zone}")
        return True
    return False

def show_flood_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=15)

    # Add FEMA's flood hazard WMS tile layer
    folium.raster_layers.WmsTileLayer(
        url="https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/export",
        layers="28",
        name="FEMA Flood Zones",
        format="image/png",
        transparent=True,
        attribution="FEMA NFHL"
    ).add_to(m)

    folium.Marker([lat, lon], popup="Site").add_to(m)

    st_folium(m, width=700, height=500)
        
def is_in_high_seismic_zone(lat, lon):
    url = "https://earthquake.usgs.gov/ws/designmaps/asce7-16.json"
    params = {
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "riskCategory": "III",        # uppercase is acceptable
        "siteClass": "D",
        "title": f"{lat:.6f},{lon:.6f}"
    }
    headers = {"User-Agent": "EV-Feasibility-App"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        ss = float(data['response']['data']['ss'])
        st.write(f"USGS seismic Ss value: {ss}")
        return ss > 1.0
    except Exception as e:
        try:
            st.warning(f"USGS seismic risk API error: {e}\nDetails: {response.text}")
        except:
            st.warning(f"USGS seismic risk API error: {e}")
        return False

def check_site_feasibility(address):
    lat, lon = geocode_address(address)
    if not lat:
        return {"status": "Invalid address"}

    time.sleep(1)


    elevation = get_elevation(lat, lon) or 1000
    elevation_ok = elevation < MAX_ELEVATION_M

    temp_ok = is_not_in_heat_warning_zone(lat, lon)
    flood_zone = is_in_flood_zone(lat, lon)
    seismic_risk = is_in_high_seismic_zone(lat, lon)

    feasible = all([
        elevation_ok,
        temp_ok,
        not flood_zone,
        not seismic_risk
    ])

    return {
        "latitude": lat,
        "longitude": lon,
        "elevation_m": elevation,
        "elevation_ok": elevation_ok,
        "temperature_range_ok": temp_ok,
        "in_fema_flood_zone": flood_zone,
        "in_high_seismic_zone": seismic_risk,
        "feasible": feasible
    }

# Streamlit UI
st.title("EV Charging Site Feasibility Checker")

address = st.text_input("Enter a site address:")

if address:
    with st.spinner('Evaluating site feasibility...'):
        results = check_site_feasibility(address)

    if "status" in results:
        st.error("Invalid address or geocoding failed.")
    else:
        st.success("Feasibility evaluation complete.")
        st.write("**Feasibility Results:**")
        for key, value in results.items():
            st.write(f"{key.replace('_', ' ').capitalize()}: {value}")

        if results['feasible']:
            st.success("✅ Site is likely feasible for EV charging deployment.")
        else:
            st.error("❌ Site has one or more feasibility risks.")

