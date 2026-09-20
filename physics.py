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
    segments: List[SegmentCalculationResult] = field(default_factory=list)


class EbikePhysicsModel:
    GRAVITY = 9.81  # м/с^2
    AIR_DENSITY_STP = 1.225  # кг/м^3 при 15°C
    ROLLING_COEFF = 0.007  # Коэффициент трения качения велопокрышек по асфальту
    CDA_COURIER = 0.62  # Площадь * коэф лобового сопротивления курьера с термосумкой (м^2)
    SYSTEM_EFFICIENCY = 0.80  # КПД связки: аккумулятор -> контроллер -> мотор -> колесо
    AVERAGE_SPEED_KMH = 20.0  # Средняя скорость движения курьера в городе (км/ч)

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
    ) -> EnergyCalculationResult:
        """
        Рассчитывает потребление энергии для одиночного отрезка или суммарного маршрута.
        """
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
                details={"rolling_wh": 0.0, "aero_wh": 0.0, "gravity_wh": 0.0}
            )

        total_mass_kg = bike_weight_kg + rider_weight_kg + cargo_weight_kg
        distance_m = distance_km * 1000.0

        if duration_seconds > 0:
            speed_ms = distance_m / duration_seconds
            duration_min = duration_seconds / 60.0
        else:
            speed_ms = cls.AVERAGE_SPEED_KMH / 3.6
            duration_min = (distance_km / cls.AVERAGE_SPEED_KMH) * 60.0

        # 1. Сила и работа сопротивления качению: W_roll = F_roll * d
        f_roll = cls.ROLLING_COEFF * total_mass_kg * cls.GRAVITY
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
        is_round_trip: bool = False
    ) -> EnergyCalculationResult:
        """
        Посегментный расчет мульти-доставки.
        На каждом промежуточном заказе вес короба уменьшается.
        Если включен round_trip, обратный путь на базу курьер едет с пустым рюкзаком (0 кг).
        """
        num_segments = len(segments_data)
        if num_segments == 0:
            return cls.calculate_energy(
                0, 0, 0, 0, total_cargo_start_kg, rider_weight_kg,
                bike_weight_kg, battery_capacity_wh, initial_charge_percent, temp_c, headwind_kmh
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
                headwind_kmh=headwind_kmh
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
            segments=segment_results
        )
