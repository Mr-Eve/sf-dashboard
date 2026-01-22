#!/usr/bin/env python3
"""
Test script to verify Open-Meteo weather API accuracy
Compares current temperature with another weather source
"""
import requests
import json
from datetime import datetime

def test_open_meteo():
    """Test Open-Meteo API (what the dashboard uses)"""
    url = 'https://api.open-meteo.com/v1/forecast'
    params = {
        'latitude': 37.7749,
        'longitude': -122.4194,
        'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m',
        'hourly': 'temperature_2m,precipitation_probability',
        'daily': 'sunrise,sunset',
        'temperature_unit': 'fahrenheit',
        'wind_speed_unit': 'mph',
        'timezone': 'America/Los_Angeles'
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data.get('current', {})
        hourly = data.get('hourly', {})
        daily = data.get('daily', {})
        
        print("=" * 60)
        print("OPEN-METEO API (Current Dashboard Source)")
        print("=" * 60)
        print(f"Location: {data.get('latitude')}, {data.get('longitude')}")
        print(f"Elevation: {data.get('elevation')}m")
        print(f"\nCURRENT CONDITIONS:")
        print(f"  Temperature: {current.get('temperature_2m', 'N/A')}°F")
        print(f"  Humidity: {current.get('relative_humidity_2m', 'N/A')}%")
        print(f"  Wind Speed: {current.get('wind_speed_10m', 'N/A')} mph")
        print(f"  Time: {current.get('time', 'N/A')}")
        
        if hourly.get('temperature_2m'):
            print(f"\nNEXT 3 HOURS:")
            for i in range(min(3, len(hourly['temperature_2m']))):
                time_str = hourly['time'][i]
                temp = hourly['temperature_2m'][i]
                rain = hourly.get('precipitation_probability', [0] * len(hourly['temperature_2m']))[i]
                print(f"  {time_str}: {temp}°F (rain: {rain}%)")
        
        if daily.get('sunrise') and daily.get('sunset'):
            print(f"\nSUNRISE/SUNSET:")
            print(f"  Sunrise: {daily['sunrise'][0]}")
            print(f"  Sunset: {daily['sunset'][0]}")
        
        return data
        
    except Exception as e:
        print(f"Error fetching Open-Meteo data: {e}")
        return None

def test_weather_gov():
    """Test NOAA/NWS API for comparison (US only, very accurate)"""
    # SF Bay Area grid point
    url = 'https://api.weather.gov/gridpoints/MTR/88,103/forecast/hourly'
    
    try:
        headers = {'User-Agent': 'SF-Dashboard-Test/1.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        periods = data.get('properties', {}).get('periods', [])
        if periods:
            current = periods[0]
            print("\n" + "=" * 60)
            print("NOAA/NWS API (For Comparison)")
            print("=" * 60)
            print(f"CURRENT CONDITIONS:")
            print(f"  Temperature: {current.get('temperature', 'N/A')}°F")
            print(f"  Wind: {current.get('windSpeed', 'N/A')} {current.get('windDirection', '')}")
            print(f"  Conditions: {current.get('shortForecast', 'N/A')}")
            print(f"  Time: {current.get('startTime', 'N/A')}")
            
            print(f"\nNEXT 3 HOURS:")
            for period in periods[1:4]:
                print(f"  {period.get('startTime', 'N/A')}: {period.get('temperature', 'N/A')}°F - {period.get('shortForecast', 'N/A')}")
            
            return data
    except Exception as e:
        print(f"\nNOAA/NWS API unavailable (may require US location): {e}")
        return None

def compare_accuracy(meteo_data, noaa_data):
    """Compare the two sources"""
    if not meteo_data or not noaa_data:
        print("\n" + "=" * 60)
        print("COMPARISON: Cannot compare (one or both APIs unavailable)")
        print("=" * 60)
        return
    
    meteo_temp = meteo_data.get('current', {}).get('temperature_2m')
    noaa_temp = noaa_data.get('properties', {}).get('periods', [{}])[0].get('temperature')
    
    if meteo_temp and noaa_temp:
        diff = abs(meteo_temp - noaa_temp)
        print("\n" + "=" * 60)
        print("ACCURACY COMPARISON")
        print("=" * 60)
        print(f"Open-Meteo: {meteo_temp}°F")
        print(f"NOAA/NWS:   {noaa_temp}°F")
        print(f"Difference: {diff}°F")
        
        if diff <= 2:
            print("✓ Very close match (within 2°F)")
        elif diff <= 5:
            print("⚠ Reasonable match (within 5°F)")
        else:
            print("⚠ Significant difference (>5°F)")

if __name__ == '__main__':
    print("Testing Weather API Accuracy for San Francisco")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    meteo_data = test_open_meteo()
    noaa_data = test_weather_gov()
    compare_accuracy(meteo_data, noaa_data)
    
    print("\n" + "=" * 60)
    print("NOTES:")
    print("=" * 60)
    print("• Open-Meteo is free, global, and doesn't require an API key")
    print("• NOAA/NWS is US-only but very accurate for US locations")
    print("• Temperature differences of 1-3°F are normal between sources")
    print("• Precipitation forecasts are less accurate than temperature")
    print("• The dashboard uses Open-Meteo (line 125 in dashboard.html)")
