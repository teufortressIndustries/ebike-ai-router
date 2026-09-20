"""
Streamlit Web UI для E-Bike AI Route & Energy Optimizer.
Интерактивная карта, выбор точек кликом, физический расчет расхода и сравнение маршрутов.
"""

import streamlit as st
import folium
from streamlit_folium import st_folium
import requests

from physics import BIKE_PRESETS, EbikePhysicsModel

st.set_page_config(
    page_title="E-Bike AI Route & Energy Optimizer",
    page_icon="🚲",
    layout="wide"
)

# ----------------- Стилизация -----------------
st.markdown("""
<style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 5px solid #28a745;
        margin-bottom: 10px;
    }
    .badge-eco {
        background-color: #28a745;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
    .badge-fast {
        background-color: #007bff;
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- Инициализация Session State -----------------
if "start_point" not in st.session_state:
    st.session_state.start_point = [49.8019, 73.1021]  # [lat, lon] Караганда центр
if "end_point" not in st.session_state:
    st.session_state.end_point = [49.7900, 73.1100]
if "route_data" not in st.session_state:
    st.session_state.route_data = None
if "click_mode" not in st.session_state:
    st.session_state.click_mode = "start"  # 'start' or 'end'

# ----------------- Боковая панель (Параметры курьера и байка) -----------------
with st.sidebar:
    st.header("⚙️ Параметры транспорта и условий")
    
    preset_keys = list(BIKE_PRESETS.keys())
    preset_labels = [BIKE_PRESETS[k].name for k in preset_keys]
    
    selected_idx = st.selectbox(
        "Тип электровелосипеда",
        range(len(preset_keys)),
        format_func=lambda i: preset_labels[i]
    )
    chosen_preset_key = preset_keys[selected_idx]
    chosen_preset = BIKE_PRESETS[chosen_preset_key]
    
    st.caption(f"ℹ️ {chosen_preset.description}")
    st.caption(f"⚡ Номинальная емкость АКБ: **{chosen_preset.battery_capacity_wh:.0f} Вт·ч** | Вес байка: **{chosen_preset.bike_weight_kg:.0f} кг**")
    
    st.divider()
    st.subheader("🔋 Состояние батареи курьера")
    initial_charge = st.slider("Текущий заряд батареи (%)", min_value=5, max_value=100, value=75, step=5)
    
    st.subheader("📦 Груз и райдер")
    col_w1, col_w2 = st.columns(2)
    with col_w1:
        cargo_weight = st.number_input("Термосумка (кг)", min_value=0.0, max_value=30.0, value=6.0, step=0.5)
    with col_w2:
        rider_weight = st.number_input("Вес курьера (кг)", min_value=40.0, max_value=150.0, value=75.0, step=1.0)
        
    st.subheader("❄️ Погодные условия")
    temp_c = st.slider("Температура воздуха (°C)", min_value=-30, max_value=40, value=15, step=1)
    
    # Визуализация температурного эффекта
    temp_factor = EbikePhysicsModel.get_temperature_capacity_factor(temp_c)
    effective_cap = chosen_preset.battery_capacity_wh * temp_factor
    if temp_c < 10:
        st.warning(f"❄️ На холоде ({temp_c}°C) эффективная емкость АКБ: **{effective_cap:.0f} Вт·ч** ({temp_factor*100:.0f}% от номинала).")
    
    headwind = st.slider("Встречный ветер (км/ч)", min_value=0, max_value=50, value=5, step=5)
    
    st.divider()
    api_backend_url = st.text_input("Адрес FastAPI бэкенда", value="http://127.0.0.1:8000")


# ----------------- Основная зона -----------------
st.title("🚲 E-Bike AI Route & Energy Optimizer")
st.markdown("Интеллектуальная прокладка маршрутов для микромобильной логистики с честным расчетом тягового усилия и энергопотребления.")

# Управление точками маршрута
st.subheader("📍 Выбор маршрута")
st.info("💡 **Как задать маршрут:** кликните по карте для установки точки **Старта** (🟢) или **Финиша** (🔴), либо настройте переключатель ниже.")

col_mode1, col_mode2, col_mode3 = st.columns([1.5, 1.5, 2])
with col_mode1:
    click_target = st.radio("Клик по карте устанавливает:", ["Точку старта 🟢", "Точку финиша 🔴"], horizontal=True)
    st.session_state.click_mode = "start" if "старта" in click_target else "end"

with col_mode2:
    if st.button("🔄 Сбросить к центру города"):
        st.session_state.start_point = [49.8019, 73.1021]
        st.session_state.end_point = [49.7900, 73.1100]
        st.session_state.route_data = None
        st.rerun()

with st.expander("🛠️ Ручной ввод точных GPS-координат"):
    c_lat1, c_lon1 = st.columns(2)
    with c_lat1:
        s_lat = st.number_input("Широта старта", value=float(st.session_state.start_point[0]), format="%.6f")
        e_lat = st.number_input("Широта финиша", value=float(st.session_state.end_point[0]), format="%.6f")
    with c_lon1:
        s_lon = st.number_input("Долгота старта", value=float(st.session_state.start_point[1]), format="%.6f")
        e_lon = st.number_input("Долгота финиша", value=float(st.session_state.end_point[1]), format="%.6f")
    st.session_state.start_point = [s_lat, s_lon]
    st.session_state.end_point = [e_lat, e_lon]


# Создаем Folium карту
map_center = [
    (st.session_state.start_point[0] + st.session_state.end_point[0]) / 2,
    (st.session_state.start_point[1] + st.session_state.end_point[1]) / 2,
]
m = folium.Map(location=map_center, zoom_start=13, tiles="cartodbpositron")

# Маркеры старта и финиша
folium.Marker(
    location=st.session_state.start_point,
    popup="Старт (Отправление)",
    tooltip="Старт 🟢",
    icon=folium.Icon(color="green", icon="play", prefix="fa")
).add_to(m)

folium.Marker(
    location=st.session_state.end_point,
    popup="Финиш (Доставка)",
    tooltip="Финиш 🔴",
    icon=folium.Icon(color="red", icon="flag-checkered", prefix="fa")
).add_to(m)

# Отрисовка рассчитанных маршрутов
colors = ["#0066FF", "#28A745", "#FD7E14"]
if st.session_state.route_data and "routes" in st.session_state.route_data:
    for idx, r in enumerate(st.session_state.route_data["routes"]):
        route_color = colors[idx % len(colors)]
        weight = 6 if r.get("is_recommended") else 4
        opacity = 0.9 if r.get("is_recommended") else 0.6
        coords = [[c[1], c[0]] for c in r["geometry"]]
        tooltip_text = f"{r['name']}: {r['distance_km']} км | {r['energy_consumed_wh']} Вт·ч"
        folium.PolyLine(
            coords,
            color=route_color,
            weight=weight,
            opacity=opacity,
            tooltip=tooltip_text
        ).add_to(m)

# Отображаем интерактивную карту и ловим клики
map_out = st_folium(m, width="100%", height=480, returned_objects=["last_clicked"])

# Обработка клика по карте
if map_out and map_out.get("last_clicked"):
    clicked = map_out["last_clicked"]
    new_point = [round(clicked["lat"], 6), round(clicked["lng"], 6)]
    
    if st.session_state.click_mode == "start":
        if new_point != st.session_state.start_point:
            st.session_state.start_point = new_point
            st.rerun()
    else:
        if new_point != st.session_state.end_point:
            st.session_state.end_point = new_point
            st.rerun()


# ----------------- Кнопка расчета -----------------
col_calc, _ = st.columns([2, 3])
with col_calc:
    calculate_clicked = st.button("🚀 Рассчитать энергооптимальный маршрут", type="primary", use_container_width=True)

if calculate_clicked:
    with st.spinner("Запрашиваем данные у AI-маршрутизатора и рассчитываем физику..."):
        payload = {
            "start_lon": float(st.session_state.start_point[1]),
            "start_lat": float(st.session_state.start_point[0]),
            "end_lon": float(st.session_state.end_point[1]),
            "end_lat": float(st.session_state.end_point[0]),
            "bike_preset": chosen_preset_key,
            "cargo_weight_kg": float(cargo_weight),
            "rider_weight_kg": float(rider_weight),
            "temp_c": float(temp_c),
            "initial_charge_percent": float(initial_charge),
            "headwind_kmh": float(headwind),
            "find_alternatives": True
        }
        
        try:
            res = requests.post(f"{api_backend_url}/optimize", json=payload, timeout=12)
            if res.status_code == 200:
                st.session_state.route_data = res.json()
                st.success("Маршруты успешно рассчитаны!")
                st.rerun()
            else:
                error_detail = res.json().get("detail", res.text)
                st.error(f"Ошибка бэкенда ({res.status_code}): {error_detail}")
        except requests.exceptions.ConnectionError:
            st.error(f"❌ Не удалось подключиться к FastAPI бэкенду по адресу `{api_backend_url}`. Убедитесь, что запущен `uvicorn main:app --reload`.")
        except Exception as e:
            st.error(f"Произошла ошибка: {str(e)}")


# ----------------- Результаты анализа и рекомендации -----------------
if st.session_state.route_data and "routes" in st.session_state.route_data:
    st.divider()
    routes = st.session_state.route_data["routes"]
    
    st.header("📊 Результаты расчета и сравнение маршрутов")
    
    tabs = st.tabs([f"{r['name']}{' ⭐' if r.get('is_recommended') else ''}" for r in routes])
    
    for idx, (tab, r) in enumerate(zip(tabs, routes)):
        with tab:
            if r.get("is_recommended"):
                st.info(f"⭐ **Рекомендация алгоритма:** {r.get('recommendation_reason', 'Оптимальный маршрут.')}")
            
            # Статус безопасности батареи
            if not r["can_complete_route"] or r["safety_status"] == "critical":
                st.error(f"⛔ **КРИТИЧЕСКИЙ УРОВЕНЬ:** Заряда батареи не хватит на поездку! Расход составит {r['energy_consumed_percent']}%, доступно {initial_charge}%. Необходима замена АКБ.")
            elif r["safety_status"] == "warning":
                st.warning(f"⚠️ **ВНИМАНИЕ:** Опасный остаток заряда: останется всего {r['final_charge_percent']}% батареи. Рекомендуется экономичный режим.")
            else:
                st.success(f"✅ **МАРШРУТ БЕЗОПАСЕН:** Заряда батареи хватит с комфортным запасом. Остаток после рейса: {r['final_charge_percent']}%.")

            # Карточки ключевых метрик
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                st.metric("📏 Дистанция", f"{r['distance_km']} км")
            with c2:
                st.metric("⏱️ Время в пути", f"{r['duration_minutes']} мин")
            with c3:
                st.metric("⛰️ Набор высоты", f"{r['ascent_m']} м", delta=f"-{r['descent_m']} м спуск", delta_color="inverse")
            with c4:
                st.metric("🔋 Расход энергии", f"{r['energy_consumed_wh']} Вт·ч", delta=f"{r['energy_consumed_percent']}% АКБ", delta_color="inverse")
            with c5:
                st.metric("🎯 Итоговый заряд", f"{r['final_charge_percent']}%", delta=f"-{r['energy_consumed_percent']}%")

            # Детализация физики потребления
            with st.expander("🔬 Физическая структура энергозатрат (куда ушла энергия)"):
                b = r.get("energy_breakdown", {})
                e1, e2, e3, e4 = st.columns(4)
                with e1:
                    st.metric("Трение качения колес", f"{b.get('rolling_wh', 0)} Вт·ч")
                with e2:
                    st.metric("Сопротивление воздуха", f"{b.get('aero_wh', 0)} Вт·ч")
                with e3:
                    st.metric("Работа против гравитации", f"{b.get('climb_wh', 0)} Вт·ч")
                with e4:
                    st.metric("Удельный расход", f"{r['wh_per_km']} Вт·ч/км")