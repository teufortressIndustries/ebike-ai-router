# 📊 ТЕКУЩЕЕ СОСТОЯНИЕ ПРОЕКТА (PROJECT STATE)

> **Дата среза:** 21 сентября 2026  
> **Активная ветка:** `feature/physics-and-ui`  
> **Форк пользователя:** `git@github.com:teufortressIndustries/ebike-ai-router.git`  
> **Upstream репозиторий:** `https://github.com/qlmiran/ebike-ai-router.git`  
> **Публичный Live Demo:** `https://teufortressindustries.github.io/ebike-ai-router/`

---

## 🧭 1. Общий статус выполнения Milestone Roadmap

| Фаза | Описание | Статус |
| :--- | :--- | :--- |
| **ФАЗА 1: Ультимативный навигатор курьера (v1.0)** | Базовая физика, мульти-точки, гараж, высоты, GPX, PWA | **✅ Завершена на 100%** |
| **ФАЗА 2: Умная логистика и физика (v2.0)** | Порядок объезда (TSP), типы покрытий ($C_{\text{rr}}$), погода, Backend-First | **✅ Завершена на 100%** |
| **ФАЗА 2.5: Настоящий Mobile-First UI/UX (v2.5)** | Настоящая жестовая шторка (Peek/Half/Full), разгрузка экрана карты (85%), Map-First | **✅ Завершена на 100%** |
| **ФАЗА 2.6: Модернизация фронтенда и Dark Theme (v2.6)** | Модульный Frontend (`docs/app.js`, `docs/styles.css`), Dark/Light Mode, интерактивный график высоты, неблокирующие уведомления и защита от XSS | **✅ Завершена на 100%** |
| **ФАЗА 3: Слой Swap-станций и зарядок (v3.0)** | Зарядки и обменники АКБ по Overpass OSM API при заряде < 15% | ⚪ Запланировано |
| **ФАЗА 4: Телеметрия и машинное обучение (v4.0)** | Трекер смены, калибровка $C_d A$ курьера по GPS | ⚪ Запланировано |
| **ФАЗА 5: Fleet Management для дарксторов (v5.0)** | B2B дашборд для парков Самоката/Яндекса | ⚪ Запланировано |

---

## 🧩 2. Инвентарь реализованных фич

### А. Мобильный клиент (`docs/index.html`, `docs/app.js`, `docs/styles.css`)
* **Модульная архитектура (Zero-Build):**
  * Разделение монолитного HTML на чистый каркас `index.html`, стили и переменные тем `styles.css` и функциональный модуль `app.js`.
* **Dark Mode & Light Mode:**
  * Полноценная поддержка тёмного оформления для ночных курьерских смен (автоматически по системной теме или по кнопке в шапке, сохраняется в `localStorage`).
* **Безопасность и защищенность:**
  * Полное экранирование динамического контента (устранены уязвимости XSS при поиске через Nominatim и выводе названий).
  * Прерывание устаревших сетевых запросов геопоиска через `AbortController`.
* **Улучшенный UX (без системных `alert` / `prompt`):**
  * Всплывающие неблокирующие Toast-уведомления с анимацией.
  * Модальные окна для добавления закладок и смены города.
* **Интерактивный график высот с синхронизацией по карте:**
  * При перемещении курсора/пальца по графику на карте отображается маркер точного положения на отрезке трека.
* **Полноэкранная карта и жестовая шторка:**
  * Leaflet + тайлы CARTO Voyager, 3 состояния шторки (`Peek`, `Half`, `Full`) без потери рассчитанного маршрута.
* **Мульти-точки, Energy-Aware TSP и экспорт:**
  * Цветные отрезки пути, стрелки азимута, динамический сброс веса посылок, перестановка доставок для экономии батареи и скачивание GPX.

### Б. Бэкенд и физика (`physics.py`, `main.py`)
* **Физическая модель тягового усилия:**
  * Расчет сопротивления качению ($F_{\text{roll}}$) с матрицей `SURFACE_CRR_MAP` (18 типов покрытий OSM).
  * Аэродинамика с коррекцией плотности воздуха по температуре ($F_{\text{aero}}$).
  * Гравитация и рекуперация ($F_{\text{climb}}, F_{\text{regen}}$).
  * Кривая емкости Li-ion аккумулятора на морозе до $-25^\circ\text{C}$.
* **FastAPI Backend:**
  * Асинхронные запросы к OpenRouteService через `httpx.AsyncClient`.
  * Эндпоинты `POST /optimize` (нарезка `legs`, анализ покрытий) и `POST /optimize-order` (Energy-Aware TSP).
  * Автоматическая раздача статики `docs/` и главной страницы на `/`.

---

## 📂 3. Структура файлов репозитория

| Файл | Назначение | Текущий статус |
| :--- | :--- | :--- |
| [`docs/index.html`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/docs/index.html) | Главная разметка веб-клиента | Очищен от монолитного кода, адаптирован под Dark Mode и модули |
| [`docs/app.js`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/docs/app.js) | Основная клиентская логика и управление картой | Создан: безопасность, тосты, синхронизация рельефа с картой, TSP |
| [`docs/styles.css`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/docs/styles.css) | Стили, темы (Dark/Light) и анимации | Создан: CSS variables, адаптивные стили, кастомные скроллбары |
| [`DESIGN.md`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/DESIGN.md) | Спецификация мобильного редизайна (Mobile-First UX) | Актуален: спецификация Map-First и жестовой шторки |
| [`physics.py`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/physics.py) | Модуль физики и классических тяговых уравнений | Стабилен |
| [`main.py`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/main.py) | Асинхронный FastAPI бэкенд (SSOT) | Стабилен, раздает статику `docs/` |
| [`ROADMAP.md`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/ROADMAP.md) | Инженерный манифест проекта и спринты | Актуализирован под фазу v2.6 |
| [`README.md`](file:///mnt/PatriotDrive/GateXenia/DevCrate/GithubWorks/ebike-ai-router/README.md) | Главная документация проекта | Обновлен |
