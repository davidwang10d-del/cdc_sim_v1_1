// --- i18n Localization Dictionary ---
const currentLang = localStorage.getItem('cdc_lang') || 'en'; 

const i18n = {
    en: {
        radar: "TACTICAL RADAR",
        altitude: "ALTITUDE",
        unmapped: "Unmapped / Plains",
        speed: "SPEED",
        status: "STATUS",
        personnel: "PERSONNEL ALIVE",
        btn_relocate: "Relocate",
        btn_stop: "Halt",
        sys_ready: "System Ready. Awaiting orders."
    },
    zh: {
        radar: "战区遥测雷达",
        altitude: "实时海拔",
        unmapped: "未测绘区 / 平原",
        speed: "行军速度",
        status: "当前建制状态",
        personnel: "现存兵力",
        btn_relocate: "📍下达转移指令",
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

function mapDistanceKm(lon1, lat1, lon2, lat2) {
    const radiusKm = 6371;
    const toRadians = value => Number(value) * Math.PI / 180;
    const deltaLat = toRadians(lat2 - lat1);
    const deltaLon = toRadians(lon2 - lon1);
    const firstLat = toRadians(lat1);
    const secondLat = toRadians(lat2);
    const a = Math.sin(deltaLat / 2) ** 2
        + Math.cos(firstLat) * Math.cos(secondLat) * Math.sin(deltaLon / 2) ** 2;
    return radiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
}

function remainingRouteDistanceKm(unit) {
    let lon = Number(unit?.lon);
    let lat = Number(unit?.lat);
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) return 0;
    return (unit?.waypoints || []).reduce((total, waypoint) => {
        const nextLon = Number(waypoint?.[0]);
        const nextLat = Number(waypoint?.[1]);
        if (!Number.isFinite(nextLon) || !Number.isFinite(nextLat)) return total;
        const distance = mapDistanceKm(lon, lat, nextLon, nextLat);
        lon = nextLon;
        lat = nextLat;
        return total + distance;
    }, 0);
}

function formatSimulationDuration(hours) {
    if (!Number.isFinite(hours) || hours < 0) return 'ETA unavailable';
    if (hours >= 24) return `${(hours / 24).toFixed(1)} simulation days`;
    if (hours >= 1) return `${hours.toFixed(1)} simulation hours`;
    return `${Math.max(1, Math.ceil(hours * 60))} simulation minutes`;
}

function isSupportMissionActive(unit) {
    return ['BOMBARDING', 'AIRSTRIKE_OUTBOUND', 'AIRSTRIKE_RTB'].includes(unit?.status);
}

function airstrikePerformance(unit) {
    if (unit?.airstrike_profile) return unit.airstrike_profile;
    const rules = globalRules?.missions?.airstrike || {};
    const typeId = unit?.aircraft_type || rules.default_aircraft_type;
    const profile = rules.aircraft_types?.[typeId] || rules.aircraft_types?.[rules.default_aircraft_type] || {};
    return {
        aircraft_type: typeId || '',
        label: profile.label || typeId || 'DLC default aircraft',
        description: profile.description || 'Uses the mounted DLC airstrike baseline.',
        attack_profile: profile.attack_profile || 'Tactical strike',
        cruise_speed_kmh: Number(unit?.speed || 0) * Number(profile.cruise_speed_multiplier ?? 1),
        sortie_range_km: Number(rules.sortie_range_km || 0) * Number(profile.sortie_range_multiplier ?? 1),
        blast_radius_km: Number(rules.blast_radius_km || 0) * Number(profile.blast_radius_multiplier ?? 1),
        supply_cost: Number(rules.supply_cost || 0) * Number(profile.supply_cost_multiplier ?? 1),
        fatigue_cost: Number(rules.fatigue_cost || 0) * Number(profile.fatigue_cost_multiplier ?? 1),
        accuracy_multiplier: Number(profile.accuracy_multiplier ?? 1),
        unobserved_targeting_multiplier: Number(profile.unobserved_targeting_multiplier ?? 1),
        payload_multiplier: Number(profile.payload_multiplier ?? 1),
        soft_target_multiplier: Number(profile.soft_target_multiplier ?? 1),
        hard_target_multiplier: Number(profile.hard_target_multiplier ?? 1),
        aa_vulnerability_multiplier: Number(profile.aa_vulnerability_multiplier ?? 1),
        strike_weapon_ids: (unit?.weapon_loadout || [])
            .filter(weapon => (weapon.roles || []).includes('airstrike'))
            .map(weapon => weapon.id)
    };
}

// 🟢 1. Global Variable Registration
let map;
let geojsonLayer = null;
let pathLine = null;
let draftLine = null;
let draftImpactCircle = null;
let draftRangeCircle = null;
let draftMarker = null;
let draftedTarget = null;
window.unitMarkersMap = {};
window.installationMarkersMap = {};

let draftedWaypoints = [];
let draftMarkers = [];
let roadLayer = null;
let roadsVisible = false;
let mountedGisStatus = null;

let globalWeapons = {};
let globalBattalions = {};
let globalRules = {};
let isDeploying = false;
let selectedUnitId = null;
let selectedUnitLon = null;
let selectedUnitLat = null;
let provincePolitics = {};
let selectedPoliticsProvince = null;
let selectedPoliticsFaction = null;
let politicsDraftNew = false;
let cityInfluenceAreas = [];
let cityLayersMap = {};
let selectedCityId = null;
let cityDraftNew = false;
let pendingAction = null;
let lastLogCount = 0;
let heartbeatInterval = null;
let committeeState = null;
let availableFactions = [];
let mapClickHandler = null;
let tacticalHudPointerActive = false;
let tacticalHudPointerReleaseFrame = null;
let stateRequestSequence = 0;
let latestAppliedStateRequest = 0;
let latestUnits = {};
let latestInstallations = {};
let selectedInstallationId = null;
let simulationPaused = true;
let saveSlotCatalog = {};
let saveLoadBusy = false;

document.addEventListener('pointerdown', event => {
    if (event.target?.closest?.('#tactical-hud')) {
        tacticalHudPointerActive = true;
        if (tacticalHudPointerReleaseFrame !== null) {
            cancelAnimationFrame(tacticalHudPointerReleaseFrame);
            tacticalHudPointerReleaseFrame = null;
        }
    }
}, true);

function releaseTacticalHudPointer() {
    if (!tacticalHudPointerActive) return;
    if (tacticalHudPointerReleaseFrame !== null) cancelAnimationFrame(tacticalHudPointerReleaseFrame);
    // Keep the lock through the click event so polling cannot replace its target
    // between pointer-up and click dispatch.
    tacticalHudPointerReleaseFrame = requestAnimationFrame(() => {
        tacticalHudPointerActive = false;
        tacticalHudPointerReleaseFrame = null;
    });
}

document.addEventListener('pointerup', releaseTacticalHudPointer, true);
document.addEventListener('pointercancel', releaseTacticalHudPointer, true);
window.addEventListener('blur', () => {
    tacticalHudPointerActive = false;
    if (tacticalHudPointerReleaseFrame !== null) cancelAnimationFrame(tacticalHudPointerReleaseFrame);
    tacticalHudPointerReleaseFrame = null;
});

function tacticalHudInteractionInProgress(container) {
    const active = document.activeElement;
    const focusedEditor = active
        && container.contains(active)
        && active.matches('select, input, textarea, button, [contenteditable="true"]');
    return tacticalHudPointerActive || Boolean(focusedEditor);
}

function releaseFocusedTacticalHudButton() {
    const active = document.activeElement;
    if (active?.matches?.('button') && active.closest?.('#tactical-hud')) active.blur();
}

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

function createLocalGridBasemap() {
    const layer = L.gridLayer({maxZoom: 18, noWrap: true, bounds: [[-90, -180], [90, 180]]});
    layer.createTile = function() {
        const tile = document.createElement('canvas');
        const size = this.getTileSize();
        tile.width = size.x;
        tile.height = size.y;
        const context = tile.getContext('2d');
        context.fillStyle = '#03070b';
        context.fillRect(0, 0, size.x, size.y);
        context.strokeStyle = 'rgba(88, 166, 255, 0.08)';
        context.lineWidth = 1;
        for (let offset = 0; offset <= size.x; offset += 64) {
            context.beginPath(); context.moveTo(offset, 0); context.lineTo(offset, size.y); context.stroke();
            context.beginPath(); context.moveTo(0, offset); context.lineTo(size.x, offset); context.stroke();
        }
        return tile;
    };
    return layer;
}

const mapLayers = leafletReady ? {
    // The default is generated locally, so missing internet access or a tile
    // vendor policy change can never replace the operational map with an error tile.
    'clean': createLocalGridBasemap(),
    'topo': L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', {
        maxZoom: 12,
        className: 'topo-basemap',
        attribution: 'Tiles &copy; Esri'
    }),
    'admin': L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        className: 'admin-basemap',
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    })
} : {};
let currentMapMode = 'clean';
const basemapFailureCounts = {topo: 0, admin: 0};

// 🟢 2. System Boot: Scan and Mount DLCs
window.onload = function() {
    if (!leafletReady) {
        document.getElementById('dlc-list-container').innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">Map library unavailable. Check the internet connection, then reload.<br><a href="/status" style="color:#58a6ff;">Open readiness check</a></div>`;
        return;
    }
    map = L.map('map', {
        zoomControl: false,
        attributionControl: false,
        doubleClickZoom: false,
        // Shift-drag box zoom looks like an unexplained order rectangle and
        // conflicts with map-based targeting, so it is deliberately disabled.
        boxZoom: false
    }).setView([0, 0], 2);
    mapLayers['clean'].addTo(map); 
    map.attributionControl = L.control.attribution({position: 'bottomleft', prefix: false}).addTo(map);
    L.control.scale({ position: 'bottomleft', metric: true, imperial: false }).addTo(map);
    ['topo', 'admin'].forEach(mode => mapLayers[mode].on('tileerror', () => {
        basemapFailureCounts[mode] += 1;
        if (currentMapMode !== mode || basemapFailureCounts[mode] < 3) return;
        switchMapMode('clean');
        const statusSpan = document.getElementById('pause-status');
        if (statusSpan) statusSpan.title = `${mode.toUpperCase()} basemap unavailable; local Clean fallback is active.`;
    }));
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
    Object.values(window.installationMarkersMap).forEach(record => {
        map.removeLayer(record.marker);
        if (record.circle) map.removeLayer(record.circle);
    });
    Object.values(cityLayersMap).forEach(layer => map.removeLayer(layer));
    cityLayersMap = {};
    cityInfluenceAreas = [];
    selectedCityId = null;
    cityDraftNew = false;
    provincePolitics = {};
    selectedPoliticsProvince = null;
    selectedPoliticsFaction = null;
    politicsDraftNew = false;
    window.unitMarkersMap = {};
    window.installationMarkersMap = {};
    geojsonLayer = roadLayer = pathLine = draftLine = null;
    selectedUnitId = null;
    selectedInstallationId = null;
    latestInstallations = {};
    committeeState = null;
    roadsVisible = false;
    const roadsButton = document.getElementById('btn-toggle-roads');
    if (roadsButton) {
        roadsButton.classList.remove('active');
        roadsButton.style.borderColor = '';
        roadsButton.style.color = '';
    }
    mountedGisStatus = null;
    const gisPanel = document.getElementById('gis-status-panel');
    if (gisPanel) gisPanel.style.display = 'none';
    if (currentMapMode !== 'clean') switchMapMode('clean');
}

function gisFeatureText(feature, fallbackElevation) {
    const copy = currentLang === 'zh'
        ? {
            terrain_dem: {
                label: '地形高程 DEM',
                on: '已安装高程数据；地形成本与视线使用真实高程。',
                off: `默认：平坦地形 ${fallbackElevation} 米，视线不受高程阻挡。`
            },
            roads: {
                label: '道路网络',
                on: '已安装道路数据；寻路和移动成本会考虑道路。',
                off: '默认：所有位置使用基础地形移动成本。'
            },
            rivers: {
                label: '河流网络',
                on: '已安装河流数据；寻路会计算渡河惩罚。',
                off: '默认：不施加渡河惩罚。'
            },
            provinces: {
                label: '省份边界',
                on: '已安装省份边界；启用位置名称与政治着色。',
                off: '默认：位置显示为未知/未测绘，不显示省界政治着色。'
            }
        }
        : {
            terrain_dem: {
                label: 'Terrain elevation DEM',
                on: 'Installed elevation drives terrain cost and line of sight.',
                off: `Default: flat terrain at ${fallbackElevation} m with unobstructed elevation-based line of sight.`
            },
            roads: {
                label: 'Road network',
                on: 'Installed roads affect route finding and movement cost.',
                off: 'Default: base terrain movement cost is used everywhere.'
            },
            rivers: {
                label: 'River network',
                on: 'Installed rivers apply crossing penalties during route finding.',
                off: 'Default: no river-crossing penalty is applied.'
            },
            provinces: {
                label: 'Province boundaries',
                on: 'Installed boundaries enable location names and political shading.',
                off: 'Default: locations are Unknown/Unmapped and boundary shading is off.'
            }
        };
    const selected = copy[feature.id] || {label: feature.label, on: feature.detail, off: feature.detail};
    return {label: selected.label, detail: feature.enabled ? selected.on : selected.off};
}

function renderGisStatus(status) {
    mountedGisStatus = status || {enabled_count: 0, features: []};
    const panel = document.getElementById('gis-status-panel');
    const list = document.getElementById('gis-status-list');
    const summary = document.getElementById('gis-status-summary');
    if (!panel || !list || !summary) return;

    const features = mountedGisStatus.features || [];
    summary.textContent = `${mountedGisStatus.enabled_count || 0}/${features.length} ON`;
    list.replaceChildren();
    for (const feature of features) {
        const text = gisFeatureText(feature, mountedGisStatus.fallback_elevation_m ?? 0);
        const row = document.createElement('div');
        row.className = `gis-feature-row${feature.enabled ? '' : ' off'}${feature.configured && !feature.enabled ? ' warning' : ''}`;
        row.title = feature.warning || feature.detail || text.detail;

        const heading = document.createElement('div');
        heading.className = 'gis-feature-heading';
        const label = document.createElement('span');
        label.textContent = text.label;
        const badge = document.createElement('span');
        badge.className = 'gis-feature-badge';
        badge.textContent = feature.enabled ? 'ON' : 'OFF · DEFAULT';
        heading.append(label, badge);

        const detail = document.createElement('div');
        detail.className = 'gis-feature-detail';
        detail.textContent = text.detail;
        row.append(heading, detail);
        list.appendChild(row);
    }
    panel.style.display = 'block';

    const roads = features.find(feature => feature.id === 'roads');
    const roadsButton = document.getElementById('btn-toggle-roads');
    if (roadsButton && roads) {
        roadsButton.disabled = !roads.enabled;
        roadsButton.title = roads.enabled
            ? (currentLang === 'zh' ? '显示或隐藏已安装的道路网络。' : 'Show or hide the installed road network.')
            : (currentLang === 'zh' ? '未安装可用道路数据；系统使用基础移动成本。' : 'No usable road data is installed; base movement costs are active.');
        roadsButton.textContent = roads.enabled
            ? (currentLang === 'zh' ? '🛣️ 路网' : '🛣️ Roads')
            : (currentLang === 'zh' ? '🛣️ 路网 OFF' : '🛣️ Roads OFF');
    }
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
        renderGisStatus(res.config.gis);
        map.setView([res.config.center[0], res.config.center[1]], res.config.zoom);
        document.title = "CDC Command Radar - " + res.config.name;

        const [registry, geojson] = await Promise.all([fetchJson('/api/registry'), fetchJson('/geojson')]);
        globalWeapons = registry.weapons;
        globalBattalions = registry.battalions;
        globalRules = registry.rules;
        updateRuleDrivenUI();
        updateDeployUI();
        if (geojson.type === 'FeatureCollection' && geojson.features?.length) {
            geojsonLayer = L.geoJSON(geojson, {
                style: styleProvince,
                onEachFeature: (feature, layer) => layer.bindTooltip(provincePoliticsTooltip(feature.properties?.cdc_name || 'Unknown'))
            }).addTo(map);
        }

        document.getElementById('bootloader-screen').style.display = 'none';
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
    if (speedInput) {
        speedInput.min = clock.speed_multiplier_min;
        speedInput.max = clock.speed_multiplier_max;
        speedInput.value = clock.default_time_multiplier;
    }
    const defaultSpeedButton = document.getElementById('speed-default-button');
    const maximumSpeedButton = document.getElementById('speed-maximum-button');
    if (defaultSpeedButton) defaultSpeedButton.textContent = `${clock.default_time_multiplier}X`;
    if (maximumSpeedButton) maximumSpeedButton.textContent = `${clock.speed_multiplier_max}X MAX`;

    const modifierRules = globalRules.modifiers;
    const modifierSelect = document.getElementById('admin-mod-type');
    if (modifierSelect) {
        modifierSelect.replaceChildren();
        for (const type of modifierRules.allowed_types) {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = zeusModifierLabel(type);
            modifierSelect.appendChild(option);
        }
    }
    const modifierValue = document.getElementById('admin-mod-val');
    if (modifierValue) {
        modifierValue.min = modifierRules.value_minimum;
        modifierValue.max = modifierRules.value_maximum;
        modifierValue.value = modifierRules.default_value;
    }
    const modifierDuration = document.getElementById('admin-mod-dur');
    if (modifierDuration) {
        modifierDuration.min = modifierRules.duration_minimum_hours;
        modifierDuration.max = modifierRules.duration_maximum_hours;
        modifierDuration.value = modifierRules.default_duration_hours;
    }
    updateZeusModifierHelp();

    const directiveRules = globalRules.directives;
    const effectSelect = document.getElementById('committee-effect');
    if (effectSelect) {
        effectSelect.replaceChildren();
        for (const effect of directiveRules.allowed_effects) {
            const option = document.createElement('option');
            option.value = effect;
            option.textContent = effect === 'none' ? 'No mechanical effect' : effect.replaceAll('_', ' ');
            effectSelect.appendChild(option);
        }
    }
    const committeeFaction = document.getElementById('committee-faction');
    const committeeDuration = document.getElementById('committee-duration');
    if (committeeFaction) committeeFaction.value = directiveRules.default_faction;
    if (committeeDuration) committeeDuration.value = directiveRules.default_duration_hours;
}

function updateDeployUI() {
    const typeSelect = document.getElementById('dep-unit-type');
    if (typeSelect) {
        typeSelect.replaceChildren();
        for (const [typeId, profile] of Object.entries(globalRules.unit_types || {})) {
            const option = document.createElement('option');
            option.value = typeId;
            option.textContent = `${profile.icon || '◆'} ${profile.label || typeId}`;
            option.selected = typeId === globalRules.unit_defaults.unit_type;
            typeSelect.appendChild(option);
        }
    }
    const aircraftTypeSelect = document.getElementById('dep-aircraft-type');
    if (aircraftTypeSelect) {
        aircraftTypeSelect.replaceChildren();
        const airstrikeRules = globalRules.missions?.airstrike || {};
        for (const [typeId, profile] of Object.entries(airstrikeRules.aircraft_types || {})) {
            const option = document.createElement('option');
            option.value = typeId;
            option.textContent = profile.label || typeId;
            option.selected = typeId === airstrikeRules.default_aircraft_type;
            aircraftTypeSelect.appendChild(option);
        }
    }
    updateDeployUnitTypeHelp();

    const cGrid = document.getElementById('dep-comp-grid');
    if (cGrid) {
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
    }
    const firstBattalion = Object.keys(globalBattalions)[0];
    if (firstBattalion && document.getElementById(`dep-${firstBattalion}`)) {
        document.getElementById(`dep-${firstBattalion}`).value = 1;
    }
    const factionInput = document.getElementById('dep-faction');
    if (factionInput) factionInput.value = availableFactions[0] || '';
    calcDeployStats();
}

function updateDeployUnitTypeHelp(resetComposition = false) {
    const typeId = document.getElementById('dep-unit-type')?.value;
    const profile = globalRules.unit_types?.[typeId];
    const help = document.getElementById('dep-unit-type-help');
    if (!help || !profile) return;
    const capabilities = Array.isArray(profile.capabilities) && profile.capabilities.length
        ? profile.capabilities.join(', ')
        : 'none';
    help.textContent = `Role: ${profile.label || typeId} · Built-in capabilities: ${capabilities}`;
    const aircraftGroup = document.getElementById('dep-aircraft-type-group');
    const airstrikeCapability = globalRules.missions?.airstrike?.capability;
    const canAirstrike = Array.isArray(profile.capabilities) && profile.capabilities.includes(airstrikeCapability);
    if (aircraftGroup) aircraftGroup.style.display = canAirstrike ? 'block' : 'none';
    if (resetComposition) {
        const bombardCapability = globalRules.missions?.bombard?.capability;
        const requiredRole = canAirstrike
            ? 'airstrike'
            : (Array.isArray(profile.capabilities) && profile.capabilities.includes(bombardCapability)
                ? 'bombard'
                : 'direct_fire');
        const compatibleBattalion = Object.entries(globalBattalions).find(([, battalion]) =>
            Object.keys(battalion.weapons || {}).some(weaponId =>
                (globalWeapons[weaponId]?.roles || []).includes(requiredRole)
            )
        )?.[0];
        if (compatibleBattalion) {
            for (const battalionId of Object.keys(globalBattalions)) {
                const input = document.getElementById(`dep-${battalionId}`);
                if (input) input.value = battalionId === compatibleBattalion ? '1' : '0';
            }
            calcDeployStats();
        }
    }
    updateDeployAircraftTypeHelp();
}

function updateDeployAircraftTypeHelp() {
    const typeId = document.getElementById('dep-aircraft-type')?.value;
    const profile = globalRules.missions?.airstrike?.aircraft_types?.[typeId];
    const help = document.getElementById('dep-aircraft-type-help');
    if (!help || !profile) return;
    const baseRules = globalRules.missions.airstrike;
    const unitTypeId = document.getElementById('dep-unit-type')?.value;
    const baseSpeed = Number(globalRules.unit_types?.[unitTypeId]?.fixed_stats?.speed_kmh || 0);
    const cruiseSpeed = baseSpeed * Number(profile.cruise_speed_multiplier);
    const range = Number(baseRules.sortie_range_km) * Number(profile.sortie_range_multiplier);
    const radius = Number(baseRules.blast_radius_km) * Number(profile.blast_radius_multiplier);
    help.textContent = `${profile.attack_profile}: ${profile.description} Cruise ${cruiseSpeed.toFixed(0)} km/h · range ${range.toFixed(0)} km · effect radius ${radius.toFixed(1)} km.`;
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
    const roadFeature = mountedGisStatus?.features?.find(feature => feature.id === 'roads');
    if (!roadFeature?.enabled) return;
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
        clearDraft();
        panel.style.display = 'block';
        panel.setAttribute('aria-hidden', 'false');
        calcDeployStats();
    } else {
        panel.style.display = 'none';
        panel.setAttribute('aria-hidden', 'true');
        isDeploying = false;
        document.getElementById('targeting-alert').style.display = 'none';
    }
}

function calcDeployStats() {
    let totalPop = 0;
    const weaponTotals = {};
    for (const key of Object.keys(globalBattalions)) {
        const input = document.getElementById(`dep-${key}`);
        if (input) {
            const battalionCount = parseInt(input.value) || 0;
            totalPop += battalionCount * (Number(input.dataset.size) || 0);
            for (const [weaponId, quantity] of Object.entries(globalBattalions[key]?.weapons || {})) {
                weaponTotals[weaponId] = (weaponTotals[weaponId] || 0) + battalionCount * Number(quantity || 0);
            }
        }
    }
    document.getElementById('dep-pop-display').innerText = totalPop + " Personnel";
    document.getElementById('dep-personnel').value = totalPop;
    const weaponDisplay = document.getElementById('dep-weapons-display');
    if (weaponDisplay) {
        const descriptions = Object.entries(weaponTotals)
            .filter(([, quantity]) => quantity > 0)
            .map(([weaponId, quantity]) => {
                const weapon = globalWeapons[weaponId] || {};
                const bands = Array.isArray(weapon.range_bands) ? weapon.range_bands : [];
                const maximumRange = bands.length ? Number(bands[bands.length - 1].max_range_km || 0) : 0;
                return `${quantity.toFixed(Number.isInteger(quantity) ? 0 : 2)}× ${weapon.name || weaponId} · Gen ${Number(weapon.generation || 0)} · ${maximumRange.toFixed(1)} km`;
            });
        weaponDisplay.textContent = descriptions.length
            ? descriptions.join(' | ')
            : 'No weapon groups are mounted by the selected battalions.';
    }
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

function canonicalTargetingAction(actionStr) {
    // `move` was the original internal name. Keep callers compatible while
    // presenting and transmitting one clear command: Relocate.
    return actionStr === 'move' ? 'relocate' : actionStr;
}

function orderRoleForTargetingAction(actionStr) {
    const action = canonicalTargetingAction(actionStr);
    return action === 'attack' ? 'assault' : action;
}

function positionConfirmationPanel() {
    const panel = document.getElementById('confirmation-panel');
    if (!panel || panel.style.display !== 'block') return;

    const viewportWidth = document.documentElement.clientWidth;
    const viewportHeight = document.documentElement.clientHeight;
    const gap = 12;
    const clockRect = document.getElementById('clock-panel')?.getBoundingClientRect();
    const hudRect = document.getElementById('tactical-hud')?.getBoundingClientRect();
    const intelRect = document.getElementById('intel-feed')?.getBoundingClientRect();
    const panelWidth = panel.getBoundingClientRect().width;

    // Prefer the open map area directly beside the unit controls. On narrow
    // screens the card moves in front, where its higher z-index keeps it usable.
    const preferredLeft = (hudRect?.left ?? viewportWidth) - panelWidth - gap;
    const fallbackLeft = Math.max(gap, (viewportWidth - panelWidth) / 2);
    const left = preferredLeft >= gap ? preferredLeft : fallbackLeft;
    const top = Math.max(gap, (clockRect?.bottom ?? 0) + gap);
    const bottomLimit = Math.min(viewportHeight - gap, (intelRect?.top ?? viewportHeight) - gap);

    panel.style.left = `${Math.round(left)}px`;
    panel.style.right = 'auto';
    panel.style.top = `${Math.round(top)}px`;
    panel.style.bottom = 'auto';
    panel.style.maxHeight = `${Math.max(150, Math.floor(bottomLimit - top))}px`;
}

function showConfirmationPanel(action, profile) {
    const panel = document.getElementById('confirmation-panel');
    const title = document.getElementById('draft-confirmation-title');
    const instruction = document.getElementById('draft-instruction');
    if (!panel) return;

    const aircraft = action === 'airstrike' ? airstrikePerformance(latestUnits[selectedUnitId]) : null;
    const actionLabel = aircraft ? `Airstrike — ${aircraft.label}` : (profile?.label || String(action).toUpperCase());
    if (title) {
        title.textContent = currentLang === 'zh'
            ? `⚠️ 授权${actionLabel}`
            : `⚠️ AUTHORIZE ${actionLabel.toUpperCase()}`;
    }
    if (instruction) {
        const instructions = currentLang === 'zh'
            ? {
                relocate: '确认下方单一目的地。转移任务不会主动发起远程交火；已侦测敌军威胁剩余路线时，系统会保留目的地并自动规划避敌路径。',
                route: '继续点击地图可添加航点；完成后再授权。',
                attack: '确认突击目的地；部队会在远程火力接触中继续接近，只在已侦测敌军形成近距离地面阻挡时停止。',
                bombard: `确认坐标后开始持续 ${Number(globalRules.missions?.bombard?.duration_hours || 0).toFixed(1)} 小时的区域炮击。原移动路线会被取消；未发现部队仍可能以较低精度受击。`,
                airstrike: `确认 ${aircraft?.label || '飞机'} 的目标坐标。陆军、炮兵和停在基地的空军可受打击；正在出击或返航的飞机不属于对地目标。起飞时结算 ${Number(aircraft?.supply_cost || 0).toFixed(1)}% 补给与 ${Number(aircraft?.fatigue_cost || 0).toFixed(1)}% 疲劳；飞机会按该机型的防空易损性承受威胁并在投弹后返航。`
            }
            : {
                relocate: 'Confirm the single destination below. Relocate withholds initiating ranged fire and preserves the destination while rerouting around detected threats to the remaining path.',
                route: 'Keep clicking the map to add waypoints, then authorize the complete route.',
                attack: 'Confirm the assault destination. The unit keeps closing through ranged fire and stops only when a detected hostile blocks it at close ground contact.',
                bombard: `Confirm coordinates for a ${Number(globalRules.missions?.bombard?.duration_hours || 0).toFixed(1)}-hour area bombardment. The old movement route is cancelled; unobserved formations can still be hit at reduced accuracy.`,
                airstrike: `Confirm coordinates for the ${aircraft?.label || 'aircraft'}. Armies, artillery, and air wings parked at base are valid ground targets; outbound or returning aircraft are not. ${Number(aircraft?.supply_cost || 0).toFixed(1)}% supply and ${Number(aircraft?.fatigue_cost || 0).toFixed(1)}% fatigue are committed at takeoff; profile-specific air-defense exposure applies until it returns.`
            };
        instruction.textContent = instructions[action] || (currentLang === 'zh' ? '确认目标后再授权。' : 'Confirm the target before authorization.');
    }

    panel.style.display = 'block';
    positionConfirmationPanel();
    requestAnimationFrame(positionConfirmationPanel);
}

window.addEventListener('resize', positionConfirmationPanel);

function setTargetingMode(actionStr) {
    releaseFocusedTacticalHudButton();
    const action = canonicalTargetingAction(actionStr);
    clearDraft();
    pendingAction = action;
    document.getElementById('map')?.classList.add('targeting-mode');
    const selectedUnit = latestUnits[selectedUnitId];
    if (selectedUnit && ['bombard', 'airstrike'].includes(action)) {
        const rangeKm = action === 'bombard'
            ? Number(selectedUnit.bombard_range || 0)
            : Number(airstrikePerformance(selectedUnit).sortie_range_km || 0);
        const color = action === 'bombard' ? '#f85149' : '#e3b341';
        if (rangeKm > 0) {
            draftRangeCircle = L.circle([selectedUnit.lat, selectedUnit.lon], {
                radius: rangeKm * 1000,
                color,
                fillColor: color,
                fillOpacity: 0.025,
                opacity: 0.55,
                weight: 1,
                dashArray: '7,6',
                interactive: false
            }).addTo(map);
        }
    }
    const role = orderRoleForTargetingAction(action);
    const profile = orderProfileByRole(role);
    const routeHint = action === 'route' ? ' Click once for each waypoint, then authorize.' : ' Click the destination, review, then authorize.';
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
                unit_type: document.getElementById('dep-unit-type')?.value || globalRules.unit_defaults.unit_type,
                stance: globalRules.unit_defaults.stance,
                composition: dynamicComp
            };
            const selectedType = globalRules.unit_types?.[data.unit_type];
            if (selectedType?.capabilities?.includes(globalRules.missions?.airstrike?.capability)) {
                data.aircraft_type = document.getElementById('dep-aircraft-type')?.value
                    || globalRules.missions.airstrike.default_aircraft_type;
            }
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

        // Selecting a unit does not silently create a generic Move order.
        // A destination is accepted only after an explicit task button is used.
        if (!selectedUnitId || !pendingAction) return;

        const tLat = e.latlng.lat; const tLon = e.latlng.lng;
        
        if (pendingAction === 'route') draftedWaypoints.push({lon: tLon, lat: tLat});
        else draftedWaypoints = [{lon: tLon, lat: tLat}]; 
        
        draftMarkers.forEach(m => map.removeLayer(m)); draftMarkers = [];
        if (draftLine) map.removeLayer(draftLine);
        if (draftImpactCircle) map.removeLayer(draftImpactCircle);

        const latlngs = [[selectedUnitLat, selectedUnitLon]];
        const iconHtml = pendingAction === 'attack'
            ? '🎯'
            : (pendingAction === 'bombard' ? '💥' : (pendingAction === 'airstrike' ? '✈️' : '📍'));
        const draftRole = orderRoleForTargetingAction(pendingAction);
        const lineColor = pendingAction === 'bombard' ? '#f85149' : (pendingAction === 'airstrike' ? '#e3b341' : orderProfileByRole(draftRole).color);

        draftedWaypoints.forEach((wp, index) => {
            latlngs.push([wp.lat, wp.lon]);
            let htmlText = pendingAction === 'route' ? `<div style="color:${lineColor}; background:rgba(0,0,0,0.7); border:1px solid ${lineColor}; border-radius:50%; width:16px; height:16px; line-height:16px; text-align:center; font-size:10px;">${index+1}</div>` : `<span style="color:${lineColor}; text-shadow:0 0 5px #000;">${iconHtml}</span>`;
            const m = L.marker([wp.lat, wp.lon], {icon: L.divIcon({className: 'mil-icon', html: htmlText, iconSize: [20,20], iconAnchor: [10,10]})}).addTo(map);
            draftMarkers.push(m);
        });

        draftLine = L.polyline(latlngs, {color: lineColor, dashArray: '5,5', weight: 2}).addTo(map);

        const draftProfile = orderProfileByRole(draftRole);
        const selectedUnit = latestUnits[selectedUnitId] || {};
        const targetDistance = mapDistanceKm(selectedUnitLon, selectedUnitLat, tLon, tLat);
        const missionRules = globalRules.missions?.[pendingAction];
        const missionPerformance = pendingAction === 'airstrike'
            ? airstrikePerformance(selectedUnit)
            : missionRules;
        const isSupportMission = ['bombard', 'airstrike'].includes(pendingAction);
        const maximumRange = pendingAction === 'bombard'
            ? Number(selectedUnit.bombard_range || 0)
            : Number(missionPerformance?.sortie_range_km || 0);
        const blastRadius = Number(missionPerformance?.blast_radius_km || 0);
        const outOfRange = isSupportMission && maximumRange > 0 && targetDistance > maximumRange;
        const authorizeButton = document.getElementById('draft-authorize-button');
        if (authorizeButton) {
            authorizeButton.disabled = outOfRange;
            authorizeButton.title = outOfRange ? `Target is ${targetDistance.toFixed(1)} km away; maximum range is ${maximumRange.toFixed(1)} km.` : '';
        }
        if (isSupportMission && blastRadius > 0) {
            draftImpactCircle = L.circle([tLat, tLon], {
                radius: blastRadius * 1000,
                color: lineColor,
                fillColor: lineColor,
                fillOpacity: 0.12,
                opacity: 0.9,
                weight: 1.5,
                interactive: false
            }).addTo(map);
        }

        let typeStr = pendingAction === 'route'
            ? `${draftProfile.label.toUpperCase()} (${draftedWaypoints.length} waypoint${draftedWaypoints.length === 1 ? '' : 's'}): ${draftProfile.description}`
            : (pendingAction === 'bombard'
                ? `BOMBARD AREA (${Number(missionRules?.duration_hours || 0).toFixed(1)} h)`
                : (pendingAction === 'airstrike'
                    ? `${String(missionPerformance?.label || 'AIRSTRIKE').toUpperCase()} SORTIE`
                    : `${draftProfile.label.toUpperCase()}: ${draftProfile.description}`));
        document.getElementById('draft-type').innerText = typeStr;
        let coordsText = pendingAction === 'route' ? `DEST LON: ${tLon.toFixed(4)} | LAT: ${tLat.toFixed(4)}` : `LON: ${tLon.toFixed(4)} | LAT: ${tLat.toFixed(4)}`;
        const missionAssessment = isSupportMission
            ? `<br><span class="mission-target-${outOfRange ? 'invalid' : 'valid'}">Distance ${targetDistance.toFixed(1)} / ${maximumRange.toFixed(1)} km · Effect radius ${blastRadius.toFixed(1)} km${outOfRange ? ' · OUT OF RANGE' : ''}</span>`
            : '';
        const coordinateSummary = `${coordsText}${missionAssessment}`;
        document.getElementById('draft-coords').innerHTML = `${coordinateSummary}<br><span style="color:#e3b341; font-size:12px;">Scanning destination topography...</span>`;
        showConfirmationPanel(pendingAction, draftProfile);

        const requestedAction = pendingAction;
        const isCurrentTarget = () => {
            const currentTarget = draftedWaypoints[draftedWaypoints.length - 1];
            return pendingAction === requestedAction
                && currentTarget
                && currentTarget.lon === tLon
                && currentTarget.lat === tLat;
        };
        try {
            const res = await fetchJson(`/api/terrain?lon=${encodeURIComponent(tLon)}&lat=${encodeURIComponent(tLat)}`);
            if (!isCurrentTarget()) return;
            document.getElementById('draft-coords').innerHTML = `${coordinateSummary}<br><span style="color:#8b949e; font-size:12px;">Dest. Topography: ${res.complexity > 0.6 ? '🏔️ Mountains' : (res.complexity > 0.3 ? '⛰️ Hills' : '🛣️ Plains')} (Drag: ${res.complexity})</span>`;
        } catch (error) {
            if (!isCurrentTarget()) return;
            document.getElementById('draft-coords').innerHTML = `${coordinateSummary}<br><span style="color:#ff7b72; font-size:12px;">Terrain unavailable: ${escapeHtml(error.message)}</span>`;
        }
    };
    map.on('click', mapClickHandler);
}

async function executeDraftedCommand() {
    const authorizeButton = document.getElementById('draft-authorize-button');
    if (!selectedUnitId || draftedWaypoints.length === 0 || authorizeButton?.disabled) return;
    const payload = { command: `${pendingAction} ${selectedUnitId} ${draftedWaypoints[0].lon} ${draftedWaypoints[0].lat}`, waypoints: draftedWaypoints };
    try {
        const result = await fetchJson('/api/command', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
        clearDraft();
        await fetchState();
        if (result.queued) {
            const statusSpan = document.getElementById('pause-status');
            if (statusSpan) statusSpan.title = result.msg;
        }
    } catch (error) {
        alert("Command rejected: " + error.message);
    }
}

function clearDraft() {
    if (draftLine) map.removeLayer(draftLine);
    if (draftImpactCircle) map.removeLayer(draftImpactCircle);
    if (draftRangeCircle) map.removeLayer(draftRangeCircle);
    if (draftMarkers) draftMarkers.forEach(m => map.removeLayer(m));
    draftLine = null; draftImpactCircle = null; draftRangeCircle = null;
    draftMarkers = []; draftedWaypoints = []; pendingAction = null;
    document.getElementById('map')?.classList.remove('targeting-mode');
    document.getElementById('confirmation-panel').style.display = "none"; document.getElementById('targeting-alert').style.display = "none";
    const authorizeButton = document.getElementById('draft-authorize-button');
    if (authorizeButton) { authorizeButton.disabled = false; authorizeButton.title = ''; }
}

async function sendCommand(cmdStr) {
    releaseFocusedTacticalHudButton();
    try {
        const result = await fetchJson('/api/command', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({command: cmdStr}) });
        fetchState();
        return result;
    } catch (error) {
        alert(`Command rejected: ${error.message}`);
        return null;
    }
}

function deselectUnit() {
    selectedUnitId = null;
    selectedInstallationId = null;
    selectedUnitLon = null;
    selectedUnitLat = null;
    clearDraft();
    if (pathLine) {
        map.removeLayer(pathLine);
        pathLine = null;
    }
    document.getElementById('unit-info').innerHTML = `<div style="color: #8b949e; font-style: italic; text-align: center; padding: 30px 0;">[ RADAR SCANNING ]<br>Awaiting Commander to select a unit or military target...</div>`;
    fetchState();
}

function provincePoliticalAppearance(provinceName) {
    const state = provincePolitics[provinceName];
    if (!state) return {color: 'transparent', opacity: 0};
    if (state.contested) return {color: '#e3b341', opacity: 0.38};
    if (state.controller && state.factions?.[state.controller]) {
        const occupation = Number(state.factions[state.controller].occupation) || 0;
        return {color: getFactionColor(state.controller), opacity: 0.14 + occupation * 0.3};
    }
    const leading = Object.entries(state.factions || {})
        .sort((a, b) => Number(b[1].influence || 0) - Number(a[1].influence || 0))[0];
    if (leading && Number(leading[1].influence) > 0) {
        return {color: getFactionColor(leading[0]), opacity: Math.min(0.22, Number(leading[1].influence) * 0.18)};
    }
    return {color: 'transparent', opacity: 0};
}

function styleProvince(feature) {
    const provName = feature.properties?.cdc_name || 'Unknown';
    const appearance = provincePoliticalAppearance(provName);
    return { fillColor: appearance.color, weight: 1, opacity: 0.3, color: '#1f6feb', fillOpacity: appearance.opacity };
}

function provincePoliticsTooltip(provinceName) {
    const state = provincePolitics[provinceName];
    if (!state) return `<b>${escapeHtml(provinceName)}</b><br>Neutral / no political record`;
    const status = state.contested ? 'CONTESTED' : (state.controller ? `Controlled by ${state.controller}` : 'No established control');
    const rows = Object.entries(state.factions || {}).map(([faction, record]) => {
        const presence = Math.round(Number(record.military_presence || 0) * 100);
        const strength = Math.round(Number(record.force_strength || 0) * 100);
        return `${escapeHtml(faction)}: presence ${presence}% (force ${strength}%), sentiment ${Number(record.civilian_sentiment).toFixed(2)}, occupation ${Number(record.occupation).toFixed(2)}, influence ${Number(record.influence).toFixed(2)}`;
    }).join('<br>');
    return `<b>${escapeHtml(provinceName)}</b> · ${escapeHtml(status)}${rows ? `<br>${rows}` : ''}`;
}

function updateProvincePoliticalLayers() {
    if (!geojsonLayer) return;
    geojsonLayer.setStyle(styleProvince);
    geojsonLayer.eachLayer(layer => {
        const provinceName = layer.feature?.properties?.cdc_name || 'Unknown';
        layer.unbindTooltip().bindTooltip(provincePoliticsTooltip(provinceName), {sticky: true});
    });
}

function getUnitIcon(u) {
    // 🟢 优先级 1：如果部队拥有自定义图标，强制使用自定义图标
    if (u.icon && u.icon.trim() !== "") {
        return u.icon;
    }
    
    return globalRules.unit_types?.[u.unit_type]?.icon || "◆";
}    

function fetchState() {
    const requestSequence = ++stateRequestSequence;
    return fetchJson('/api/state').then(data => {
        if (requestSequence < latestAppliedStateRequest) return;
        latestAppliedStateRequest = requestSequence;
        if(data.status === "unmounted") return;
        latestUnits = data.units || {};
        latestInstallations = data.installations || {};
        simulationPaused = Boolean(data.time.paused);
        const pad = (n) => (n||0).toString().padStart(2, '0');
        document.getElementById('time-display').innerText = `D${pad(data.time.day)} ${pad(data.time.hour)}:${pad(data.time.minute)}:${pad(data.time.second)}`;
        const statusSpan = document.getElementById('pause-status');
        if (data.time.paused) { statusSpan.innerText = '[ PAUSED ]'; statusSpan.style.color = '#ff7b72'; } 
        else { statusSpan.innerText = `[ RUNNING ${data.time.multiplier}X ]`; statusSpan.style.color = '#7ee787'; }

        provincePolitics = data.province_politics || {};
        updateProvincePoliticalLayers();
        refreshChairPoliticsEditor();
        cityInfluenceAreas = data.cities || [];
        refreshCityLayers(cityInfluenceAreas);
        refreshChairCityEditor();

        updateIntelFeed(data.latest_logs);
        refreshUnitsSmoothly(latestUnits);
        refreshInstallationsSmoothly(latestInstallations);

        if (selectedUnitId && data.units[selectedUnitId]) {
            const u = data.units[selectedUnitId]; selectedUnitLon = u.lon; selectedUnitLat = u.lat; updateTacticalHUD(u);
            if (pathLine) map.removeLayer(pathLine);
            if (u.waypoints && u.waypoints.length > 0) {
                const latlngs = u.waypoints.map(wp => [wp[1], wp[0]]); latlngs.unshift([u.lat, u.lon]); 
                pathLine = L.polyline(latlngs, { color: orderProfileForUnit(u).color, dashArray: '5,5', weight: 2, opacity: 0.8 }).addTo(map);
            }
        } else if (selectedUnitId) {
            selectedUnitId = null;
            clearDraft();
            document.getElementById('unit-info').innerHTML = `<div style="color: #ff7b72; font-weight: bold; text-align: center; padding: 30px 0;">[ SIGNAL LOST ]</div>`;
            if (pathLine) {
                map.removeLayer(pathLine);
                pathLine = null;
            }
        } else if (selectedInstallationId && latestInstallations[selectedInstallationId]) {
            updateInstallationHUD(latestInstallations[selectedInstallationId]);
            if (pathLine) {
                map.removeLayer(pathLine);
                pathLine = null;
            }
        } else if (selectedInstallationId) {
            selectedInstallationId = null;
            document.getElementById('unit-info').innerHTML = `<div style="color: #ff7b72; font-weight: bold; text-align: center; padding: 30px 0;">[ MILITARY TARGET RECORD LOST ]</div>`;
        }
        updateZeusTarget(selectedUnitId ? data.units[selectedUnitId] : null);
    }).catch(error => {
        if (requestSequence < latestAppliedStateRequest) return;
        const statusSpan = document.getElementById('pause-status');
        if (statusSpan) {
            statusSpan.innerText = '[ CONNECTION LOST ]';
            statusSpan.style.color = '#ff7b72';
            statusSpan.title = error.message;
        }
    });
}

function refreshCityLayers(cities) {
    const currentIds = new Set(cities.map(city => city.id));
    for (const [cityId, layer] of Object.entries(cityLayersMap)) {
        if (!currentIds.has(cityId)) {
            map.removeLayer(layer);
            delete cityLayersMap[cityId];
        }
    }
    for (const city of cities) {
        const rate = Math.max(0, Math.min(1, Number(city.influence_rate) || 0));
        const style = {
            color: rate > 0 ? '#d2a8ff' : '#8b949e',
            fillColor: '#d2a8ff',
            fillOpacity: rate * 0.13,
            opacity: rate > 0 ? 0.75 : 0.35,
            weight: 1.5,
            dashArray: '5,5',
            interactive: false,
            radius: Math.max(0, Number(city.radius_km) || 0) * 1000
        };
        const tooltip = `${escapeHtml(city.name)} · ${Number(city.area_km2).toFixed(1)} km² · influence ${rate.toFixed(2)}`;
        if (cityLayersMap[city.id]) {
            cityLayersMap[city.id].setLatLng([Number(city.lat), Number(city.lon)]);
            cityLayersMap[city.id].setRadius(style.radius);
            cityLayersMap[city.id].setStyle(style);
            cityLayersMap[city.id].unbindTooltip().bindTooltip(tooltip, {sticky: true});
        } else {
            cityLayersMap[city.id] = L.circle([Number(city.lat), Number(city.lon)], style)
                .bindTooltip(tooltip, {sticky: true})
                .addTo(map);
        }
    }
}

function refreshUnitsSmoothly(unitsData) {
    const currentIds = new Set(Object.keys(unitsData));
    for (const uid in window.unitMarkersMap) {
        if (!currentIds.has(uid) || (unitsData[uid] && Number(unitsData[uid].personnel) <= 0)) {
            map.removeLayer(window.unitMarkersMap[uid].marker); if (window.unitMarkersMap[uid].circle) map.removeLayer(window.unitMarkersMap[uid].circle); delete window.unitMarkersMap[uid];
        }
    }
    
    for (const [uid, u] of Object.entries(unitsData)) {
        if (Number(u.personnel) <= 0) continue;
        
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
            marker.on('click', (e) => {
                L.DomEvent.stopPropagation(e);
                selectedInstallationId = null;
                selectedUnitId = uid;
                selectedUnitLon = u.lon;
                selectedUnitLat = u.lat;
                clearDraft();
                document.getElementById('targeting-alert').style.display = "none";
                fetchState();
            });
            window.unitMarkersMap[uid] = { marker: marker, circle: circle, lastStance: u.stance, wasSelected: isSelected };
        }
    }
}

function installationTooltip(site) {
    const integrity = Math.max(0, Number(site.integrity || 0));
    const maximum = Math.max(1, Number(site.max_integrity || 1));
    const progress = Math.max(0, Math.min(100, Number(site.construction_progress || 0) * 100));
    const condition = site.status === 'UNDER_CONSTRUCTION'
        ? `${progress.toFixed(0)}% built`
        : `${(integrity / maximum * 100).toFixed(0)}% integrity`;
    return `<b>${escapeHtml(site.name)}</b><br>${escapeHtml(site.type_label)} · ${escapeHtml(site.faction)}<br>${escapeHtml(site.status.replaceAll('_', ' '))} · ${condition}`;
}

function installationIcon(site, selected) {
    const factionColor = getFactionColor(site.faction);
    const statusClass = site.status === 'DESTROYED'
        ? ' destroyed'
        : (site.status === 'UNDER_CONSTRUCTION' ? ' constructing' : '');
    const progress = Math.max(0, Math.min(100, Number(site.construction_progress || 0) * 100));
    const badge = site.status === 'UNDER_CONSTRUCTION' ? `<small>${progress.toFixed(0)}%</small>` : '';
    return L.divIcon({
        className: `installation-icon${selected ? ' selected-installation' : ''}${statusClass}`,
        html: `<div style="--installation-color:${factionColor}; color:${factionColor};"><span>${escapeHtml(site.icon || '⌂')}</span>${badge}</div>`,
        iconSize: [34, 34],
        iconAnchor: [17, 17],
    });
}

function refreshInstallationsSmoothly(installationsData) {
    const currentIds = new Set(Object.keys(installationsData || {}));
    for (const installationId in window.installationMarkersMap) {
        if (!currentIds.has(installationId)) {
            const record = window.installationMarkersMap[installationId];
            map.removeLayer(record.marker);
            if (record.circle) map.removeLayer(record.circle);
            delete window.installationMarkersMap[installationId];
        }
    }

    for (const [installationId, site] of Object.entries(installationsData || {})) {
        const latitude = Number(site.lat);
        const longitude = Number(site.lon);
        if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) continue;
        const selected = installationId === selectedInstallationId;
        const operational = site.status === 'OPERATIONAL';
        const effectRadius = operational
            ? Math.max(Number(site.radius || 0), Number(site.effect_radius_km || 0), Number(site.radar_range_km || 0))
            : Number(site.radius || 0);
        const displayRadius = selected ? effectRadius : Number(site.radius || 0);
        const factionColor = getFactionColor(site.faction);
        const style = {
            color: site.status === 'DESTROYED' ? '#6e7681' : factionColor,
            fillColor: factionColor,
            fillOpacity: selected && operational ? 0.045 : 0.015,
            opacity: selected ? 0.8 : 0.35,
            weight: selected ? 1.5 : 1,
            dashArray: Number(site.radar_range_km || 0) > 0 && operational ? '8,6' : '4,4',
            radius: Math.max(0, displayRadius) * 1000,
            interactive: false,
        };
        const signature = [site.status, site.icon, site.faction, selected, Math.round(Number(site.construction_progress || 0) * 100)].join('|');
        let record = window.installationMarkersMap[installationId];
        if (record) {
            record.marker.setLatLng([latitude, longitude]);
            if (record.signature !== signature) {
                record.marker.setIcon(installationIcon(site, selected));
                record.signature = signature;
            }
            record.marker.unbindTooltip().bindTooltip(installationTooltip(site), {sticky: true});
            record.circle.setLatLng([latitude, longitude]);
            record.circle.setRadius(style.radius);
            record.circle.setStyle(style);
        } else {
            const circle = L.circle([latitude, longitude], style).addTo(map);
            const marker = L.marker([latitude, longitude], {
                icon: installationIcon(site, selected),
                zIndexOffset: 250,
            }).bindTooltip(installationTooltip(site), {sticky: true}).addTo(map);
            marker.on('click', event => {
                L.DomEvent.stopPropagation(event);
                if (selectedUnitId && pendingAction && !isDeploying && mapClickHandler) {
                    mapClickHandler({latlng: L.latLng(Number(site.lat), Number(site.lon))});
                    return;
                }
                selectedInstallationId = installationId;
                selectedUnitId = null;
                selectedUnitLon = null;
                selectedUnitLat = null;
                clearDraft();
                if (pathLine) {
                    map.removeLayer(pathLine);
                    pathLine = null;
                }
                document.getElementById('targeting-alert').style.display = 'none';
                fetchState();
            });
            record = {marker, circle, signature};
            window.installationMarkersMap[installationId] = record;
        }
    }
}

function updateIntelFeed(logs) {
    if (!logs || logs.length === 0) return;
    const container = document.getElementById('logs-container');
    if (logs.length !== lastLogCount || logs[logs.length-1].message !== container.dataset.lastMsg) {
        const previousScrollTop = container.scrollTop;
        container.innerHTML = logs.slice().reverse().map(log => `<div class="log-entry ${log.type === "combat" ? "log-combat" : (log.type === "move" ? "log-move" : "log-system")}">${escapeHtml(log.message)}</div>`).join('');
        container.scrollTop = previousScrollTop;
        container.dataset.lastMsg = logs[logs.length-1].message; lastLogCount = logs.length;
    }
}

function installationEffectSummary(site) {
    const effects = [];
    const cover = Math.max(0, Number(site.fortification_cover_bonus || 0));
    const effectRadius = Math.max(0, Number(site.effect_radius_km || 0));
    const radarRange = Math.max(0, Number(site.radar_range_km || 0));
    if (cover > 0) {
        effects.push(`Fort cover +${Math.round(cover * 100)}% for allied units within ${effectRadius.toFixed(1)} km`);
    }
    if (radarRange > 0) {
        effects.push(`Radar searches ${radarRange.toFixed(0)} km with recon power ${Number(site.radar_recon_power || 0).toFixed(2)}`);
    }
    return effects.length ? effects.join(' · ') : 'No passive operational effect; this remains a physical military target.';
}

function updateInstallationHUD(site) {
    const unitInfo = document.getElementById('unit-info');
    if (!unitInfo || tacticalHudInteractionInProgress(unitInfo)) return;
    const tacticalHud = document.getElementById('tactical-hud');
    const previousScrollTop = tacticalHud?.scrollTop || 0;
    const factionColor = getFactionColor(site.faction);
    const integrity = Math.max(0, Number(site.integrity || 0));
    const maximumIntegrity = Math.max(1, Number(site.max_integrity || 1));
    const integrityPercent = Math.max(0, Math.min(100, integrity / maximumIntegrity * 100));
    const constructionPercent = Math.max(0, Math.min(100, Number(site.construction_progress || 0) * 100));
    const statusColor = site.status === 'DESTROYED'
        ? '#ff7b72'
        : (site.status === 'UNDER_CONSTRUCTION' ? '#e3b341' : '#7ee787');
    const builderRow = site.builder_unit_id
        ? `<div class="data-row"><span class="data-label">Builder:</span> ${escapeHtml(latestUnits[site.builder_unit_id]?.name || site.builder_unit_id)}</div>`
        : '';
    const constructionBlock = site.status === 'UNDER_CONSTRUCTION'
        ? `<div class="installation-progress-label"><span>Construction</span><strong>${constructionPercent.toFixed(0)}%</strong></div>
           <div class="installation-meter"><span style="width:${constructionPercent}%; background:#e3b341;"></span></div>
           <div class="installation-help">The assigned builder must remain nearby in CONSTRUCTING status. Work consumes supply and adds fatigue only while the timeline runs.</div>`
        : '';
    const targetingHelp = site.status === 'DESTROYED'
        ? 'This wreck has no active effect and cannot take further damage.'
        : 'To attack this site: select a hostile-capable unit, choose Assault, Bombard Area, or Airstrike, then click this map symbol as the objective.';
    const detectedBy = Array.isArray(site.detected_by) && site.detected_by.length
        ? site.detected_by.map(escapeHtml).join(', ')
        : 'None recorded';
    unitInfo.innerHTML = `
        <div class="installation-panel">
            <div class="installation-heading">
                <span><span class="installation-heading-icon" style="color:${factionColor};">${escapeHtml(site.icon || '⌂')}</span> ${escapeHtml(site.name)}</span>
                <button class="cmd-btn cmd-danger" onclick="deselectUnit()">❌ Release</button>
            </div>
            <div class="data-row"><span class="data-label">Type:</span> <span style="color:#58a6ff; font-weight:bold;">${escapeHtml(site.type_label || site.type_id)}</span></div>
            <div class="data-row"><span class="data-label">Faction:</span> <span style="color:${factionColor}; font-weight:bold;">${escapeHtml(site.faction)}</span></div>
            <div class="data-row"><span class="data-label">Status:</span> <span style="color:${statusColor}; font-weight:bold;">${escapeHtml(String(site.status || '').replaceAll('_', ' '))}</span></div>
            <div class="data-row"><span class="data-label">Integrity:</span> ${integrity.toFixed(0)} / ${maximumIntegrity.toFixed(0)}</div>
            <div class="installation-meter" role="meter" aria-label="Installation integrity" aria-valuemin="0" aria-valuemax="${maximumIntegrity}" aria-valuenow="${integrity.toFixed(0)}"><span style="width:${integrityPercent}%; background:${statusColor};"></span></div>
            ${constructionBlock}
            ${builderRow}
            <div class="telemetry-box">
                <div class="telemetry-row"><span>LON: ${Number(site.lon).toFixed(4)}</span><span>LAT: ${Number(site.lat).toFixed(4)}</span></div>
                <div style="text-align:center; border-top:1px dashed #58a6ff; padding-top:5px; margin-top:3px;">Altitude ${Math.floor(Number(site.altitude || 0))} m · ${escapeHtml(site.current_province || 'Unknown province')}</div>
            </div>
            <div class="data-row"><span class="data-label">Protection:</span> Armor ${Number(site.armor || 0).toFixed(0)} · Softness ${Math.round(Number(site.softness || 0) * 100)}%</div>
            <div class="data-row"><span class="data-label">Footprint:</span> ${Number(site.radius || 0).toFixed(2)} km radius</div>
            <div class="data-row"><span class="data-label">Detected By:</span> ${detectedBy}</div>
            <div class="panel-title installation-effect-title">⚙ Operational Effect</div>
            <div class="installation-effect ${site.status === 'OPERATIONAL' ? 'active' : 'inactive'}">${escapeHtml(site.status === 'OPERATIONAL' ? installationEffectSummary(site) : 'Inactive until construction is complete and integrity remains above zero.')}</div>
            <div class="panel-title installation-target-title">🎯 Military Target</div>
            <div class="installation-help">${escapeHtml(targetingHelp)}</div>
        </div>`;
    if (tacticalHud) tacticalHud.scrollTop = previousScrollTop;
}

function updateConstructionPreview(unitId) {
    const select = document.getElementById(`construction-type-${unitId}`);
    const preview = document.getElementById(`construction-preview-${unitId}`);
    if (!select || !preview) return;
    const profile = globalRules.military_installations?.types?.[select.value];
    if (!profile) {
        preview.textContent = 'No installation profile selected.';
        return;
    }
    const effects = [];
    if (Number(profile.fortification_cover_bonus || 0) > 0) {
        effects.push(`+${Math.round(Number(profile.fortification_cover_bonus) * 100)}% allied cover within ${Number(profile.effect_radius_km).toFixed(1)} km`);
    }
    if (Number(profile.radar_range_km || 0) > 0) {
        effects.push(`${Number(profile.radar_range_km).toFixed(0)} km radar search`);
    }
    preview.textContent = `${profile.description} Build ${Number(profile.construction_hours).toFixed(1)} h · Total supply ${Number(profile.construction_supply_cost).toFixed(1)}%${effects.length ? ` · ${effects.join(' · ')}` : ''}.`;
}

async function startInstallationConstruction(unitId) {
    const typeSelect = document.getElementById(`construction-type-${unitId}`);
    if (!typeSelect?.value) return;
    const button = document.getElementById(`construction-start-${unitId}`);
    if (button?.disabled) return;
    if (button) button.disabled = true;
    try {
        const result = await fetchJson('/api/command', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command: `build ${unitId} ${typeSelect.value}`}),
        });
        await fetchState();
        if (result.queued) {
            const statusSpan = document.getElementById('pause-status');
            if (statusSpan) statusSpan.title = result.msg;
        }
    } catch (error) {
        alert(`Construction rejected: ${error.message}`);
        if (button) button.disabled = false;
    }
}

function updateTacticalHUD(u) {
    const unitInfo = document.getElementById('unit-info');
    if (!unitInfo || tacticalHudInteractionInProgress(unitInfo)) return;
    const compStr = Object.entries(u.composition || {}).filter(([k,v])=>v>0).map(([k,v]) => `${escapeHtml(k)}:${Number(v)}`).join(' | ');
    const weaponStr = (u.weapon_loadout || []).map(weapon => {
        const quantity = Number(weapon.quantity || 0);
        const quantityText = quantity.toFixed(Number.isInteger(quantity) ? 0 : 2);
        return `${quantityText}× ${escapeHtml(weapon.name || weapon.id)} · Gen ${Number(weapon.generation || 0)} · ${Number(weapon.max_range_km || 0).toFixed(1)} km`;
    }).join(' | ');
    const capabilities = new Set(u.effective_capabilities || u.capabilities || []);
    const missionCards = [];
    const supportBusy = isSupportMissionActive(u);
    const supportStatus = u.status === 'BOMBARDING'
        ? `BOMBARDING · ${Number(u.bombard_timer || 0).toFixed(2)} h remaining · ${Number(u.bombard_casualties || 0).toFixed(0)} estimated casualties · ${Number(u.bombard_installation_damage || 0).toFixed(0)} target integrity damage${Number(u.bombard_installations_destroyed || 0) > 0 ? ` · ${Number(u.bombard_installations_destroyed)} site(s) destroyed` : ''}`
        : (u.status === 'AIRSTRIKE_OUTBOUND'
            ? 'AIRSTRIKE OUTBOUND · flying to the selected impact area'
            : (u.status === 'AIRSTRIKE_RTB' ? 'AIRSTRIKE RTB · returning to launch base' : ''));
    const missionButton = (action, icon, label, meta, disabledReason) => {
        const disabled = Boolean(disabledReason);
        return `<div class="support-mission-card">
            <button class="cmd-btn cmd-warn support-mission-button" onclick="setTargetingMode('${action}')" ${disabled ? 'disabled' : ''} title="${escapeHtml(disabledReason || `Select a ${label.toLowerCase()} target on the map`)}">${icon} ${escapeHtml(label)}</button>
            <div class="support-mission-meta">${escapeHtml(meta)}</div>
            <div class="support-mission-readiness ${disabled ? 'blocked' : 'ready'}">${escapeHtml(disabledReason || 'READY')}</div>
        </div>`;
    };
    if (capabilities.has(globalRules.missions?.bombard?.capability)) {
        const rules = globalRules.missions.bombard;
        const disabledReason = Number(u.bombard_range || 0) <= 0
            ? 'No battalion mounts an indirect bombard weapon'
            : (Number(u.personnel || 0) <= 0
            ? 'Unit is neutralized'
            : (supportBusy
                ? 'Finish or halt the active support mission first'
                : (Number(u.supply || 0) < Number(rules.minimum_supply_to_start)
                    ? `Requires ${Number(rules.minimum_supply_to_start).toFixed(0)}% supply`
                    : '')));
        missionCards.push(missionButton(
            'bombard',
            '💥',
            'Bombard Area',
            `Weapon-band range ${Number(u.bombard_range || 0).toFixed(1)} km · Effect radius ${Number(rules.blast_radius_km).toFixed(1)} km · ${Number(rules.duration_hours).toFixed(1)} h · Supply ${Number(rules.supply_per_hour).toFixed(1)}%/h`,
            disabledReason
        ));
    }
    if (capabilities.has(globalRules.missions?.airstrike?.capability)) {
        const rules = globalRules.missions.airstrike;
        const aircraft = airstrikePerformance(u);
        const disabledReason = !(aircraft.strike_weapon_ids || []).length
            ? 'No battalion mounts an airstrike weapon'
            : (Number(u.personnel || 0) <= 0
            ? 'Unit is neutralized'
            : (supportBusy
                ? 'Finish or halt the active support mission first'
                : (Number(u.supply || 0) < Number(aircraft.supply_cost)
                    ? `Requires ${Number(aircraft.supply_cost).toFixed(0)}% supply`
                    : '')));
        missionCards.push(missionButton(
            'airstrike',
            '✈️',
            `Launch Airstrike — ${aircraft.label}`,
            `${aircraft.attack_profile} · Cruise ${Number(aircraft.cruise_speed_kmh).toFixed(0)} km/h · Range ${Number(aircraft.sortie_range_km).toFixed(0)} km · Effect radius ${Number(aircraft.blast_radius_km).toFixed(1)} km · Soft ×${Number(aircraft.soft_target_multiplier).toFixed(2)} / Hard ×${Number(aircraft.hard_target_multiplier).toFixed(2)} · Accuracy ×${Number(aircraft.accuracy_multiplier).toFixed(2)} · Unobserved ×${Number(aircraft.unobserved_targeting_multiplier).toFixed(2)} · Payload ×${Number(aircraft.payload_multiplier).toFixed(2)} · Cost ${Number(aircraft.supply_cost).toFixed(1)}% supply / ${Number(aircraft.fatigue_cost).toFixed(1)}% fatigue · AA exposure ×${Number(aircraft.aa_vulnerability_multiplier).toFixed(2)} · Max ${Math.round(Number(rules.maximum_casualty_fraction) * 100)}% loss/formation`,
            disabledReason
        ));
    }
    const weaponPanel = missionCards.length
        ? `<div class="panel-title support-mission-title">🎯 Support Mission</div>${supportStatus ? `<div class="support-mission-status">${escapeHtml(supportStatus)}</div>` : ''}<div class="support-mission-grid">${missionCards.join('')}</div>`
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
    const installationRules = globalRules.military_installations || {};
    const constructionRules = installationRules.construction || {};
    const installationTypes = Object.entries(installationRules.types || {});
    const activeProject = u.active_construction || null;
    const selectedBuildType = activeProject?.type_id || installationTypes[0]?.[0] || '';
    const selectedBuildProfile = installationRules.types?.[selectedBuildType] || null;
    let constructionDisabledReason = '';
    if (!canPrepareGroundDefense) {
        constructionDisabledReason = 'Only ground-combat formations can build military installations';
    } else if (Number(u.personnel || 0) <= 0) {
        constructionDisabledReason = 'A neutralized formation cannot construct';
    } else if (u.status === 'CONSTRUCTING') {
        constructionDisabledReason = simulationPaused
            ? 'Work is queued; press Run to advance construction'
            : 'Construction is already progressing';
    } else if (['MOVING', 'BOMBARDING', 'AIRSTRIKE_OUTBOUND', 'AIRSTRIKE_RTB'].includes(u.status) || (u.waypoints || []).length > 0) {
        constructionDisabledReason = 'Halt movement or the active support mission before building';
    } else if (activeProject && Number(u.supply || 0) <= Number(constructionRules.stop_supply_threshold || 0)) {
        constructionDisabledReason = `Supply must exceed ${Number(constructionRules.stop_supply_threshold || 0).toFixed(0)}% to resume work`;
    } else if (!activeProject && Number(u.supply || 0) < Number(constructionRules.minimum_supply_to_start || 0)) {
        constructionDisabledReason = `Requires ${Number(constructionRules.minimum_supply_to_start || 0).toFixed(0)}% supply to begin`;
    }
    const constructionOptions = installationTypes.map(([typeId, profile]) =>
        `<option value="${escapeHtml(typeId)}" ${typeId === selectedBuildType ? 'selected' : ''}>${escapeHtml(profile.icon || '⌂')} ${escapeHtml(profile.label || typeId)}</option>`
    ).join('');
    const constructionProgress = Math.max(0, Math.min(100, Number(activeProject?.construction_progress || 0) * 100));
    const initialConstructionEffects = selectedBuildProfile
        ? installationEffectSummary(selectedBuildProfile)
        : '';
    const constructionActionLabel = activeProject ? 'Resume Construction' : 'Build at Current Position';
    const constructionStatus = activeProject
        ? `${escapeHtml(activeProject.name)} · ${constructionProgress.toFixed(0)}% complete${u.status === 'CONSTRUCTING' ? (simulationPaused ? ' · queued while paused' : ' · crews working') : ' · work paused'}`
        : 'No active construction project.';
    const constructionPanel = installationTypes.length
        ? `<div class="panel-title construction-title">🏗 Military Construction</div>
           <div class="construction-panel">
               <div class="construction-distinction"><strong>Build</strong> creates a persistent, separately targetable site. <strong>Fortify</strong> only prepares temporary fieldworks for this unit.</div>
               <div class="construction-status">${constructionStatus}</div>
               ${activeProject ? `<div class="installation-meter" role="meter" aria-label="Construction progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${constructionProgress.toFixed(0)}"><span style="width:${constructionProgress}%; background:#e3b341;"></span></div>` : ''}
               <div class="construction-controls">
                   <select id="construction-type-${u.id}" class="dark-input" aria-label="Military installation type" onchange="updateConstructionPreview('${u.id}')" ${activeProject ? 'disabled title="Finish or lose the existing project before selecting another type"' : ''}>${constructionOptions}</select>
                   <button id="construction-start-${u.id}" class="cmd-btn construction-start" onclick="startInstallationConstruction('${u.id}')" ${constructionDisabledReason ? 'disabled' : ''}>${escapeHtml(constructionActionLabel)}</button>
               </div>
               <div id="construction-preview-${u.id}" class="construction-preview">${selectedBuildProfile ? `${escapeHtml(selectedBuildProfile.description)} Build ${Number(selectedBuildProfile.construction_hours).toFixed(1)} h · Total supply ${Number(selectedBuildProfile.construction_supply_cost).toFixed(1)}% · ${escapeHtml(initialConstructionEffects)}.` : 'No installation type is configured.'}</div>
               <div class="support-mission-readiness ${constructionDisabledReason ? 'blocked' : 'ready'}">${escapeHtml(constructionDisabledReason || (simulationPaused ? 'READY · construction will begin when the timeline runs' : (activeProject ? 'READY TO RESUME' : 'READY TO BUILD HERE')))}</div>
               ${activeProject && u.status === 'CONSTRUCTING' && simulationPaused ? `<button class="cmd-btn construction-run" onclick="sendCommand('play')">▶ Run Timeline to Build</button>` : ''}
           </div>`
        : '';
    let engagementSummary = 'This unit cannot conduct direct ground combat.';
    if (canPrepareGroundDefense) {
        const movementTaskWithholdsFire = (
            (activeOrderRole === 'relocate' && !globalRules.orders.relocate_allows_stance_fire)
            || (activeOrderRole === 'route' && !globalRules.orders.route_allows_stance_fire)
        );
        if (!currentStance.allows_ranged_fire) {
            engagementSummary = 'Ranged fire is withheld by stance; close-contact self-defense remains active.';
        } else if (movementTaskWithholdsFire) {
            engagementSummary = activeOrderRole === 'relocate'
                ? 'Ranged fire is withheld; detected threats to the route trigger an automatic detour while close-contact self-defense remains active.'
                : 'Ranged fire is withheld by the movement task; close-contact self-defense remains active.';
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
    const relocateButton = orderButton('relocate', '📍', "setTargetingMode('relocate')");
    const routeButton = orderButton('route', '🗺️', "setTargetingMode('route')");
    const holdButton = orderButton('hold', '⏹', `sendCommand('halt ${u.id}')`, 'order-hold');
    const maximumEntrenchment = Math.max(Number(globalRules.recovery?.maximum_entrenchment) || 1, 0.001);
    const entrenchmentPercent = Math.max(0, Math.min(100, Number(u.entrenchment || 0) / maximumEntrenchment * 100));
    const moralePercent = Math.max(0, Math.min(100, Number(u.morale || 0)));
    const moraleColor = moralePercent <= 25 ? '#ff7b72' : (moralePercent <= 50 ? '#e3b341' : '#7ee787');
    const aircraft = u.airstrike_profile ? airstrikePerformance(u) : null;
    const aircraftDataRow = aircraft
        ? `<div class="data-row" title="${escapeHtml(aircraft.description)}"><span class="data-label">Aircraft Type:</span> <span style="color:#d2a8ff; font-weight:bold;">${escapeHtml(aircraft.label)}</span> · ${escapeHtml(aircraft.attack_profile)}</div>`
        : '';
    const remainingDistance = remainingRouteDistanceKm(u);
    const effectiveMovementSpeed = Math.max(0, Number(u.effective_movement_speed || 0));
    const movementEta = effectiveMovementSpeed > 0 ? remainingDistance / effectiveMovementSpeed : Number.NaN;
    const relocationAvoidance = u.relocation_avoidance || {};
    const avoidanceContacts = Array.isArray(relocationAvoidance.contacts) ? relocationAvoidance.contacts : [];
    const avoidanceNames = avoidanceContacts.slice(0, 3).map(contact => escapeHtml(contact.name || contact.id || 'contact')).join(', ');
    const avoidanceActive = Boolean(relocationAvoidance.active && avoidanceContacts.length);
    const movementLabel = avoidanceActive ? 'CONTACT-AVOIDANCE ROUTE' : 'EN ROUTE';
    const avoidanceDetail = avoidanceActive
        ? ` · avoiding ${avoidanceNames}${avoidanceContacts.length > 3 ? ` +${avoidanceContacts.length - 3}` : ''}`
        : '';
    const movementExecution = u.status === 'MOVING' && remainingDistance > 0
        ? (simulationPaused
            ? `<div class="order-execution queued"><div><strong>${avoidanceActive ? 'CONTACT-AVOIDANCE ROUTE QUEUED' : 'ORDER QUEUED — TIMELINE PAUSED'}</strong><span>${remainingDistance.toFixed(1)} km remains${avoidanceDetail}. Press Run to execute all queued orders.</span></div><button class="cmd-btn" onclick="sendCommand('play')">▶ Run</button></div>`
            : `<div class="order-execution active"><strong>${movementLabel}</strong><span>${remainingDistance.toFixed(1)} km remaining · ${effectiveMovementSpeed.toFixed(1)} km/h effective · ${formatSimulationDuration(movementEta)}${avoidanceDetail}</span></div>`)
        : '';
    
    // 🟢 Dynamic HUD Color Based on Palette
    const uColor = getFactionColor(u.faction);

    const tacticalHud = document.getElementById('tactical-hud');
    const previousScrollTop = tacticalHud?.scrollTop || 0;
    unitInfo.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid #1f6feb; padding-bottom: 5px;">
            <span style="color:#fff; font-size:15px; font-weight:bold;">${escapeHtml(u.name)}</span><button class="cmd-btn cmd-danger" style="padding: 3px 6px;" onclick="deselectUnit()">❌ Release</button>
        </div>
        <div class="data-row"><span class="data-label">Faction:</span> <span style="color:${uColor}">${escapeHtml(u.faction)}</span></div>
        <div class="data-row"><span class="data-label">Status:</span> <span style="color:#58a6ff; font-weight:bold;">${escapeHtml(u.status)}</span></div>
        <div class="data-row" title="Personnel currently alive after combat and mission losses"><span class="data-label">Personnel Alive:</span> ${Math.floor(Number(u.personnel))} Pers.</div>
        <div class="data-row"><span class="data-label">Morale:</span> <span style="color:${moraleColor}; font-weight:bold;">${moralePercent.toFixed(0)}%</span></div>
        <div class="morale-meter" role="meter" aria-label="Unit morale" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${moralePercent.toFixed(0)}"><span style="width:${moralePercent}%; background:${moraleColor};"></span></div>
        <div class="data-row"><span class="data-label">Readiness:</span> Supply ${Math.floor(u.supply ?? globalRules.unit_defaults.supply)}% | Fatigue ${Math.floor(u.fatigue ?? globalRules.unit_defaults.fatigue)}% | Supp. ${Math.floor(u.suppression ?? globalRules.unit_defaults.suppression)}%</div>
        <div class="data-row"><span class="data-label">Prepared Defense:</span> ${entrenchmentPercent.toFixed(0)}%</div>
        <div style="height:6px; background:#161b22; border:1px solid #30363d; margin:2px 0 8px;"><div style="height:100%; width:${entrenchmentPercent}%; background:#3fb950;"></div></div>
        <div class="data-row"><span class="data-label">Fort Cover:</span> <span style="color:#7ee787; font-weight:bold;">+${Math.round(Number(u.installation_cover_bonus || 0) * 100)}%</span> from nearby operational sites</div>
        <div class="telemetry-box">
            <div class="telemetry-row"><span>LON: ${parseFloat(u.lon).toFixed(4)}</span><span>LAT: ${parseFloat(u.lat).toFixed(4)}</span><span>MOV: ${effectiveMovementSpeed.toFixed(1)} km/h</span></div>
            <div style="text-align:center; border-top:1px dashed #58a6ff; padding-top:5px; margin-top:3px;">Real-time Altitude: <span style="color:#fff; font-size:14px; font-weight:bold;">${Math.floor(u.altitude || 0)}</span> m</div>
        </div>
        <div class="data-row"><span class="data-label">Def. Radius:</span> <span style="color:#7ee787; font-weight:bold;">${(u.radius || 0).toFixed(2)} km</span></div>
        <div class="data-row"><span class="data-label">City Influence:</span> <span style="color:#d2a8ff; font-weight:bold;">${u.city_name ? `${escapeHtml(u.city_name)} · ${Number(u.city_influence_rate || 0).toFixed(2)}` : 'None · 0.00'}</span></div>
        <div class="data-row"><span class="data-label">Effective Complexity:</span> ${Number(u.effective_terrain_complexity || 0).toFixed(2)}</div>
        <div class="data-row"><span class="data-label">OOB:</span> <span style="color:#a5d6ff">${compStr || 'Non-Combat Unit'}</span></div>
        <div class="data-row"><span class="data-label">Weapon Groups:</span> <span style="color:#e3b341; font-weight:bold;">${weaponStr || 'Unarmed'}</span></div>
        <div class="data-row"><span class="data-label">Protection:</span> Armor ${Number(u.stats?.armor || 0).toFixed(1)} · Armor Gen ${Number(u.stats?.armor_generation || 0).toFixed(1)}</div>
        ${aircraftDataRow}
        <div class="panel-title operational-order-title">📍 Operational Order</div>
        <div class="operational-order-panel" style="--order-color:${escapeHtml(orderProfile.color)}; border-color:${escapeHtml(orderProfile.color)};">
            <div class="order-section-label"><span>Current Task</span><small>WHAT &amp; WHERE</small></div>
            <div class="order-status-heading">
                <span>${escapeHtml(orderProfile.label)}</span>
                <span>${escapeHtml(orderProfile.summary)}</span>
            </div>
            <div class="order-status-description">${escapeHtml(orderProfile.description)}</div>
            ${movementExecution}

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
        ${constructionPanel}
    `;
    if (tacticalHud) tacticalHud.scrollTop = previousScrollTop;
}
// ==========================================
// IN-GAME EDITOR (ZEUS CONSOLE) LOGIC
// ==========================================

function toggleAdminConsole() {
    const panel = document.getElementById('admin-console');
    const opening = panel.style.display === 'none' || panel.style.display === '';
    panel.style.display = opening ? 'block' : 'none';
    if (opening) {
        document.getElementById('deploy-panel').style.display = 'none';
        document.getElementById('committee-panel').style.display = 'none';
        document.getElementById('save-load-panel').style.display = 'none';
        updateZeusTarget(null);
        fetchState();
    }
}

function zeusModifierLabel(type) {
    const labels = currentLang === 'zh'
        ? {combat: '战斗效能', speed: '移动速度', morale: '士气恢复速度'}
        : {combat: 'Combat effectiveness', speed: 'Movement speed', morale: 'Morale recovery rate'};
    return labels[type] || String(type).replaceAll('_', ' ');
}

function updateZeusModifierHelp() {
    const type = document.getElementById('admin-mod-type')?.value;
    const help = document.getElementById('zeus-modifier-help');
    if (!help) return;
    const descriptions = currentLang === 'zh'
        ? {
            combat: '按倍率改变战斗伤害计算，不直接增加人数。',
            speed: '按倍率改变地图移动速度，不改变攻击命令。',
            morale: '按倍率改变部队在待命或防御时的士气恢复速度，不会立即增加士气。'
        }
        : {
            combat: 'Multiplies combat effectiveness; it does not add personnel.',
            speed: 'Multiplies map movement speed; it does not issue a movement order.',
            morale: 'Multiplies morale recovery while idle or defending; it does not add morale immediately.'
        };
    help.textContent = descriptions[type] || (currentLang === 'zh'
        ? '按输入倍率临时改变此项目。'
        : 'Temporarily multiplies this effect by the entered value.');
}

function updateZeusTarget(unit) {
    const target = document.getElementById('zeus-selected-unit');
    if (!target) return;
    if (!unit) {
        target.textContent = currentLang === 'zh'
            ? '目标部队：请先在地图上选择一支部队。'
            : 'Target unit: select a unit on the map first.';
        target.classList.remove('active');
        return;
    }
    target.textContent = currentLang === 'zh'
        ? `目标部队：${unit.name} · ${unit.faction} · ${unit.id}`
        : `Target unit: ${unit.name} · ${unit.faction} · ${unit.id}`;
    target.classList.add('active');
}

function setZeusStatus(message, kind = '') {
    const status = document.getElementById('zeus-status');
    if (!status) return;
    status.textContent = message;
    status.className = `zeus-status${kind ? ` ${kind}` : ''}`;
}

async function applyAdminModifier() {
    if (!selectedUnitId) {
        setZeusStatus(currentLang === 'zh' ? '请先在地图上选择一支目标部队。' : 'Select a target unit on the map first.', 'error');
        return;
    }

    const type = document.getElementById('admin-mod-type').value;
    const valueInput = document.getElementById('admin-mod-val').value.trim();
    const durationInput = document.getElementById('admin-mod-dur').value.trim();
    const val = Number(valueInput);
    const dur = Number(durationInput);
    const rules = globalRules.modifiers;
    if (!type || !valueInput || !Number.isFinite(val) || val < Number(rules.value_minimum) || val > Number(rules.value_maximum)) {
        setZeusStatus(currentLang === 'zh'
            ? `倍率必须在 ${rules.value_minimum} 到 ${rules.value_maximum} 之间。`
            : `Multiplier must be between ${rules.value_minimum} and ${rules.value_maximum}.`, 'error');
        return;
    }
    if (!durationInput || !Number.isFinite(dur) || dur < Number(rules.duration_minimum_hours) || dur > Number(rules.duration_maximum_hours)) {
        setZeusStatus(currentLang === 'zh'
            ? `持续时间必须在 ${rules.duration_minimum_hours} 到 ${rules.duration_maximum_hours} 个推演小时之间。`
            : `Duration must be between ${rules.duration_minimum_hours} and ${rules.duration_maximum_hours} simulation hours.`, 'error');
        return;
    }
    const modName = `Chair ${type} x${val}`;

    try {
        await fetchJson('/api/modifier', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ id: selectedUnitId, name: modName, type, value: val, duration: dur })
        });
        await fetchState();
        setZeusStatus(currentLang === 'zh'
            ? `已对选中部队应用“${zeusModifierLabel(type)}”×${val}，持续 ${dur} 个推演小时。`
            : `${zeusModifierLabel(type)} ×${val} applied to the selected unit for ${dur} simulation hours.`, 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '临时效果被拒绝：' : 'Temporary effect rejected: ') + error.message, 'error');
    }
}

async function forceUnitHP() {
    if (!selectedUnitId) {
        setZeusStatus(currentLang === 'zh' ? '请先在地图上选择一支目标部队。' : 'Select a target unit on the map first.', 'error');
        return;
    }

    const personnelInput = document.getElementById('admin-edit-hp').value.trim();
    const newPersonnel = Number(personnelInput);
    if (!personnelInput || !Number.isInteger(newPersonnel) || newPersonnel < 0) {
        setZeusStatus(currentLang === 'zh' ? '新兵力必须是大于或等于 0 的整数。' : 'New personnel must be a whole number of 0 or greater.', 'error');
        return;
    }

    try {
        await fetchJson('/api/admin_edit', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ original_id: selectedUnitId, id: selectedUnitId, personnel: newPersonnel })
        });
        await fetchState();
        document.getElementById('admin-edit-hp').value = '';
        setZeusStatus(currentLang === 'zh'
            ? `选中部队的当前兵力已设为 ${newPersonnel}；此更改尚未手动保存。`
            : `Selected unit personnel set to ${newPersonnel}; this change has not been manually saved.`, 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '兵力修改被拒绝：' : 'Personnel change rejected: ') + error.message, 'error');
    }
}

function refreshChairCityEditor() {
    const select = document.getElementById('admin-city-select');
    if (!select) return;
    const signature = cityInfluenceAreas.map(city => `${city.id}:${city.name}:${city.influence_rate}`).join('|');
    if (select.dataset.signature !== signature) {
        select.replaceChildren();
        for (const city of cityInfluenceAreas) {
            const option = document.createElement('option');
            option.value = city.id;
            option.textContent = `${city.name} (${Number(city.influence_rate).toFixed(2)})`;
            select.appendChild(option);
        }
        select.dataset.signature = signature;
    }
    if (cityDraftNew) return;
    if (!cityInfluenceAreas.some(city => city.id === selectedCityId)) {
        selectedCityId = cityInfluenceAreas[0]?.id || null;
    }
    select.value = selectedCityId || '';
    if (document.activeElement?.closest?.('#zeus-city-fields')) return;
    populateChairCityFields(cityInfluenceAreas.find(item => item.id === selectedCityId));
}

function populateChairCityFields(city) {
    const center = map?.getCenter?.() || {lng: 0, lat: 0};
    const values = city || {
        id: '', name: '', description: '', lon: center.lng, lat: center.lat,
        area_km2: 0, influence_rate: 0
    };
    for (const field of ['id', 'name', 'description', 'lon', 'lat', 'area_km2', 'influence_rate']) {
        const input = document.getElementById(`admin-city-${field}`);
        if (input) input.value = values[field] ?? '';
    }
}

function selectChairCity(cityId) {
    cityDraftNew = false;
    selectedCityId = cityId || null;
    populateChairCityFields(cityInfluenceAreas.find(city => city.id === selectedCityId));
}

function startNewChairCity() {
    cityDraftNew = true;
    selectedCityId = null;
    const select = document.getElementById('admin-city-select');
    if (select) select.value = '';
    populateChairCityFields(null);
    document.getElementById('admin-city-id')?.focus();
    setZeusStatus(currentLang === 'zh' ? '填写新城市资料，然后点击保存。' : 'Enter the new city details, then save it.');
}

async function saveChairCity() {
    const read = field => document.getElementById(`admin-city-${field}`).value.trim();
    const payload = {
        action: 'upsert',
        id: read('id'),
        name: read('name'),
        description: read('description'),
        lon: Number(read('lon')),
        lat: Number(read('lat')),
        area_km2: Number(read('area_km2')),
        influence_rate: Number(read('influence_rate'))
    };
    if (!cityDraftNew && selectedCityId) payload.original_id = selectedCityId;
    if (!payload.id || !payload.name || !Number.isFinite(payload.lon) || payload.lon < -180 || payload.lon > 180
        || !Number.isFinite(payload.lat) || payload.lat < -90 || payload.lat > 90
        || !Number.isFinite(payload.area_km2) || payload.area_km2 < 0
        || !Number.isFinite(payload.influence_rate) || payload.influence_rate < 0 || payload.influence_rate > 1) {
        setZeusStatus(currentLang === 'zh'
            ? '请填写城市 ID、名称、有效坐标、非负面积和 0–1 影响率。'
            : 'Enter an ID, name, valid coordinates, non-negative area, and an influence rate from 0 to 1.', 'error');
        return;
    }
    try {
        const result = await fetchJson('/api/city', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
        });
        cityDraftNew = false;
        selectedCityId = result.city.id;
        await fetchState();
        setZeusStatus(currentLang === 'zh'
            ? `城市“${result.city.name}”已更新，影响率 ${Number(result.city.influence_rate).toFixed(2)}。`
            : `${result.city.name} updated with influence ${Number(result.city.influence_rate).toFixed(2)}.`, 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '城市更新被拒绝：' : 'City update rejected: ') + error.message, 'error');
    }
}

async function deleteChairCity() {
    if (!selectedCityId || cityDraftNew) {
        setZeusStatus(currentLang === 'zh' ? '请先选择一个已有城市。' : 'Select an existing city first.', 'error');
        return;
    }
    const city = cityInfluenceAreas.find(item => item.id === selectedCityId);
    if (!confirm(`Remove city influence area "${city?.name || selectedCityId}"?`)) return;
    try {
        await fetchJson('/api/city', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'delete', id: selectedCityId})
        });
        selectedCityId = null;
        await fetchState();
        setZeusStatus(currentLang === 'zh' ? '城市影响区已删除。' : 'City influence area removed.', 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '删除失败：' : 'Delete failed: ') + error.message, 'error');
    }
}

function provincePoliticsRecords() {
    const records = [];
    for (const [province, state] of Object.entries(provincePolitics)) {
        for (const [faction, record] of Object.entries(state.factions || {})) {
            records.push({province, faction, ...record, controller: state.controller, contested: state.contested});
        }
    }
    return records.sort((a, b) => a.province.localeCompare(b.province) || a.faction.localeCompare(b.faction));
}

function refreshChairPoliticsEditor() {
    const select = document.getElementById('admin-politics-select');
    if (!select) return;
    const records = provincePoliticsRecords();
    const signature = records.map(record => `${record.province}\u0000${record.faction}\u0000${record.civilian_sentiment}\u0000${record.occupation}`).join('|');
    if (select.dataset.signature !== signature) {
        select.replaceChildren();
        for (const record of records) {
            const option = document.createElement('option');
            option.value = JSON.stringify([record.province, record.faction]);
            option.textContent = `${record.province} · ${record.faction}`;
            select.appendChild(option);
        }
        select.dataset.signature = signature;
    }
    if (politicsDraftNew) return;
    let selected = records.find(record => record.province === selectedPoliticsProvince && record.faction === selectedPoliticsFaction);
    if (!selected) {
        selected = records[0];
        selectedPoliticsProvince = selected?.province || null;
        selectedPoliticsFaction = selected?.faction || null;
    }
    select.value = selected ? JSON.stringify([selected.province, selected.faction]) : '';
    if (document.activeElement?.closest?.('#zeus-politics-fields')) return;
    populateChairPoliticsFields(selected);
}

function populateChairPoliticsFields(record) {
    const values = record || {
        province: '', faction: availableFactions[0] || '', civilian_sentiment: 0, occupation: 0,
        influence: 0, military_presence: 0, controller: null, contested: false
    };
    for (const field of ['province', 'faction', 'civilian_sentiment', 'occupation']) {
        const input = document.getElementById(`admin-politics-${field}`);
        if (input) input.value = values[field] ?? '';
    }
    const summary = document.getElementById('admin-politics-summary');
    if (summary) {
        const control = values.contested ? 'CONTESTED' : (values.controller ? `Controlled by ${values.controller}` : 'No established control');
        summary.textContent = `${control} · influence ${Number(values.influence || 0).toFixed(2)} · military presence ${Number(values.military_presence || 0).toFixed(2)}`;
    }
}

function selectChairPolitics(value) {
    politicsDraftNew = false;
    let province = null;
    let faction = null;
    try {
        [province, faction] = JSON.parse(value || '[]');
    } catch (_) {
        // Invalid option values are treated as no selection.
    }
    selectedPoliticsProvince = province || null;
    selectedPoliticsFaction = faction || null;
    populateChairPoliticsFields(provincePoliticsRecords().find(record => record.province === province && record.faction === faction));
}

function startNewChairPolitics() {
    politicsDraftNew = true;
    selectedPoliticsProvince = null;
    selectedPoliticsFaction = null;
    const select = document.getElementById('admin-politics-select');
    if (select) select.value = '';
    populateChairPoliticsFields(null);
    document.getElementById('admin-politics-province')?.focus();
    setZeusStatus(currentLang === 'zh' ? '填写省份和阵营；民意默认中立 0。' : 'Enter a province and faction; civilian sentiment defaults to neutral (0).');
}

async function saveChairPolitics() {
    const read = field => document.getElementById(`admin-politics-${field}`).value.trim();
    const payload = {
        action: 'upsert',
        province: read('province'),
        faction: read('faction'),
        civilian_sentiment: Number(read('civilian_sentiment')),
        occupation: Number(read('occupation'))
    };
    if (!politicsDraftNew && selectedPoliticsProvince && selectedPoliticsFaction) {
        payload.original_province = selectedPoliticsProvince;
        payload.original_faction = selectedPoliticsFaction;
    }
    if (!payload.province || !payload.faction
        || !Number.isFinite(payload.civilian_sentiment) || payload.civilian_sentiment < -1 || payload.civilian_sentiment > 1
        || !Number.isFinite(payload.occupation) || payload.occupation < 0 || payload.occupation > 1) {
        setZeusStatus(currentLang === 'zh'
            ? '请填写省份、阵营、−1 到 +1 的民意，以及 0 到 1 的占领度。'
            : 'Enter a province, faction, sentiment from −1 to +1, and occupation from 0 to 1.', 'error');
        return;
    }
    try {
        const result = await fetchJson('/api/province_politics', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
        });
        politicsDraftNew = false;
        selectedPoliticsProvince = result.entry.province;
        selectedPoliticsFaction = result.entry.faction;
        await fetchState();
        setZeusStatus(currentLang === 'zh'
            ? `${result.entry.province} 对 ${result.entry.faction} 的民意已设为 ${Number(result.entry.civilian_sentiment).toFixed(2)}。`
            : `${result.entry.province} sentiment toward ${result.entry.faction} set to ${Number(result.entry.civilian_sentiment).toFixed(2)}.`, 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '政治状态更新被拒绝：' : 'Political update rejected: ') + error.message, 'error');
    }
}

async function deleteChairPolitics() {
    if (!selectedPoliticsProvince || !selectedPoliticsFaction || politicsDraftNew) {
        setZeusStatus(currentLang === 'zh' ? '请先选择已有的省份阵营记录。' : 'Select an existing province-faction record first.', 'error');
        return;
    }
    if (!confirm(`Remove the ${selectedPoliticsFaction} political record for ${selectedPoliticsProvince}?`)) return;
    try {
        await fetchJson('/api/province_politics', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: 'delete', province: selectedPoliticsProvince, faction: selectedPoliticsFaction})
        });
        selectedPoliticsProvince = null;
        selectedPoliticsFaction = null;
        await fetchState();
        setZeusStatus(currentLang === 'zh' ? '省份阵营政治记录已删除。' : 'Province-faction political record removed.', 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '删除失败：' : 'Delete failed: ') + error.message, 'error');
    }
}

async function forceDiplomacy(isAllied) {
    const f1 = document.getElementById('admin-dip-f1').value.trim();
    const f2 = document.getElementById('admin-dip-f2').value.trim();

    if (!f1 || !f2) {
        setZeusStatus(currentLang === 'zh' ? '请输入两个阵营的准确名称。' : 'Enter the exact names of both factions.', 'error');
        return;
    }
    if (f1 === f2) {
        setZeusStatus(currentLang === 'zh' ? '请选择两个不同的阵营。' : 'Choose two different factions.', 'error');
        return;
    }

    try {
        await fetchJson('/api/diplomacy', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ f1, f2, allied: isAllied })
        });
        await fetchState();
        setZeusStatus(currentLang === 'zh'
            ? `${f1} 与 ${f2} 已设为${isAllied ? '盟友' : '敌对'}；此操作不会自动下达军事命令。`
            : `${f1} and ${f2} are now marked as ${isAllied ? 'allied' : 'hostile'}; no military order was issued.`, 'success');
    } catch (error) {
        setZeusStatus((currentLang === 'zh' ? '阵营关系修改失败：' : 'Relationship change failed: ') + error.message, 'error');
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
        document.getElementById('committee-panel').style.display = 'none';
        refreshSaveSlots();
    } else {
        panel.style.display = 'none';
    }
}

function checkpointLabel(slot) {
    const number = slot.split('_').at(-1);
    return currentLang === 'zh' ? `检查点 ${number}` : `Checkpoint ${number}`;
}

function formatCheckpointTime(gameHours) {
    if (!Number.isFinite(Number(gameHours))) return currentLang === 'zh' ? '未知推演时间' : 'unknown simulation time';
    const totalMinutes = Math.max(0, Math.floor(Number(gameHours) * 60));
    const day = Math.floor(totalMinutes / (24 * 60));
    const hour = Math.floor((totalMinutes % (24 * 60)) / 60);
    const minute = totalMinutes % 60;
    return `D${String(day).padStart(2, '0')} ${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

function formatSavedAt(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return currentLang === 'zh' ? '时间未知' : 'unknown date';
    return date.toLocaleString(currentLang === 'zh' ? 'zh-CN' : undefined, {
        year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
    });
}

function setSaveLoadStatus(message, kind = '') {
    const status = document.getElementById('save-load-status');
    if (!status) return;
    status.textContent = message;
    status.className = `save-load-status${kind ? ` ${kind}` : ''}`;
}

function setSaveLoadBusy(busy) {
    saveLoadBusy = busy;
    for (const slot of ['slot_1', 'slot_2', 'slot_3']) {
        const saveButton = document.getElementById(`${slot}-save`);
        const loadButton = document.getElementById(`${slot}-load`);
        if (saveButton) saveButton.disabled = busy;
        if (loadButton) loadButton.disabled = busy || !saveSlotCatalog[slot]?.can_load;
    }
    const resetButton = document.getElementById('scenario-reset-button');
    if (resetButton) resetButton.disabled = busy;
}

function renderSaveSlot(slotInfo) {
    const slot = slotInfo.slot;
    const card = document.querySelector(`[data-save-slot="${slot}"]`);
    const state = document.getElementById(`${slot}-state`);
    const meta = document.getElementById(`${slot}-meta`);
    const saveButton = document.getElementById(`${slot}-save`);
    const loadButton = document.getElementById(`${slot}-load`);
    if (!card || !state || !meta || !saveButton || !loadButton) return;

    card.dataset.condition = slotInfo.condition;
    const stateLabels = currentLang === 'zh'
        ? {empty: '空', available: '可恢复', wrong_dlc: '其他 DLC', incompatible_rules: '规则不兼容', invalid: '已损坏'}
        : {empty: 'Empty', available: 'Ready', wrong_dlc: 'Other DLC', incompatible_rules: 'Incompatible', invalid: 'Invalid'};
    state.textContent = stateLabels[slotInfo.condition] || slotInfo.condition;

    if (!slotInfo.exists) {
        meta.textContent = currentLang === 'zh' ? '此检查点尚未保存。' : 'Nothing has been saved here yet.';
    } else if (slotInfo.can_load) {
        const legacy = slotInfo.legacy
            ? (currentLang === 'zh' ? ' · 旧版存档，未记录 DLC' : ' · legacy save; DLC not recorded')
            : '';
        const unitText = currentLang === 'zh' ? `${slotInfo.unit_count} 支部队` : `${slotInfo.unit_count} units`;
        const installationCount = Number(slotInfo.installation_count || 0);
        const installationText = currentLang === 'zh' ? `${installationCount} 处设施` : `${installationCount} military sites`;
        meta.textContent = `${formatSavedAt(slotInfo.saved_at_utc)} · ${formatCheckpointTime(slotInfo.game_hours)} · ${unitText} · ${installationText}${legacy}`;
    } else {
        const prefix = currentLang === 'zh' ? '无法恢复：' : 'Cannot restore: ';
        meta.textContent = prefix + slotInfo.message;
    }

    saveButton.textContent = slotInfo.exists
        ? (currentLang === 'zh' ? '覆盖此检查点' : 'Overwrite')
        : (currentLang === 'zh' ? '保存到此处' : 'Save here');
    saveButton.disabled = saveLoadBusy;
    loadButton.disabled = saveLoadBusy || !slotInfo.can_load;
}

async function refreshSaveSlots() {
    setSaveLoadBusy(true);
    setSaveLoadStatus(currentLang === 'zh' ? '正在检查手动存档…' : 'Checking manual checkpoints…');
    try {
        const data = await fetchJson('/api/save_slots');
        saveSlotCatalog = Object.fromEntries(data.slots.map(slot => [slot.slot, slot]));
        data.slots.forEach(renderSaveSlot);
        setSaveLoadStatus(currentLang === 'zh'
            ? '仅手动保存。恢复存档后，推演会保持暂停。'
            : 'Manual saves only. Restoring a checkpoint leaves the simulation paused.');
    } catch (error) {
        setSaveLoadStatus((currentLang === 'zh' ? '无法读取检查点：' : 'Could not read checkpoints: ') + error.message, 'error');
    } finally {
        setSaveLoadBusy(false);
    }
}

async function saveGame(slot) {
    const existing = saveSlotCatalog[slot];
    if (existing?.exists) {
        const confirmed = confirm(currentLang === 'zh'
            ? `覆盖${checkpointLabel(slot)}？原有存档将无法恢复。`
            : `Overwrite ${checkpointLabel(slot)}? Its current save cannot be recovered.`);
        if (!confirmed) return;
    }

    setSaveLoadBusy(true);
    setSaveLoadStatus(currentLang === 'zh' ? `正在保存${checkpointLabel(slot)}…` : `Saving ${checkpointLabel(slot)}…`);
    try {
        const data = await fetchJson('/api/save_game', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({slot, overwrite: Boolean(existing?.exists)})
        });
        saveSlotCatalog[slot] = data.slot;
        renderSaveSlot(data.slot);
        setSaveLoadStatus(currentLang === 'zh'
            ? `已手动保存到${checkpointLabel(slot)}。`
            : `${checkpointLabel(slot)} was saved manually.`, 'success');
        fetchState();
    } catch (error) {
        await refreshSaveSlots();
        setSaveLoadStatus((currentLang === 'zh' ? '保存失败：' : 'Save failed: ') + error.message, 'error');
    } finally {
        setSaveLoadBusy(false);
    }
}

async function loadGame(slot) {
    const slotInfo = saveSlotCatalog[slot];
    if (!slotInfo?.can_load) {
        setSaveLoadStatus(currentLang === 'zh' ? '此检查点当前无法恢复。' : 'This checkpoint cannot currently be restored.', 'error');
        return;
    }
    const confirmed = confirm(currentLang === 'zh'
        ? `恢复${checkpointLabel(slot)}？上次手动保存之后的所有更改都将丢失。恢复后推演会暂停。`
        : `Restore ${checkpointLabel(slot)}? All changes made after that manual save will be lost. The simulation will be paused.`);
    if (!confirmed) return;

    setSaveLoadBusy(true);
    setSaveLoadStatus(currentLang === 'zh' ? `正在恢复${checkpointLabel(slot)}…` : `Restoring ${checkpointLabel(slot)}…`);
    try {
        await fetchJson('/api/load_game', {
            method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ slot })
        });
        deselectUnit();
        await fetchState();
        setSaveLoadStatus(currentLang === 'zh'
            ? `已恢复${checkpointLabel(slot)}；推演保持暂停。`
            : `${checkpointLabel(slot)} restored; the simulation remains paused.`, 'success');
    } catch (error) {
        setSaveLoadStatus((currentLang === 'zh' ? '恢复失败：' : 'Restore failed: ') + error.message, 'error');
    } finally {
        setSaveLoadBusy(false);
    }
}

async function resetScenario() {
    const confirmed = confirm(currentLang === 'zh'
        ? '重置当前剧本？所有未手动保存的更改都会丢失，而且系统不会自动创建备份。'
        : 'Reset this scenario? All changes not manually saved will be lost, and no backup will be created automatically.');
    if (!confirmed) return;

    setSaveLoadBusy(true);
    setSaveLoadStatus(currentLang === 'zh' ? '正在恢复剧本初始状态…' : 'Restoring the scenario starting state…');
    try {
        await fetchJson('/api/reset_scenario', {method: 'POST'});
        deselectUnit();
        await fetchState();
        setSaveLoadStatus(currentLang === 'zh'
            ? '剧本已重置到 DLC 初始状态；未创建自动备份。'
            : 'Scenario reset to its DLC starting state; no automatic backup was created.', 'success');
    } catch (error) {
        setSaveLoadStatus((currentLang === 'zh' ? '重置失败：' : 'Reset failed: ') + error.message, 'error');
    } finally {
        setSaveLoadBusy(false);
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
        `<div class="committee-faction-row"><span>${escapeHtml(f.faction)}</span><span>${Number(f.active_personnel)} living personnel | morale ${Number(f.average_morale)}% | supply ${Number(f.average_supply)}% | sites ${Number(f.operational_installations || 0)} active / ${Number(f.construction_sites || 0)} building / ${Number(f.destroyed_installations || 0)} destroyed</span></div>`
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
