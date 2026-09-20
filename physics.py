"""
Физическая модель расхода энергии электровелосипеда (Tractive Effort Model).

Модель учитывает:
1. Силу сопротивления качению колес по асфальту (Rolling Resistance).
2. Аэродинамическое сопротивление курьера с объемным коробом (Aerodynamic Drag).
3. Работу преодоления гравитации при наборе высоты (Gravity / Grade Resistance).
4. КПД электрической системы и трансмиссии (Controller + Motor + Drivetrain Efficiency).
5. Температурную деградацию полезной емкости Li-Ion аккумулятора на холоде.
"""

from dataclasses import dataclass
from typing import Dict, Any


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
        Рассчитывает потребление энергии на основе физических параметров поездки.
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

        # Общая движущаяся масса
        total_mass_kg = bike_weight_kg + rider_weight_kg + cargo_weight_kg
        distance_m = distance_km * 1000.0

        # Время движения и скорость
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
        # Плотность воздуха с поправкой на температуру (уравнение Менделеева-Клапейрона)
        air_density = cls.AIR_DENSITY_STP * (288.15 / (temp_c + 273.15))
        rel_speed_ms = speed_ms + (headwind_kmh / 3.6)
        f_aero = 0.5 * air_density * cls.CDA_COURIER * (rel_speed_ms ** 2)
        work_aero_joules = f_aero * distance_m

        # 3. Гравитационная составляющая (набор высоты): W_climb = m * g * delta_h
        work_climb_joules = total_mass_kg * cls.GRAVITY * max(0.0, ascent_m)
        # Рекуперация/накат на спусках (ограниченная отдача в АКБ)
        work_regen_joules = total_mass_kg * cls.GRAVITY * max(0.0, descent_m) * regen_efficiency

        # Суммарная механическая работа
        net_mechanical_work_joules = work_roll_joules + work_aero_joules + work_climb_joules - work_regen_joules
        net_mechanical_work_joules = max(net_mechanical_work_joules, 0.0)

        # Перевод в электрическую энергию батареи с учетом КПД
        # 1 Вт*ч = 3600 Джоулей
        electrical_energy_joules = net_mechanical_work_joules / cls.SYSTEM_EFFICIENCY
        energy_consumed_wh = electrical_energy_joules / 3600.0

        # Учет влияния температуры на доступную емкость АКБ
        temp_factor = cls.get_temperature_capacity_factor(temp_c)
        effective_capacity_wh = battery_capacity_wh * temp_factor

        # Расход в процентах от исходной номинальной батареи
        consumed_percent = (energy_consumed_wh / effective_capacity_wh) * 100.0
        final_charge_percent = initial_charge_percent - consumed_percent

        wh_per_km = energy_consumed_wh / distance_km if distance_km > 0 else 0.0

        # Оценка безопасности поездки
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
