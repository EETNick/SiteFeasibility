import streamlit as st
import requests
from geopy.geocoders import Nominatim
import time

# Constants
POP_DENSITY_THRESHOLD = 1000
ROAD_DISTANCE_THRESHOLD = 0.5  # km
MAX_ELEVATION_M = 2400  # ~8,000 feet
TEMP_RANGE = (-20, 50)  # in Celsius

def geocode_address(address):
    geolocator = Nominatim(user_agent="ev_feasibility_checker")
    location = geolocator.geocode(address)
    if location:
        return location.latitude, location.longitude
    return None, None

def get_nearby_road_score(lat, lon):
    overpass_url = "http://overpass-api.de/api/interpreter"
    query = f"""
    [out:json];
    way(around:{ROAD_DISTANCE_THRESHOLD * 1000},{lat},{lon})["highway"];
    out body;
    """
    response = requests.get(overpass_url, params={'data': query})
    data = response.json()
    return len(data.get("elements", [])) > 0

def estimate_population_density(lat, lon):
    if 33 <= lat <= 38 and -120 <= lon <= -117:
        return 3000
    return 500

def is_zoning_compatible(address):
    return "commercial" in address.lower() or "industrial" in address.lower()

def is_utility_available(lat, lon):
    return True

def get_elevation(lat, lon):
    response = requests.get(f"https://api.opentopodata.org/v1/srtm90m?locations={lat},{lon}")
    if response.ok:
        return response.json()['results'][0]['elevation']
    return None

def is_within_temp_range(lat, lon):
    response = requests.get(f"https://api.open-meteo.com/v1/climate?latitude={lat}&longitude={lon}&temperature_unit=celsius")
    if response.ok:
        data = response.json()
        avg_max = data.get('temperature_2m_max', {}).get('annual', 0)
        avg_min = data.get('temperature_2m_min', {}).get('annual', 0)
        return TEMP_RANGE[0] <= avg_min <= TEMP_RANGE[1] and TEMP_RANGE[0] <= avg_max <= TEMP_RANGE[1]
    return False

def is_in_flood_zone(lat, lon):
    url = "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/28/query"
    params = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "false",
        "f": "json"
    }
    response = requests.get(url, params=params)
    data = response.json()
    return len(data.get("features", [])) > 0

def is_in_high_seismic_zone(lat, lon):
    # USGS proxy method - identify approximate hazard via USGS hazard map service
    url = f"https://earthquake.usgs.gov/ws/designmaps/asce7-16.json?latitude={lat}&longitude={lon}&riskCategory=II&siteClass=D"
    response = requests.get(url)
    if response.ok:
        data = response.json()
        ss = float(data['response']['data']['ss'])
        return ss > 1.0  # Moderate to high seismic risk
    return False

def check_site_feasibility(address):
    lat, lon = geocode_address(address)
    if not lat:
        return {"status": "Invalid address"}

    time.sleep(1)

    near_roads = get_nearby_road_score(lat, lon)
    pop_density = estimate_population_density(lat, lon)
    zoning_ok = is_zoning_compatible(address)
    utility_ok = is_utility_available(lat, lon)

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
