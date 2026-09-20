"""
FastAPI Backend для ebike-ai-router:
- Асинхронные запросы к OpenRouteService через httpx
- Расчет реалистичного расхода энергии через physics.py
- Построение и сравнение альтернативных маршрутов (Быстрый vs Эко-пологий)
"""

import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
from dotenv import load_dotenv

from physics import EbikePhysicsModel, BIKE_PRESETS, BikePreset

load_dotenv()

ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/cycling-electric/geojson"

app = FastAPI(
    title="E-Bike AI Route & Energy Optimizer",
    description="API для построения маршрутов и оптимизации расхода батареи электровелосипедов курьеров",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    start_lon: float = Field(..., ge=-180, le=180, description="Долгота точки старта")
    start_lat: float = Field(..., ge=-90, le=90, description="Широта точки старта")
    end_lon: float = Field(..., ge=-180, le=180, description="Долгота точки финиша")
    end_lat: float = Field(..., ge=-90, le=90, description="Широта точки финиша")
    bike_preset: str = Field("courier_standard", description="Пресет электровелосипеда")
    custom_battery_capacity_wh: Optional[float] = Field(None, gt=50, le=5000, description="Кастомная емкость АКБ (Вт*ч)")
    cargo_weight_kg: float = Field(5.0, ge=0.0, le=50.0, description="Вес термосумки/груза (кг)")
    rider_weight_kg: float = Field(75.0, ge=30.0, le=160.0, description="Вес курьера (кг)")
    temp_c: float = Field(15.0, ge=-40.0, le=50.0, description="Температура на улице (°C)")
    initial_charge_percent: float = Field(100.0, ge=1.0, le=100.0, description="Текущий уровень заряда батареи (%)")
    headwind_kmh: float = Field(0.0, ge=0.0, le=100.0, description="Скорость встречного ветра (км/ч)")
    find_alternatives: bool = Field(True, description="Искать альтернативные маршруты (быстрый vs эко)")


class RouteDetails(BaseModel):
    route_id: int
    name: str
    is_recommended: bool
    recommendation_reason: str
    distance_km: float
    ascent_m: float
    descent_m: float
    duration_minutes: float
    energy_consumed_wh: float
    energy_consumed_percent: float
    wh_per_km: float
    final_charge_percent: float
    can_complete_route: bool
    safety_status: str
    energy_breakdown: Dict[str, float]
    geometry: List[List[float]]


class RouteOptimizationResponse(BaseModel):
    status: str
    routes: List[RouteDetails]
    bike_info: Dict[str, Any]
    ambient_info: Dict[str, Any]


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "has_ors_key": bool(ORS_API_KEY and not ORS_API_KEY.startswith("your_")),
        "presets": {k: {"name": v.name, "capacity_wh": v.battery_capacity_wh} for k, v in BIKE_PRESETS.items()}
    }


async def _fetch_routes_from_ors(
    start_lon: float,
    start_lat: float,
    end_lon: float,
    end_lat: float,
    find_alternatives: bool
) -> List[Dict[str, Any]]:
    """Асинхронный запрос маршрутов в OpenRouteService с профилем высот."""
    if not ORS_API_KEY or ORS_API_KEY.startswith("your_"):
        raise HTTPException(
            status_code=500,
            detail="ORS_API_KEY не сконфигурирован в .env файле. Получите бесплатный ключ на openrouteservice.org"
        )

    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }

    body: Dict[str, Any] = {
        "coordinates": [[start_lon, start_lat], [end_lon, end_lat]],
        "elevation": True,
    }

    if find_alternatives:
        body["alternative_routes"] = {
            "target_count": 2,
            "share_factor": 0.8,
            "weight_factor": 1.6
        }

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.post(ORS_DIRECTIONS_URL, headers=headers, json=body)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=502, detail=f"Сетевая ошибка при обращении к гео-сервису: {str(exc)}")

    if response.status_code != 200:
        error_msg = response.text
        try:
            err_json = response.json()
            if "error" in err_json:
                error_msg = err_json["error"].get("message", error_msg)
        except Exception:
            pass
        raise HTTPException(
            status_code=response.status_code,
            detail=f"OpenRouteService вернул ошибку: {error_msg}"
        )

    data = response.json()
    features = data.get("features", [])
    if not features:
        raise HTTPException(status_code=404, detail="Маршрут между указанными точками не найден.")

    return features


def _process_routes_energy(
    features: List[Dict[str, Any]],
    req: RouteRequest
) -> RouteOptimizationResponse:
    # Определение параметров байка
    preset = BIKE_PRESETS.get(req.bike_preset, BIKE_PRESETS["courier_standard"])
    battery_capacity = req.custom_battery_capacity_wh or preset.battery_capacity_wh
    bike_weight = preset.bike_weight_kg

    computed_routes: List[RouteDetails] = []

    for idx, feat in enumerate(features):
        segment = feat["properties"]["segments"][0]
        distance_km = segment.get("distance", 0.0) / 1000.0
        duration_sec = segment.get("duration", 0.0)
        ascent_m = segment.get("ascent", 0.0)
        descent_m = segment.get("descent", 0.0)
        coords = feat["geometry"]["coordinates"]

        # Если ORS вернул плоский сегмент, рассчитаем перепад по 3D точкам
        if ascent_m == 0.0 and len(coords) > 1 and len(coords[0]) > 2:
            elevations = [c[2] for c in coords if len(c) > 2]
            ascent_m = sum(max(0.0, elevations[i] - elevations[i-1]) for i in range(1, len(elevations)))
            descent_m = sum(max(0.0, elevations[i-1] - elevations[i]) for i in range(1, len(elevations)))

        energy_res = EbikePhysicsModel.calculate_energy(
            distance_km=distance_km,
            ascent_m=ascent_m,
            descent_m=descent_m,
            duration_seconds=duration_sec,
            cargo_weight_kg=req.cargo_weight_kg,
            rider_weight_kg=req.rider_weight_kg,
            bike_weight_kg=bike_weight,
            battery_capacity_wh=battery_capacity,
            initial_charge_percent=req.initial_charge_percent,
            temp_c=req.temp_c,
            headwind_kmh=req.headwind_kmh,
        )

        name = "Основной маршрут" if idx == 0 else f"Альтернативный маршрут #{idx}"

        computed_routes.append(RouteDetails(
            route_id=idx,
            name=name,
            is_recommended=False,
            recommendation_reason="",
            distance_km=energy_res.distance_km,
            ascent_m=energy_res.ascent_m,
            descent_m=energy_res.descent_m,
            duration_minutes=energy_res.duration_minutes,
            energy_consumed_wh=energy_res.energy_consumed_wh,
            energy_consumed_percent=energy_res.energy_consumed_percent,
            wh_per_km=energy_res.wh_per_km,
            final_charge_percent=energy_res.final_charge_percent,
            can_complete_route=energy_res.can_complete_route,
            safety_status=energy_res.safety_status,
            energy_breakdown=energy_res.details,
            geometry=coords
        ))

    # Логика AI-рекомендации оптимального маршрута
    if len(computed_routes) > 1:
        # Сравниваем: если у курьера мало заряда, рекомендуем наименее энергозатратный
        lowest_energy = min(computed_routes, key=lambda r: r.energy_consumed_wh)
        fastest = min(computed_routes, key=lambda r: r.duration_minutes)

        if req.initial_charge_percent < 25.0 or not fastest.can_complete_route:
            lowest_energy.is_recommended = True
            lowest_energy.recommendation_reason = "Энергосберегающий выбор: экономит АКБ при низком остатке заряда."
            if fastest != lowest_energy:
                fastest.name = "Быстрый маршрут (энергоемкий)"
                lowest_energy.name = "Эко-маршрут (минимальный набор высоты)"
        else:
            fastest.is_recommended = True
            fastest.recommendation_reason = "Оптимальный баланс времени доставки и расхода батареи."
            fastest.name = "Самый быстрый маршрут"
            if lowest_energy != fastest:
                lowest_energy.name = "Эко-альтернатива (пологий рельеф)"
    elif computed_routes:
        computed_routes[0].is_recommended = True
        computed_routes[0].recommendation_reason = "Единственный доступный маршрут."

    return RouteOptimizationResponse(
        status="ok",
        routes=computed_routes,
        bike_info={
            "preset_key": req.bike_preset,
            "preset_name": preset.name,
            "battery_capacity_wh": battery_capacity,
            "bike_weight_kg": bike_weight,
            "effective_capacity_wh": round(battery_capacity * EbikePhysicsModel.get_temperature_capacity_factor(req.temp_c), 1)
        },
        ambient_info={
            "temp_c": req.temp_c,
            "headwind_kmh": req.headwind_kmh,
            "cargo_weight_kg": req.cargo_weight_kg,
            "rider_weight_kg": req.rider_weight_kg,
            "temperature_capacity_factor": round(EbikePhysicsModel.get_temperature_capacity_factor(req.temp_c), 2)
        }
    )


@app.post("/optimize", response_model=RouteOptimizationResponse)
async def optimize_route(request: RouteRequest):
    """
    Основной POST-эндпоинт для расчета и оптимизации маршрута.
    """
    features = await _fetch_routes_from_ors(
        start_lon=request.start_lon,
        start_lat=request.start_lat,
        end_lon=request.end_lon,
        end_lat=request.end_lat,
        find_alternatives=request.find_alternatives
    )
    return _process_routes_energy(features, request)


@app.get("/optimize")
async def optimize_route_get(
    start_lon: float = Query(..., ge=-180, le=180),
    start_lat: float = Query(..., ge=-90, le=90),
    end_lon: float = Query(..., ge=-180, le=180),
    end_lat: float = Query(..., ge=-90, le=90),
    weight: float = Query(5.0, ge=0.0, le=50.0, description="Вес сумки (кг)"),
    temp: float = Query(15.0, ge=-40.0, le=50.0, description="Температура (°C)"),
    bike_preset: str = Query("courier_standard"),
    battery_wh: Optional[float] = Query(None),
    charge: float = Query(100.0, ge=1.0, le=100.0)
):
    """
    GET-эндпоинт для обратной совместимости и быстрого тестирования в браузере.
    """
    req = RouteRequest(
        start_lon=start_lon,
        start_lat=start_lat,
        end_lon=end_lon,
        end_lat=end_lat,
        cargo_weight_kg=weight,
        temp_c=temp,
        bike_preset=bike_preset,
        custom_battery_capacity_wh=battery_wh,
        initial_charge_percent=charge,
        find_alternatives=True
    )
    res = await optimize_route(req)
    # Формируем компактный ответ, совместимый со старым форматом + расширенные данные
    primary = res.routes[0]
    return {
        "distance_km": primary.distance_km,
        "ascent_m": primary.ascent_m,
        "predicted_battery_drop_percent": primary.energy_consumed_percent,
        "energy_consumed_wh": primary.energy_consumed_wh,
        "final_charge_percent": primary.final_charge_percent,
        "safety_status": primary.safety_status,
        "geometry": primary.geometry,
        "all_routes": [r.model_dump() for r in res.routes]
    }