"""
Физическая модель расхода энергии электровелосипеда (Tractive Effort Model).

Модель учитывает:
1. Силу сопротивления качению колес по асфальту (Rolling Resistance).
2. Аэродинамическое сопротивление курьера с объемным коробом (Aerodynamic Drag).
3. Работу преодоления гравитации при наборе высоты (Gravity / Grade Resistance).
4. КПД электрической системы и трансмиссии (Controller + Motor + Drivetrain Efficiency).
5. Температурную деградацию полезной емкости Li-Ion аккумулятора на холоде.
6. Мульти-точечные маршруты и динамическое уменьшение веса короба при доставках.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional


@dataclass
class BikePreset:
    name: str
    battery_capacity_wh: float
    bike_weight_kg: float
    nominal_voltage_v: float
    rated_power_w: float
    description: str


BIKE_PRESETS: Dict[str, BikePreset] = {
    "courier_standard": BikePreset(
        name="Курьерский стандарт (48V 15Ah)",
        battery_capacity_wh=720.0,
        bike_weight_kg=32.0,
        nominal_voltage_v=48.0,
        rated_power_w=500.0,
        description="Самый популярный тип (Minako V8 / 'Колхозник'). Отличный баланс мощности и веса."
    ),
    "courier_heavy": BikePreset(
        name="Курьерский дальнобойный (60V 20Ah)",
        battery_capacity_wh=1200.0,
        bike_weight_kg=38.0,
        nominal_voltage_v=60.0,
        rated_power_w=750.0,
        description="Тяжелый байк с огромным запасом хода для полных смен."
    ),
    "city_compact": BikePreset(
        name="Городской легкий (36V 10.4Ah)",
        battery_capacity_wh=374.4,
        bike_weight_kg=20.0,
        nominal_voltage_v=36.0,
        rated_power_w=250.0,
        description="Легкий педальный электровелосипед для коротких городских поездок."
    )
}


def create_custom_preset(
    voltage_v: float,
    capacity_ah: float,
    bike_weight_kg: float = 30.0,
    rated_power_w: float = 500.0,
    name: str = "Мой кастомный электробайк"
) -> BikePreset:
    """Создает кастомный пресет электровелосипеда на основе Вольт и Ампер-часов."""
    capacity_wh = voltage_v * capacity_ah
    return BikePreset(
        name=name,
        battery_capacity_wh=capacity_wh,
        bike_weight_kg=bike_weight_kg,
        nominal_voltage_v=voltage_v,
        rated_power_w=rated_power_w,
        description=f"Кастомная сборка {voltage_v:.0f}V {capacity_ah:.1f}Ah ({capacity_wh:.0f} Вт·ч)"
    )


@dataclass
class SegmentCalculationResult:
    segment_idx: int
    distance_km: float
    ascent_m: float
    descent_m: float
    cargo_weight_kg: float
    energy_consumed_wh: float
    energy_consumed_percent: float


@dataclass
class EnergyCalculationResult:
    distance_km: float
    ascent_m: float
    descent_m: float
    duration_minutes: float
    energy_consumed_wh: float
    energy_consumed_percent: float
    wh_per_km: float
    effective_battery_capacity_wh: float
    temperature_capacity_factor: float
    initial_charge_percent: float
    final_charge_percent: float
    can_complete_route: bool
    safety_status: str  # "safe", "warning", "critical"
    details: Dict[str, float]
    effective_crr: float = 0.007
    road_condition: str = "dry"
    segments: List[SegmentCalculationResult] = field(default_factory=list)


# Коэффициенты трения качения для типов покрытий OpenRouteService
# https://openrouteservice-backend.readthedocs.io/en/latest/api/extra-info/
SURFACE_CRR_MAP: Dict[int, float] = {
    0: 0.007,   # Unknown (по умолчанию гладкий асфальт)
    1: 0.007,   # Paved
    2: 0.020,   # Unpaved
    3: 0.007,   # Asphalt
    4: 0.008,   # Concrete
    5: 0.018,   # Cobblestone (брусчатка)
    6: 0.008,   # Metal
    7: 0.010,   # Wood
    8: 0.015,   # Compacted Gravel
    9: 0.018,   # Fine Gravel
    10: 0.022,  # Gravel
    11: 0.025,  # Dirt
    12: 0.030,  # Ground / Mud
    13: 0.035,  # Ice / Snow
    14: 0.015,  # Paving Stones (тротуарная плитка)
    15: 0.060,  # Sand
    16: 0.025,  # Woodchips
    17: 0.030,  # Grass
    18: 0.020,  # Grass Paver
}

SURFACE_NAMES_RU: Dict[int, str] = {
    0: "Асфальт",
    1: "Асфальт/покрытие",
    2: "Без покрытия",
    3: "Асфальт",
    4: "Бетон",
    5: "Брусчатка",
    6: "Металл",
    7: "Дерево",
    8: "Утрамбованный гравий",
    9: "Мелкий гравий",
    10: "Гравий",
    11: "Грунт",
    12: "Грунтовая дорога",
    13: "Снег / лед",
    14: "Тротуарная плитка",
    15: "Песок",
    16: "Щепа",
    17: "Трава",
    18: "Экоплитка",
}


class EbikePhysicsModel:
    GRAVITY = 9.81  # м/с^2
    AIR_DENSITY_STP = 1.225  # кг/м^3 при 15°C
    ROLLING_COEFF = 0.007  # Базовый коэффициент трения качения велопокрышек по асфальту
    CDA_COURIER = 0.62  # Площадь * коэф лобового сопротивления курьера с термосумкой (м^2)
    SYSTEM_EFFICIENCY = 0.80  # КПД связки: аккумулятор -> контроллер -> мотор -> колесо
    AVERAGE_SPEED_KMH = 20.0  # Средняя скорость движения курьера в городе (км/ч)

    @classmethod
    def get_effective_crr(
        cls,
        base_crr: float = 0.007,
        road_condition: str = "dry"
    ) -> float:
        """
        Корректирует коэффициент трения качения в зависимости от дорожных и сезонных условий.
        - 'dry': сухое чистое полотно (множитель 1.0)
        - 'wet': мокрое полотно / дождь / лужи (множитель 1.30)
        - 'slush': зима, снежная каша, слякоть (множитель 3.20, минимум 0.028)
        """
        cond = (road_condition or "dry").lower()
        if cond == "wet":
            return round(base_crr * 1.30, 4)
        elif cond == "slush":
            return round(max(base_crr * 3.20, 0.028), 4)
        return round(base_crr, 4)

    @classmethod
    def calculate_weighted_crr_from_ors_summary(
        cls,
        surface_summary: List[Dict[str, Any]],
        road_condition: str = "dry"
    ) -> float:
        """
        Вычисляет взвешенный C_rr на основе сводки extra_info.surface от OpenRouteService.
        """
        if not surface_summary:
            return cls.get_effective_crr(cls.ROLLING_COEFF, road_condition)

        total_amount = sum(item.get("amount", 0.0) for item in surface_summary)
        if total_amount <= 0:
            return cls.get_effective_crr(cls.ROLLING_COEFF, road_condition)

        weighted_base = 0.0
        for item in surface_summary:
            code = int(item.get("value", 0))
            amt = item.get("amount", 0.0)
            base_crr = SURFACE_CRR_MAP.get(code, cls.ROLLING_COEFF)
            weighted_base += (amt / total_amount) * base_crr

        return cls.get_effective_crr(weighted_base, road_condition)

    @classmethod
    def get_temperature_capacity_factor(cls, temp_c: float) -> float:
        """
        Расчет эффективной емкости литий-ионного аккумулятора (18650 / 21700) в зависимости от температуры.
        При минусовых температурах растет внутреннее сопротивление и падает отдаваемая емкость.
        """
        if temp_c >= 20.0:
            return 1.00
        elif temp_c >= 10.0:
            return 0.95 + 0.05 * ((temp_c - 10.0) / 10.0)
        elif temp_c >= 0.0:
            return 0.88 + 0.07 * (temp_c / 10.0)
        elif temp_c >= -10.0:
            return 0.74 + 0.14 * ((temp_c + 10.0) / 10.0)
        elif temp_c >= -20.0:
            return 0.55 + 0.19 * ((temp_c + 20.0) / 10.0)
        else:
            return max(0.40, 0.55 + 0.015 * (temp_c + 20.0))

    @classmethod
    def calculate_energy(
        cls,
        distance_km: float,
        ascent_m: float,
        descent_m: float = 0.0,
        duration_seconds: float = 0.0,
        cargo_weight_kg: float = 5.0,
        rider_weight_kg: float = 75.0,
        bike_weight_kg: float = 32.0,
        battery_capacity_wh: float = 720.0,
        initial_charge_percent: float = 100.0,
        temp_c: float = 15.0,
        headwind_kmh: float = 0.0,
        regen_efficiency: float = 0.05,
        rolling_coeff: Optional[float] = None,
        road_condition: str = "dry",
    ) -> EnergyCalculationResult:
        """
        Рассчитывает потребление энергии для одиночного отрезка или суммарного маршрута с учетом дорожного покрытия.
        """
        eff_crr = rolling_coeff if rolling_coeff is not None else cls.get_effective_crr(cls.ROLLING_COEFF, road_condition)

        if distance_km <= 0:
            effective_cap = battery_capacity_wh * cls.get_temperature_capacity_factor(temp_c)
            return EnergyCalculationResult(
                distance_km=0.0,
                ascent_m=0.0,
                descent_m=0.0,
                duration_minutes=0.0,
                energy_consumed_wh=0.0,
                energy_consumed_percent=0.0,
                wh_per_km=0.0,
                effective_battery_capacity_wh=effective_cap,
                temperature_capacity_factor=cls.get_temperature_capacity_factor(temp_c),
                initial_charge_percent=initial_charge_percent,
                final_charge_percent=initial_charge_percent,
                can_complete_route=True,
                safety_status="safe",
                details={"rolling_wh": 0.0, "aero_wh": 0.0, "gravity_wh": 0.0},
                effective_crr=eff_crr,
                road_condition=road_condition
            )

        total_mass_kg = bike_weight_kg + rider_weight_kg + cargo_weight_kg
        distance_m = distance_km * 1000.0

        if duration_seconds > 0:
            speed_ms = distance_m / duration_seconds
            duration_min = duration_seconds / 60.0
        else:
            speed_ms = cls.AVERAGE_SPEED_KMH / 3.6
            duration_min = (distance_km / cls.AVERAGE_SPEED_KMH) * 60.0

        # 1. Сила и работа сопротивления качению: W_roll = F_roll * d с учетом типа покрытия и слякоти/снега
        f_roll = eff_crr * total_mass_kg * cls.GRAVITY
        work_roll_joules = f_roll * distance_m

        # 2. Аэродинамическое сопротивление: F_aero = 0.5 * rho * CdA * v_rel^2
        air_density = cls.AIR_DENSITY_STP * (288.15 / (temp_c + 273.15))
        rel_speed_ms = speed_ms + (headwind_kmh / 3.6)
        f_aero = 0.5 * air_density * cls.CDA_COURIER * (rel_speed_ms ** 2)
        work_aero_joules = f_aero * distance_m

        # 3. Гравитационная составляющая (набор высоты и рекуперация на спусках)
        work_climb_joules = total_mass_kg * cls.GRAVITY * max(0.0, ascent_m)
        work_regen_joules = total_mass_kg * cls.GRAVITY * max(0.0, descent_m) * regen_efficiency

        net_mechanical_work_joules = max(0.0, work_roll_joules + work_aero_joules + work_climb_joules - work_regen_joules)

        # Перевод в электрическую энергию батареи с учетом КПД
        electrical_energy_joules = net_mechanical_work_joules / cls.SYSTEM_EFFICIENCY
        energy_consumed_wh = electrical_energy_joules / 3600.0

        # Учет влияния температуры на доступную емкость АКБ
        temp_factor = cls.get_temperature_capacity_factor(temp_c)
        effective_capacity_wh = battery_capacity_wh * temp_factor

        consumed_percent = (energy_consumed_wh / effective_capacity_wh) * 100.0
        final_charge_percent = initial_charge_percent - consumed_percent

        wh_per_km = energy_consumed_wh / distance_km if distance_km > 0 else 0.0

        if final_charge_percent <= 0.0:
            can_complete = False
            safety_status = "critical"
        elif final_charge_percent < 15.0:
            can_complete = True
            safety_status = "warning"
        else:
            can_complete = True
            safety_status = "safe"

        details = {
            "rolling_wh": round((work_roll_joules / cls.SYSTEM_EFFICIENCY) / 3600.0, 2),
            "aero_wh": round((work_aero_joules / cls.SYSTEM_EFFICIENCY) / 3600.0, 2),
            "climb_wh": round((work_climb_joules / cls.SYSTEM_EFFICIENCY) / 3600.0, 2),
            "regen_saved_wh": round((work_regen_joules / cls.SYSTEM_EFFICIENCY) / 3600.0, 2),
        }

        return EnergyCalculationResult(
            distance_km=round(distance_km, 2),
            ascent_m=round(ascent_m, 1),
            descent_m=round(descent_m, 1),
            duration_minutes=round(duration_min, 1),
            energy_consumed_wh=round(energy_consumed_wh, 1),
            energy_consumed_percent=round(consumed_percent, 1),
            wh_per_km=round(wh_per_km, 1),
            effective_battery_capacity_wh=round(effective_capacity_wh, 1),
            temperature_capacity_factor=round(temp_factor, 2),
            initial_charge_percent=round(initial_charge_percent, 1),
            final_charge_percent=round(final_charge_percent, 1),
            can_complete_route=can_complete,
            safety_status=safety_status,
            details=details,
            effective_crr=eff_crr,
            road_condition=road_condition
        )

    @classmethod
    def calculate_multistop_energy(
        cls,
        segments_data: List[Dict[str, float]],
        total_cargo_start_kg: float = 6.0,
        rider_weight_kg: float = 75.0,
        bike_weight_kg: float = 32.0,
        battery_capacity_wh: float = 720.0,
        initial_charge_percent: float = 100.0,
        temp_c: float = 15.0,
        headwind_kmh: float = 0.0,
        is_round_trip: bool = False,
        rolling_coeff: Optional[float] = None,
        road_condition: str = "dry"
    ) -> EnergyCalculationResult:
        """
        Посегментный расчет мульти-доставки.
        На каждом промежуточном заказе вес короба уменьшается.
        Если включен round_trip, обратный путь на базу курьер едет с пустым рюкзаком (0 кг).
        """
        eff_crr = rolling_coeff if rolling_coeff is not None else cls.get_effective_crr(cls.ROLLING_COEFF, road_condition)
        num_segments = len(segments_data)
        if num_segments == 0:
            return cls.calculate_energy(
                0, 0, 0, 0, total_cargo_start_kg, rider_weight_kg,
                bike_weight_kg, battery_capacity_wh, initial_charge_percent, temp_c, headwind_kmh,
                rolling_coeff=eff_crr, road_condition=road_condition
            )

        temp_factor = cls.get_temperature_capacity_factor(temp_c)
        effective_capacity_wh = battery_capacity_wh * temp_factor

        total_distance = 0.0
        total_ascent = 0.0
        total_descent = 0.0
        total_duration = 0.0
        total_wh = 0.0

        details_sum = {"rolling_wh": 0.0, "aero_wh": 0.0, "climb_wh": 0.0, "regen_saved_wh": 0.0}
        segment_results: List[SegmentCalculationResult] = []

        # Количество доставок (исключая возврат в депо, если есть)
        delivery_segments_count = max(1, num_segments - 1 if is_round_trip else num_segments)

        for i, seg in enumerate(segments_data):
            # Расчет текущего веса груза
            if is_round_trip and i == num_segments - 1:
                # Возврат на базу: сумка пуста
                current_cargo = 0.0
            else:
                # Постепенная разгрузка
                current_cargo = total_cargo_start_kg * max(0.0, (1.0 - (i / delivery_segments_count)))

            seg_dist = seg.get("distance_km", 0.0)
            seg_ascent = seg.get("ascent_m", 0.0)
            seg_descent = seg.get("descent_m", 0.0)
            seg_duration = seg.get("duration_seconds", 0.0)

            res = cls.calculate_energy(
                distance_km=seg_dist,
                ascent_m=seg_ascent,
                descent_m=seg_descent,
                duration_seconds=seg_duration,
                cargo_weight_kg=current_cargo,
                rider_weight_kg=rider_weight_kg,
                bike_weight_kg=bike_weight_kg,
                battery_capacity_wh=battery_capacity_wh,
                initial_charge_percent=initial_charge_percent,
                temp_c=temp_c,
                headwind_kmh=headwind_kmh,
                rolling_coeff=eff_crr,
                road_condition=road_condition
            )

            total_distance += seg_dist
            total_ascent += seg_ascent
            total_descent += seg_descent
            total_duration += res.duration_minutes
            total_wh += res.energy_consumed_wh

            for k in details_sum:
                details_sum[k] += res.details.get(k, 0.0)

            segment_results.append(SegmentCalculationResult(
                segment_idx=i,
                distance_km=round(seg_dist, 2),
                ascent_m=round(seg_ascent, 1),
                descent_m=round(seg_descent, 1),
                cargo_weight_kg=round(current_cargo, 1),
                energy_consumed_wh=res.energy_consumed_wh,
                energy_consumed_percent=res.energy_consumed_percent
            ))

        consumed_percent = (total_wh / effective_capacity_wh) * 100.0
        final_charge = initial_charge_percent - consumed_percent

        if final_charge <= 0.0:
            can_complete = False
            safety_status = "critical"
        elif final_charge < 15.0:
            can_complete = True
            safety_status = "warning"
        else:
            can_complete = True
            safety_status = "safe"

        return EnergyCalculationResult(
            distance_km=round(total_distance, 2),
            ascent_m=round(total_ascent, 1),
            descent_m=round(total_descent, 1),
            duration_minutes=round(total_duration, 1),
            energy_consumed_wh=round(total_wh, 1),
            energy_consumed_percent=round(consumed_percent, 1),
            wh_per_km=round(total_wh / total_distance, 1) if total_distance > 0 else 0.0,
            effective_battery_capacity_wh=round(effective_capacity_wh, 1),
            temperature_capacity_factor=round(temp_factor, 2),
            initial_charge_percent=round(initial_charge_percent, 1),
            final_charge_percent=round(final_charge, 1),
            can_complete_route=can_complete,
            safety_status=safety_status,
            details={k: round(v, 2) for k, v in details_sum.items()},
            effective_crr=eff_crr,
            road_condition=road_condition,
            segments=segment_results
        )


def haversine_distance_km(p1: List[float], p2: List[float]) -> float:
    """Вычисляет расстояние между двумя точками [lat, lon] по формуле гаверсинусов (км)."""
    import math
    lat1, lon1 = math.radians(p1[0]), math.radians(p1[1])
    lat2, lon2 = math.radians(p2[0]), math.radians(p2[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2.0)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2.0)**2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return 6371.0 * c


@dataclass
class DeliveryOrderOptimizationResult:
    optimized_indices: List[int]
    reordered_waypoints: List[List[float]]
    original_estimated_energy_wh: float
    optimized_estimated_energy_wh: float
    energy_savings_percent: float
    explanation: str


def optimize_delivery_order(
    start_point: List[float],
    waypoints: List[List[float]],
    end_point: Optional[List[float]] = None,
    round_trip: bool = False,
    cargo_weight_kg: float = 6.0,
    rider_weight_kg: float = 75.0,
    bike_weight_kg: float = 32.0,
    road_condition: str = "dry",
) -> DeliveryOrderOptimizationResult:
    """
    Energy-Aware TSP: находит оптимальную последовательность доставок,
    минимизирующую механическую работу курьера с учетом постепенного сброса веса груза.
    Координаты задаются в формате [lat, lon].
    """
    import itertools

    n = len(waypoints)
    if n < 2:
        return DeliveryOrderOptimizationResult(
            optimized_indices=list(range(n)),
            reordered_waypoints=waypoints,
            original_estimated_energy_wh=0.0,
            optimized_estimated_energy_wh=0.0,
            energy_savings_percent=0.0,
            explanation="Для оптимизации порядка требуется как минимум 2 заказа."
        )

    final_target = start_point if round_trip else (end_point or start_point)
    eff_crr = EbikePhysicsModel.get_effective_crr(EbikePhysicsModel.ROLLING_COEFF, road_condition)

    def evaluate_order(indices: List[int]) -> float:
        total_energy_wh = 0.0
        prev_pt = start_point
        num_orders = len(indices)

        for i, idx in enumerate(indices):
            target_pt = waypoints[idx]
            # Городской коэффициент извилистости сети дорог ~1.32
            dist_km = haversine_distance_km(prev_pt, target_pt) * 1.32
            curr_cargo = cargo_weight_kg * max(0.0, 1.0 - (i / max(1, num_orders)))
            total_mass = bike_weight_kg + rider_weight_kg + curr_cargo
            
            # Оценка работы качения и аэродинамики
            f_roll = eff_crr * total_mass * EbikePhysicsModel.GRAVITY
            work_j = (f_roll * dist_km * 1000.0) / EbikePhysicsModel.SYSTEM_EFFICIENCY
            total_energy_wh += work_j / 3600.0
            prev_pt = target_pt

        # Отрезок на финиш / базу
        dist_to_finish = haversine_distance_km(prev_pt, final_target) * 1.32
        empty_mass = bike_weight_kg + rider_weight_kg
        f_roll_return = eff_crr * empty_mass * EbikePhysicsModel.GRAVITY
        return_work_j = (f_roll_return * dist_to_finish * 1000.0) / EbikePhysicsModel.SYSTEM_EFFICIENCY
        total_energy_wh += return_work_j / 3600.0

        return total_energy_wh

    original_indices = list(range(n))
    original_energy = evaluate_order(original_indices)

    best_indices: List[int] = []
    best_energy: float = float("inf")

    if n <= 8:
        # Точный перебор всех перестановок
        for perm in itertools.permutations(range(n)):
            e = evaluate_order(list(perm))
            if e < best_energy:
                best_energy = e
                best_indices = list(perm)
    else:
        # Энерго-жадный алгоритм
        unvisited = set(range(n))
        curr_pt = start_point
        best_indices = []
        step = 0

        while unvisited:
            best_next = None
            best_cost = float("inf")
            curr_cargo = cargo_weight_kg * max(0.0, 1.0 - (step / max(1, n)))
            total_mass = bike_weight_kg + rider_weight_kg + curr_cargo

            for candidate in unvisited:
                cand_pt = waypoints[candidate]
                d = haversine_distance_km(curr_pt, cand_pt)
                cost = d * total_mass
                if cost < best_cost:
                    best_cost = cost
                    best_next = candidate

            best_indices.append(best_next)
            unvisited.remove(best_next)
            curr_pt = waypoints[best_next]
            step += 1

        best_energy = evaluate_order(best_indices)

    savings_pct = 0.0
    if original_energy > 0:
        savings_pct = max(0.0, round(((original_energy - best_energy) / original_energy) * 100.0, 1))

    reordered = [waypoints[i] for i in best_indices]

    if savings_pct > 0.5:
        explanation = f"Оптимальный порядок экономит ~{savings_pct}% энергии за счет разгрузки сумки на ранних этапах пути."
    else:
        explanation = "Текущий порядок уже близок к оптимальному по расходу батареи."

    return DeliveryOrderOptimizationResult(
        optimized_indices=best_indices,
        reordered_waypoints=reordered,
        original_estimated_energy_wh=round(original_energy, 1),
        optimized_estimated_energy_wh=round(best_energy, 1),
        energy_savings_percent=savings_pct,
        explanation=explanation
    )
