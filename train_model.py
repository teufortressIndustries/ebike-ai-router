import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestRegressor
import joblib

# 1. Генерируем 1000 синтетических поездок курьера
np.random.seed(42)
n = 1000
distance = np.random.uniform(1, 15, n) # дистанция маршрута от 1 до 15 км
elevation = np.random.uniform(0, 100, n) # перепад высот от 0 до 100 метров
weight = np.random.uniform(2, 10, n) # вес рюкзака/термосумки от 2 до 10 кг
temp = np.random.uniform(-15, 35, n) # температура на улице (влияет на АКБ)

# Формула искусственного расхода батареи для обучения
battery_drop = (distance * 2) + (elevation * 0.05) + (weight * 0.1) + np.where(temp < 0, 5, 0)
battery_drop = np.clip(battery_drop, 1, 100) # Ограничиваем от 1 до 100%

df = pd.DataFrame({
    'distance': distance, 
    'elevation': elevation, 
    'weight': weight, 
    'temp': temp, 
    'battery_drop': battery_drop
})

# 2. Обучаем ИИ-модель (Random Forest)
X = df[['distance', 'elevation', 'weight', 'temp']]
y = df['battery_drop']

print("Обучение ИИ-модели началось...")
model = RandomForestRegressor(n_estimators=100)
model.fit(X, y)

# 3. Сохраняем результат
joblib.dump(model, 'battery_model.pkl')
print("Готово! Модель сохранена в файл battery_model.pkl")