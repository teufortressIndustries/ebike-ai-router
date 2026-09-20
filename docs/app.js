/**
 * E-Bike AI Route & Energy Optimizer - Frontend Module
 * Modern, secure, responsive, dark/light theme supporting client
 */

(function () {
  'use strict';

  // --- Constants & Config ---
  const LEG_COLORS = [
    '#2563EB', // Leg 1: Blue
    '#9333EA', // Leg 2: Purple
    '#D97706', // Leg 3: Amber
    '#DB2777', // Leg 4: Rose
    '#0891B2', // Leg 5: Cyan
    '#EA580C'  // Leg 6: Orange
  ];

  const DEFAULT_PRESETS = {
    courier_standard: { name: "Курьерский стандарт", capacityWh: 720, weightKg: 32, desc: "Minako / Колхозник" },
    courier_heavy: { name: "Курьерский дальнобойный", capacityWh: 1200, weightKg: 38, desc: "60V 20Ah" },
    city_compact: { name: "Городской легкий", capacityWh: 374.4, weightKg: 20, desc: "36V 10.4Ah" }
  };

  const DEFAULT_API_URL = 'https://ebike-ai-router.onrender.com';

  function getEffectiveApiUrl() {
    let saved = localStorage.getItem('ebike_api_url');
    if (saved) {
      saved = saved.trim().replace(/\/+$/, '');
      const isLocalHost = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
      if (!isLocalHost && (saved.includes('localhost') || saved.includes('127.0.0.1'))) {
        localStorage.removeItem('ebike_api_url');
        saved = null;
      }
    }

    if (saved && saved !== '') {
      return saved;
    }

    // Direct FastAPI backend detection: only if running on port 8000 or on Render host
    const isDirectBackend = (window.location.port === '8000') || (window.location.hostname && window.location.hostname.includes('onrender.com'));
    if (isDirectBackend && (window.location.protocol === 'http:' || window.location.protocol === 'https:')) {
      return window.location.origin.replace(/\/+$/, '');
    }

    return DEFAULT_API_URL;
  }

  const ACTIVE_API_URL = getEffectiveApiUrl();

  let savedCustomBike = null;
  try { savedCustomBike = JSON.parse(localStorage.getItem('ebike_custom_bike')); } catch (e) { }

  const DEFAULT_BOOKMARKS = [
    { id: 'b1', name: 'Склад / База', icon: 'fa-warehouse', lat: 49.8019, lon: 73.1021 },
    { id: 'b2', name: 'Дом', icon: 'fa-house', lat: 49.7900, lon: 73.1100 },
    { id: 'b3', name: 'Центр / Хаб', icon: 'fa-store', lat: 49.7960, lon: 73.1080 }
  ];

  let savedBookmarks = null;
  try { savedBookmarks = JSON.parse(localStorage.getItem('ebike_bookmarks')); } catch (e) { }
  let bookmarks = (savedBookmarks && savedBookmarks.length > 0) ? savedBookmarks : DEFAULT_BOOKMARKS;

  // --- App State ---
  const state = {
    theme: localStorage.getItem('ebike_theme') || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'),
    clickMode: 'start', // 'start' | 'add_stop' | 'end'
    isRoundTrip: false,
    roadCondition: 'dry', // 'dry' | 'wet' | 'slush'
    currentCity: localStorage.getItem('ebike_city') || 'Караганда',
    startPoint: [49.8019, 73.1021], // [lat, lon]
    waypoints: [
      [49.7960, 73.1080]
    ],
    endPoint: [49.7900, 73.1100],
    bikeType: savedCustomBike ? 'custom' : 'courier_standard',
    customBike: savedCustomBike || { volts: 48, ah: 21, weightKg: 35, powerW: 500 },
    initialCharge: 85,
    tempC: 15,
    cargoKg: 8,
    riderKg: 75,
    headwindKmh: 5,
    apiBaseUrl: ACTIVE_API_URL,
    calculatedResponse: null,
    calculatedRoutes: null,
    selectedRouteIdx: 0,
    isRouteCalculated: false,
    isRouteStale: true,
    lastCalculatedHash: null
  };

  // --- Sanitization & Safety ---
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // --- Toast Notifications System ---
  function showToast(message, type = 'info', duration = 3200) {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.className = 'fixed top-4 left-1/2 -translate-x-1/2 z-50 flex flex-col gap-2 pointer-events-none max-w-sm w-full px-4';
      document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const bgColors = {
      info: 'bg-slate-900/90 dark:bg-slate-800/95 text-white border-slate-700',
      success: 'bg-emerald-600/95 text-white border-emerald-500',
      warning: 'bg-amber-600/95 text-white border-amber-500',
      error: 'bg-rose-600/95 text-white border-rose-500'
    };

    const icons = {
      info: 'fa-circle-info',
      success: 'fa-circle-check',
      warning: 'fa-triangle-exclamation',
      error: 'fa-circle-xmark'
    };

    toast.className = `toast-in pointer-events-auto p-3 rounded-2xl shadow-xl border backdrop-blur-md text-xs font-semibold flex items-center gap-2.5 transition-all ${bgColors[type] || bgColors.info}`;
    toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info} text-sm flex-shrink-0"></i><span class="flex-1">${escapeHtml(message)}</span>`;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.remove('toast-in');
      toast.classList.add('toast-out');
      setTimeout(() => toast.remove(), 250);
    }, duration);
  }

  // --- Theme Controller ---
  function applyTheme(theme) {
    state.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ebike_theme', theme);

    const themeBtn = document.getElementById('btnToggleTheme');
    if (themeBtn) {
      themeBtn.innerHTML = theme === 'dark'
        ? '<i class="fa-solid fa-sun text-amber-400"></i>'
        : '<i class="fa-solid fa-moon text-slate-600"></i>';
    }

    // Update map tile layer if necessary
    updateMapTiles();
  }

  // --- Parameter Hash & Staleness ---
  function generateParamsHash() {
    const allPoints = [state.startPoint, ...state.waypoints];
    if (state.isRoundTrip) allPoints.push(state.startPoint);
    else allPoints.push(state.endPoint);

    return JSON.stringify({
      points: allPoints,
      isRoundTrip: state.isRoundTrip,
      roadCondition: state.roadCondition,
      bikeType: state.bikeType,
      customBike: state.bikeType === 'custom' ? state.customBike : null,
      cargoKg: state.cargoKg,
      riderKg: state.riderKg,
      tempC: state.tempC,
      initialCharge: state.initialCharge,
      headwindKmh: state.headwindKmh
    });
  }

  function checkRouteStaleness() {
    if (!state.isRouteCalculated) {
      state.isRouteStale = true;
      updateCalculateButton();
      return;
    }
    const currentHash = generateParamsHash();
    state.isRouteStale = (currentHash !== state.lastCalculatedHash);
    updateCalculateButton();

    const recalcMini = document.getElementById('btnSheetRecalcMini');
    const recalcHeader = document.getElementById('btnRecalcFromSheet');
    if (recalcMini) {
      if (state.isRouteStale) recalcMini.classList.remove('hidden');
      else recalcMini.classList.add('hidden');
    }
    if (recalcHeader) {
      if (state.isRouteStale) recalcHeader.classList.remove('hidden');
      else recalcHeader.classList.add('hidden');
    }
  }

  function updateCalculateButton() {
    const btn = document.getElementById('btnCalculate');
    const reopenContainer = document.getElementById('routeReopenContainer');
    const reopenDist = document.getElementById('reopenDistText');
    const reopenBat = document.getElementById('reopenBatText');
    const btnRecalcStale = document.getElementById('btnRecalcStaleFloating');

    if (!btn) return;

    if (state.isRouteCalculated && state.calculatedRoutes && state.calculatedRoutes.length > 0) {
      const primary = state.calculatedRoutes[state.selectedRouteIdx] || state.calculatedRoutes[0];
      const dist = `${primary.distance_km} км (${Math.round(primary.duration_minutes)} мин)`;
      const bat = `Остаток АКБ: ${primary.final_charge_percent}%`;

      if (reopenContainer) {
        btn.classList.add('hidden');
        reopenContainer.classList.remove('hidden');
        if (reopenDist) reopenDist.innerText = state.isRouteStale ? `${dist} • Есть изменения` : dist;
        if (reopenBat) reopenBat.innerText = bat;

        if (btnRecalcStale) {
          if (state.isRouteStale) btnRecalcStale.classList.remove('hidden');
          else btnRecalcStale.classList.add('hidden');
        }
      }
    } else {
      if (reopenContainer) reopenContainer.classList.add('hidden');
      btn.classList.remove('hidden');
      btn.className = "w-full pointer-events-auto bg-slate-900 hover:bg-slate-800 dark:bg-blue-600 dark:hover:bg-blue-500 text-white font-semibold py-3.5 px-5 rounded-2xl shadow-xl shadow-slate-900/30 flex items-center justify-center gap-2 transition active:scale-[0.98]";
      btn.innerHTML = `<i class="fa-solid fa-bolt text-amber-400"></i><span id="btnCalculateText">Рассчитать маршрут и физику</span>`;
    }

    updateFloatingReopenBtn();
  }

  function updateFloatingReopenBtn() {
    const floatBtn = document.getElementById('btnFloatReopenRoute');
    if (!floatBtn) return;
    if (state.isRouteCalculated && bottomSheet && bottomSheet.state === 'hidden') {
      floatBtn.classList.remove('hidden');
    } else {
      floatBtn.classList.add('hidden');
    }
  }

  let isCheckingHealth = false;
  let wakingPollingTimer = null;

  function updateServerStatus(status) {
    const badge = document.getElementById('serverStatusBadge');
    if (!badge) return;

    if (status === 'online' || status === true) {
      badge.className = "h-8 px-2.5 rounded-xl text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800 flex items-center gap-1.5 cursor-pointer flex-shrink-0 transition active:scale-95";
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> <span class="hidden sm:inline">В сети</span>';
      badge.title = "FastAPI сервер активен (нажмите для проверки)";
    } else if (status === 'waking') {
      badge.className = "h-8 px-2.5 rounded-xl text-[10px] font-bold bg-amber-100 text-amber-900 dark:bg-amber-950/80 dark:text-amber-200 border border-amber-300 dark:border-amber-700 flex items-center gap-1.5 cursor-pointer flex-shrink-0 transition active:scale-95";
      badge.innerHTML = '<i class="fa-solid fa-spinner fa-spin text-[10px] text-amber-600 dark:text-amber-400"></i> <span class="hidden sm:inline">Запуск...</span>';
      badge.title = "Сервер Render просыпается (~30–50 сек). Нажмите для обновления";
    } else {
      badge.className = "h-8 px-2.5 rounded-xl text-[10px] font-bold bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border border-rose-300 dark:border-rose-800 flex items-center gap-1.5 cursor-pointer flex-shrink-0 transition active:scale-95";
      badge.innerHTML = '<span class="w-2 h-2 rounded-full bg-rose-500"></span> <span class="hidden sm:inline">Офлайн</span>';
      badge.title = "Сервер недоступен. Нажмите, чтобы разбудить";
    }
  }

  async function checkServerHealth(userTriggered = false) {
    if (isCheckingHealth) return;
    isCheckingHealth = true;

    const targetUrl = (state.apiBaseUrl || DEFAULT_API_URL).replace(/\/+$/, '');

    if (userTriggered) {
      updateServerStatus('waking');
      showToast("Отправлен запрос на сервер (пробуждение Render)...", "info", 2500);
    }

    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 6000);
      const res = await fetch(`${targetUrl}/health`, { signal: controller.signal });
      clearTimeout(timer);

      if (res.ok) {
        updateServerStatus('online');
        if (wakingPollingTimer) {
          clearInterval(wakingPollingTimer);
          wakingPollingTimer = null;
        }
        if (userTriggered) {
          showToast("Бэкенд в сети и готов к работе!", "success", 3000);
        }
        isCheckingHealth = false;
        return true;
      }
    } catch (e) {
      // If Render backend is in cold sleep or timing out, start auto-polling until ready
      if (targetUrl.includes('onrender.com')) {
        updateServerStatus('waking');
        if (!wakingPollingTimer) {
          wakingPollingTimer = setInterval(async () => {
            try {
              const res = await fetch(`${targetUrl}/health`, { signal: AbortSignal.timeout(5000) });
              if (res.ok) {
                clearInterval(wakingPollingTimer);
                wakingPollingTimer = null;
                updateServerStatus('online');
                showToast("✨ Сервер Render успешно проснулся!", "success", 4000);
              }
            } catch (err) { }
          }, 7000);
        }
        isCheckingHealth = false;
        return false;
      }
    }

    updateServerStatus('offline');
    isCheckingHealth = false;
    return false;
  }

  // --- Map Initialization ---
  let map, tileLayer, mapMarkers = [], routeLayersGroup, elevationMarker = null;

  function initMap() {
    map = L.map('map', { zoomControl: false }).setView([49.7960, 73.1060], 13);
    L.control.zoom({ position: 'topright' }).addTo(map);

    routeLayersGroup = L.layerGroup().addTo(map);
    updateMapTiles();

    map.on('click', (e) => {
      const lat = parseFloat(e.latlng.lat.toFixed(6));
      const lng = parseFloat(e.latlng.lng.toFixed(6));

      if (state.clickMode === 'start') {
        state.startPoint = [lat, lng];
        setClickMode('add_stop');
      } else if (state.clickMode === 'add_stop') {
        state.waypoints.push([lat, lng]);
      } else if (state.clickMode === 'end') {
        state.endPoint = [lat, lng];
        setClickMode('add_stop');
      }
      refreshMarkers();
    });
  }

  function updateMapTiles() {
    if (!map) return;
    if (tileLayer) map.removeLayer(tileLayer);

    const isDark = state.theme === 'dark';
    const tileUrl = isDark
      ? 'https://{s}.basemaps.cartocdn.com/rastertiles/dark_all/{z}/{x}/{y}{r}.png'
      : 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';

    tileLayer = L.tileLayer(tileUrl, {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
    }).addTo(map);

    const mapEl = document.getElementById('map');
    if (mapEl) {
      mapEl.style.filter = 'none';
    }
  }

  function createMarkerIcon(type, number = 1) {
    if (type === 'start') {
      return L.divIcon({
        className: '',
        html: '<div style="background:#10b981; width:34px; height:34px; border-radius:50%; border:3px solid white; box-shadow:0 4px 12px rgba(0,0,0,0.35); display:flex; align-items:center; justify-content:center; color:white; font-size:13px;"><i class="fa-solid fa-play" style="margin-left:2px;"></i></div>',
        iconSize: [34, 34],
        iconAnchor: [17, 17]
      });
    } else if (type === 'end') {
      return L.divIcon({
        className: '',
        html: '<div style="background:#ef4444; width:34px; height:34px; border-radius:50%; border:3px solid white; box-shadow:0 4px 12px rgba(0,0,0,0.35); display:flex; align-items:center; justify-content:center; color:white; font-size:13px;"><i class="fa-solid fa-flag-checkered"></i></div>',
        iconSize: [34, 34],
        iconAnchor: [17, 17]
      });
    } else {
      const markerColor = LEG_COLORS[(number - 1) % LEG_COLORS.length] || '#2563eb';
      return L.divIcon({
        className: '',
        html: `<div style="background:${markerColor}; width:30px; height:30px; border-radius:50%; border:3px solid white; box-shadow:0 4px 10px rgba(0,0,0,0.35); display:flex; align-items:center; justify-content:center; color:white; font-weight:bold; font-size:12px;">${number}</div>`,
        iconSize: [30, 30],
        iconAnchor: [15, 15]
      });
    }
  }

  function refreshMarkers() {
    mapMarkers.forEach(m => map.removeLayer(m));
    mapMarkers = [];

    // Start Marker
    const sm = L.marker(state.startPoint, { icon: createMarkerIcon('start'), draggable: true }).addTo(map);
    sm.bindTooltip("Точка Старта 🟢");
    sm.on('dragend', (e) => {
      state.startPoint = [e.target.getLatLng().lat, e.target.getLatLng().lng];
      checkRouteStaleness();
    });
    mapMarkers.push(sm);

    // Waypoints
    state.waypoints.forEach((wp, idx) => {
      const wm = L.marker(wp, { icon: createMarkerIcon('waypoint', idx + 1), draggable: true }).addTo(map);
      wm.bindTooltip(`Заказ #${idx + 1} 🔵`);

      const popupDiv = document.createElement('div');
      popupDiv.style.minWidth = '140px';
      popupDiv.style.textAlign = 'center';
      popupDiv.style.padding = '4px';
      popupDiv.innerHTML = `
        <b style="font-size: 13px; color: #1e293b;">Заказ #${idx + 1} 🔵</b>
        <div style="font-size: 10px; color: #64748b; margin-top: 2px;">${wp[0].toFixed(4)}, ${wp[1].toFixed(4)}</div>
      `;
      const delBtn = document.createElement('button');
      delBtn.style.cssText = 'margin-top: 8px; width: 100%; background: #fee2e2; color: #dc2626; border: 1px solid #fecaca; border-radius: 8px; padding: 6px 10px; font-weight: bold; font-size: 11px; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 4px;';
      delBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Удалить точку';
      delBtn.onclick = () => removeWaypoint(idx);
      popupDiv.appendChild(delBtn);

      wm.bindPopup(popupDiv);

      wm.on('dragend', (e) => {
        state.waypoints[idx] = [e.target.getLatLng().lat, e.target.getLatLng().lng];
        checkRouteStaleness();
      });
      mapMarkers.push(wm);
    });

    // Finish Marker
    if (!state.isRoundTrip) {
      const em = L.marker(state.endPoint, { icon: createMarkerIcon('end'), draggable: true }).addTo(map);
      em.bindTooltip("Финиш 🔴");
      em.on('dragend', (e) => {
        state.endPoint = [e.target.getLatLng().lat, e.target.getLatLng().lng];
        checkRouteStaleness();
      });
      mapMarkers.push(em);
    }

    renderWaypointsChips();
    checkRouteStaleness();
  }

  function renderWaypointsChips() {
    const strip = document.getElementById('activeWaypointsStrip');
    const container = document.getElementById('waypointsChips');
    const countEl = document.getElementById('waypointsCount');
    if (!strip || !container) return;

    if (state.waypoints.length === 0) {
      strip.classList.add('hidden');
      return;
    }

    strip.classList.remove('hidden');
    countEl.innerText = `${state.waypoints.length} ${state.waypoints.length === 1 ? 'заказ' : (state.waypoints.length < 5 ? 'заказа' : 'заказов')}`;
    container.innerHTML = '';

    state.waypoints.forEach((wp, idx) => {
      const markerColor = LEG_COLORS[idx % LEG_COLORS.length] || '#2563eb';
      const chip = document.createElement('div');
      chip.className = "flex items-center gap-1.5 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 border border-slate-200 dark:border-slate-700 rounded-xl px-2.5 py-1 text-[11px] font-semibold flex-shrink-0 shadow-xs";
      chip.innerHTML = `
        <span class="w-2 h-2 rounded-full flex-shrink-0" style="background-color: ${markerColor};"></span>
        <span>Заказ #${idx + 1}</span>
      `;
      const closeBtn = document.createElement('button');
      closeBtn.className = "text-slate-400 hover:text-rose-500 p-0.5 rounded transition";
      closeBtn.title = "Удалить заказ";
      closeBtn.innerHTML = '<i class="fa-solid fa-xmark text-[10px]"></i>';
      closeBtn.onclick = (e) => {
        e.stopPropagation();
        removeWaypoint(idx);
      };
      chip.appendChild(closeBtn);
      container.appendChild(chip);
    });
  }

  function removeWaypoint(idx) {
    if (idx >= 0 && idx < state.waypoints.length) {
      state.waypoints.splice(idx, 1);
      refreshMarkers();
      showToast(`Заказ #${idx + 1} удален`, 'info');
    }
  }

  // --- Click Mode Control ---
  function setClickMode(mode) {
    state.clickMode = mode;
    const modeStartBtn = document.getElementById('modeStart');
    const modeAddStopBtn = document.getElementById('modeAddStop');
    const modeEndBtn = document.getElementById('modeEnd');
    const topStatusText = document.getElementById('topStatusText');

    [modeStartBtn, modeAddStopBtn, modeEndBtn].forEach(b => {
      if (!b) return;
      b.className = "flex-1 py-1.5 px-2 rounded-xl flex items-center justify-center gap-1.5 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition font-medium text-xs";
    });

    if (mode === 'start' && modeStartBtn) {
      modeStartBtn.className = "flex-1 py-1.5 px-2 rounded-xl flex items-center justify-center gap-1.5 bg-emerald-500 text-white shadow-xs transition font-semibold text-xs";
      if (topStatusText) topStatusText.innerText = "Кликните по карте для выбора точки Старта 🟢";
    } else if (mode === 'add_stop' && modeAddStopBtn) {
      modeAddStopBtn.className = "flex-1 py-1.5 px-2 rounded-xl flex items-center justify-center gap-1.5 bg-blue-600 text-white shadow-xs transition font-semibold text-xs";
      if (topStatusText) topStatusText.innerText = `Добавление точек заказов 🔵 (всего ${state.waypoints.length})`;
    } else if (mode === 'end' && modeEndBtn) {
      modeEndBtn.className = "flex-1 py-1.5 px-2 rounded-xl flex items-center justify-center gap-1.5 bg-rose-500 text-white shadow-xs transition font-semibold text-xs";
      if (topStatusText) topStatusText.innerText = "Кликните по карте для выбора точки Финиша 🔴";
    }
  }

  // --- Road Condition Control ---
  function setRoadCondition(cond) {
    state.roadCondition = cond;
    const btnDry = document.getElementById('btnCondDry');
    const btnWet = document.getElementById('btnCondWet');
    const btnSlush = document.getElementById('btnCondSlush');

    const activeBase = "py-1.5 px-2 rounded-xl border text-center transition flex items-center justify-center gap-1 font-semibold text-xs shadow-xs ";
    const inactive = "py-1.5 px-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 text-center transition flex items-center justify-center gap-1 font-medium text-xs";

    if (btnDry) btnDry.className = inactive;
    if (btnWet) btnWet.className = inactive;
    if (btnSlush) btnSlush.className = inactive;

    if (cond === 'wet' && btnWet) {
      btnWet.className = activeBase + "bg-blue-50 dark:bg-blue-950/60 border-blue-500 text-blue-700 dark:text-blue-300";
    } else if (cond === 'slush' && btnSlush) {
      btnSlush.className = activeBase + "bg-amber-50 dark:bg-amber-950/60 border-amber-500 text-amber-700 dark:text-amber-300";
    } else if (btnDry) {
      btnDry.className = activeBase + "bg-blue-50 dark:bg-blue-950/60 border-blue-500 text-blue-700 dark:text-blue-300";
    }
    checkRouteStaleness();
  }

  // --- Live Weather (Open-Meteo) ---
  async function updateLiveWeather(lat, lon) {
    try {
      const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat.toFixed(4)}&longitude=${lon.toFixed(4)}&current=temperature_2m,wind_speed_10m,weather_code`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();
      if (!data.current) return;

      const temp = Math.round(data.current.temperature_2m);
      const wind = Math.round(data.current.wind_speed_10m);
      const code = data.current.weather_code;

      state.tempC = temp;
      state.headwindKmh = wind;

      let icon = '☀️';
      if (code >= 1 && code <= 3) icon = '⛅';
      else if (code >= 45 && code <= 48) icon = '🌫️';
      else if (code >= 51 && code <= 67) icon = '🌧️';
      else if (code >= 71 && code <= 77) icon = '❄️';
      else if (code >= 80 && code <= 99) icon = '⛈️';

      const badge = document.getElementById('liveWeatherBadge');
      if (badge) {
        document.getElementById('weatherIcon').innerText = icon;
        document.getElementById('weatherTemp').innerText = `${temp > 0 ? '+' : ''}${temp}°C • 💨 ${wind} км/ч`;
        badge.classList.remove('hidden');
      }

      const isSnow = (code >= 71 && code <= 77) || (code >= 85 && code <= 86) || (temp <= 0 && (code >= 51 || code >= 80));
      const isRain = (code >= 51 && code <= 67) || (code >= 80 && code <= 82);
      const hintEl = document.getElementById('autoWeatherHint');

      if (isSnow) {
        setRoadCondition('slush');
        if (hintEl) {
          hintEl.innerText = "❄️ Авто: Снег / мороз";
          hintEl.classList.remove('hidden');
        }
      } else if (isRain) {
        setRoadCondition('wet');
        if (hintEl) {
          hintEl.innerText = "🌧️ Авто: Дождь / мокро";
          hintEl.classList.remove('hidden');
        }
      } else {
        setRoadCondition('dry');
        if (hintEl) {
          hintEl.innerText = "☀️ Авто: Сухо";
          hintEl.classList.remove('hidden');
        }
      }

      const cfgTemp = document.getElementById('cfgTemp');
      if (cfgTemp) {
        cfgTemp.value = temp;
        document.getElementById('cfgTempVal').innerText = `${temp > 0 ? '+' : ''}${temp}°C`;
      }
      const cfgWind = document.getElementById('cfgWind');
      if (cfgWind) {
        cfgWind.value = wind;
        document.getElementById('cfgWindVal').innerText = `${wind} км/ч`;
      }
    } catch (err) {
      console.log("Weather fetch skipped:", err);
    }
  }

  // --- Smart Parser for 2GIS, Yandex, Google Maps URLs & Coords ---
  function extractCoordsFromText(text) {
    if (!text) return null;
    const t = text.trim();

    // 1. 2GIS: m=lon%2Clat or points/lon%2Clat
    const m2gis = t.match(/2gis\.[a-z.]+\/.*?(?:m=|points\/)(-?[0-9.]+)[,%2C]+(-?[0-9.]+)/i);
    if (m2gis) return [parseFloat(m2gis[2]), parseFloat(m2gis[1])];

    // 2. Yandex Maps: ll=lon%2Clat or pt=lon,lat
    const mYa = t.match(/[?&](?:ll|pt|whatshere%5Bpoint%5D)=(-?[0-9.]+)[,%2C]+(-?[0-9.]+)/i);
    if (mYa) return [parseFloat(mYa[2]), parseFloat(mYa[1])];

    // 3. Google Maps: /@lat,lon or ?q=lat,lon
    const mG = t.match(/(?:\/@|[?&]q=)(-?[0-9.]+)[,%2C]+(-?[0-9.]+)/i);
    if (mG) return [parseFloat(mG[1]), parseFloat(mG[2])];

    // 4. Coordinates: 49.8019, 73.1021
    const mC = t.match(/^(-?[0-9]{1,2}\.[0-9]+)[\s,]+(-?[0-9]{1,3}\.[0-9]+)$/);
    if (mC) return [parseFloat(mC[1]), parseFloat(mC[2])];

    return null;
  }

  function getSearchBoundingBox() {
    if (!map) return "72.7,49.6,73.5,50.0";
    const center = map.getCenter();
    const b = map.getBounds();
    const padLat = Math.max(0.25, Math.abs(b.getNorth() - b.getSouth()) / 2);
    const padLon = Math.max(0.35, Math.abs(b.getEast() - b.getWest()) / 2);
    const west = (center.lng - padLon).toFixed(4);
    const east = (center.lng + padLon).toFixed(4);
    const north = (center.lat + padLat).toFixed(4);
    const south = (center.lat - padLat).toFixed(4);
    return `${west},${north},${east},${south}`;
  }

  async function geocodeAddress(addressText) {
    try {
      const viewbox = getSearchBoundingBox();
      let query = addressText.trim();
      if (state.currentCity && !query.toLowerCase().includes(state.currentCity.toLowerCase())) {
        query = `${state.currentCity}, ${query}`;
      }

      let url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&viewbox=${viewbox}&bounded=1&limit=1`;
      let res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        let data = await res.json();
        if (data && data.length > 0) {
          return [parseFloat(data[0].lat), parseFloat(data[0].lon)];
        }
      }

      url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(query)}&viewbox=${viewbox}&bounded=0&limit=1`;
      res = await fetch(url, { headers: { 'Accept': 'application/json' } });
      if (res.ok) {
        let data = await res.json();
        if (data && data.length > 0) {
          return [parseFloat(data[0].lat), parseFloat(data[0].lon)];
        }
      }
    } catch (e) { }
    return null;
  }

  function applyFoundCoordinates(coords, label = "") {
    if (!coords) return;
    const [lat, lon] = coords;

    if (state.clickMode === 'start') {
      state.startPoint = [lat, lon];
      updateLiveWeather(lat, lon);
      setClickMode('add_stop');
    } else if (state.clickMode === 'add_stop') {
      state.waypoints.push([lat, lon]);
    } else if (state.clickMode === 'end') {
      state.endPoint = [lat, lon];
      setClickMode('add_stop');
    }

    refreshMarkers();
    map.flyTo([lat, lon], 16, { duration: 1.2 });
    showToast(label ? `Точка добавлена: ${label}` : "Точка установлена на карте", 'success');
  }

  // --- Bookmarks Controller ---
  function renderBookmarks() {
    const list = document.getElementById('bookmarksList');
    if (!list) return;
    list.innerHTML = '';

    bookmarks.forEach(b => {
      const item = document.createElement('div');
      item.className = "flex items-center gap-1.5 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700/80 border border-slate-200/90 dark:border-slate-700 rounded-xl px-2.5 py-1 text-xs font-semibold shadow-xs transition active:scale-95 cursor-pointer whitespace-nowrap text-slate-700 dark:text-slate-200";
      
      const content = document.createElement('div');
      content.className = "flex items-center gap-1.5";
      content.innerHTML = `<i class="fa-solid ${b.icon || 'fa-location-dot'} text-amber-500 text-[11px]"></i><span>${escapeHtml(b.name)}</span>`;
      content.onclick = () => {
        if (state.clickMode === 'start') {
          state.startPoint = [b.lat, b.lon];
          setClickMode('add_stop');
        } else if (state.clickMode === 'add_stop') {
          state.waypoints.push([b.lat, b.lon]);
        } else if (state.clickMode === 'end') {
          state.endPoint = [b.lat, b.lon];
          setClickMode('add_stop');
        }
        map.panTo([b.lat, b.lon]);
        refreshMarkers();
        showToast(`Выбрано: ${b.name}`, 'info');
      };

      const delBtn = document.createElement('button');
      delBtn.className = "text-slate-300 dark:text-slate-500 hover:text-rose-500 ml-1 text-[10px] p-0.5";
      delBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
      delBtn.onclick = (e) => {
        e.stopPropagation();
        bookmarks = bookmarks.filter(x => x.id !== b.id);
        localStorage.setItem('ebike_bookmarks', JSON.stringify(bookmarks));
        renderBookmarks();
        showToast(`Закладка удалена`, 'info');
      };

      item.appendChild(content);
      item.appendChild(delBtn);
      list.appendChild(item);
    });
  }

  // --- Modal Management (Non-blocking replacements for prompt/alert) ---
  function openBookmarkModal() {
    const modal = document.getElementById('bookmarkModal');
    const input = document.getElementById('bookmarkNameInput');
    if (modal && input) {
      input.value = `База ${state.currentCity}`;
      modal.classList.remove('hidden');
      setTimeout(() => input.focus(), 50);
    }
  }

  function closeBookmarkModal() {
    const modal = document.getElementById('bookmarkModal');
    if (modal) modal.classList.add('hidden');
  }

  // --- Route Calculation (FastAPI SSOT) ---
  async function executeRouteCalculation() {
    const allPoints = [state.startPoint, ...state.waypoints];
    if (state.isRoundTrip) {
      allPoints.push(state.startPoint);
    } else {
      allPoints.push(state.endPoint);
    }

    const btnCalculate = document.getElementById('btnCalculate');
    if (btnCalculate) {
      btnCalculate.disabled = true;
      btnCalculate.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i><span>Расчет на сервере FastAPI...</span>';
    }

    const recalcMini = document.getElementById('btnSheetRecalcMini');
    const recalcHeader = document.getElementById('btnRecalcFromSheet');
    if (recalcMini) recalcMini.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin text-xs"></i>';
    if (recalcHeader) recalcHeader.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin text-xs"></i><span>Расчет...</span>';

    const coordsLonLat = allPoints.map(p => [p[1], p[0]]);

    const payload = {
      coordinates: coordsLonLat,
      round_trip: state.isRoundTrip,
      bike_preset: state.bikeType,
      custom_voltage_v: state.bikeType === 'custom' ? state.customBike.volts : null,
      custom_capacity_ah: state.bikeType === 'custom' ? state.customBike.ah : null,
      custom_bike_weight_kg: state.bikeType === 'custom' ? state.customBike.weightKg : null,
      cargo_weight_kg: state.cargoKg,
      rider_weight_kg: state.riderKg,
      temp_c: state.tempC,
      initial_charge_percent: state.initialCharge,
      headwind_kmh: state.headwindKmh,
      road_condition: state.roadCondition,
      find_alternatives: (allPoints.length === 2)
    };

    try {
      const baseUrl = (state.apiBaseUrl || DEFAULT_API_URL).replace(/\/+$/, '');
      const res = await fetch(`${baseUrl}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Ошибка сервера (${res.status})`);
      }

      const data = await res.json();
      if (!data.routes || data.routes.length === 0) throw new Error("Маршрут не найден");

      state.calculatedResponse = data;
      state.calculatedRoutes = data.routes;
      state.isRouteCalculated = true;
      state.isRouteStale = false;
      state.lastCalculatedHash = generateParamsHash();

      displayResults(0);
      updateServerStatus(true);
      showToast("Маршрут и физика успешно рассчитаны!", "success");
    } catch (err) {
      console.error("Calculate route error:", err);
      let errMsg = `Ошибка расчета: ${err.message}`;
      if (err.message && (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))) {
        updateServerStatus('waking');
        errMsg = "Сервер Render просыпается после спящего режима (~30–50 сек). Запрос отправлен — подождите полминуты и нажмите «Рассчитать» снова.";
      } else {
        updateServerStatus(false);
      }
      showToast(errMsg, "error", 7000);
    } finally {
      if (btnCalculate) btnCalculate.disabled = false;
      updateCalculateButton();
      if (recalcMini) recalcMini.innerHTML = '<i class="fa-solid fa-rotate text-xs"></i><span>Обновить</span>';
      if (recalcHeader) recalcHeader.innerHTML = '<i class="fa-solid fa-rotate text-[9px]"></i><span>Пересчитать</span>';
      checkRouteStaleness();
    }
  }

  function calculateBearing(lat1, lon1, lat2, lon2) {
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const y = Math.sin(dLon) * Math.cos(lat2 * Math.PI / 180);
    const x = Math.cos(lat1 * Math.PI / 180) * Math.sin(lat2 * Math.PI / 180) -
      Math.sin(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) * Math.cos(dLon);
    return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
  }

  function renderRouteLines(route) {
    routeLayersGroup.clearLayers();
    if (!route) return;

    if (route.legs && route.legs.length > 0) {
      route.legs.forEach((leg) => {
        const poly = L.polyline(leg.coordinates, {
          color: leg.color,
          weight: 6,
          opacity: 0.88,
          dashArray: leg.is_return ? '8, 8' : null
        }).addTo(routeLayersGroup);

        poly.bindTooltip(`<b>${escapeHtml(leg.name)}</b><br>Дистанция: ${leg.distance_km} км | Расход: ${leg.energy_wh} Вт·ч`, { sticky: true });

        const step = Math.max(6, Math.floor(leg.coordinates.length / 4));
        for (let i = Math.floor(step / 2); i < leg.coordinates.length - 1; i += step) {
          const p1 = leg.coordinates[i];
          const p2 = leg.coordinates[i + 1];
          const angle = calculateBearing(p1[0], p1[1], p2[0], p2[1]);

          const arrowIcon = L.divIcon({
            className: '',
            html: `<div style="transform: rotate(${angle}deg); width:18px; height:18px; display:flex; align-items:center; justify-content:center;">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="${leg.color}">
                <path d="M12 2L4 20l8-4 8 4z" stroke="#ffffff" stroke-width="1.5"/>
              </svg>
            </div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9]
          });

          L.marker(p1, { icon: arrowIcon, interactive: false }).addTo(routeLayersGroup);
        }
      });
    }

    if (route.geometry && route.geometry.length > 0) {
      const boundsCoords = route.geometry.map(c => [c[1], c[0]]);
      map.fitBounds(L.latLngBounds(boundsCoords), { padding: [60, 60] });
    }
  }

  function displayResults(idx) {
    state.selectedRouteIdx = idx;
    const r = state.calculatedRoutes[idx];
    const bikeInfo = state.calculatedResponse?.bike_info || {};
    const ambientInfo = state.calculatedResponse?.ambient_info || {};

    renderRouteLines(r);

    const badgeRoundTrip = document.getElementById('badgeRoundTrip');
    if (badgeRoundTrip) {
      badgeRoundTrip.className = state.isRoundTrip
        ? "text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 px-2 py-0.5 rounded-full border border-emerald-300 dark:border-emerald-800"
        : "hidden";
    }

    // Tabs for alternative routes
    const tabsEl = document.getElementById('routeTabsContainer');
    if (tabsEl) {
      if (state.calculatedRoutes.length > 1) {
        tabsEl.innerHTML = '';
        state.calculatedRoutes.forEach((item, i) => {
          const tabBtn = document.createElement('button');
          tabBtn.className = `flex-1 py-1.5 px-2.5 rounded-xl text-xs font-semibold flex items-center justify-center gap-1.5 transition ${i === idx ? 'bg-slate-900 text-white shadow dark:bg-blue-600' : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200'}`;
          tabBtn.innerHTML = `<span>${escapeHtml(item.name)}</span><span class="text-[10px] opacity-75">${item.energy_consumed_wh} Вт·ч</span>`;
          tabBtn.onclick = () => displayResults(i);
          tabsEl.appendChild(tabBtn);
        });
        tabsEl.classList.remove('hidden');
      } else {
        tabsEl.classList.add('hidden');
      }
    }

    // Safety Banner
    const banner = document.getElementById('safetyBanner');
    if (banner) {
      if (r.safety_status === 'critical') {
        banner.className = "p-3 rounded-2xl mb-3 text-xs flex items-center gap-2.5 bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-200 border border-rose-300 dark:border-rose-800";
        banner.innerHTML = `<i class="fa-solid fa-triangle-exclamation text-lg text-rose-600"></i><div><b>КРИТИЧЕСКИЙ РАЗРЯД!</b> Расход ${r.energy_consumed_percent}% превышает остаток ${state.initialCharge}%. Необходима подзарядка!</div>`;
      } else if (r.safety_status === 'warning') {
        banner.className = "p-3 rounded-2xl mb-3 text-xs flex items-center gap-2.5 bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-200 border border-amber-300 dark:border-amber-800";
        banner.innerHTML = `<i class="fa-solid fa-circle-exclamation text-lg text-amber-600"></i><div><b>Внимание:</b> останется всего ${r.final_charge_percent}% заряда. Рекомендуется экономичный режим.</div>`;
      } else {
        banner.className = "p-3 rounded-2xl mb-3 text-xs flex items-center gap-2.5 bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-200 border border-emerald-300 dark:border-emerald-800";
        banner.innerHTML = `<i class="fa-solid fa-circle-check text-lg text-emerald-600"></i><div><b>Маршрут безопасен:</b> запас хода достаточен. Остаток АКБ: <b>${r.final_charge_percent}%</b>.</div>`;
      }
    }

    document.getElementById('resDistance').innerText = r.distance_km + ' км';
    document.getElementById('resDuration').innerText = Math.round(r.duration_minutes) + ' мин';
    document.getElementById('resAscent').innerText = '+' + r.ascent_m + ' м';
    document.getElementById('resEnergy').innerText = r.energy_consumed_wh + ' Вт·ч';
    document.getElementById('resDropPercent').innerText = '-' + r.energy_consumed_percent + '% АКБ';
    document.getElementById('resFinalCharge').innerText = r.final_charge_percent + '%';
    document.getElementById('resEffectiveCap').innerText = 'Эфф. емкость: ' + (bikeInfo.effective_capacity_wh || Math.round(r.energy_consumed_wh / (r.energy_consumed_percent / 100))) + ' Вт·ч';

    // Surface Analysis
    const surfaceBadge = document.getElementById('surfaceCrrBadge');
    const surfaceBreakdown = document.getElementById('surfaceBreakdownText');
    const surfaceAlert = document.getElementById('surfaceImpactAlert');

    if (surfaceBadge && surfaceBreakdown) {
      const crrVal = (typeof r.effective_crr === 'number') ? r.effective_crr : 0.007;
      surfaceBadge.innerText = `C_rr = ${crrVal.toFixed(3)}`;
      if (crrVal <= 0.010) {
        surfaceBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300";
      } else if (crrVal <= 0.020) {
        surfaceBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-300";
      } else {
        surfaceBadge.className = "text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-300";
      }

      surfaceBreakdown.innerText = (r.surface_labels && r.surface_labels.length > 0)
        ? r.surface_labels.join(' • ')
        : (r.dominant_surface || '100% Асфальт');

      if (surfaceAlert) {
        surfaceAlert.classList.remove('hidden');
        if (r.surface_warning) {
          surfaceAlert.className = "mt-1.5 p-2 rounded-xl text-[11px] font-medium flex items-center gap-1.5 bg-cyan-50 dark:bg-cyan-950/50 border border-cyan-200 dark:border-cyan-800 text-cyan-900 dark:text-cyan-200";
          surfaceAlert.innerHTML = `<span>${escapeHtml(r.surface_warning)}</span>`;
        } else if (crrVal > 0.014) {
          surfaceAlert.className = "mt-1.5 p-2 rounded-xl text-[11px] font-medium flex items-center gap-1.5 bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 text-amber-900 dark:text-amber-200";
          surfaceAlert.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-amber-600"></i><span><b>Сложное покрытие:</b> плитка, брусчатка или грунт увеличивают трение шин.</span>';
        } else {
          surfaceAlert.className = "mt-1.5 p-2 rounded-xl text-[11px] font-medium flex items-center gap-1.5 bg-emerald-50 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 text-emerald-900 dark:text-emerald-200";
          surfaceAlert.innerHTML = '<i class="fa-solid fa-circle-check text-emerald-600"></i><span><b>Сухой асфальт:</b> оптимальный накат и минимальный расход энергии.</span>';
        }
      }
    }

    renderElevationSvg(r.elevation_profile, r.geometry);

    // Segment list
    const segContainer = document.getElementById('segmentsListContainer');
    if (segContainer) {
      if (r.legs && r.legs.length > 0) {
        segContainer.innerHTML = '';
        r.legs.forEach(s => {
          const row = document.createElement('div');
          row.className = "flex justify-between items-center p-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-200/80 dark:border-slate-700 shadow-xs";
          row.innerHTML = `
            <div class="flex items-center gap-2.5">
              <span class="w-3 h-3 rounded-full flex-shrink-0" style="background-color: ${s.color};"></span>
              <div>
                <b class="text-slate-800 dark:text-slate-200 text-xs">${escapeHtml(s.name)}</b>
                <div class="text-slate-400 text-[10px]">${s.distance_km} км • Груз: ${s.cargo_weight_kg} кг • Подъем +${s.ascent_m}м</div>
              </div>
            </div>
            <div class="text-right font-bold text-slate-800 dark:text-slate-200 text-xs">
              ${s.energy_wh} Вт·ч
            </div>
          `;
          segContainer.appendChild(row);
        });
      } else {
        segContainer.innerHTML = '<div class="text-center text-slate-400 text-xs py-2">Нет данных по отрезкам</div>';
      }
    }

    // Energy breakdown
    const brk = r.energy_breakdown || {};
    const tFactor = ambientInfo.temperature_capacity_factor || 1.0;
    const brkContainer = document.getElementById('energyBreakdownList');
    if (brkContainer) {
      brkContainer.innerHTML = `
        <div class="flex justify-between"><span>Качение колес:</span><b>${brk.rolling_wh || 0} Вт·ч</b></div>
        <div class="flex justify-between"><span>Сопротивление ветра (короб):</span><b>${brk.aero_wh || 0} Вт·ч</b></div>
        <div class="flex justify-between"><span>Преодоление подъемов:</span><b>${brk.climb_wh || 0} Вт·ч</b></div>
        <div class="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-700"><span>Эффективность АКБ на холоде:</span><b>${Math.round(tFactor * 100)}%</b></div>
      `;
    }

    // Mini Dashboard sync
    document.getElementById('miniDistance').innerText = r.distance_km + ' км';
    document.getElementById('miniDuration').innerText = Math.round(r.duration_minutes) + ' мин';
    document.getElementById('miniEnergy').innerText = r.energy_consumed_wh + ' Вт·ч';

    const miniBat = document.getElementById('miniBattery');
    miniBat.innerText = r.final_charge_percent + '%';
    if (r.safety_status === 'critical') {
      miniBat.className = "text-sm font-black text-rose-600";
    } else if (r.safety_status === 'warning') {
      miniBat.className = "text-sm font-black text-amber-600";
    } else {
      miniBat.className = "text-sm font-black text-emerald-600 dark:text-emerald-400";
    }

    bottomSheet.snapTo('half');
  }

  // --- Interactive Elevation SVG Chart with Map Cursor Sync ---
  function renderElevationSvg(profile, geometry) {
    const svg = document.getElementById('elevationSvg');
    if (!svg || !profile || profile.length < 2) {
      if (svg) svg.innerHTML = '';
      return;
    }

    const step = Math.max(1, Math.floor(profile.length / 90));
    const sampled = profile.filter((_, i) => i % step === 0);

    const eles = sampled.map(p => p.elevation_m);
    const minEle = Math.min(...eles);
    const maxEle = Math.max(...eles);
    const eleDiff = Math.max(10, maxEle - minEle);

    const statsText = document.getElementById('elevStatsText');
    if (statsText) {
      statsText.innerText = `мин ${minEle}м / макс ${maxEle}м (перепад ${maxEle - minEle}м)`;
    }

    const width = 400;
    const height = 90;
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);

    let pathD = `M 0 ${height}`;
    sampled.forEach((p, idx) => {
      const x = (idx / (sampled.length - 1)) * width;
      const normY = (p.elevation_m - minEle) / eleDiff;
      const y = height - (normY * (height - 18)) - 8;
      pathD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    pathD += ` L ${width} ${height} Z`;

    svg.innerHTML = `
      <defs>
        <linearGradient id="elevGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#10b981" stop-opacity="0.65"/>
          <stop offset="100%" stop-color="#10b981" stop-opacity="0.05"/>
        </linearGradient>
      </defs>
      <path d="${pathD}" fill="url(#elevGrad)" stroke="#10b981" stroke-width="2"/>
      <line id="elevCrosshair" class="elev-crosshair hidden" x1="0" y1="0" x2="0" y2="${height}"/>
      <circle id="elevDot" class="hidden" r="3.5" fill="#2563eb" stroke="#ffffff" stroke-width="1.5"/>
    `;

    // Add pointer interaction for elevation crosshair
    svg.onmousemove = (e) => handleSvgPointer(e.clientX);
    svg.ontouchmove = (e) => {
      if (e.touches.length > 0) handleSvgPointer(e.touches[0].clientX);
    };

    const hideIndicator = () => {
      const cross = document.getElementById('elevCrosshair');
      const dot = document.getElementById('elevDot');
      if (cross) cross.classList.add('hidden');
      if (dot) dot.classList.add('hidden');
      if (elevationMarker) {
        map.removeLayer(elevationMarker);
        elevationMarker = null;
      }
    };

    svg.onmouseleave = hideIndicator;
    svg.ontouchend = hideIndicator;

    function handleSvgPointer(clientX) {
      const rect = svg.getBoundingClientRect();
      const relX = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const ptIdx = Math.round(relX * (sampled.length - 1));
      const pt = sampled[ptIdx];
      if (!pt) return;

      const x = relX * width;
      const normY = (pt.elevation_m - minEle) / eleDiff;
      const y = height - (normY * (height - 18)) - 8;

      const cross = document.getElementById('elevCrosshair');
      const dot = document.getElementById('elevDot');
      if (cross && dot) {
        cross.setAttribute('x1', x);
        cross.setAttribute('x2', x);
        cross.classList.remove('hidden');

        dot.setAttribute('cx', x);
        dot.setAttribute('cy', y);
        dot.classList.remove('hidden');
      }

      // Sync position on Map
      if (geometry && geometry.length > 0) {
        const geoIdx = Math.min(geometry.length - 1, Math.round(relX * (geometry.length - 1)));
        const geoCoord = [geometry[geoIdx][1], geometry[geoIdx][0]];

        if (!elevationMarker) {
          elevationMarker = L.circleMarker(geoCoord, {
            radius: 6,
            color: '#ffffff',
            fillColor: '#2563eb',
            fillOpacity: 1,
            weight: 2
          }).addTo(map);
        } else {
          elevationMarker.setLatLng(geoCoord);
        }
      }
    }
  }

  // --- BottomSheet Controller ---
  class BottomSheetController {
    constructor(elementId) {
      this.el = document.getElementById(elementId);
      this.handle = document.getElementById('closeResults');
      this.miniDashboard = document.getElementById('sheetMiniDashboard');
      this.expandIcon = document.getElementById('sheetExpandIcon');
      this.bottomArea = document.getElementById('bottomActionArea');

      this.state = 'hidden';
      this.currentY = window.innerHeight;
      this.startY = 0;
      this.startTranslateY = 0;
      this.isDragging = false;
      this.startTime = 0;
      this.hideTimeout = null;

      this.initEvents();
    }

    getSnapPositions() {
      const vh = window.innerHeight;
      return {
        hidden: vh + 30,
        peek: vh - 78,
        half: Math.max(vh * 0.48, vh - 430),
        full: Math.max(40, vh * 0.12)
      };
    }

    snapTo(targetState, animated = true) {
      this.state = targetState;
      const snaps = this.getSnapPositions();

      if (this.hideTimeout) {
        clearTimeout(this.hideTimeout);
        this.hideTimeout = null;
      }

      if (this.state === 'hidden') {
        const targetY = snaps.hidden;
        this.currentY = targetY;
        this.el.style.transition = animated ? 'transform 0.28s cubic-bezier(0.22, 1, 0.36, 1)' : 'none';
        this.el.style.transform = `translateY(${targetY}px)`;

        this.hideTimeout = setTimeout(() => {
          if (this.state === 'hidden') {
            this.el.classList.add('hidden');
          }
        }, animated ? 290 : 0);

        if (this.bottomArea) {
          this.bottomArea.classList.remove('hidden');
        }
        updateCalculateButton();
        updateFloatingReopenBtn();
        return;
      }

      // Opening from hidden
      if (this.el.classList.contains('hidden')) {
        this.el.classList.remove('hidden');
        if (animated) {
          this.el.style.transition = 'none';
          this.el.style.transform = `translateY(${snaps.hidden}px)`;
          void this.el.offsetHeight; // Force reflow
        }
      }

      if (this.bottomArea) {
        this.bottomArea.classList.add('hidden');
      }
      updateFloatingReopenBtn();

      const targetY = (snaps[targetState] !== undefined) ? snaps[targetState] : snaps.half;
      this.currentY = targetY;

      this.el.style.transition = animated ? 'transform 0.32s cubic-bezier(0.22, 1, 0.36, 1)' : 'none';
      this.el.style.transform = `translateY(${targetY}px)`;

      if (this.expandIcon) {
        this.expandIcon.className = this.state === 'peek' 
          ? 'fa-solid fa-chevron-up text-xs' 
          : 'fa-solid fa-chevron-down text-xs';
      }
    }

    initEvents() {
      const onStart = (clientY) => {
        this.isDragging = true;
        this.startY = clientY;
        this.startTime = Date.now();
        this.startTranslateY = this.currentY;
        this.el.style.transition = 'none';
      };

      const onMove = (clientY) => {
        if (!this.isDragging) return;
        const deltaY = clientY - this.startY;
        const snaps = this.getSnapPositions();
        let newY = this.startTranslateY + deltaY;

        // Top resistance
        if (newY < snaps.full) {
          newY = snaps.full + (newY - snaps.full) * 0.2;
        }
        // Bottom resistance only past hidden off-screen
        else if (newY > snaps.hidden) {
          newY = snaps.hidden + (newY - snaps.hidden) * 0.2;
        }

        this.currentY = newY;
        this.el.style.transform = `translateY(${newY}px)`;
      };

      const onEnd = (clientY) => {
        if (!this.isDragging) return;
        this.isDragging = false;
        const elapsed = Math.max(1, Date.now() - this.startTime);
        const deltaY = clientY - this.startY;
        const velocity = deltaY / elapsed;

        const snaps = this.getSnapPositions();
        let targetState = this.state;

        // Velocity gestures
        if (velocity > 0.4) {
          // Fast swipe down
          if (this.state === 'full') {
            targetState = (velocity > 0.95 || deltaY > 240) ? 'peek' : 'half';
          } else if (this.state === 'half') {
            targetState = (velocity > 0.75 || deltaY > 150) ? 'hidden' : 'peek';
          } else if (this.state === 'peek') {
            targetState = 'hidden';
          }
        } else if (velocity < -0.4) {
          // Fast swipe up
          if (this.state === 'peek') targetState = 'half';
          else if (this.state === 'half') targetState = 'full';
          else targetState = 'full';
        } else {
          // Position-based snapping
          if (this.currentY >= snaps.peek + 35) {
            // Dragged down towards bottom edge -> hide completely
            targetState = 'hidden';
          } else {
            const distFull = Math.abs(this.currentY - snaps.full);
            const distHalf = Math.abs(this.currentY - snaps.half);
            const distPeek = Math.abs(this.currentY - snaps.peek);
            const minDist = Math.min(distFull, distHalf, distPeek);

            if (minDist === distFull) targetState = 'full';
            else if (minDist === distHalf) targetState = 'half';
            else targetState = 'peek';
          }
        }

        this.snapTo(targetState, true);
      };

      [this.handle, this.miniDashboard].forEach(zone => {
        if (!zone) return;
        zone.addEventListener('touchstart', (e) => {
          if (e.touches.length === 1) onStart(e.touches[0].clientY);
        }, { passive: true });

        zone.addEventListener('touchmove', (e) => {
          if (e.touches.length === 1) onMove(e.touches[0].clientY);
        }, { passive: true });

        zone.addEventListener('touchend', (e) => {
          if (e.changedTouches.length === 1) onEnd(e.changedTouches[0].clientY);
        }, { passive: true });
      });

      const onMouseDown = (e) => {
        if (e.target.closest('#btnCloseResults') || e.target.closest('#btnMinimizeResults') || e.target.closest('#btnSheetRecalcMini')) return;
        onStart(e.clientY);
        const onMouseMove = (ev) => onMove(ev.clientY);
        const onMouseUp = (ev) => {
          onEnd(ev.clientY);
          window.removeEventListener('mousemove', onMouseMove);
          window.removeEventListener('mouseup', onMouseUp);
        };
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);
      };

      if (this.handle) this.handle.addEventListener('mousedown', onMouseDown);
      if (this.miniDashboard) this.miniDashboard.addEventListener('mousedown', onMouseDown);

      if (this.handle) {
        this.handle.addEventListener('click', () => {
          if (this.state === 'peek') this.snapTo('half');
          else if (this.state === 'half') this.snapTo('peek');
          else if (this.state === 'full') this.snapTo('half');
        });
      }

      if (this.miniDashboard) {
        this.miniDashboard.addEventListener('click', (e) => {
          if (e.target.closest('#btnCloseResults') || e.target.closest('#btnMinimizeResults') || e.target.closest('#btnSheetRecalcMini')) return;
          if (this.state === 'peek') this.snapTo('half');
        });
      }

      const btnClose = document.getElementById('btnCloseResults');
      if (btnClose) {
        btnClose.addEventListener('click', (e) => {
          e.stopPropagation();
          if (this.state === 'peek') this.snapTo('half');
          else if (this.state === 'half') this.snapTo('peek');
          else if (this.state === 'full') this.snapTo('half');
        });
      }

      const btnMin = document.getElementById('btnMinimizeResults');
      if (btnMin) {
        btnMin.addEventListener('click', (e) => {
          e.stopPropagation();
          this.snapTo('hidden');
        });
      }

      const btnScrollClose = document.getElementById('btnScrollBodyClose');
      if (btnScrollClose) {
        btnScrollClose.addEventListener('click', (e) => {
          e.stopPropagation();
          this.snapTo('hidden');
        });
      }

      window.addEventListener('resize', () => {
        if (this.state !== 'hidden') {
          this.snapTo(this.state, false);
        }
      });
    }
  }

  let bottomSheet;

  // --- City Selection & Geocoding ---
  async function changeCity(cityName, centerMap = true) {
    if (!cityName || !cityName.trim()) return;
    const name = cityName.trim();
    state.currentCity = name;
    localStorage.setItem('ebike_city', name);

    const badgeText = document.getElementById('cityBadgeText');
    if (badgeText) badgeText.innerText = name;

    const searchInp = document.getElementById('searchInput');
    if (searchInp) searchInp.placeholder = `Поиск в г. ${name}...`;

    const cfgCityInp = document.getElementById('cfgCity');
    if (cfgCityInp) cfgCityInp.value = name;

    if (centerMap) {
      try {
        const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(name)}&limit=1`);
        if (res.ok) {
          const data = await res.json();
          if (data && data.length > 0) {
            const lat = parseFloat(data[0].lat);
            const lon = parseFloat(data[0].lon);
            map.flyTo([lat, lon], 13, { duration: 1.2 });
            updateLiveWeather(lat, lon);
            showToast(`Город изменен на ${name}`, 'info');
          }
        }
      } catch (e) { }
    }
  }

  // --- Document Event Listeners Setup ---
  function setupEventListeners() {
    // Theme toggle button
    const themeBtn = document.getElementById('btnToggleTheme');
    if (themeBtn) {
      themeBtn.onclick = () => {
        const nextTheme = state.theme === 'dark' ? 'light' : 'dark';
        applyTheme(nextTheme);
        showToast(nextTheme === 'dark' ? "Включена тёмная тема" : "Включена светлая тема", "info");
      };
    }

    // Server health badge click triggers wake-up ping / recheck
    const serverBadge = document.getElementById('serverStatusBadge');
    if (serverBadge) {
      serverBadge.onclick = (e) => {
        e.stopPropagation();
        checkServerHealth(true);
      };
    }

    // Road conditions
    document.getElementById('btnCondDry')?.addEventListener('click', () => setRoadCondition('dry'));
    document.getElementById('btnCondWet')?.addEventListener('click', () => setRoadCondition('wet'));
    document.getElementById('btnCondSlush')?.addEventListener('click', () => setRoadCondition('slush'));

    // Modes
    document.getElementById('modeStart')?.addEventListener('click', () => setClickMode('start'));
    document.getElementById('modeAddStop')?.addEventListener('click', () => setClickMode('add_stop'));
    document.getElementById('modeEnd')?.addEventListener('click', () => setClickMode('end'));

    // FAB Buttons
    document.getElementById('btnUndoStop')?.addEventListener('click', () => {
      if (state.waypoints.length > 0) {
        state.waypoints.pop();
        refreshMarkers();
        showToast("Последний заказ удален", 'info');
      }
    });

    document.getElementById('btnClearStops')?.addEventListener('click', () => {
      state.waypoints = [];
      state.isRouteCalculated = false;
      state.calculatedRoutes = null;
      state.calculatedResponse = null;
      refreshMarkers();
      setClickMode('add_stop');
      routeLayersGroup.clearLayers();
      if (bottomSheet) bottomSheet.snapTo('hidden');
      updateCalculateButton();
      showToast("Все промежуточные точки очищены", 'info');
    });

    document.getElementById('btnGeo')?.addEventListener('click', () => {
      if (!navigator.geolocation) return showToast("Геолокация недоступна в браузере", 'error');
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          state.startPoint = [pos.coords.latitude, pos.coords.longitude];
          map.setView(state.startPoint, 14);
          refreshMarkers();
          setClickMode('add_stop');
          updateLiveWeather(state.startPoint[0], state.startPoint[1]);
          showToast("Старт установлен по вашему местоположению", 'success');
        },
        (err) => showToast("Ошибка геолокации: " + err.message, 'error'),
        { enableHighAccuracy: true }
      );
    });

    // Quick Options Drawer
    const btnToggleQuickOptions = document.getElementById('btnToggleQuickOptions');
    const quickOptionsPanel = document.getElementById('quickOptionsPanel');
    const quickOptionsArrow = document.getElementById('quickOptionsArrow');
    if (btnToggleQuickOptions && quickOptionsPanel) {
      btnToggleQuickOptions.onclick = () => {
        const isHidden = quickOptionsPanel.classList.toggle('hidden');
        if (quickOptionsArrow) {
          quickOptionsArrow.classList.toggle('rotate-180', !isHidden);
        }
      };
    }

    // Round trip toggle
    const toggleRoundTrip = document.getElementById('toggleRoundTrip');
    if (toggleRoundTrip) {
      toggleRoundTrip.onchange = (e) => {
        state.isRoundTrip = e.target.checked;
        const modeEndBtn = document.getElementById('modeEnd');
        if (modeEndBtn) {
          modeEndBtn.disabled = state.isRoundTrip;
          modeEndBtn.style.opacity = state.isRoundTrip ? '0.4' : '1.0';
        }
        if (state.isRoundTrip && state.clickMode === 'end') {
          setClickMode('add_stop');
        }
        refreshMarkers();
      };
    }

    // City Button (using City Modal instead of prompt)
    document.getElementById('btnCityBadge')?.addEventListener('click', () => {
      const cityModal = document.getElementById('cityModal');
      const cityInput = document.getElementById('cityModalInput');
      if (cityModal && cityInput) {
        cityInput.value = state.currentCity;
        cityModal.classList.remove('hidden');
        setTimeout(() => cityInput.focus(), 50);
      }
    });

    // Smart Paste
    document.getElementById('btnSmartPaste')?.addEventListener('click', async () => {
      let text = '';
      try {
        text = await navigator.clipboard.readText();
      } catch (err) {
        showToast("Нажмите Ctrl+V в строку поиска или разрешите доступ к буферу", 'info');
        document.getElementById('searchInput')?.focus();
        return;
      }

      if (!text || !text.trim()) return;

      const directCoords = extractCoordsFromText(text);
      if (directCoords) {
        applyFoundCoordinates(directCoords, "Локация из ссылки");
      } else {
        const btn = document.getElementById('btnSmartPaste');
        const oldHtml = btn.innerHTML;
        btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin"></i>';
        const geoCoords = await geocodeAddress(text);
        btn.innerHTML = oldHtml;

        if (geoCoords) {
          applyFoundCoordinates(geoCoords, text);
        } else {
          showToast(`Адрес не найден: "${text}"`, 'error');
        }
      }
    });

    // Address Search with debounced autocomplete and AbortController
    const searchInput = document.getElementById('searchInput');
    const btnClearSearch = document.getElementById('btnClearSearch');
    const searchSuggestions = document.getElementById('searchSuggestions');
    let searchDebounceTimer = null;
    let searchAbortController = null;

    if (searchInput) {
      searchInput.oninput = (e) => {
        const q = e.target.value.trim();
        if (btnClearSearch) btnClearSearch.classList.toggle('hidden', q.length === 0);

        clearTimeout(searchDebounceTimer);
        if (searchAbortController) searchAbortController.abort();

        if (q.length < 2) {
          searchSuggestions?.classList.add('hidden');
          return;
        }

        searchDebounceTimer = setTimeout(async () => {
          searchAbortController = new AbortController();
          try {
            const viewbox = getSearchBoundingBox();
            let query = q;
            if (state.currentCity && !q.toLowerCase().includes(state.currentCity.toLowerCase())) {
              query = `${state.currentCity}, ${q}`;
            }

            const url = `https://nominatim.openstreetmap.org/search?format=json&addressdetails=1&q=${encodeURIComponent(query)}&viewbox=${viewbox}&bounded=0&limit=6`;
            const res = await fetch(url, {
              headers: { 'Accept': 'application/json' },
              signal: searchAbortController.signal
            });

            if (!res.ok) return;
            const data = await res.json();

            if (!data || data.length === 0) {
              if (searchSuggestions) {
                searchSuggestions.innerHTML = `
                  <div class="p-3 text-center text-slate-400 text-xs">
                    <i class="fa-solid fa-location-crosshairs text-slate-300 mb-1 block text-sm"></i>
                    Улица не найдена в г. ${escapeHtml(state.currentCity)}
                  </div>
                `;
                searchSuggestions.classList.remove('hidden');
              }
              return;
            }

            if (searchSuggestions) {
              searchSuggestions.innerHTML = '';
              data.forEach(item => {
                const addr = item.address || {};
                const road = addr.road || addr.pedestrian || addr.street || addr.neighbourhood || item.name || "";
                const house = addr.house_number ? `, ${addr.house_number}` : "";
                const city = addr.city || addr.town || addr.village || addr.municipality || "";
                const stateName = addr.state || addr.country || "";

                const mainTitle = road ? `${road}${house}` : item.display_name.split(',')[0];
                const subTitle = [city, stateName].filter(Boolean).join(', ') || item.display_name;

                const row = document.createElement('div');
                row.className = "p-2.5 hover:bg-blue-50 dark:hover:bg-slate-800 cursor-pointer text-slate-700 dark:text-slate-200 flex items-start gap-2.5 transition border-b border-slate-100 dark:border-slate-800 last:border-0";
                row.innerHTML = `
                  <div class="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-600 dark:text-blue-400 flex items-center justify-center flex-shrink-0 mt-0.5 text-[11px]">
                    <i class="fa-solid fa-location-dot"></i>
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="font-bold text-slate-800 dark:text-slate-100 text-xs truncate">${escapeHtml(mainTitle)}</div>
                    <div class="text-slate-400 dark:text-slate-400 text-[10px] truncate">📍 ${escapeHtml(subTitle)}</div>
                  </div>
                `;
                row.onclick = () => {
                  searchSuggestions.classList.add('hidden');
                  searchInput.value = mainTitle;
                  btnClearSearch?.classList.remove('hidden');
                  applyFoundCoordinates([parseFloat(item.lat), parseFloat(item.lon)], mainTitle);
                };
                searchSuggestions.appendChild(row);
              });
              searchSuggestions.classList.remove('hidden');
            }
          } catch (err) {
            if (err.name !== 'AbortError') console.log("Search error:", err);
          }
        }, 300);
      };
    }

    btnClearSearch?.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      btnClearSearch.classList.add('hidden');
      searchSuggestions?.classList.add('hidden');
    });

    document.addEventListener('click', (e) => {
      if (searchInput && searchSuggestions && !searchInput.contains(e.target) && !searchSuggestions.contains(e.target)) {
        searchSuggestions.classList.add('hidden');
      }
    });

    // Calculate & Reopen Sheet Actions
    document.getElementById('btnCalculate')?.addEventListener('click', async () => {
      if (state.isRouteCalculated && state.calculatedRoutes && state.calculatedRoutes.length > 0) {
        bottomSheet.snapTo('half');
        return;
      }
      await executeRouteCalculation();
    });

    // Reopen Results Button (Floating dock when hidden)
    document.getElementById('btnReopenResults')?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (state.isRouteCalculated && state.calculatedRoutes && state.calculatedRoutes.length > 0) {
        bottomSheet.snapTo('half');
      }
    });

    // FAB Stack Reopen Route Button
    document.getElementById('btnFloatReopenRoute')?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (state.isRouteCalculated && state.calculatedRoutes && state.calculatedRoutes.length > 0) {
        bottomSheet.snapTo('half');
      }
    });

    // Floating Recalculate button when stale
    document.getElementById('btnRecalcStaleFloating')?.addEventListener('click', async (e) => {
      e.stopPropagation();
      await executeRouteCalculation();
    });

    document.getElementById('btnSheetRecalcMini')?.addEventListener('click', async (e) => {
      e.stopPropagation();
      await executeRouteCalculation();
    });

    document.getElementById('btnRecalcFromSheet')?.addEventListener('click', async (e) => {
      e.stopPropagation();
      await executeRouteCalculation();
    });

    // GPX Export
    document.getElementById('btnExportGpx')?.addEventListener('click', () => {
      if (!state.calculatedRoutes || state.calculatedRoutes.length === 0) return;
      const r = state.calculatedRoutes[state.selectedRouteIdx];
      if (!r || !r.geometry || r.geometry.length === 0) return;

      const now = new Date().toISOString();
      let gpx = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="EBike-AI-Router" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>${escapeHtml(r.name)} (${r.distance_km} km, ${r.energy_consumed_wh} Wh)</name>
    <time>${now}</time>
  </metadata>
  <wpt lat="${state.startPoint[0]}" lon="${state.startPoint[1]}"><name>Старт</name></wpt>\n`;

      state.waypoints.forEach((wp, idx) => {
        gpx += `  <wpt lat="${wp[0]}" lon="${wp[1]}"><name>Заказ #${idx + 1}</name></wpt>\n`;
      });

      if (!state.isRoundTrip) {
        gpx += `  <wpt lat="${state.endPoint[0]}" lon="${state.endPoint[1]}"><name>Финиш</name></wpt>\n`;
      }

      gpx += `  <trk>\n    <name>${escapeHtml(r.name)}</name>\n    <trkseg>\n`;
      r.geometry.forEach((pt) => {
        const lat = pt[1];
        const lon = pt[0];
        const ele = pt[2] !== undefined ? `<ele>${pt[2]}</ele>` : '';
        gpx += `      <trkpt lat="${lat}" lon="${lon}">${ele}</trkpt>\n`;
      });
      gpx += `    </trkseg>\n  </trk>\n</gpx>`;

      const blob = new Blob([gpx], { type: 'application/gpx+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ebike_route_${Date.now()}.gpx`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("Файл GPX загружен!", "success");
    });

    // TSP Optimize Order
    document.getElementById('btnOptimizeOrder')?.addEventListener('click', async () => {
      const n = state.waypoints.length;
      if (n < 2) {
        showToast("Для оптимизации порядка добавьте минимум 2 заказа", 'warning');
        return;
      }

      const btn = document.getElementById('btnOptimizeOrder');
      const oldHtml = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin text-[9px]"></i><span>Оптимизация...</span>';

      let bikeWeight = 32.0;
      if (state.bikeType === 'custom') {
        bikeWeight = state.customBike.weightKg;
      } else if (DEFAULT_PRESETS[state.bikeType]) {
        bikeWeight = DEFAULT_PRESETS[state.bikeType].weightKg;
      }

      const payload = {
        start_point: state.startPoint,
        waypoints: state.waypoints,
        end_point: state.endPoint,
        round_trip: state.isRoundTrip,
        cargo_weight_kg: state.cargoKg,
        rider_weight_kg: state.riderKg,
        bike_weight_kg: bikeWeight,
        road_condition: state.roadCondition
      };

      try {
        const baseUrl = (state.apiBaseUrl || DEFAULT_API_URL).replace(/\/+$/, '');
        const res = await fetch(`${baseUrl}/optimize-order`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Ошибка сервера (${res.status})`);
        }

        const data = await res.json();
        state.waypoints = data.reordered_waypoints;
        refreshMarkers();
        updateServerStatus(true);
        showToast(`✨ ${data.explanation}`, 'success', 5000);
      } catch (err) {
        console.error("TSP error:", err);
        let errMsg = `Ошибка TSP: ${err.message}`;
        if (err.message && (err.message.includes('Failed to fetch') || err.message.includes('NetworkError'))) {
          updateServerStatus('waking');
          errMsg = "Сервер Render просыпается (~30–50 сек). Подождите полминуты и повторите.";
        } else {
          updateServerStatus(false);
        }
        showToast(errMsg, 'error', 6000);
      } finally {
        btn.disabled = false;
        btn.innerHTML = oldHtml;
      }
    });

    // Settings Modal
    const settingsModal = document.getElementById('settingsModal');
    const cfgBike = document.getElementById('cfgBike');
    const customBikeBox = document.getElementById('customBikeBox');

    document.getElementById('btnSettings')?.addEventListener('click', () => {
      if (cfgBike) cfgBike.value = state.bikeType;
      if (state.bikeType === 'custom') {
        customBikeBox?.classList.remove('hidden');
        document.getElementById('customVolts').value = state.customBike.volts;
        document.getElementById('customAh').value = state.customBike.ah;
        document.getElementById('customWeight').value = state.customBike.weightKg;
        document.getElementById('customPower').value = state.customBike.powerW;
        updateCustomWhCalc();
      } else {
        customBikeBox?.classList.add('hidden');
      }

      document.getElementById('cfgCity').value = state.currentCity || '';
      document.getElementById('cfgCharge').value = state.initialCharge;
      document.getElementById('cfgChargeVal').innerText = state.initialCharge + '%';
      document.getElementById('cfgTemp').value = state.tempC;
      document.getElementById('cfgTempVal').innerText = (state.tempC > 0 ? '+' : '') + state.tempC + '°C';
      document.getElementById('cfgCargo').value = state.cargoKg;
      document.getElementById('cfgRider').value = state.riderKg;
      document.getElementById('cfgWind').value = state.headwindKmh;
      document.getElementById('cfgWindVal').innerText = state.headwindKmh + ' км/ч';
      document.getElementById('cfgApiUrl').value = state.apiBaseUrl || DEFAULT_API_URL;

      settingsModal?.classList.remove('hidden');
    });

    document.getElementById('btnCloseSettings')?.addEventListener('click', () => settingsModal?.classList.add('hidden'));

    cfgBike?.addEventListener('change', (e) => {
      customBikeBox?.classList.toggle('hidden', e.target.value !== 'custom');
    });

    function updateCustomWhCalc() {
      const v = parseFloat(document.getElementById('customVolts').value);
      const ah = parseFloat(document.getElementById('customAh').value);
      const wh = Math.round(v * ah);
      document.getElementById('customWhCalc').innerText = `${v}V × ${ah}Ah = ${wh} Вт·ч`;
    }

    document.getElementById('customVolts')?.addEventListener('change', updateCustomWhCalc);
    document.getElementById('customAh')?.addEventListener('input', updateCustomWhCalc);

    document.getElementById('cfgCharge')?.addEventListener('input', (e) => {
      document.getElementById('cfgChargeVal').innerText = e.target.value + '%';
    });

    document.getElementById('cfgTemp')?.addEventListener('input', (e) => {
      const v = parseInt(e.target.value);
      document.getElementById('cfgTempVal').innerText = (v > 0 ? '+' : '') + v + '°C';
      const f = (v >= 20 ? 1 : (v >= 10 ? 0.95 + 0.05 * ((v - 10) / 10) : (v >= 0 ? 0.88 + 0.07 * (v / 10) : (v >= -10 ? 0.74 + 0.14 * ((v + 10) / 10) : 0.55))));
      const note = document.getElementById('tempEffectNote');
      if (v < 0) {
        note.innerText = `❄️ Мороз! Доступная емкость АКБ падает до ${Math.round(f * 100)}%.`;
        note.className = "text-[11px] text-rose-500 font-medium mt-1";
      } else {
        note.innerText = `Оптимальная температура (емкость ${Math.round(f * 100)}%).`;
        note.className = "text-[11px] text-slate-400 mt-1";
      }
    });

    document.getElementById('cfgWind')?.addEventListener('input', (e) => {
      document.getElementById('cfgWindVal').innerText = e.target.value + ' км/ч';
    });

    document.getElementById('btnSaveSettings')?.addEventListener('click', () => {
      const cityVal = document.getElementById('cfgCity').value.trim();
      if (cityVal && cityVal !== state.currentCity) {
        changeCity(cityVal, false);
      }

      state.bikeType = cfgBike.value;
      if (state.bikeType === 'custom') {
        state.customBike = {
          volts: parseFloat(document.getElementById('customVolts').value),
          ah: parseFloat(document.getElementById('customAh').value),
          weightKg: parseFloat(document.getElementById('customWeight').value),
          powerW: parseFloat(document.getElementById('customPower').value)
        };
        localStorage.setItem('ebike_custom_bike', JSON.stringify(state.customBike));
      } else {
        localStorage.removeItem('ebike_custom_bike');
      }

      state.initialCharge = parseInt(document.getElementById('cfgCharge').value);
      state.tempC = parseInt(document.getElementById('cfgTemp').value);
      state.cargoKg = parseFloat(document.getElementById('cfgCargo').value);
      state.riderKg = parseFloat(document.getElementById('cfgRider').value);
      state.headwindKmh = parseInt(document.getElementById('cfgWind').value);

      const customApi = document.getElementById('cfgApiUrl').value.trim().replace(/\/+$/, '');
      if (!customApi || customApi === DEFAULT_API_URL) {
        state.apiBaseUrl = DEFAULT_API_URL;
        localStorage.removeItem('ebike_api_url');
        document.getElementById('cfgApiUrl').value = DEFAULT_API_URL;
      } else {
        state.apiBaseUrl = customApi;
        localStorage.setItem('ebike_api_url', customApi);
      }

      const customBadge = document.getElementById('customBikeBadge');
      if (customBadge) {
        customBadge.classList.toggle('hidden', state.bikeType !== 'custom');
      }

      checkServerHealth();
      checkRouteStaleness();
      settingsModal?.classList.add('hidden');
      showToast("Параметры курьера сохранены", "success");
    });

    // Bookmark Modal Controls
    document.getElementById('btnAddBookmark')?.addEventListener('click', openBookmarkModal);
    document.getElementById('btnCloseBookmarkModal')?.addEventListener('click', closeBookmarkModal);
    document.getElementById('btnSaveBookmarkModal')?.addEventListener('click', () => {
      const nameInput = document.getElementById('bookmarkNameInput');
      const name = nameInput ? nameInput.value.trim() : '';
      if (name) {
        const newBm = {
          id: 'bm_' + Date.now(),
          name: name,
          icon: 'fa-star',
          lat: state.startPoint[0],
          lon: state.startPoint[1]
        };
        bookmarks.push(newBm);
        localStorage.setItem('ebike_bookmarks', JSON.stringify(bookmarks));
        renderBookmarks();
        closeBookmarkModal();
        showToast(`Закладка "${name}" добавлена`, "success");
      }
    });

    // City Modal Controls
    const cityModal = document.getElementById('cityModal');
    document.getElementById('btnCloseCityModal')?.addEventListener('click', () => cityModal?.classList.add('hidden'));
    document.getElementById('btnSaveCityModal')?.addEventListener('click', () => {
      const inp = document.getElementById('cityModalInput');
      if (inp && inp.value.trim()) {
        changeCity(inp.value.trim(), true);
        cityModal?.classList.add('hidden');
      }
    });

    // Batch Import Modal Controls
    const batchModal = document.getElementById('batchModal');
    document.getElementById('btnOpenBatch')?.addEventListener('click', () => batchModal?.classList.remove('hidden'));
    document.getElementById('btnCloseBatch')?.addEventListener('click', () => batchModal?.classList.add('hidden'));

    document.getElementById('btnRunBatch')?.addEventListener('click', async () => {
      const batchText = document.getElementById('batchText');
      const raw = batchText ? batchText.value.trim() : '';
      if (!raw) return showToast("Введите хотя бы один адрес", 'warning');

      const lines = raw.split('\n').map(l => l.replace(/^[0-9]+[.)\s-]*/, '').trim()).filter(l => l.length > 0);
      if (lines.length === 0) return showToast("Список адресов пуст", 'warning');

      const btnRunBatch = document.getElementById('btnRunBatch');
      const btnRunBatchText = document.getElementById('btnRunBatchText');
      btnRunBatch.disabled = true;
      if (btnRunBatchText) btnRunBatchText.innerText = `Импорт (0 / ${lines.length})...`;

      let addedCount = 0;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (btnRunBatchText) btnRunBatchText.innerText = `Ищем адрес ${i + 1} из ${lines.length}...`;

        let coords = extractCoordsFromText(line);
        if (!coords) {
          coords = await geocodeAddress(line);
        }

        if (coords) {
          state.waypoints.push(coords);
          addedCount++;
        }
      }

      btnRunBatch.disabled = false;
      if (btnRunBatchText) btnRunBatchText.innerText = "Распознать и расставить заказы";
      batchModal?.classList.add('hidden');
      if (batchText) batchText.value = '';

      if (addedCount > 0) {
        refreshMarkers();
        showToast(`Успешно добавлено ${addedCount} точек заказов!`, 'success');
        if (state.waypoints.length > 0) {
          map.fitBounds(L.latLngBounds([state.startPoint, ...state.waypoints]), { padding: [50, 50] });
        }
      } else {
        showToast("Не удалось найти введенные адреса", 'error');
      }
    });
  }

  // --- Startup / Initialization ---
  document.addEventListener('DOMContentLoaded', () => {
    applyTheme(state.theme);
    initMap();
    bottomSheet = new BottomSheetController('resultsCard');
    setupEventListeners();
    refreshMarkers();
    renderBookmarks();
    changeCity(state.currentCity, false);
    updateLiveWeather(state.startPoint[0], state.startPoint[1]);
    checkServerHealth();
  });

})();
