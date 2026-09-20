import streamlit as st
import requests
import folium
from streamlit_folium import st_folium

st.title("🔋 AI-оптимизатор для курьеров")
st.write("Этот интерфейс отправляет данные на ваш локальный сервер (main.py), который строит маршрут по улицам Караганды и рассчитывает расход батареи электровелосипеда.")

col1, col2 = st.columns(2)
with col1:
    weight = st.number_input("Вес термосумки (кг)", min_value=1.0, max_value=20.0, value=5.0)
with col2:
    temp = st.number_input("Температура на улице (°C)", min_value=-30.0, max_value=40.0, value=15.0)

st.write("Координаты (по умолчанию - центр Караганды):")
col3, col4 = st.columns(2)
with col3:
    start_lat = st.text_input("Широта старта", value="49.8019")
    end_lat = st.text_input("Широта финиша", value="49.7900")
with col4:
    start_lon = st.text_input("Долгота старта", value="73.1021")
    end_lon = st.text_input("Долгота финиша", value="73.1100")

if st.button("Построить маршрут и рассчитать батарею"):
    with st.spinner("Запрашиваем данные у AI..."):
        url = f"http://127.0.0.1:8000/optimize?start_lon={start_lon}&start_lat={start_lat}&end_lon={end_lon}&end_lat={end_lat}&weight={weight}&temp={temp}"
        try:
            res = requests.get(url)
            if res.status_code == 200 and "error" not in res.json():
                data = res.json()
                st.success(f"Дистанция: {data['distance_km']} км | Ожидаемый расход батареи: {data['predicted_battery_drop_percent']}%")
                
                if data['predicted_battery_drop_percent'] > 20:
                    st.error("Внимание! Тяжелый маршрут, потребуется много энергии.")
                    
                m = folium.Map(location=[float(start_lat), float(start_lon)], zoom_start=13)
                route_coords = [[coord[1], coord[0]] for coord in data['geometry']]
                folium.PolyLine(route_coords, color="blue", weight=5, opacity=0.8).add_to(m)
                import streamlit.components.v1 as components
                components.html(m._repr_html_(), width=700, height=500)
            else:
                st.error("Ошибка при построении маршрута.")
        except Exception as e:
            st.error("Сервер FastAPI (main.py) не запущен! Сначала запустите его в другом терминале командой uvicorn main:app --reload")