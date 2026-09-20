from fastapi import FastAPI
import requests
import joblib

app = FastAPI()
# Загружаем наш обученный ИИ
model = joblib.load('battery_model.pkl')

# Вставьте ваш скопированный длинный ключ между кавычками вместо слова ВСТАВЬТЕ_КЛЮЧ_СЮДА:
ORS_TOKEN = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjdhN2FlNzVjNDkyZTRkNmJiOTc0OWZkYWI5MWZiMzBjIiwiaCI6Im11cm11cjY0In0="

@app.get("/optimize")
def get_route(start_lon: float, start_lat: float, end_lon: float, end_lat: float, weight: float, temp: float):
    url = f"https://api.openrouteservice.org/v2/directions/cycling-electric?api_key={ORS_TOKEN}&start={start_lon},{start_lat}&end={end_lon},{end_lat}"
    
    response = requests.get(url).json()
    
    if 'error' in response or 'features' not in response:
        return {"error": "Не удалось построить маршрут. Проверьте координаты."}

    distance_km = response['features'][0]['properties']['summary']['distance'] / 1000
    elevation_m = response['features'][0]['properties']['summary']['ascent']
    geometry = response['features'][0]['geometry']['coordinates']

    predicted_drop = model.predict([[distance_km, elevation_m, weight, temp]])[0]

    return {
        "distance_km": round(distance_km, 2),
        "predicted_battery_drop_percent": round(predicted_drop, 1),
        "geometry": geometry
    }