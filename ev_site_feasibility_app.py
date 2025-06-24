import streamlit as st
import requests
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
Add commentMore actions
# Constants
POP_DENSITY_THRESHOLD = 1000
ROAD_DISTANCE_THRESHOLD = 0.5  # km
MAX_ELEVATION_M = 2400  # ~8,000 feet
TEMP_RANGE = (-20, 50)  # in Celsius
TEMP_RANGE = (-25, 45)  # in Celsius

def geocode_address(address):
    geolocator = Nominatim(user_agent="ev_feasibility_checker")
    location = geolocator.geocode(address)
    geolocator = Nominatim(user_agent="ev_feasibility_checker_v3")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    location = geocode(address)
    if location:
        return location.latitude, location.longitude
    return None, None
@@ -23,54 +25,48 @@
    way(around:{ROAD_DISTANCE_THRESHOLD * 1000},{lat},{lon})["highway"];
    out body;
    """
    response = requests.get(overpass_url, params={'data': query})
    data = response.json()
    return len(data.get("elements", [])) > 0
    try:
        response = requests.get(overpass_url, params={'data': query}, timeout=10)
        response.raise_for_status()
        data = response.json()
        return len(data.get("elements", [])) > 0
    except Exception as e:
        st.warning(f"Road API error: {e}")
        return False

def estimate_population_density(lat, lon):
    if 33 <= lat <= 38 and -120 <= lon <= -117:
        return 3000
    return 500
    # Simplified logic — replace with a real API or dataset
    return 500  # default to low density for now

def is_zoning_compatible(address):
    return "commercial" in address.lower() or "industrial" in address.lower()

def is_utility_available(lat, lon):
    return True

def get_elevation_usgs(lat, lon):
    url = f"https://nationalmap.gov/epqs/pqs.php?x={lon}&y={lat}&units=Meters&output=json"
def get_elevation(lat, lon):
    url = f"https://api.open-meteo.com/v1/elevation?latitude={lat}&longitude={lon}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        elevation = data['USGS_Elevation_Point_Query_Service']['Elevation_Query']['Elevation']
        st.write(f"Elevation (USGS) at {lat},{lon} is {elevation} m")
        elevation = data.get("elevation")
        st.write(f"Elevation (Open-Meteo) at {lat},{lon} is {elevation} m")
        return elevation
    except Exception as e:
        st.warning(f"USGS Elevation API error: {e}")
        st.warning(f"Open-Meteo Elevation API error: {e}")
        return None

def is_within_temp_range(lat, lon):
    url = (
        f"https://climate-api.open-meteo.com/v1/climate"
        f"?latitude={lat}&longitude={lon}&temperature_unit=celsius"
        f"&models=ERA5&format=json"
    )
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            annual = data.get('temperature_2m_mean', {}).get('annual', {})
            avg_min = annual.get('min', -50)
            avg_max = annual.get('max', 60)
            return TEMP_RANGE[0] <= avg_min and avg_max <= TEMP_RANGE[1]
    except Exception:
        pass
    return False
    # Replace with real API if needed
    avg_min_temp = 0
    avg_max_temp = 25
    temp_ok = TEMP_RANGE[0] <= avg_min_temp <= TEMP_RANGE[1] and TEMP_RANGE[0] <= avg_max_temp <= TEMP_RANGE[1]
    st.write(f"Temperature range check: {temp_ok} (min {avg_min_temp}, max {avg_max_temp})")
    return temp_ok

def is_in_flood_zone(lat, lon):
    url = "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query"
    url = "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/0/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
@@ -85,18 +81,29 @@
        response.raise_for_status()
        data = response.json()
        return len(data.get("features", [])) > 0
    except (requests.RequestException, ValueError):
        return False  # Assume not in flood zone on error
    except Exception as e:
        st.warning(f"FEMA flood zone API error: {e}")
        return False

def is_in_high_seismic_zone(lat, lon):
    # USGS proxy method - identify approximate hazard via USGS hazard map service
    url = f"https://earthquake.usgs.gov/ws/designmaps/asce7-16.json?latitude={lat}&longitude={lon}&riskCategory=II&siteClass=D"
    response = requests.get(url)
    if response.ok:
    url = "https://earthquake.usgs.gov/ws/designmaps/asce7-16.json"
    params = {
        "latitude": float(lat),
        "longitude": float(lon),
        "riskCategory": "II",
        "siteClass": "D"
    }
    headers = {"User-Agent": "EV-Feasibility-App"}
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        ss = float(data['response']['data']['ss'])
        return ss > 1.0  # Moderate to high seismic risk
    return False
        st.write(f"Seismic Ss value: {ss}")
        return ss > 1.0  # Consider risky if > 1.0
    except Exception as e:
        st.warning(f"USGS seismic risk API error: {e}")
        return False

def check_site_feasibility(address):
    lat, lon = geocode_address(address)
@@ -110,57 +117,57 @@
    zoning_ok = is_zoning_compatible(address)
    utility_ok = is_utility_available(lat, lon)

    elevation = get_elevation_usgs(lat, lon) or 1000
    elevation = get_elevation(lat, lon) or 1000
    elevation_ok = elevation < MAX_ELEVATION_M

    temp_ok = is_within_temp_range(lat, lon)
    flood_zone = is_in_flood_zone(lat, lon)
    seismic_risk = is_in_high_seismic_zone(lat, lon)

    feasible = all([
        near_roads,
        pop_density > POP_DENSITY_THRESHOLD,
        zoning_ok,
        utility_ok,
        elevation_ok,
        temp_ok,
        not flood_zone,
        not seismic_risk
    ])

    return {
        "latitude": lat,
        "longitude": lon,
        "near_major_roads": near_roads,
        "population_density": pop_density,
        "zoning_compatible": zoning_ok,
        "utility_available": utility_ok,
        "elevation_m": elevation,
        "elevation_ok": elevation_ok,
        "temperature_range_ok": temp_ok,
        "in_flood_zone": flood_zone,
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
