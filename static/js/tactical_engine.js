// --- i18n Localization Dictionary ---
const currentLang = localStorage.getItem('cdc_lang') || 'en'; 

const i18n = {
    en: {
        radar: "TACTICAL RADAR",
        altitude: "ALTITUDE",
        unmapped: "Unmapped / Plains",
        speed: "SPEED",
        status: "STATUS",
        personnel: "PERSONNEL",
        btn_move: "Move Order",
        btn_stop: "Halt",
        sys_ready: "System Ready. Awaiting orders."
    },
    zh: {
        radar: "战区遥测雷达",
        altitude: "实时海拔",
        unmapped: "未测绘区 / 平原",
        speed: "行军速度",
        status: "当前建制状态",
        personnel: "兵力存活",
        btn_move: "📍下达机动指令",
        btn_stop: "🛑紧急停止",
        sys_ready: "系统就绪。等待指挥官指令。"
    }
};

function t(key) {
    return i18n[currentLang][key] || key;
}

function orderProfileByRole(role) {
    return globalRules.orders?.modes?.[role] || {
        id: role.toUpperCase(), label: role, summary: '', description: '', color: '#8b949e'
    };
}

function orderProfileForUnit(unit) {
    return Object.values(globalRules.orders?.modes || {}).find(profile => profile.id === unit.order_mode)
        || orderProfileByRole(globalRules.orders?.default_role || 'hold');
}

// 🟢 1. Global Variable Registration
let map;
let geojsonLayer = null;
let pathLine = null;
let draftLine = null;
let draftMarker = null;
let draftedTarget = null;
window.unitMarkersMap = {};

let draftedWaypoints = [];
let draftMarkers = [];
let roadLayer = null;
let roadsVisible = false;

let globalWeapons = {};
let globalBattalions = {};
let globalRules = {};
let isDeploying = false;
let selectedUnitId = null;
let selectedUnitLon = null;
let selectedUnitLat = null;
let provinceInfluence = {};
let pendingAction = "move";
let lastLogCount = 0;
let heartbeatInterval = null;
let committeeState = null;
let availableFactions = [];
let mapClickHandler = null;

function escapeHtml(value) {
    return String(value ?? '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#039;');
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    let data;
    try { data = await response.json(); }
    catch (_) { throw new Error(`The server returned an unreadable response (${response.status}).`); }
    if (!response.ok || data.status === 'error') {
        throw new Error(data.msg || `Request failed (${response.status}).`);
    }
    return data;
}

// 🟢 Dynamic Faction Palette (Universal Color Assigner)
const factionPalette = ['#ff7b72', '#7ee787', '#58a6ff', '#e3b341', '#d2a8ff', '#ff94c2', '#a5d6ff'];
let factionColorMap = {};
let paletteIndex = 0;

function getFactionColor(faction) {
    if (!faction) return '#8b949e';
    if (!factionColorMap[faction]) {
        factionColorMap[faction] = factionPalette[paletteIndex % factionPalette.length];
        paletteIndex++;
    }
    return factionColorMap[faction];
}

const leafletReady = typeof window.L !== 'undefined';
const mapLayers = leafletReady ? {
    'clean': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', { maxZoom: 12 }),
    'topo': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', { maxZoom: 12 }),
    'admin': L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { maxZoom: 12 })
} : {};
let currentMapMode = 'clean';

// 🟢 2. System Boot: Scan and Mount DLCs
window.onload = function() {
    if (!leafletReady) {
        document.getElementById('dlc-list-container').innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">Map library unavailable. Check the internet connection, then reload.<br><a href="/status" style="color:#58a6ff;">Open readiness check</a></div>`;
        return;
    }
    map = L.map('map', { zoomControl: false, attributionControl: false, doubleClickZoom: false }).setView([0, 0], 2);
    mapLayers['clean'].addTo(map); 
    L.control.scale({ position: 'bottomleft', metric: true, imperial: false }).addTo(map);
    loadDlcList();
};

async function loadDlcList() {
    const container = document.getElementById('dlc-list-container');
    try {
        const dlcs = await fetchJson('/api/list_dlcs');
        container.replaceChildren();
        if (dlcs.length === 0) {
            container.innerHTML = `<div style="color:#ff7b72; text-align:center;">No DLC detected. Place a package in the dlc directory or use the DLC Builder.</div>`;
            return;
        }
        dlcs.forEach(dlc => {
            const card = document.createElement('div');
            card.style.cssText = `border:1px solid ${dlc.valid ? '#30363d' : '#f85149'}; padding:15px; background:rgba(0,0,0,0.5); margin-bottom:10px;`;
            const title = document.createElement('div');
            title.style.cssText = `color:${dlc.valid ? '#7ee787' : '#ff7b72'}; font-size:18px; font-weight:bold;`;
            title.textContent = `${dlc.valid ? '📂' : '⚠️'} ${dlc.name}`;
            const description = document.createElement('div');
            description.style.cssText = 'color:#8b949e; font-size:12px;';
            description.textContent = dlc.valid ? dlc.desc : (dlc.errors || []).join('; ');
            card.append(title, description);
            if (dlc.valid) {
                card.style.cursor = 'pointer';
                card.addEventListener('mouseenter', () => { card.style.borderColor = '#58a6ff'; });
                card.addEventListener('mouseleave', () => { card.style.borderColor = '#30363d'; });
                card.addEventListener('click', () => mountDLC(dlc.id));
            }
            container.appendChild(card);
        });
    } catch (error) {
        container.innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">DLC scan failed: ${escapeHtml(error.message)}</div>`;
    }
}

function resetMountedMap() {
    if (heartbeatInterval) clearInterval(heartbeatInterval);
    heartbeatInterval = null;
    if (geojsonLayer) map.removeLayer(geojsonLayer);
    if (roadLayer) map.removeLayer(roadLayer);
    if (pathLine) map.removeLayer(pathLine);
    if (draftLine) map.removeLayer(draftLine);
    Object.values(window.unitMarkersMap).forEach(record => {
        map.removeLayer(record.marker);
        if (record.circle) map.removeLayer(record.circle);
    });
    window.unitMarkersMap = {};
    geojsonLayer = roadLayer = pathLine = draftLine = null;
    selectedUnitId = null;
    committeeState = null;
    roadsVisible = false;
}

async function mountDLC(dlcId) {
    document.getElementById('dlc-list-container').innerHTML = `<div style="color:#e3b341; text-align:center; padding:20px;">[ MOUNTING CORE MODULES... ]<br>Loading campaign data...</div>`;
    
    // Clear the palette for the new campaign
    factionColorMap = {}; 
    paletteIndex = 0;

    try {
        const res = await fetchJson('/api/mount_dlc', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({dlc_id: dlcId})
        });
        resetMountedMap();
        availableFactions = res.config.factions || [];
        map.setView([res.config.center[0], res.config.center[1]], res.config.zoom);
        document.title = "CDC Command Radar - " + res.config.name;

        const [registry, geojson] = await Promise.all([fetchJson('/api/registry'), fetchJson('/geojson')]);
        globalWeapons = registry.weapons;
        globalBattalions = registry.battalions;
        globalRules = registry.rules;
        updateRuleDrivenUI();
        updateDeployUI();
        if (geojson.type === 'FeatureCollection' && geojson.features?.length) {
            geojsonLayer = L.geoJSON(geojson, { style: styleProvince }).addTo(map);
        }

        document.getElementById('bootloader-screen').style.display = 'none';
        if (res.config.warnings?.length) {
            alert(`Scenario mounted with warnings:\n\n${res.config.warnings.join('\n')}`);
        }
        await fetchState();
        fetchCommitteeState();
        heartbeatInterval = setInterval(fetchState, 1000);
        setupMapClicks();
    } catch (error) {
        const container = document.getElementById('dlc-list-container');
        container.innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">Mount failed: ${escapeHtml(error.message)}<br><button class="cmd-btn" id="retry-dlc-list" style="margin-top:12px;">Back to scenarios</button></div>`;
        document.getElementById('retry-dlc-list')?.addEventListener('click', loadDlcList);
    }
}

function setRuleSpeed(which) {
    const clock = globalRules.clock;
    const value = which === 'maximum' ? clock.speed_multiplier_max : clock.default_time_multiplier;
    sendCommand(`speed ${value}`);
}

function updateRuleDrivenUI() {
    const clock = globalRules.clock;
    const speedInput = document.getElementById('custom-speed-input');
    speedInput.min = clock.speed_multiplier_min;
    speedInput.max = clock.speed_multiplier_max;
    speedInput.value = clock.default_time_multiplier;
    document.getElementById('speed-default-button').textContent = `${clock.default_time_multiplier}X`;
    document.getElementById('speed-maximum-button').textContent = `${clock.speed_multiplier_max}X MAX`;

    const modifierRules = globalRules.modifiers;
    const modifierSelect = document.getElementById('admin-mod-type');
    modifierSelect.replaceChildren();
    for (const type of modifierRules.allowed_types) {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type.replaceAll('_', ' ');
        modifierSelect.appendChild(option);
    }
    const modifierValue = document.getElementById('admin-mod-val');
    modifierValue.min = modifierRules.value_minimum;
    modifierValue.max = modifierRules.value_maximum;
    modifierValue.value = modifierRules.default_value;
    const modifierDuration = document.getElementById('admin-mod-dur');
    modifierDuration.min = modifierRules.duration_minimum_hours;
    modifierDuration.max = modifierRules.duration_maximum_hours;
    modifierDuration.value = modifierRules.default_duration_hours;

    const directiveRules = globalRules.directives;
    const effectSelect = document.getElementById('committee-effect');
    effectSelect.replaceChildren();
    for (const effect of directiveRules.allowed_effects) {
        const option = document.createElement('option');
        option.value = effect;
        option.textContent = effect === 'none' ? 'No mechanical effect' : effect.replaceAll('_', ' ');
        effectSelect.appendChild(option);
    }
    document.getElementById('committee-faction').value = directiveRules.default_faction;
    document.getElementById('committee-duration').value = directiveRules.default_duration_hours;
}

function updateDeployUI() {
    const wSelect = document.getElementById('dep-weapon');
    wSelect.replaceChildren();
    for (const [key, w] of Object.entries(globalWeapons)) {
        const option = document.createElement('option');
        option.value = key;
        option.textContent = `${w.name} - Range ${w.range}km`;
        wSelect.appendChild(option);
    }
    const cGrid = document.getElementById('dep-comp-grid');
    cGrid.replaceChildren();
    for (const [key, b] of Object.entries(globalBattalions)) {
        const size = Number.isFinite(Number(b.size)) ? Number(b.size) : 0;
        const item = document.createElement('div');
        item.className = 'comp-item';
        item.title = `Base Complement: ${size} personnel`;
        const label = document.createElement('label');
        label.textContent = b.name || key;
        const input = document.createElement('input');
        input.type = 'number';
        input.id = `dep-${key}`;
        input.value = '0';
        input.min = '0';
        input.step = '1';
        input.dataset.size = String(size);
        input.addEventListener('input', calcDeployStats);
        item.append(label, input);
        cGrid.appendChild(item);
    }
    const firstBattalion = Object.keys(globalBattalions)[0];
    if (firstBattalion && document.getElementById(`dep-${firstBattalion}`)) {
        document.getElementById(`dep-${firstBattalion}`).value = 1;
    }
    document.getElementById('dep-faction').value = availableFactions[0] || '';
    calcDeployStats();
}

// 🟢 3. Core Radar and Interaction Logic
function switchMapMode(mode) {
    if (mode === currentMapMode) return;
    map.removeLayer(mapLayers[currentMapMode]);
    mapLayers[mode].addTo(map);
    currentMapMode = mode;
    ['clean', 'topo', 'admin'].forEach(m => document.getElementById('btn-view-' + m).classList.remove('active'));
    document.getElementById('btn-view-' + mode).classList.add('active');
}

function toggleHistoricRoads() {
    roadsVisible = !roadsVisible;
    const btn = document.getElementById('btn-toggle-roads');
    if (!roadsVisible) {
        if (roadLayer) map.removeLayer(roadLayer);
        btn.classList.remove('active'); btn.style.borderColor = ""; btn.style.color = ""; return;
    }
    btn.classList.add('active'); btn.style.borderColor = "#ff4444"; btn.style.color = "#ff7b72"; btn.innerHTML = "⏳ Scanning...";
    fetchJson('/api/roads_overlay').then(data => {
        if (roadLayer) map.removeLayer(roadLayer);
        roadLayer = L.geoJSON(data, { pointToLayer: function (feature, latlng) { return L.circleMarker(latlng, { radius: 1, fillColor: "#ff0000", color: "#ff0000", weight: 1, opacity: 0.6, fillOpacity: 0.8 }); } }).addTo(map);
        btn.innerHTML = "🛣️ Roads"; 
    }).catch(err => { btn.innerHTML = "❌ Load Failed"; roadsVisible = false; });
}

function toggleDeployPanel() {
    const panel = document.getElementById('deploy-panel');
    if (panel.style.display === 'none' || panel.style.display === '') {
        panel.style.display = 'block'; calcDeployStats();
    } else {
        panel.style.display = 'none'; isDeploying = false; document.getElementById('targeting-alert').style.display = 'none';
    }
}

function calcDeployStats() {
    let totalPop = 0;
    for (const key of Object.keys(globalBattalions)) {
        const input = document.getElementById(`dep-${key}`);
        if (input) { totalPop += (parseInt(input.value) || 0) * (Number(input.dataset.size) || 0); }
    }
    document.getElementById('dep-pop-display').innerText = totalPop + " Personnel";
    document.getElementById('dep-personnel').value = totalPop;
}

function enableDeployTargeting() {
    const personnel = Number(document.getElementById('dep-personnel').value);
    const hasBattalion = Object.keys(globalBattalions).some(key => Number(document.getElementById(`dep-${key}`)?.value) > 0);
    if (!Number.isFinite(personnel) || personnel <= 0 || !hasBattalion) {
        alert('Choose at least one battalion and deploy at least one person before selecting a drop zone.');
        return;
    }
    isDeploying = true;
    document.getElementById('targeting-alert').style.display = "block";
    document.getElementById('targeting-alert').innerText = `[ AIRDROP INITIATED ] Click on the map to deploy armed forces...`;
}

function setTargetingMode(actionStr) {
    pendingAction = actionStr; clearDraft(); pendingAction = actionStr; 
    const role = actionStr === 'attack' ? 'assault' : (actionStr === 'move' ? 'relocate' : actionStr);
    const profile = orderProfileByRole(role);
    const routeHint = actionStr === 'route' ? ' Click once for each waypoint, then authorize.' : ' Click the destination, review, then authorize.';
    document.getElementById('targeting-alert').style.display = "block";
    document.getElementById('targeting-alert').innerText = `${profile.label.toUpperCase()}: ${profile.description}${routeHint}`;
}

function setupMapClicks() {
    if (mapClickHandler) map.off('click', mapClickHandler);
    mapClickHandler = async function(e) {
        if (isDeploying) {
            let dynamicComp = {};
            for (const key of Object.keys(globalBattalions)) {
                const input = document.getElementById(`dep-${key}`);
                if (input && parseInt(input.value) > 0) dynamicComp[key] = parseInt(input.value);
            }
            const name = document.getElementById('dep-name').value.trim();
            const faction = document.getElementById('dep-faction').value.trim();
            const personnel = parseFloat(document.getElementById('dep-personnel').value);
            if (!name || !faction || !Number.isFinite(personnel) || personnel <= 0 || Object.keys(dynamicComp).length === 0) {
                alert('Enter a unit name, faction, positive personnel count, and at least one battalion.');
                return;
            }
            const data = {
                id: "unit_" + (window.crypto?.randomUUID ? window.crypto.randomUUID().replaceAll('-', '').slice(0, 16) : Math.floor(Math.random() * 1000000)), name,
                faction,
                icon: document.getElementById('dep-icon') ? document.getElementById('dep-icon').value : "",
                personnel,
                equipment_level: Number(globalRules.unit_defaults.equipment_level),
                lon: e.latlng.lng,
                lat: e.latlng.lat,
                unit_type: globalRules.unit_defaults.unit_type,
                stance: globalRules.unit_defaults.stance,
                composition: dynamicComp,
                primary_weapon: document.getElementById('dep-weapon').value
            };
            try {
                const created = await fetchJson('/api/edit_unit', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) });
                toggleDeployPanel();
                selectedUnitId = created.unit.id;
                selectedUnitLon = created.unit.lon;
                selectedUnitLat = created.unit.lat;
                await fetchState();
                map.panTo([created.unit.lat, created.unit.lon]);
                alert(`✅ ${created.unit.name} deployed with ${Math.floor(created.unit.personnel)} personnel. The new map symbol is selected.`);
            } catch (error) {
                alert("HQ Rejected: " + error.message);
            }
            return; 
        }

        if (!selectedUnitId) return;

        const tLat = e.latlng.lat; const tLon = e.latlng.lng;
        
        if (pendingAction === 'route') draftedWaypoints.push({lon: tLon, lat: tLat});
        else draftedWaypoints = [{lon: tLon, lat: tLat}]; 
        
        draftMarkers.forEach(m => map.removeLayer(m)); draftMarkers = [];
        if (draftLine) map.removeLayer(draftLine);

        const latlngs = [[selectedUnitLat, selectedUnitLon]];
        const iconHtml = pendingAction === 'attack' ? '🎯' : (pendingAction === 'bombard' ? '💥' : '📍');
        const draftRole = pendingAction === 'attack' ? 'assault' : (pendingAction === 'move' ? 'relocate' : pendingAction);
        const lineColor = pendingAction === 'bombard' ? '#f85149' : (pendingAction === 'airstrike' ? '#e3b341' : orderProfileByRole(draftRole).color);

        draftedWaypoints.forEach((wp, index) => {
            latlngs.push([wp.lat, wp.lon]);
            let htmlText = pendingAction === 'route' ? `<div style="color:${lineColor}; background:rgba(0,0,0,0.7); border:1px solid ${lineColor}; border-radius:50%; width:16px; height:16px; line-height:16px; text-align:center; font-size:10px;">${index+1}</div>` : `<span style="color:${lineColor}; text-shadow:0 0 5px #000;">${iconHtml}</span>`;
            const m = L.marker([wp.lat, wp.lon], {icon: L.divIcon({className: 'mil-icon', html: htmlText, iconSize: [20,20], iconAnchor: [10,10]})}).addTo(map);
            draftMarkers.push(m);
        });

        draftLine = L.polyline(latlngs, {color: lineColor, dashArray: '5,5', weight: 2}).addTo(map);

        document.getElementById('confirmation-panel').style.display = "block";
        const draftProfile = orderProfileByRole(draftRole);
        let typeStr = pendingAction === 'route'
            ? `${draftProfile.label.toUpperCase()} (${draftedWaypoints.length} waypoint${draftedWaypoints.length === 1 ? '' : 's'}): ${draftProfile.description}`
            : (pendingAction === 'bombard'
                ? "BOMBARD (long-range fire mission)"
                : (pendingAction === 'airstrike'
                    ? "AIRSTRIKE (close air support)"
                    : `${draftProfile.label.toUpperCase()}: ${draftProfile.description}`));
        document.getElementById('draft-type').innerText = typeStr;
        let coordsText = pendingAction === 'route' ? `DEST LON: ${tLon.toFixed(4)} | LAT: ${tLat.toFixed(4)}` : `LON: ${tLon.toFixed(4)} | LAT: ${tLat.toFixed(4)}`;
        document.getElementById('draft-coords').innerHTML = `${coordsText}<br><span style="color:#e3b341; font-size:12px;">Scanning destination topography...</span>`;
        
        try {
            const res = await fetchJson(`/api/terrain?lon=${encodeURIComponent(tLon)}&lat=${encodeURIComponent(tLat)}`);
            document.getElementById('draft-coords').innerHTML = `${coordsText}<br><span style="color:#8b949e; font-size:12px;">Dest. Topography: ${res.complexity > 0.6 ? '🏔️ Mountains' : (res.complexity > 0.3 ? '⛰️ Hills' : '🛣️ Plains')} (Drag: ${res.complexity})</span>`;
        } catch (error) {
            document.getElementById('draft-coords').textContent = `${coordsText} | Terrain unavailable: ${error.message}`;
        }
    };
    map.on('click', mapClickHandler);
}

async function executeDraftedCommand() {
    if (!selectedUnitId || draftedWaypoints.length === 0) return;
    const payload = { command: `${pendingAction} ${selectedUnitId} ${draftedWaypoints[0].lon} ${draftedWaypoints[0].lat}`, waypoints: draftedWaypoints };
    try {
        await fetchJson('/api/command', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
        clearDraft();
        await fetchState();
    } catch (error) {
        alert("Command rejected: " + error.message);
    }
}

function clearDraft() {
    if (draftLine) map.removeLayer(draftLine);
    if (draftMarkers) draftMarkers.forEach(m => map.removeLayer(m));
    draftMarkers = []; draftedWaypoints = []; pendingAction = "move";
    document.getElementById('confirmation-panel').style.display = "none"; document.getElementById('targeting-alert').style.display = "none";
}

async function sendCommand(cmdStr) {
    try {
        const result = await fetchJson('/api/command', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command: cmdStr}) });
        fetchState();
        return result;
    } catch (error) {
        alert(`Command rejected: ${error.message}`);
        return null;
    }
}

function deselectUnit() { selectedUnitId = null; selectedUnitLon = null; selectedUnitLat = null; clearDraft(); if (pathLine) map.removeLayer(pathLine); document.getElementById('unit-info').innerHTML = `<div style="color: #8b949e; font-style: italic; text-align: center; padding: 30px 0;">[ RADAR SCANNING ]<br>Awaiting Commander to select a target...</div>`; fetchState(); }

function getProvinceColor(influence) {
    if (!influence) return 'transparent';
    const political = globalRules.political_influence || {minimum: -100, maximum: 100};
    const positiveThreshold = Number(political.maximum) / 2;
    const negativeThreshold = Number(political.minimum) / 2;
    if (influence >= positiveThreshold) return '#ff4444'; if (influence > 0) return '#a80000';
    if (influence <= negativeThreshold) return '#44ff44'; if (influence < 0) return '#00a800'; return 'transparent';
}

function styleProvince(feature) {
    const provName = feature.properties?.cdc_name || 'Unknown';
    const infl = provinceInfluence[provName] || 0;
    const political = globalRules.political_influence || {minimum: -100, maximum: 100};
    const influenceScale = Math.max(Math.abs(Number(political.minimum)), Math.abs(Number(political.maximum)), 1);
    return { fillColor: getProvinceColor(infl), weight: 1, opacity: 0.3, color: '#1f6feb', fillOpacity: (Math.abs(infl) / influenceScale) * 0.35 };
}

function getUnitIcon(u) {
    // 🟢 优先级 1：如果部队拥有自定义图标，强制使用自定义图标
    if (u.icon && u.icon.trim() !== "") {
        return u.icon;
    }
    
    return globalRules.unit_types?.[u.unit_type]?.icon || "◆";
}    

function fetchState() {
    return fetchJson('/api/state').then(data => {
        if(data.status === "unmounted") return;
        const pad = (n) => (n||0).toString().padStart(2, '0');
        document.getElementById('time-display').innerText = `D${pad(data.time.day)} ${pad(data.time.hour)}:${pad(data.time.minute)}:${pad(data.time.second)}`;
        const statusSpan = document.getElementById('pause-status');
        if (data.time.paused) { statusSpan.innerText = '[ PAUSED ]'; statusSpan.style.color = '#ff7b72'; } 
        else { statusSpan.innerText = `[ RUNNING ${data.time.multiplier}X ]`; statusSpan.style.color = '#7ee787'; }

        provinceInfluence = data.provinces; if (geojsonLayer) geojsonLayer.setStyle(styleProvince);

        updateIntelFeed(data.latest_logs); refreshUnitsSmoothly(data.units);

        if (selectedUnitId && data.units[selectedUnitId]) {
            const u = data.units[selectedUnitId]; selectedUnitLon = u.lon; selectedUnitLat = u.lat; updateTacticalHUD(u);
            if (pathLine) map.removeLayer(pathLine);
            if (u.waypoints && u.waypoints.length > 0) {
                const latlngs = u.waypoints.map(wp => [wp[1], wp[0]]); latlngs.unshift([u.lat, u.lon]); 
                pathLine = L.polyline(latlngs, { color: orderProfileForUnit(u).color, dashArray: '5,5', weight: 2, opacity: 0.8 }).addTo(map);
            }
        } else if (selectedUnitId) { selectedUnitId = null; clearDraft(); document.getElementById('unit-info').innerHTML = `<div style="color: #ff7b72; font-weight: bold; text-align: center; padding: 30px 0;">[ SIGNAL LOST ]</div>`; if (pathLine) map.removeLayer(pathLine); }
    }).catch(error => {
        const statusSpan = document.getElementById('pause-status');
        if (statusSpan) {
            statusSpan.innerText = '[ CONNECTION LOST ]';
            statusSpan.style.color = '#ff7b72';
            statusSpan.title = error.message;
        }
    });
}

function refreshUnitsSmoothly(unitsData) {
    const currentIds = new Set(Object.keys(unitsData));
    for (const uid in window.unitMarkersMap) {
        if (!currentIds.has(uid) || (unitsData[uid] && unitsData[uid].personnel <= 0)) {
            map.removeLayer(window.unitMarkersMap[uid].marker); if (window.unitMarkersMap[uid].circle) map.removeLayer(window.unitMarkersMap[uid].circle); delete window.unitMarkersMap[uid];
        }
    }
    
    for (const [uid, u] of Object.entries(unitsData)) {
        if (u.personnel <= 0) continue;
        
        // 🟢 Assign Dynamic Colors! 
        const fColor = getFactionColor(u.faction);
        const isSelected = (uid === selectedUnitId);
        
        // Render icon with dynamic inline styles instead of fixed CSS classes
        const dynamicIconHtml = `<div style="color:${fColor};">${escapeHtml(getUnitIcon(u))}</div>`;
        
        if (window.unitMarkersMap[uid]) {
            const record = window.unitMarkersMap[uid];
            if (record.lastStance !== u.stance || record.wasSelected !== isSelected) {
                record.marker.setIcon(L.divIcon({ className: `mil-icon ${isSelected ? 'selected-unit' : ''}`, html: dynamicIconHtml, iconSize: [26, 26], iconAnchor: [13, 13] }));
                record.lastStance = u.stance; record.wasSelected = isSelected;
            }
            record.marker.setLatLng([parseFloat(u.lat), parseFloat(u.lon)]); 
            record.circle.setLatLng([parseFloat(u.lat), parseFloat(u.lon)]); 
            record.circle.setRadius((u.radius || 0) * 1000);
            record.circle.setStyle({ color: fColor, fillColor: fColor }); // Update circle color just in case
        } else {
            const marker = L.marker([parseFloat(u.lat), parseFloat(u.lon)], { icon: L.divIcon({ className: `mil-icon ${isSelected ? 'selected-unit' : ''}`, html: dynamicIconHtml, iconSize: [26, 26], iconAnchor: [13, 13] }) }).addTo(map);
            const circle = L.circle([parseFloat(u.lat), parseFloat(u.lon)], { color: fColor, fillColor: fColor, fillOpacity: 0.05, weight: 1, radius: (u.radius || 0) * 1000 }).addTo(map);
            marker.on('click', (e) => { L.DomEvent.stopPropagation(e); selectedUnitId = uid; selectedUnitLon = u.lon; selectedUnitLat = u.lat; clearDraft(); pendingAction = "move"; document.getElementById('targeting-alert').style.display = "none"; fetchState(); });
            window.unitMarkersMap[uid] = { marker: marker, circle: circle, lastStance: u.stance, wasSelected: isSelected };
        }
    }
}

function updateIntelFeed(logs) {
    if (!logs || logs.length === 0) return;
    const container = document.getElementById('logs-container');
    if (logs.length !== lastLogCount || logs[logs.length-1].message !== container.dataset.lastMsg) {
        container.innerHTML = logs.slice().reverse().map(log => `<div class="log-entry ${log.type === "combat" ? "log-combat" : (log.type === "move" ? "log-move" : "log-system")}">${escapeHtml(log.message)}</div>`).join('');
        container.dataset.lastMsg = logs[logs.length-1].message; lastLogCount = logs.length;
    }
}

function updateTacticalHUD(u) {
    const compStr = Object.entries(u.composition || {}).filter(([k,v])=>v>0).map(([k,v]) => `${escapeHtml(k)}:${Number(v)}`).join(' | ');
    const capabilities = new Set(u.effective_capabilities || u.capabilities || []);
    const missionButtons = [];
    if (capabilities.has(globalRules.missions?.bombard?.capability)) missionButtons.push(`<button class="cmd-btn cmd-warn" onclick="setTargetingMode('bombard')">🎯 Lock Fire Mission Coords</button>`);
    if (capabilities.has(globalRules.missions?.airstrike?.capability)) missionButtons.push(`<button class="cmd-btn cmd-warn" onclick="setTargetingMode('airstrike')">✈️ Authorize Strike Vector</button>`);
    const weaponPanel = missionButtons.length
        ? `<div class="panel-title" style="margin-top:15px;">🎯 Support Mission</div><div style="text-align:center;">${missionButtons.join(' ')}</div>`
        : '';
    const currentStance = globalRules.stances?.[u.stance] || {};
    const orderProfile = orderProfileForUnit(u);
    const activeOrderRole = Object.entries(globalRules.orders?.modes || {})
        .find(([, profile]) => profile.id === u.order_mode)?.[0]
        || globalRules.orders?.default_role
        || 'hold';
    const stanceOptions = Object.entries(globalRules.stances || {}).map(([stanceId, profile]) =>
        `<option value="${escapeHtml(stanceId)}" ${stanceId === u.stance ? 'selected' : ''}>${escapeHtml(profile.label || stanceId)}</option>`
    ).join('');
    const combatMultiplier = Number(currentStance.combat_multiplier ?? 0).toFixed(2);
    const speedMultiplier = Number(currentStance.movement_multiplier ?? 0).toFixed(2);
    const coverPercent = Math.round(Number(currentStance.base_cover ?? 0) * 100);
    const canPrepareGroundDefense = Boolean(globalRules.unit_types?.[u.unit_type]?.can_direct_combat);
    let engagementSummary = 'This unit cannot conduct direct ground combat.';
    if (canPrepareGroundDefense) {
        const movementTaskWithholdsFire = (
            (activeOrderRole === 'relocate' && !globalRules.orders.relocate_allows_stance_fire)
            || (activeOrderRole === 'route' && !globalRules.orders.route_allows_stance_fire)
        );
        if (!currentStance.allows_ranged_fire) {
            engagementSummary = 'Ranged fire is withheld by stance; close-contact self-defense remains active.';
        } else if (movementTaskWithholdsFire) {
            engagementSummary = 'Ranged fire is withheld by the movement task; close-contact self-defense remains active.';
        } else if (activeOrderRole === 'assault') {
            engagementSummary = 'The unit seeks detected contact, fights within weapon range, and resumes its advance when clear.';
        } else {
            engagementSummary = 'The unit may engage detected enemies within weapon range while holding its task.';
        }
    }
    const orderButton = (role, icon, action, extraClass = '') => {
        const profile = orderProfileByRole(role);
        const activeClass = u.order_mode === profile.id ? ' active-order' : '';
        return `<button class="cmd-btn order-command ${extraClass}${activeClass}" style="--order-color:${escapeHtml(profile.color)}; border-color:${escapeHtml(profile.color)};" title="${escapeHtml(profile.description)}" onclick="${action}">
            <span class="order-command-title">${icon} ${escapeHtml(profile.label)}</span>
            <span class="order-command-summary">${escapeHtml(profile.summary)}</span>
        </button>`;
    };
    const assaultButton = canPrepareGroundDefense
        ? orderButton('assault', '⚔️', "setTargetingMode('attack')")
        : '';
    const defenseButtons = canPrepareGroundDefense
        ? `${orderButton('defend', '🛡️', `sendCommand('defend ${u.id}')`)}
           ${orderButton('fortify', '🛠️', `sendCommand('fortify ${u.id}')`)}`
        : '';
    const relocateButton = orderButton('relocate', '📍', "setTargetingMode('move')");
    const routeButton = orderButton('route', '🗺️', "setTargetingMode('route')");
    const holdButton = orderButton('hold', '⏹', `sendCommand('halt ${u.id}')`, 'order-hold');
    const maximumEntrenchment = Math.max(Number(globalRules.recovery?.maximum_entrenchment) || 1, 0.001);
    const entrenchmentPercent = Math.max(0, Math.min(100, Number(u.entrenchment || 0) / maximumEntrenchment * 100));
    
    // 🟢 Dynamic HUD Color Based on Palette
    const uColor = getFactionColor(u.faction);

    document.getElementById('unit-info').innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid #1f6feb; padding-bottom: 5px;">
            <span style="color:#fff; font-size:15px; font-weight:bold;">${escapeHtml(u.name)}</span><button class="cmd-btn cmd-danger" style="padding: 3px 6px;" onclick="deselectUnit()">❌ Release</button>
        </div>
        <div class="data-row"><span class="data-label">Faction:</span> <span style="color:${uColor}">${escapeHtml(u.faction)}</span></div>
        <div class="data-row"><span class="data-label">Status:</span> <span style="color:#58a6ff; font-weight:bold;">${escapeHtml(u.status)}</span></div>
        <div class="data-row"><span class="data-label">Strength:</span> ${Math.floor(u.personnel)} Pers.</div>
        <div class="data-row"><span class="data-label">Readiness:</span> Supply ${Math.floor(u.supply ?? globalRules.unit_defaults.supply)}% | Fatigue ${Math.floor(u.fatigue ?? globalRules.unit_defaults.fatigue)}% | Supp. ${Math.floor(u.suppression ?? globalRules.unit_defaults.suppression)}%</div>
        <div class="data-row"><span class="data-label">Prepared Defense:</span> ${entrenchmentPercent.toFixed(0)}%</div>
        <div style="height:6px; background:#161b22; border:1px solid #30363d; margin:2px 0 8px;"><div style="height:100%; width:${entrenchmentPercent}%; background:#3fb950;"></div></div>
        <div class="telemetry-box">
            <div class="telemetry-row"><span>LON: ${parseFloat(u.lon).toFixed(4)}</span><span>LAT: ${parseFloat(u.lat).toFixed(4)}</span><span>SPD: ${u.speed.toFixed(1)} km/h</span></div>
            <div style="text-align:center; border-top:1px dashed #58a6ff; padding-top:5px; margin-top:3px;">Real-time Altitude: <span style="color:#fff; font-size:14px; font-weight:bold;">${Math.floor(u.altitude || 0)}</span> m</div>
        </div>
        <div class="data-row"><span class="data-label">Def. Radius:</span> <span style="color:#7ee787; font-weight:bold;">${(u.radius || 0).toFixed(2)} km</span></div>
        <div class="data-row"><span class="data-label">OOB:</span> <span style="color:#a5d6ff">${compStr || 'Non-Combat Unit'}</span></div>
        <div class="data-row"><span class="data-label">Primary Arm:</span> <span style="color:#e3b341; font-weight:bold;">${escapeHtml(u.weapon_name || 'Unspecified')}</span></div>
        <div class="panel-title operational-order-title">📍 Operational Order</div>
        <div class="operational-order-panel" style="--order-color:${escapeHtml(orderProfile.color)}; border-color:${escapeHtml(orderProfile.color)};">
            <div class="order-section-label"><span>Current Task</span><small>WHAT &amp; WHERE</small></div>
            <div class="order-status-heading">
                <span>${escapeHtml(orderProfile.label)}</span>
                <span>${escapeHtml(orderProfile.summary)}</span>
            </div>
            <div class="order-status-description">${escapeHtml(orderProfile.description)}</div>

            <div class="order-divider"></div>
            <div class="order-section-label"><span>Combat Stance</span><small>HOW TO EXECUTE</small></div>
            <div class="stance-control-row">
                <select id="stance-select-${u.id}" class="dark-input" aria-label="Combat stance">${stanceOptions}</select>
                <button class="cmd-btn stance-apply" onclick="sendCommand('stance ${u.id} ' + document.getElementById('stance-select-${u.id}').value)">Set Stance</button>
            </div>
            <div class="stance-description" style="border-left-color:${escapeHtml(currentStance.color || '#8b949e')};">${escapeHtml(currentStance.description || '')}</div>
            <div class="order-metrics">
                <span>Combat ×${combatMultiplier}</span>
                <span>Speed ×${speedMultiplier}</span>
                <span>Cover ${coverPercent}%</span>
            </div>
            <div class="effective-behavior">${escapeHtml(engagementSummary)}</div>

            <div class="order-boundary-guide"><strong>Task</strong> sets the objective and contact policy. <strong>Stance</strong> sets fire discipline, speed, concealment, and combat modifiers. Changing either one keeps the other.</div>

            <div class="order-divider"></div>
            <div class="order-section-label"><span>Issue Task</span><small>STANCE WILL BE RETAINED</small></div>
            <div class="order-grid">
                ${assaultButton}
                ${relocateButton}
                ${routeButton}
                ${defenseButtons}
                ${holdButton}
            </div>
        </div>
        ${weaponPanel}
    `;
}
// ==========================================
// IN-GAME EDITOR (ZEUS CONSOLE) LOGIC
// ==========================================

function toggleAdminConsole() {
    const panel = document.getElementById('admin-console');
    panel.style.display = (panel.style.display === 'none' || panel.style.display === '') ? 'block' : 'none';
}

// 💉 Inject Buff/Debuff
async function applyAdminModifier() {
    if (!selectedUnitId) {
        alert("Zeus Error: No unit selected on radar!");
        return;
    }
    
    const type = document.getElementById('admin-mod-type').value;
    const val = parseFloat(document.getElementById('admin-mod-val').value);
    const dur = parseFloat(document.getElementById('admin-mod-dur').value);
    const modName = val > 1.0 ? "Zeus_Buff" : "Zeus_Debuff";

    try {
        await fetchJson('/api/modifier', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: selectedUnitId, name: modName, type, value: val, duration: dur })
        });
        fetchState();
    } catch (error) {
        alert(`Modifier rejected: ${error.message}`);
    }
}

// ⚙️ Live HP Edit (Reinforce or Smite)
async function forceUnitHP() {
    if (!selectedUnitId) {
        alert("Zeus Error: No unit selected on radar!");
        return;
    }
    
    const newHP = parseFloat(document.getElementById('admin-edit-hp').value);
    if (isNaN(newHP) || newHP < 0) return;

    try {
        await fetchJson('/api/admin_edit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ original_id: selectedUnitId, id: selectedUnitId, personnel: newHP })
        });
        fetchState();
        document.getElementById('admin-edit-hp').value = '';
    } catch (error) {
        alert(`Unit update rejected: ${error.message}`);
    }
}

// 🤝 / ⚔️ Diplomacy Override
async function forceDiplomacy(isAllied) {
    const f1 = document.getElementById('admin-dip-f1').value.trim();
    const f2 = document.getElementById('admin-dip-f2').value.trim();

    if (!f1 || !f2) {
        alert("Zeus Error: Specify both factions.");
        return;
    }

    try {
        await fetchJson('/api/diplomacy', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ f1, f2, allied: isAllied })
        });
        fetchState();
        document.getElementById('admin-dip-f1').value = '';
        document.getElementById('admin-dip-f2').value = '';
    } catch (error) {
        alert("Diplomacy override failed: " + error.message);
    }
}
// ==========================================
// ARCHIVE MANAGEMENT (SAVE / LOAD)
// ==========================================

function toggleSaveLoadPanel() {
    const panel = document.getElementById('save-load-panel');
    if (panel.style.display === 'none' || panel.style.display === '') {
        panel.style.display = 'block';
        // Hide other panels to avoid clutter
        document.getElementById('admin-console').style.display = 'none';
        document.getElementById('deploy-panel').style.display = 'none';
    } else {
        panel.style.display = 'none';
    }
}

async function saveGame() {
    const slot = document.getElementById('save-slot').value;
    try {
        await fetchJson('/api/save_game', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ slot })
        });
        const isZh = localStorage.getItem('cdc_lang') === 'zh';
        alert(isZh ? `✅ 战局状态已成功写入：${slot}` : `✅ State successfully saved to: ${slot}`);
        toggleSaveLoadPanel();
    } catch (error) {
        alert(`Save failed: ${error.message}`);
    }
}

async function loadGame() {
    const slot = document.getElementById('load-slot').value;
    const isZh = localStorage.getItem('cdc_lang') === 'zh';
    
    if(!confirm(isZh ? "⚠️ 警告：载入档案将覆盖当前的物理引擎状态，确认执行？" : "⚠️ WARNING: Loading will overwrite the current physics engine state. Proceed?")) {
        return;
    }
    
    try {
        await fetchJson('/api/load_game', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ slot })
        });
        alert(isZh ? `🔄 记忆读取成功，战局已重置！` : `🔄 Memory read successful. Theater restored and paused.`);
        toggleSaveLoadPanel();
        deselectUnit();
        fetchState();
    } catch (error) {
        alert((isZh ? "读取失败: " : "Load failed: ") + error.message);
    }
}

function toggleCommitteePanel() {
    const panel = document.getElementById('committee-panel');
    if (!panel) return;
    const opening = panel.style.display === 'none' || panel.style.display === '';
    panel.style.display = opening ? 'block' : 'none';
    if (opening) fetchCommitteeState();
}

async function fetchCommitteeState() {
    try {
        const data = await fetchJson('/api/committee');
        if (data.status === 'unmounted') return;
        committeeState = data;
        renderCommitteePanel();
    } catch (error) {
        const summary = document.getElementById('committee-summary');
        if (summary) summary.textContent = `Committee data unavailable: ${error.message}`;
    }
}

function renderCommitteePanel() {
    if (!committeeState) return;
    const c = committeeState.committee || {};
    const summary = document.getElementById('committee-summary');
    const records = document.getElementById('committee-records');
    if (!summary || !records) return;

    const roles = (c.delegate_roles || []).map(role =>
        `<div class="committee-role"><b>${escapeHtml(role.faction || role.role)}</b><br><span>${escapeHtml(role.role || '')}</span></div>`
    ).join('');
    const factions = (committeeState.factions || []).map(f =>
        `<div class="committee-faction-row"><span>${escapeHtml(f.faction)}</span><span>${Number(f.active_personnel)} pers | morale ${Number(f.average_morale)}% | supply ${Number(f.average_supply)}%</span></div>`
    ).join('');
    const rules = (c.rules_of_engagement || []).map(rule => `<li>${escapeHtml(rule)}</li>`).join('');

    summary.innerHTML = `
        <div style="color:#fff; font-weight:bold; font-size:14px;">${escapeHtml(c.committee_name || committeeState.scenario)}</div>
        <div style="color:#8b949e;">${escapeHtml(c.committee_type || 'committee')} | ${escapeHtml(c.simulation_scope || 'crisis')} | ${escapeHtml(committeeState.game_time)}</div>
        <div style="margin-top:8px;">${escapeHtml(c.public_briefing || '')}</div>
        <div class="committee-section-title">Rules of Engagement</div>
        <ul class="committee-rules">${rules || '<li>No committee rules configured.</li>'}</ul>
        <div class="committee-section-title">Delegate Roles</div>
        <div class="committee-role-grid">${roles || '<div class="committee-role">No roles configured.</div>'}</div>
        <div class="committee-section-title">Faction Readiness</div>
        ${factions || '<div style="color:#8b949e;">No units loaded.</div>'}
    `;

    const recHtml = (committeeState.public_records || []).slice().reverse().map(rec =>
        `<div class="committee-record"><b>${escapeHtml(rec.timestamp)} - ${escapeHtml(rec.title)}</b><br><span>${escapeHtml(rec.body || '')}</span><br><small>${escapeHtml(rec.faction)} | ${escapeHtml(rec.effect_type)} ${Number(rec.value)} | affected ${Number(rec.affected_units)}</small></div>`
    ).join('');
    records.innerHTML = `<div class="committee-section-title">Public Crisis Updates</div>${recHtml || '<div style="color:#8b949e; font-size:12px;">No public crisis updates yet.</div>'}`;
}

async function submitCommitteeDirective() {
    const payload = {
        title: document.getElementById('committee-title').value,
        body: document.getElementById('committee-body').value,
        faction: document.getElementById('committee-faction').value || 'GLOBAL',
        effect_type: document.getElementById('committee-effect').value,
        value: parseFloat(document.getElementById('committee-value').value || '0'),
        duration_hours: parseFloat(document.getElementById('committee-duration').value || '12'),
        public: document.getElementById('committee-public').checked
    };
    try {
        await fetchJson('/api/committee/adjudicate', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
        });
        document.getElementById('committee-title').value = '';
        document.getElementById('committee-body').value = '';
        fetchCommitteeState();
        fetchState();
    } catch (error) {
        alert(error.message || 'Adjudication failed');
    }
}

async function downloadSitrep() {
    try {
        const response = await fetch('/api/committee/sitrep');
        if (!response.ok) throw new Error(`SITREP export failed (${response.status}).`);
        const text = await response.text();
        const blob = new Blob([text], {type: 'text/markdown'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `cdc_sitrep_${Date.now()}.md`;
        a.click();
        URL.revokeObjectURL(a.href);
    } catch (error) {
        alert(error.message);
    }
}
