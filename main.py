"""
FastAPI Backend для ebike-ai-router:
- Поддержка мульти-точечных маршрутов (Waypoints) и режима "Туда и обратно" (Round Trip)
- Асинхронные запросы к OpenRouteService через httpx
- Расчет реалистичного расхода энергии через physics.py с учетом сброса веса на точках
- Генерация профиля высот для интерактивных графиков
"""

import os
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx
from dotenv import load_dotenv

from physics import (
    EbikePhysicsModel,
    BIKE_PRESETS,
    BikePreset,
    create_custom_preset
)

load_dotenv()

ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/cycling-electric/geojson"

app = FastAPI(
    title="E-Bike AI Route & Energy Optimizer",
    description="API для построения маршрутов, мульти-доставок и оптимизации расхода батареи электровелосипедов курьеров",
    version="2.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteRequest(BaseModel):
    # Поддержка одиночного отрезка
    start_lon: Optional[float] = Field(None, ge=-180, le=180)
    start_lat: Optional[float] = Field(None, ge=-90, le=90)
    end_lon: Optional[float] = Field(None, ge=-180, le=180)
    end_lat: Optional[float] = Field(None, ge=-90, le=90)
    
    # Поддержка мульти-точек: список [[lon, lat], [lon, lat], ...]
    coordinates: Optional[List[List[float]]] = Field(
        None,
        description="Массив координат маршрута [[lon, lat], ...]. Если указан, переопределяет start/end."
    )
    round_trip: bool = Field(False, description="Закольцевать маршрут (Туда и обратно / возврат на базу)")
    
    # Настройки транспорта
    bike_preset: str = Field("courier_standard", description="Пресет байка или 'custom'")
    custom_voltage_v: Optional[float] = Field(None, ge=24.0, le=96.0, description="Напряжение АКБ (Вольты)")
    custom_capacity_ah: Optional[float] = Field(None, ge=2.0, le=80.0, description="Емкость АКБ (Ампер-часы)")
    custom_bike_weight_kg: Optional[float] = Field(None, ge=10.0, le=60.0)
    custom_battery_capacity_wh: Optional[float] = Field(None, gt=50, le=5000)
    
    # Условия
    cargo_weight_kg: float = Field(6.0, ge=0.0, le=50.0, description="Вес сумки на старте (кг)")
    rider_weight_kg: float = Field(75.0, ge=30.0, le=160.0, description="Вес курьера (кг)")
    temp_c: float = Field(15.0, ge=-40.0, le=50.0, description="Температура на улице (°C)")
    initial_charge_percent: float = Field(80.0, ge=1.0, le=100.0, description="Текущий уровень заряда батареи (%)")
    headwind_kmh: float = Field(0.0, ge=0.0, le=100.0, description="Скорость ветра (км/ч)")
    find_alternatives: bool = Field(True, description="Искать альтернативные маршруты")


class ElevationPoint(BaseModel):
    distance_km: float
    elevation_m: float


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
    elevation_profile: List[ElevationPoint]


class RouteOptimizationResponse(BaseModel):
    status: str
    routes: List[RouteDetails]
    bike_info: Dict[str, Any]
    ambient_info: Dict[str, Any]
    is_round_trip: bool


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "has_ors_key": bool(ORS_API_KEY and not ORS_API_KEY.startswith("your_")),
        "presets": {k: {"name": v.name, "capacity_wh": v.battery_capacity_wh} for k, v in BIKE_PRESETS.items()}
    }


def _resolve_coordinates(req: RouteRequest) -> List[List[float]]:
    if req.coordinates and len(req.coordinates) >= 2:
        coords = [list(c) for c in req.coordinates]
    elif req.start_lon is not None and req.start_lat is not None and req.end_lon is not None and req.end_lat is not None:
        coords = [[req.start_lon, req.start_lat], [req.end_lon, req.end_lat]]
    else:
        raise HTTPException(
            status_code=400,
            detail="Необходимо передать либо start_lon/lat и end_lon/lat, либо массив coordinates (минимум 2 точки)."
        )

    # Логика закольцовывания маршрута
    if req.round_trip and len(coords) >= 2:
        if coords[-1] != coords[0]:
            coords.append(coords[0])

    return coords


async def _fetch_routes_from_ors(
    coords: List[List[float]],
    find_alternatives: bool
) -> List[Dict[str, Any]]:
    """Асинхронный запрос маршрутов в OpenRouteService с профилем высот."""
    if not ORS_API_KEY or ORS_API_KEY.startswith("your_"):
        raise HTTPException(
            status_code=500,
            detail="ORS_API_KEY не сконфигурирован в .env файле. Получите ключ на openrouteservice.org"
        )

    headers = {
        "Authorization": ORS_API_KEY,
        "Content-Type": "application/json"
    }

    body: Dict[str, Any] = {
        "coordinates": coords,
        "elevation": True,
    }

    # Альтернативные маршруты доступны только для 2 точек в ORS API
    if find_alternatives and len(coords) == 2:
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
    # Определение параметров байка (пресет или кастом)
    if req.custom_voltage_v and req.custom_capacity_ah:
        bike = create_custom_preset(
            voltage_v=req.custom_voltage_v,
            capacity_ah=req.custom_capacity_ah,
            bike_weight_kg=req.custom_bike_weight_kg or 32.0
        )
    elif req.bike_preset in BIKE_PRESETS:
        bike = BIKE_PRESETS[req.bike_preset]
    else:
        bike = BIKE_PRESETS["courier_standard"]

    battery_capacity = req.custom_battery_capacity_wh or bike.battery_capacity_wh
    bike_weight = bike.bike_weight_kg

    computed_routes: List[RouteDetails] = []

    for idx, feat in enumerate(features):
        segments = feat["properties"].get("segments", [])
        coords = feat["geometry"]["coordinates"]

        # Собираем данные сегментов для посегментного расчета
        segments_data = []
        for seg in segments:
            segments_data.append({
                "distance_km": seg.get("distance", 0.0) / 1000.0,
                "duration_seconds": seg.get("duration", 0.0),
                "ascent_m": seg.get("ascent", 0.0),
                "descent_m": seg.get("descent", 0.0),
            })

        # Если сегментов не было или перепады нулевые, проверим по 3D координатам
        if not segments_data:
            summary = feat["properties"].get("summary", {})
            segments_data.append({
                "distance_km": summary.get("distance", 0.0) / 1000.0,
                "duration_seconds": summary.get("duration", 0.0),
                "ascent_m": summary.get("ascent", 0.0),
                "descent_m": summary.get("descent", 0.0),
            })

        energy_res = EbikePhysicsModel.calculate_multistop_energy(
            segments_data=segments_data,
            total_cargo_start_kg=req.cargo_weight_kg,
            rider_weight_kg=req.rider_weight_kg,
            bike_weight_kg=bike_weight,
            battery_capacity_wh=battery_capacity,
            initial_charge_percent=req.initial_charge_percent,
            temp_c=req.temp_c,
            headwind_kmh=req.headwind_kmh,
            is_round_trip=req.round_trip
        )

        # Генерация профиля высот вдоль маршрута
        profile: List[ElevationPoint] = []
        cum_dist = 0.0
        for i, pt in enumerate(coords):
            ele = pt[2] if len(pt) > 2 else 0.0
            if i > 0:
                # Примерное расстояние между точками
                p1, p2 = coords[i-1], coords[i]
                d_lat = (p2[1] - p1[1]) * 111.0
                d_lon = (p2[0] - p1[0]) * 71.5
                cum_dist += (d_lat**2 + d_lon**2)**0.5
            profile.append(ElevationPoint(
                distance_km=round(cum_dist, 2),
                elevation_m=round(ele, 1)
            ))

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
            geometry=coords,
            elevation_profile=profile[::max(1, len(profile)//100)]  # сэмплирование до 100 точек
        ))

    # Рекомендации
    if len(computed_routes) > 1:
        lowest_energy = min(computed_routes, key=lambda r: r.energy_consumed_wh)
        fastest = min(computed_routes, key=lambda r: r.duration_minutes)

        if req.initial_charge_percent < 25.0 or not fastest.can_complete_route:
            lowest_energy.is_recommended = True
            lowest_energy.recommendation_reason = "Энергосберегающий выбор: экономит АКБ при низком заряде."
            fastest.name = "Быстрый маршрут (энергоемкий)"
            lowest_energy.name = "Эко-маршрут (пологий рельеф)"
        else:
            fastest.is_recommended = True
            fastest.recommendation_reason = "Оптимальный баланс скорости доставки и расхода батареи."
            fastest.name = "Самый быстрый маршрут"
            lowest_energy.name = "Эко-альтернатива (пологий)"
    elif computed_routes:
        computed_routes[0].is_recommended = True
        computed_routes[0].recommendation_reason = "Рассчитанный маршрут с учетом рельефа и остатка батареи."

    return RouteOptimizationResponse(
        status="ok",
        routes=computed_routes,
        bike_info={
            "preset_name": bike.name,
            "battery_capacity_wh": battery_capacity,
            "voltage_v": bike.nominal_voltage_v,
            "bike_weight_kg": bike_weight,
            "effective_capacity_wh": round(battery_capacity * EbikePhysicsModel.get_temperature_capacity_factor(req.temp_c), 1)
        },
        ambient_info={
            "temp_c": req.temp_c,
            "cargo_weight_start_kg": req.cargo_weight_kg,
            "rider_weight_kg": req.rider_weight_kg,
            "temperature_capacity_factor": round(EbikePhysicsModel.get_temperature_capacity_factor(req.temp_c), 2)
        },
        is_round_trip=req.round_trip
    )


@app.post("/optimize", response_model=RouteOptimizationResponse)
async def optimize_route(request: RouteRequest):
    """
    Основной POST-эндпоинт для расчета и оптимизации мульти-точечных маршрутов.
    """
    coords = _resolve_coordinates(request)
    features = await _fetch_routes_from_ors(
        coords=coords,
        find_alternatives=request.find_alternatives
    )
    return _process_routes_energy(features, request)


@app.get("/optimize")
async def optimize_route_get(
    start_lon: float = Query(..., ge=-180, le=180),
    start_lat: float = Query(..., ge=-90, le=90),
    end_lon: float = Query(..., ge=-180, le=180),
    end_lat: float = Query(..., ge=-90, le=90),
    round_trip: bool = Query(False),
    weight: float = Query(6.0, ge=0.0, le=50.0),
    temp: float = Query(15.0, ge=-40.0, le=50.0),
    bike_preset: str = Query("courier_standard"),
    battery_wh: Optional[float] = Query(None),
    charge: float = Query(80.0, ge=1.0, le=100.0)
):
    """
    GET-эндпоинт для быстрой проверки и обратной совместимости.
    """
    req = RouteRequest(
        start_lon=start_lon,
        start_lat=start_lat,
        end_lon=end_lon,
        end_lat=end_lat,
        round_trip=round_trip,
        cargo_weight_kg=weight,
        temp_c=temp,
        bike_preset=bike_preset,
        custom_battery_capacity_wh=battery_wh,
        initial_charge_percent=charge,
        find_alternatives=True
    )
    res = await optimize_route(req)
    primary = res.routes[0]
    return {
        "distance_km": primary.distance_km,
        "ascent_m": primary.ascent_m,
        "predicted_battery_drop_percent": primary.energy_consumed_percent,
        "energy_consumed_wh": primary.energy_consumed_wh,
        "final_charge_percent": primary.final_charge_percent,
        "safety_status": primary.safety_status,
        "is_round_trip": res.is_round_trip,
        "geometry": primary.geometry,
        "all_routes": [r.model_dump() for r in res.routes]
    }