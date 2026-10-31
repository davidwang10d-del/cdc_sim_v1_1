// --- i18n Localization Dictionary ---
const currentLang = localStorage.getItem('cdc_lang') === 'zh' ? 'zh' : 'en';

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
        radar: "部队信息",
        altitude: "海拔",
        unmapped: "未知区域 / 平原",
        speed: "移动速度",
        status: "当前状态",
        personnel: "当前兵力",
        btn_relocate: "📍选择目的地",
        btn_stop: "🛑停止行动",
        sys_ready: "系统已就绪，请选择一支部队。"
    }
};

function t(key) {
    return i18n[currentLang][key] || key;
}

function uiText(english, chinese) {
    return currentLang === 'zh' ? chinese : english;
}

function apiResponseMessage(data, fallbackEnglish, fallbackChinese = fallbackEnglish) {
    if (currentLang === 'zh' && data?.msg_zh) return data.msg_zh;
    return data?.msg || uiText(fallbackEnglish, fallbackChinese);
}

const effectTypeLabelsZh = {
    none: '无机制效果',
    morale: '士气',
    supply: '补给',
    fatigue: '疲劳',
    suppression: '压制',
    personnel: '人员',
    combat_modifier: '战斗倍率',
    speed_modifier: '移动速度倍率',
};

function localizedEffectType(effect) {
    const key = String(effect || 'none');
    return currentLang === 'zh'
        ? (effectTypeLabelsZh[key] || key.replaceAll('_', ' '))
        : key.replaceAll('_', ' ');
}

const operationalStatusZh = {
    OPERATIONAL: '运行中',
    UNDER_CONSTRUCTION: '建造中',
    DESTROYED: '已摧毁',
    MOVING: '移动中',
    BOMBARDING: '炮击中',
    AIRSTRIKE_OUTBOUND: '空袭出航',
    AIRSTRIKE_RTB: '空袭返航',
    CONSTRUCTING: '施工中',
    IDLE: '待命',
    NEUTRALIZED: '失去战斗力',
    DEFENDING: '防御中',
    FORTIFYING: '正在加固阵地',
    ROUTING: '溃退中',
};

function localizedOperationalStatus(status) {
    const value = String(status || '');
    return currentLang === 'zh'
        ? (operationalStatusZh[value] || value.replaceAll('_', ' '))
        : value.replaceAll('_', ' ');
}

const engineEventPrefixZh = new Map([
    ['[System]', '[系统]'],
    ['[Chair Override]', '[主席修改]'],
    ['[Construction Started]', '[开始建造]'],
    ['[Construction Resumed]', '[恢复建造]'],
    ['[Installation Operational]', '[设施投入运行]'],
    ['[Military Target Located]', '[发现军事目标]'],
    ['[Military Target Destroyed]', '[摧毁军事目标]'],
    ['[Contact]', '[发现敌军]'],
    ['[Intel]', '[情报]'],
    ['[Contact Lost]', '[失去目标]'],
    ['[Contact Avoidance]', '[绕开敌军]'],
    ['[Radar Contact]', '[雷达发现敌军]'],
    ['[Radar Target]', '[雷达目标]'],
    ['[Relocate]', '[安全转移]'],
    ['[Relocate Queued]', '[安全转移已排队]'],
    ['[Assault]', '[进攻]'],
    ['[Assault Queued]', '[进攻已排队]'],
    ['[Planned Route]', '[按路线移动]'],
    ['[Planned Route Queued]', '[按路线移动已排队]'],
    ['[Stance]', '[战斗方式]'],
    ['[Fortify]', '[加固阵地]'],
    ['[Defend]', '[防御]'],
    ['[Airstrike]', '[空袭]'],
    ['[Bombardment]', '[炮击]'],
    ['[AA Net]', '[防空网]'],
    ['[Fire Mission]', '[火力任务]'],
    ['[Armed Mobilization]', '[武装动员]'],
    ['[Unit Neutralized]', '[单位失去战斗力]'],
    ['[River Crossing]', '[渡河]'],
    ['[Unopposed Fire]', '[抢先开火]'],
    ['[Close Combat]', '[近距离交战]'],
    ['[Diplomatic Radar]', '[外交动态]'],
    ['[Maneuver]', '[机动]'],
    ['[Air Force RTB]', '[空军返航]'],
    ['[Zone Alert]', '[区域警报]'],
    ['[Public Crisis Update]', '[公开危机更新]'],
    ['[Staff-only Crisis Update]', '[主席团内部危机更新]'],
]);

function localizedCoreDoctrineName(value) {
    if (currentLang !== 'zh') return String(value ?? '');
    const terms = {
        Aggressive: '进攻优先', Defensive: '防守优先', Stealth: '隐蔽行动', Recon: '侦察优先',
        Reserve: '休整待命', 'Hold Fire': '禁止远程开火', Hold: '原地待命', Relocate: '安全转移',
        'Planned Route': '按路线移动', Assault: '进攻', 'Defend Here': '原地防守', Fortify: '加固阵地',
    };
    return terms[String(value ?? '')] || String(value ?? '');
}

function localizedFireMissionDetail(value) {
    return String(value ?? '')
        .replace('firing unit neutralized', '开火单位已失去战斗力')
        .replace('planned duration elapsed', '计划持续时间已结束')
        .replace('ammunition reserve reached', '已达到弹药储备下限')
        .replace(/estimated casualties ([\d.]+)/g, '预计伤亡 $1 人')
        .replace(/military-target integrity damage ([\d.]+)/g, '军事目标完整度损失 $1')
        .replace(/installations destroyed ([\d.]+)/g, '摧毁设施 $1 处')
        .replace('no hostile target affected', '未影响任何敌对目标')
        .replaceAll('; ', '；');
}

function translateFixedEngineLogBody(text) {
    const directRules = [
        [/^(.*?\[系统\]) Suspending simulation\.$/, '$1 正在暂停推演。'],
        [/^(.*?\[系统\]) Resuming simulation\.$/, '$1 正在恢复推演。'],
        [/^(.*?\[系统\]) Simulation speed set to ([\d.]+)x\.$/, '$1 推演速度已设为 $2 倍。'],
        [/^(.*?\[系统\]) Initial tactical scenario \[(.*)\] loaded successfully\.$/, '$1 初始战术剧本 [$2] 已成功载入。'],
        [/^(.*?\[系统\]) Battle state manually saved to: \[(.*)\]\.$/, '$1 战斗状态已手动保存到：[$2]。'],
        [/^(.*?\[系统\]) Save file awakened: \[(.*)\]\.$/, '$1 已载入存档：[$2]。'],
        [/^(.*?\[进攻\]) (.*) is advancing through ranged contact and will halt only at close ground contact\.$/, '$1 $2 正在向目标进攻。即使遭到远程攻击也会继续前进，直到与敌军近距离交战。'],
        [/^(.*?\[按路线移动\]) (.*) received a holding-fire route with (\d+) waypoints\.$/, '$1 $2 收到一条包含 $3 个途经点的移动路线；途中不会主动远程开火。'],
        [/^(.*?\[安全转移\]) (.*) is moving to the objective without initiating ranged combat and will reroute around detected threats\.$/, '$1 $2 正在向目的地转移；途中不会主动远程开火，并会绕开已发现的敌军。'],
        [/^(.*?\[加固阵地\]) (.*) began accelerated fieldwork construction in (.*) stance; supply and fatigue costs are active\.$/, (match, prefix, unit, stance) => `${prefix} ${unit} 以“${localizedCoreDoctrineName(stance)}”方式开始快速加固阵地；这会消耗补给并增加疲劳。`],
        [/^(.*?\[防御\]) (.*) began preparing its position in (.*) stance\.$/, (match, prefix, unit, stance) => `${prefix} ${unit} 开始以“${localizedCoreDoctrineName(stance)}”方式准备防守。`],
        [/^(.*?\[战斗方式\]) (.*) changed to (.*) while retaining its (.*) order\.$/, (match, prefix, unit, stance, order) => `${prefix} ${unit} 已改为“${localizedCoreDoctrineName(stance)}”，当前“${localizedCoreDoctrineName(order)}”任务不变。`],
        [/^(.*?\[主席修改\]) (.*) was updated by crisis staff\.$/, '$1 危机主席团已更新 $2。'],
        [/^(.*?\[主席修改\]) City influence area \[(.*)\] was removed\.$/, '$1 已删除城市影响区 [$2]。'],
        [/^(.*?\[主席修改\]) Political record for \[(.*)\] in \[(.*)\] was removed\.$/, '$1 已删除 [$3] 中 [$2] 的政治记录。'],
        [/^(.*?\[设施投入运行\]) (.*) is complete and active\.$/, '$1 $2 已完工并投入运行。'],
        [/^(.*?\[单位失去战斗力\]) (.*) was neutralized by an airstrike\.$/, '$1 $2 已被空袭摧毁战斗力。'],
        [/^(.*?\[单位失去战斗力\]) (.*) was neutralized by bombardment\.$/, '$1 $2 已被炮击摧毁战斗力。'],
        [/^(.*?\[单位失去战斗力\]) (.*) is no longer combat effective\.$/, '$1 $2 已失去战斗力。'],
        [/^(.*?\[抢先开火\]) (.*) engaged (.*) before the opposing unit acquired contact\.$/, '$1 $2 在对方发现自己之前抢先向 $3 开火。'],
        [/^(.*?\[近距离交战\]) (.*) and (.*) entered direct combat\.$/, '$1 $2 与 $3 已开始近距离交战。'],
        [/^(.*?\[渡河\]) (.*) met fierce resistance while crossing the river!$/, '$1 $2 渡河时遭到猛烈抵抗！'],
        [/^(.*?\[雷达发现敌军\]) (.*) acquired (.*)\.$/, '$1 $2 已发现 $3。'],
        [/^(.*?\[雷达目标\]) (.*) located (.*)\.$/, '$1 $2 已定位 $3。'],
        [/^(.*?\[失去目标\]) (.*) vanished into the fog of war\.$/, '$1 已无法继续追踪 $2。'],
        [/^(.*?\[机动\]) (.*) reached designated coordinates\.$/, '$1 $2 已抵达指定坐标。'],
        [/^(.*?\[空军返航\]) (.*) returned to base\.$/, '$1 $2 已返回基地。'],
        [/^(.*?\[区域警报\]) (.*) crossed the border into (.*)\.$/, '$1 $2 已越过边界进入 $3。'],
    ];
    for (const [pattern, replacement] of directRules) {
        if (pattern.test(text)) return text.replace(pattern, replacement);
    }

    let match = text.match(/^(.*?\[空袭\]) (.*) \((.*); (.*)\) launched for coordinates ([-\d.]+), ([-\d.]+) \(([\d.]+) km\); munitions committed and profile-adjusted AA exposure active\.$/);
    if (match) return `${match[1]} ${match[2]}（${match[3]}；${match[4]}）已飞往坐标 ${match[5]}, ${match[6]}（${match[7]} km）；弹药已投入，返航前持续承受该配置的防空威胁。`;
    match = text.match(/^(.*?\[炮击\]) (.*) opened a ([\d.]+)-hour fire mission on coordinates ([-\d.]+), ([-\d.]+) \(([\d.]+) km\)\.$/);
    if (match) return `${match[1]} ${match[2]} 已对坐标 ${match[4]}, ${match[5]}（${match[6]} km）发起为时 ${match[3]} 小时的火力任务。`;
    match = text.match(/^(.*?\[武装动员\]) (.*) \(Equipment: (.*)\) arrived in the theater at ([-\d.]+) meters\.$/);
    if (match) return `${match[1]} ${match[2]}（装备：${match[3]}）已抵达战区，海拔 ${match[4]} 米。`;
    match = text.match(/^(.*?\[主席修改\]) (.*) applied to (.*): (.*) x([-\d.]+) for ([\d.]+) hours\.$/);
    if (match) return `${match[1]} 已向 ${match[3]} 应用“${match[2]}”：${match[4]} ×${match[5]}，持续 ${match[6]} 小时。`;
    match = text.match(/^(.*?\[主席修改\]) City \[(.*)\] (created|updated): area ([\d.]+) km², influence ([-\d.]+)\.$/);
    if (match) return `${match[1]} 城市 [${match[2]}] 已${match[3] === 'created' ? '创建' : '更新'}：面积 ${match[4]} km²，影响率 ${match[5]}。`;
    match = text.match(/^(.*?\[主席修改\]) Civilian sentiment toward \[(.*)\] in \[(.*)\] set to ([-\d.]+); occupation ([-\d.]+)\.$/);
    if (match) return `${match[1]} 已将 [${match[3]}] 对 [${match[2]}] 的民意设为 ${match[4]}；占领度 ${match[5]}。`;
    match = text.match(/^(.*?\[外交动态\]) (.*) and (.*) (signed|abrogated) a bilateral non-aggression pact\.$/);
    if (match) return `${match[1]} ${match[2]} 与 ${match[3]} ${match[4] === 'signed' ? '签署了' : '废除了'}双边互不侵犯协定。`;
    match = text.match(/^(.*?\[恢复建造\]) (.*) resumed work on (.*)\.$/);
    if (match) return `${match[1]} ${match[2]} 已恢复建造 ${match[3]}。`;
    match = text.match(/^(.*?\[开始建造\]) (.*) began (.*) at ([-\d.]+), ([-\d.]+); planned duration ([\d.]+) hours\.$/);
    if (match) return `${match[1]} ${match[2]} 已在 ${match[4]}, ${match[5]} 开始建造 ${match[3]}；计划工期 ${match[6]} 小时。`;
    match = text.match(/^(.*?\[摧毁军事目标\]) (.*) was destroyed by (.*) \((.*)\)\.$/);
    if (match) {
        const attackKindZh = {'direct fire': '直接火力', airstrike: '空袭', bombardment: '炮击'};
        return `${match[1]} ${match[2]} 已被 ${match[3]} 摧毁（${attackKindZh[match[4]] || match[4]}）。`;
    }
    match = text.match(/^(.*?\[绕开敌军\]) (.*) rerouted around (.*) while retaining its original destination\.$/);
    if (match) return `${match[1]} ${match[2]} 已重新规划路线，绕开 ${match[3].replace(/ and (\d+) more$/, ' 及另外 $1 个目标')}，同时保留原目的地。`;
    match = text.match(/^(.*?\[情报\]) (.*) saw through concealment and acquired (.*)\.$/);
    if (match) return `${match[1]} ${match[2]} 识破了 ${match[3]} 的隐蔽并发现该部队。`;
    match = text.match(/^(.*?\[发现敌军\]) (.*)'s vanguard radar detected the outline of (.*)\.$/);
    if (match) return `${match[1]} ${match[2]} 的前沿侦察发现了 ${match[3]}。`;
    match = text.match(/^(.*?\[发现军事目标\]) (.*) identified (.*) \((.*)\)\.$/);
    if (match) return `${match[1]} ${match[2]} 已识别 ${match[3]}（${match[4]}）。`;
    match = text.match(/^(.*?\[火力任务\]) (.*) ceased fire: (.*?); (.*)\.$/);
    if (match) return `${match[1]} ${match[2]} 已停止射击：${localizedFireMissionDetail(match[3])}；${localizedFireMissionDetail(match[4])}。`;
    match = text.match(/^(.*?\[(公开危机更新|主席团内部危机更新)\]) (.*) \((.*), ([\d.]+) units affected\)$/);
    if (match) return `${match[1]} ${match[3]}（${match[4]}，影响 ${match[5]} 支部队）`;
    return text;
}

function localizeEngineLogMessage(message) {
    const text = String(message ?? '');
    if (currentLang !== 'zh') return text;
    let localized = text;
    const prefixStart = localized.indexOf('[');
    const prefixEnd = localized.indexOf(']', prefixStart + 1);
    if (prefixStart >= 0 && prefixEnd > prefixStart) {
        const prefix = localized.slice(prefixStart, prefixEnd + 1);
        const translated = engineEventPrefixZh.get(prefix);
        if (translated) {
            localized = localized.slice(0, prefixStart) + translated + localized.slice(prefixEnd + 1);
        }
    }
    return translateFixedEngineLogBody(localized);
}

const coreOrderTextZh = {
    hold: {
        label: '原地待命',
        summary: '停止移动 · 留在原地',
        description: '取消当前移动，让部队留在原地。当前战斗方式不会改变。',
    },
    relocate: {
        label: '安全转移',
        summary: '一个目的地 · 自动避敌',
        description: '选择一个目的地。部队途中不会主动远程开火，并会尽量绕开已经发现的敌军；敌军逼近时仍会自卫。',
    },
    route: {
        label: '按路线移动',
        summary: '多个途经点 · 不主动交战',
        description: '依次经过你选择的多个地点。途中不会主动远程开火；敌军逼近时仍会自卫。',
    },
    assault: {
        label: '进攻',
        summary: '向目标推进 · 主动攻击',
        description: '选择一个进攻目标。部队会主动攻击已经发现的敌军，并在近距离遇敌时停下交战。',
    },
    defend: {
        label: '原地防守',
        summary: '停止移动 · 准备防守',
        description: '让部队留在当前位置休整，并逐步加强临时防御。当前战斗方式不会改变。',
    },
    fortify: {
        label: '加固阵地',
        summary: '停止移动 · 快速加强防御',
        description: '让部队留在原地并快速加强临时防御。这会消耗补给、增加疲劳，但不会改变当前战斗方式。',
    },
};

const coreStanceTextZh = {
    AGGRESSIVE: {
        label: '进攻优先',
        description: '提高攻击能力并主动开火，但更容易被敌军发现。',
    },
    DEFENSIVE: {
        label: '防守优先',
        description: '加强防护并减少暴露，同时保持正常开火能力。',
    },
    STEALTH: {
        label: '隐蔽行动',
        description: '降低移动和战斗能力，换取更低的被发现概率。',
    },
    RECON: {
        label: '侦察优先',
        description: '提高移动和发现敌军的能力，但战斗能力会降低。',
    },
    RESERVE: {
        label: '休整待命',
        description: '加快恢复并保存实力，但移动和战斗能力较低。',
    },
    HOLD_FIRE: {
        label: '禁止远程开火',
        description: '不进行远程射击；如果敌军逼近，部队仍会近距离自卫。',
    },
};

function localizedStanceProfile(stanceId, profile = {}) {
    if (currentLang !== 'zh') return profile;
    return {...profile, ...(coreStanceTextZh[String(stanceId)] || {})};
}

function orderProfileByRole(role) {
    const profile = globalRules.orders?.modes?.[role] || {
        id: role.toUpperCase(), label: role, summary: '', description: '', color: '#8b949e'
    };
    if (currentLang !== 'zh') return profile;
    return {...profile, ...(coreOrderTextZh[String(role)] || {})};
}

function orderProfileForUnit(unit) {
    const match = Object.entries(globalRules.orders?.modes || {})
        .find(([, profile]) => profile.id === unit.order_mode);
    return match
        ? orderProfileByRole(match[0])
        : orderProfileByRole(globalRules.orders?.default_role || 'hold');
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

const NEARBY_SELECTION_RADIUS_KM = 5;

function buildNearbyMapSelectionCandidates(
    units,
    installations,
    centerLon,
    centerLat,
    preferredKind = '',
    preferredId = '',
    radiusKm = NEARBY_SELECTION_RADIUS_KM
) {
    const longitude = Number(centerLon);
    const latitude = Number(centerLat);
    const maximumDistance = Math.max(0, Number(radiusKm));
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude) || !Number.isFinite(maximumDistance)) return [];

    const candidates = [];
    const addCandidate = (kind, id, entity) => {
        const entityLon = Number(entity?.lon);
        const entityLat = Number(entity?.lat);
        if (!Number.isFinite(entityLon) || !Number.isFinite(entityLat)) return;
        const distanceKm = mapDistanceKm(longitude, latitude, entityLon, entityLat);
        if (distanceKm > maximumDistance + 1e-9) return;
        candidates.push({
            kind,
            id: String(id),
            name: String(entity?.name || id),
            distanceKm,
            entity,
        });
    };

    Object.entries(units || {}).forEach(([unitId, unit]) => {
        if (Number(unit?.personnel) <= 0) return;
        addCandidate('unit', unitId, unit);
    });
    Object.entries(installations || {}).forEach(([installationId, installation]) => {
        addCandidate('installation', installationId, installation);
    });

    return candidates.sort((first, second) => {
        const firstPreferred = first.kind === preferredKind && first.id === String(preferredId);
        const secondPreferred = second.kind === preferredKind && second.id === String(preferredId);
        if (firstPreferred !== secondPreferred) return firstPreferred ? -1 : 1;
        if (Math.abs(first.distanceKm - second.distanceKm) > 1e-9) return first.distanceKm - second.distanceKm;
        if (first.kind !== second.kind) return first.kind === 'unit' ? -1 : 1;
        return first.name.localeCompare(second.name) || first.id.localeCompare(second.id);
    });
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
    if (!Number.isFinite(hours) || hours < 0) return uiText('ETA unavailable', '预计时间不可用');
    if (hours >= 24) return uiText(`${(hours / 24).toFixed(1)} simulation days`, `${(hours / 24).toFixed(1)} 个推演日`);
    if (hours >= 1) return uiText(`${hours.toFixed(1)} simulation hours`, `${hours.toFixed(1)} 个推演小时`);
    return uiText(`${Math.max(1, Math.ceil(hours * 60))} simulation minutes`, `${Math.max(1, Math.ceil(hours * 60))} 个推演分钟`);
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
        label: profile.label || typeId || uiText('DLC default aircraft', '剧本默认飞机'),
        description: profile.description || uiText('Uses the mounted DLC airstrike baseline.', '使用当前剧本的默认空袭参数。'),
        attack_profile: profile.attack_profile || uiText('Tactical strike', '战术打击'),
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

document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeNearbySelectionMenu();
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
    catch (_) {
        throw new Error(uiText(
            `The server returned an unreadable response (${response.status}).`,
            `服务器返回了无法读取的响应（${response.status}）。`
        ));
    }
    if (!response.ok || data.status === 'error') {
        throw new Error(apiResponseMessage(
            data,
            `Request failed (${response.status}).`,
            `请求失败（${response.status}）。`
        ));
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

// Commercial builds use a generated local grid plus scenario-owned GIS files.
// No third-party tile service is contacted by the runtime.
const localBasemap = leafletReady ? createLocalGridBasemap() : null;

// 🟢 2. System Boot: Scan and Mount DLCs
window.onload = function() {
    if (!leafletReady) {
        document.getElementById('dlc-list-container').innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">${uiText('Map library unavailable. Repair or reinstall CDC Sim, then reload.', '地图组件不可用。请修复或重新安装 CDC Sim，然后重新加载。')}<br><a href="/status" style="color:#58a6ff;">${uiText('Open readiness check', '打开就绪检查')}</a></div>`;
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
    localBasemap.addTo(map);
    map.attributionControl = L.control.attribution({position: 'bottomleft', prefix: false}).addTo(map);
    L.control.scale({ position: 'bottomleft', metric: true, imperial: false }).addTo(map);
    loadDlcList();
};

async function loadDlcList() {
    const container = document.getElementById('dlc-list-container');
    try {
        const dlcs = await fetchJson('/api/list_dlcs');
        container.replaceChildren();
        if (dlcs.length === 0) {
            container.innerHTML = `<div style="color:#ff7b72; text-align:center;">${uiText('No DLC detected. Place a package in the dlc directory or use the DLC Builder.', '没有找到可用剧本。请把剧本包放入 dlc 文件夹，或使用剧本编辑器创建剧本。')}</div>`;
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
        container.innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">${uiText('DLC scan failed:', '读取剧本列表失败：')} ${escapeHtml(error.message)}</div>`;
    }
}

function resetMountedMap() {
    closeNearbySelectionMenu();
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
    summary.textContent = `${mountedGisStatus.enabled_count || 0}/${features.length} ${uiText('ON', '已启用')}`;
    list.replaceChildren();
    for (const feature of features) {
        const text = gisFeatureText(feature, mountedGisStatus.fallback_elevation_m ?? 0);
        const row = document.createElement('div');
        row.className = `gis-feature-row${feature.enabled ? '' : ' off'}${feature.configured && !feature.enabled ? ' warning' : ''}`;
        row.title = currentLang === 'zh' ? text.detail : (feature.warning || feature.detail || text.detail);

        const heading = document.createElement('div');
        heading.className = 'gis-feature-heading';
        const label = document.createElement('span');
        label.textContent = text.label;
        const badge = document.createElement('span');
        badge.className = 'gis-feature-badge';
        badge.textContent = feature.enabled ? uiText('ON', '启用') : uiText('OFF · DEFAULT', '关闭 · 默认');
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
            : (currentLang === 'zh' ? '🛣️ 路网不可用' : '🛣️ Roads OFF');
    }
}

async function mountDLC(dlcId) {
    document.getElementById('dlc-list-container').innerHTML = `<div style="color:#e3b341; text-align:center; padding:20px;">${uiText('[ MOUNTING CORE MODULES... ]', '正在加载剧本…')}<br>${uiText('Loading campaign data...', '正在读取地图和部队数据…')}</div>`;
    
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
        document.title = uiText('CDC Command Radar - ', 'CDC 指挥地图 - ') + res.config.name;

        const [registry, geojson] = await Promise.all([fetchJson('/api/registry'), fetchJson('/geojson')]);
        globalWeapons = registry.weapons;
        globalBattalions = registry.battalions;
        globalRules = registry.rules;
        updateRuleDrivenUI();
        updateDeployUI();
        if (geojson.type === 'FeatureCollection' && geojson.features?.length) {
            geojsonLayer = L.geoJSON(geojson, {
                style: styleProvince,
                onEachFeature: (feature, layer) => layer.bindTooltip(provincePoliticsTooltip(feature.properties?.cdc_name || uiText('Unknown', '未知')))
            }).addTo(map);
        }

        document.getElementById('bootloader-screen').style.display = 'none';
        await fetchState();
        fetchCommitteeState();
        heartbeatInterval = setInterval(fetchState, 1000);
        setupMapClicks();
    } catch (error) {
        const container = document.getElementById('dlc-list-container');
        container.innerHTML = `<div style="color:#ff7b72; text-align:center; padding:20px;">${uiText('Mount failed:', '剧本加载失败：')} ${escapeHtml(error.message)}<br><button class="cmd-btn" id="retry-dlc-list" style="margin-top:12px;">${uiText('Back to scenarios', '返回剧本列表')}</button></div>`;
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
    if (maximumSpeedButton) maximumSpeedButton.textContent = `${clock.speed_multiplier_max}X ${uiText('MAX', '最大')}`;

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
            option.textContent = effect === 'none'
                ? uiText('No mechanical effect', '无机制效果')
                : (currentLang === 'zh' ? localizedEffectType(effect) : effect.replaceAll('_', ' '));
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
            item.title = uiText(`Base Complement: ${size} personnel`, `基础编制：${size} 人`);
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
        : uiText('none', '无');
    help.textContent = uiText(
        `Role: ${profile.label || typeId} · Built-in capabilities: ${capabilities}`,
        `角色：${profile.label || typeId} · 内置能力：${capabilities}`
    );
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
    help.textContent = uiText(
        `${profile.attack_profile}: ${profile.description} Cruise ${cruiseSpeed.toFixed(0)} km/h · range ${range.toFixed(0)} km · effect radius ${radius.toFixed(1)} km.`,
        `${profile.attack_profile}：${profile.description} 巡航 ${cruiseSpeed.toFixed(0)} km/h · 航程 ${range.toFixed(0)} km · 效果半径 ${radius.toFixed(1)} km。`
    );
}

// 🟢 3. Core Radar and Interaction Logic
function toggleHistoricRoads() {
    const roadFeature = mountedGisStatus?.features?.find(feature => feature.id === 'roads');
    if (!roadFeature?.enabled) return;
    roadsVisible = !roadsVisible;
    const btn = document.getElementById('btn-toggle-roads');
    if (!roadsVisible) {
        if (roadLayer) map.removeLayer(roadLayer);
        btn.classList.remove('active'); btn.style.borderColor = ""; btn.style.color = ""; return;
    }
    btn.classList.add('active'); btn.style.borderColor = "#ff4444"; btn.style.color = "#ff7b72"; btn.innerHTML = uiText("⏳ Scanning...", "⏳ 正在扫描…");
    fetchJson('/api/roads_overlay').then(data => {
        if (roadLayer) map.removeLayer(roadLayer);
        roadLayer = L.geoJSON(data, { pointToLayer: function (feature, latlng) { return L.circleMarker(latlng, { radius: 1, fillColor: "#ff0000", color: "#ff0000", weight: 1, opacity: 0.6, fillOpacity: 0.8 }); } }).addTo(map);
        btn.innerHTML = uiText("🛣️ Roads", "🛣️ 路网");
    }).catch(() => { btn.innerHTML = uiText("❌ Load Failed", "❌ 加载失败"); roadsVisible = false; });
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
    document.getElementById('dep-pop-display').innerText = totalPop + uiText(" Personnel", " 人");
    document.getElementById('dep-personnel').value = totalPop;
    const weaponDisplay = document.getElementById('dep-weapons-display');
    if (weaponDisplay) {
        const descriptions = Object.entries(weaponTotals)
            .filter(([, quantity]) => quantity > 0)
            .map(([weaponId, quantity]) => {
                const weapon = globalWeapons[weaponId] || {};
                const bands = Array.isArray(weapon.range_bands) ? weapon.range_bands : [];
                const maximumRange = bands.length ? Number(bands[bands.length - 1].max_range_km || 0) : 0;
                return `${quantity.toFixed(Number.isInteger(quantity) ? 0 : 2)}× ${weapon.name || weaponId} · ${uiText('Gen', '代数')} ${Number(weapon.generation || 0)} · ${maximumRange.toFixed(1)} km`;
            });
        weaponDisplay.textContent = descriptions.length
            ? descriptions.join(' | ')
            : uiText('No weapon groups are mounted by the selected battalions.', '所选营未装备任何武器组。');
    }
}

function enableDeployTargeting() {
    const personnel = Number(document.getElementById('dep-personnel').value);
    const hasBattalion = Object.keys(globalBattalions).some(key => Number(document.getElementById(`dep-${key}`)?.value) > 0);
    if (!Number.isFinite(personnel) || personnel <= 0 || !hasBattalion) {
        alert(uiText(
            'Choose at least one battalion and deploy at least one person before selecting a drop zone.',
            '请至少选择一个营并部署一名人员，然后再选择投放区域。'
        ));
        return;
    }
    closeNearbySelectionMenu();
    isDeploying = true;
    document.getElementById('targeting-alert').style.display = "block";
    document.getElementById('targeting-alert').innerText = uiText(
        '[ AIRDROP INITIATED ] Click on the map to deploy armed forces...',
        '[ 已启动空投 ] 点击地图部署武装部队…'
    );
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
    const actionLabel = aircraft
        ? uiText(`Airstrike — ${aircraft.label}`, `空袭 — ${aircraft.label}`)
        : (profile?.label || String(action).toUpperCase());
    if (title) {
        title.textContent = currentLang === 'zh'
            ? `⚠️ 确认执行：${actionLabel}`
            : `⚠️ AUTHORIZE ${actionLabel.toUpperCase()}`;
    }
    if (instruction) {
        const instructions = currentLang === 'zh'
            ? {
                relocate: '确认目的地。部队会尽量绕开已经发现的敌军，途中不会主动远程开火；敌军逼近时仍会自卫。',
                route: '继续点击地图添加途经点；路线完成后点击“确认执行”。',
                attack: '确认进攻目标。部队会向目标推进并主动攻击敌军，近距离遇敌时会停下交战。',
                bombard: `确认坐标后开始持续 ${Number(globalRules.missions?.bombard?.duration_hours || 0).toFixed(1)} 小时的区域炮击。当前移动路线会被取消；尚未发现的部队也可能被击中，但命中率较低。`,
                airstrike: `确认 ${aircraft?.label || '飞机'} 的目标坐标。可攻击陆军、炮兵和停在基地的空军；不能攻击正在出击或返航的飞机。起飞会消耗 ${Number(aircraft?.supply_cost || 0).toFixed(1)}% 补给并增加 ${Number(aircraft?.fatigue_cost || 0).toFixed(1)}% 疲劳；投弹后飞机会返航。`
            }
            : {
                relocate: 'Confirm the single destination below. Relocate withholds initiating ranged fire and preserves the destination while rerouting around detected threats to the remaining path.',
                route: 'Keep clicking the map to add waypoints, then authorize the complete route.',
                attack: 'Confirm the assault destination. The unit keeps closing through ranged fire and stops only when a detected hostile blocks it at close ground contact.',
                bombard: `Confirm coordinates for a ${Number(globalRules.missions?.bombard?.duration_hours || 0).toFixed(1)}-hour area bombardment. The old movement route is cancelled; unobserved formations can still be hit at reduced accuracy.`,
                airstrike: `Confirm coordinates for the ${aircraft?.label || 'aircraft'}. Armies, artillery, and air wings parked at base are valid ground targets; outbound or returning aircraft are not. ${Number(aircraft?.supply_cost || 0).toFixed(1)}% supply and ${Number(aircraft?.fatigue_cost || 0).toFixed(1)}% fatigue are committed at takeoff; profile-specific air-defense exposure applies until it returns.`
            };
        instruction.textContent = instructions[action] || (currentLang === 'zh' ? '确认目标无误后再执行。' : 'Confirm the target before authorization.');
    }

    panel.style.display = 'block';
    positionConfirmationPanel();
    requestAnimationFrame(positionConfirmationPanel);
}

window.addEventListener('resize', positionConfirmationPanel);

function setTargetingMode(actionStr) {
    closeNearbySelectionMenu();
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
    const routeHint = action === 'route'
        ? uiText(' Click once for each waypoint, then authorize.', ' 依次点击途经点，完成后确认执行。')
        : uiText(' Click the destination, review, then authorize.', ' 点击目的地，检查后确认执行。');
    document.getElementById('targeting-alert').style.display = "block";
    document.getElementById('targeting-alert').innerText = `${profile.label.toUpperCase()}: ${profile.description}${routeHint}`;
}

function setupMapClicks() {
    if (mapClickHandler) map.off('click', mapClickHandler);
    mapClickHandler = async function(e) {
        closeNearbySelectionMenu();
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
                alert(uiText(
                    'Enter a unit name, faction, positive personnel count, and at least one battalion.',
                    '请输入单位名称、阵营、正数人员数量，并至少选择一个营。'
                ));
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
                alert(uiText(
                    `✅ ${created.unit.name} deployed with ${Math.floor(created.unit.personnel)} personnel. The new map symbol is selected.`,
                    `✅ ${created.unit.name} 已部署 ${Math.floor(created.unit.personnel)} 人。新的地图标记已选中。`
                ));
            } catch (error) {
                alert(uiText("HQ Rejected: ", "指挥部拒绝：") + error.message);
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
            authorizeButton.title = outOfRange
                ? uiText(
                    `Target is ${targetDistance.toFixed(1)} km away; maximum range is ${maximumRange.toFixed(1)} km.`,
                    `目标距离为 ${targetDistance.toFixed(1)} km；最大射程为 ${maximumRange.toFixed(1)} km。`
                )
                : '';
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
            ? uiText(
                `${draftProfile.label.toUpperCase()} (${draftedWaypoints.length} waypoint${draftedWaypoints.length === 1 ? '' : 's'}): ${draftProfile.description}`,
                `${draftProfile.label}（${draftedWaypoints.length} 个途经点）：${draftProfile.description}`
            )
            : (pendingAction === 'bombard'
                ? uiText(
                    `BOMBARD AREA (${Number(missionRules?.duration_hours || 0).toFixed(1)} h)`,
                    `区域炮击（${Number(missionRules?.duration_hours || 0).toFixed(1)} 小时）`
                )
                : (pendingAction === 'airstrike'
                    ? uiText(
                        `${String(missionPerformance?.label || 'AIRSTRIKE').toUpperCase()} SORTIE`,
                        `${String(missionPerformance?.label || '空袭')} 出击`
                    )
                    : `${draftProfile.label.toUpperCase()}: ${draftProfile.description}`));
        document.getElementById('draft-type').innerText = typeStr;
        let coordsText = pendingAction === 'route'
            ? uiText(
                `DEST LON: ${tLon.toFixed(4)} | LAT: ${tLat.toFixed(4)}`,
                `目的地经度：${tLon.toFixed(4)} | 纬度：${tLat.toFixed(4)}`
            )
            : uiText(
                `LON: ${tLon.toFixed(4)} | LAT: ${tLat.toFixed(4)}`,
                `经度：${tLon.toFixed(4)} | 纬度：${tLat.toFixed(4)}`
            );
        const missionAssessment = isSupportMission
            ? `<br><span class="mission-target-${outOfRange ? 'invalid' : 'valid'}">${uiText('Distance', '距离')} ${targetDistance.toFixed(1)} / ${maximumRange.toFixed(1)} km · ${uiText('Effect radius', '效果半径')} ${blastRadius.toFixed(1)} km${outOfRange ? uiText(' · OUT OF RANGE', ' · 超出射程') : ''}</span>`
            : '';
        const coordinateSummary = `${coordsText}${missionAssessment}`;
        document.getElementById('draft-coords').innerHTML = `${coordinateSummary}<br><span style="color:#e3b341; font-size:12px;">${uiText('Scanning destination topography...', '正在扫描目的地区域地形…')}</span>`;
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
            const terrainLabel = res.complexity > 0.6
                ? uiText('🏔️ Mountains', '🏔️ 山地')
                : (res.complexity > 0.3 ? uiText('⛰️ Hills', '⛰️ 丘陵') : uiText('🛣️ Plains', '🛣️ 平原'));
            document.getElementById('draft-coords').innerHTML = `${coordinateSummary}<br><span style="color:#8b949e; font-size:12px;">${uiText('Dest. Topography:', '目的地区域地形：')} ${terrainLabel} (${uiText('Drag', '阻力')}: ${res.complexity})</span>`;
        } catch (error) {
            if (!isCurrentTarget()) return;
            document.getElementById('draft-coords').innerHTML = `${coordinateSummary}<br><span style="color:#ff7b72; font-size:12px;">${uiText('Terrain unavailable:', '地形数据不可用：')} ${escapeHtml(error.message)}</span>`;
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
            if (statusSpan) statusSpan.title = apiResponseMessage(result, '', '');
        }
    } catch (error) {
        alert(uiText("Command rejected: ", "指令被拒绝：") + error.message);
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
        alert(uiText('Command rejected: ', '指令被拒绝：') + error.message);
        return null;
    }
}

function deselectUnit() {
    closeNearbySelectionMenu();
    selectedUnitId = null;
    selectedInstallationId = null;
    selectedUnitLon = null;
    selectedUnitLat = null;
    clearDraft();
    if (pathLine) {
        map.removeLayer(pathLine);
        pathLine = null;
    }
    document.getElementById('unit-info').innerHTML = `<div style="color: #8b949e; font-style: italic; text-align: center; padding: 30px 0;">${uiText('[ RADAR SCANNING ]', '[ 雷达扫描中 ]')}<br>${uiText('Awaiting Commander to select a unit or military target...', '等待指挥官选择单位或军事目标…')}</div>`;
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
    const provName = feature.properties?.cdc_name || uiText('Unknown', '未知');
    const appearance = provincePoliticalAppearance(provName);
    return {
        className: 'province-boundary',
        fillColor: appearance.color,
        weight: 1,
        opacity: 0.3,
        color: '#1f6feb',
        fillOpacity: appearance.opacity,
    };
}

function provincePoliticsTooltip(provinceName) {
    const state = provincePolitics[provinceName];
    if (!state) return `<b>${escapeHtml(provinceName)}</b><br>${uiText('Neutral / no political record', '中立 / 无政治记录')}`;
    const status = state.contested
        ? uiText('CONTESTED', '争夺中')
        : (state.controller
            ? uiText(`Controlled by ${state.controller}`, `由 ${state.controller} 控制`)
            : uiText('No established control', '尚未建立控制'));
    const rows = Object.entries(state.factions || {}).map(([faction, record]) => {
        const presence = Math.round(Number(record.military_presence || 0) * 100);
        const strength = Math.round(Number(record.force_strength || 0) * 100);
        return uiText(
            `${escapeHtml(faction)}: presence ${presence}% (force ${strength}%), sentiment ${Number(record.civilian_sentiment).toFixed(2)}, occupation ${Number(record.occupation).toFixed(2)}, influence ${Number(record.influence).toFixed(2)}`,
            `${escapeHtml(faction)}：驻军 ${presence}%（兵力 ${strength}%），民意 ${Number(record.civilian_sentiment).toFixed(2)}，占领度 ${Number(record.occupation).toFixed(2)}，影响力 ${Number(record.influence).toFixed(2)}`
        );
    }).join('<br>');
    return `<b>${escapeHtml(provinceName)}</b> · ${escapeHtml(status)}${rows ? `<br>${rows}` : ''}`;
}

function updateProvincePoliticalLayers() {
    if (!geojsonLayer) return;
    geojsonLayer.setStyle(styleProvince);
    geojsonLayer.eachLayer(layer => {
        const provinceName = layer.feature?.properties?.cdc_name || uiText('Unknown', '未知');
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

function showConnectionBanner(message = '') {
    const banner = document.getElementById('connection-banner');
    const text = document.getElementById('connection-banner-message');
    if (!banner || !text) return;
    text.textContent = message || (currentLang === 'zh'
        ? '与本地推演程序的连接已中断。操作可能尚未保存。'
        : 'Connection to the local simulator was lost. Your latest action may not be saved.');
    banner.hidden = false;
}

function clearConnectionBanner() {
    const banner = document.getElementById('connection-banner');
    if (banner) banner.hidden = true;
}

function fetchState() {
    const requestSequence = ++stateRequestSequence;
    return fetchJson('/api/state').then(data => {
        if (requestSequence < latestAppliedStateRequest) return;
        latestAppliedStateRequest = requestSequence;
        clearConnectionBanner();
        if(data.status === "unmounted") return;
        latestUnits = data.units || {};
        latestInstallations = data.installations || {};
        simulationPaused = Boolean(data.time.paused);
        const pad = (n) => (n||0).toString().padStart(2, '0');
        document.getElementById('time-display').innerText = `D${pad(data.time.day)} ${pad(data.time.hour)}:${pad(data.time.minute)}:${pad(data.time.second)}`;
        const statusSpan = document.getElementById('pause-status');
        if (data.time.paused) { statusSpan.innerText = uiText('[ PAUSED ]', '[ 已暂停 ]'); statusSpan.style.color = '#ff7b72'; }
        else { statusSpan.innerText = uiText(`[ RUNNING ${data.time.multiplier}X ]`, `[ 运行中 ${data.time.multiplier}X ]`); statusSpan.style.color = '#7ee787'; }

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
            document.getElementById('unit-info').innerHTML = `<div style="color: #ff7b72; font-weight: bold; text-align: center; padding: 30px 0;">${uiText('[ SIGNAL LOST ]', '[ 信号丢失 ]')}</div>`;
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
            document.getElementById('unit-info').innerHTML = `<div style="color: #ff7b72; font-weight: bold; text-align: center; padding: 30px 0;">${uiText('[ MILITARY TARGET RECORD LOST ]', '[ 军事目标记录丢失 ]')}</div>`;
        }
        updateZeusTarget(selectedUnitId ? data.units[selectedUnitId] : null);
    }).catch(error => {
        if (requestSequence < latestAppliedStateRequest) return;
        const statusSpan = document.getElementById('pause-status');
        if (statusSpan) {
            statusSpan.innerText = uiText('[ CONNECTION LOST ]', '[ 连接中断 ]');
            statusSpan.style.color = '#ff7b72';
            statusSpan.title = error.message;
        }
        showConnectionBanner((currentLang === 'zh' ? '本地推演程序连接失败：' : 'Local simulator connection failed: ') + error.message);
    });
}

async function downloadSessionBackup() {
    setSaveLoadBusy(true);
    setSaveLoadStatus(currentLang === 'zh' ? '正在创建备份…' : 'Creating backup…');
    try {
        const response = await fetch('/api/session_backup', {
            method: 'POST', headers: {'X-CDC-Requested-With': 'CDC-Sim-UI'}
        });
        if (!response.ok) {
            let message = uiText(
                `Backup failed (${response.status}).`,
                `备份失败（${response.status}）。`
            );
            try {
                const errorData = await response.json();
                message = apiResponseMessage(errorData, message, message);
            } catch (_) {}
            throw new Error(message);
        }
        const blob = await response.blob();
        const disposition = response.headers.get('Content-Disposition') || '';
        const filename = disposition.match(/filename="([^"]+)"/)?.[1] || 'cdc-sim-backup.zip';
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = filename;
        link.click();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
        setSaveLoadStatus(currentLang === 'zh'
            ? '备份已下载。请将文件保存在另一处。'
            : 'Backup downloaded. Keep the ZIP somewhere outside the installation folder.', 'success');
    } catch (error) {
        setSaveLoadStatus((currentLang === 'zh' ? '备份失败：' : 'Backup failed: ') + error.message, 'error');
    } finally {
        setSaveLoadBusy(false);
    }
}

async function importSessionBackup(input) {
    const file = input?.files?.[0];
    if (!file) return;
    const confirmed = confirm(currentLang === 'zh'
        ? '导入此备份会覆盖其中对应的本地检查点。当前运行状态不会立即改变。继续吗？'
        : 'Importing this backup overwrites matching checkpoint files. The running state will not change until you restore a checkpoint. Continue?');
    if (!confirmed) { input.value = ''; return; }
    setSaveLoadBusy(true);
    setSaveLoadStatus(currentLang === 'zh' ? '正在验证并导入备份…' : 'Validating and importing backup…');
    try {
        const form = new FormData();
        form.append('backup', file);
        form.append('confirmation', 'RESTORE');
        const data = await fetchJson('/api/session_backup/restore', {
            method: 'POST',
            headers: {'X-CDC-Requested-With': 'CDC-Sim-UI'},
            body: form
        });
        await refreshSaveSlots();
        setSaveLoadStatus(apiResponseMessage(
            data,
            'Backup imported.',
            '备份已导入。'
        ), 'success');
    } catch (error) {
        setSaveLoadStatus((currentLang === 'zh' ? '备份导入失败：' : 'Backup import failed: ') + error.message, 'error');
    } finally {
        input.value = '';
        setSaveLoadBusy(false);
    }
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
        const tooltip = `${escapeHtml(city.name)} · ${Number(city.area_km2).toFixed(1)} km² · ${uiText('influence', '影响力')} ${rate.toFixed(2)}`;
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

function closeNearbySelectionMenu() {
    const panel = document.getElementById('nearby-selection-panel');
    if (panel) panel.hidden = true;
}

function positionNearbySelectionMenu(event) {
    const panel = document.getElementById('nearby-selection-panel');
    if (!panel || panel.hidden) return;
    const pointer = event?.originalEvent;
    const viewportWidth = Math.max(document.documentElement.clientWidth || 0, window.innerWidth || 0);
    const viewportHeight = Math.max(document.documentElement.clientHeight || 0, window.innerHeight || 0);
    const preferredX = Number.isFinite(pointer?.clientX) ? pointer.clientX : viewportWidth / 2;
    const preferredY = Number.isFinite(pointer?.clientY) ? pointer.clientY : viewportHeight / 2;
    const margin = 12;
    const width = panel.offsetWidth;
    const height = panel.offsetHeight;
    const left = Math.min(Math.max(margin, preferredX + margin), Math.max(margin, viewportWidth - width - margin));
    const belowTop = preferredY + margin;
    const top = belowTop + height <= viewportHeight - margin
        ? belowTop
        : Math.max(margin, preferredY - height - margin);
    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
}

function selectMapObject(kind, objectId) {
    closeNearbySelectionMenu();
    if (kind === 'unit') {
        const unit = latestUnits[objectId];
        if (!unit || Number(unit.personnel) <= 0) {
            fetchState();
            return;
        }
        selectedInstallationId = null;
        selectedUnitId = objectId;
        selectedUnitLon = Number(unit.lon);
        selectedUnitLat = Number(unit.lat);
    } else {
        const installation = latestInstallations[objectId];
        if (!installation) {
            fetchState();
            return;
        }
        selectedInstallationId = objectId;
        selectedUnitId = null;
        selectedUnitLon = null;
        selectedUnitLat = null;
        if (pathLine) {
            map.removeLayer(pathLine);
            pathLine = null;
        }
    }
    clearDraft();
    const targetingAlert = document.getElementById('targeting-alert');
    if (targetingAlert) targetingAlert.style.display = 'none';
    fetchState();
}

function showNearbySelectionMenu(candidates, event) {
    const panel = document.getElementById('nearby-selection-panel');
    const title = document.getElementById('nearby-selection-title');
    const help = document.getElementById('nearby-selection-help');
    const list = document.getElementById('nearby-selection-list');
    if (!panel || !title || !help || !list) return;

    title.textContent = uiText(
        `Choose an icon (${candidates.length})`,
        `选择标记（${candidates.length} 个）`
    );
    help.textContent = uiText(
        `Several selectable icons are within ${NEARBY_SELECTION_RADIUS_KM} km. Choose the unit or installation you want to inspect.`,
        `附近 ${NEARBY_SELECTION_RADIUS_KM} km 内有多个标记。请选择要查看的部队或设施。`
    );
    list.replaceChildren();

    candidates.forEach(candidate => {
        const entity = candidate.entity || {};
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'nearby-selection-option';
        button.dataset.selectionKind = candidate.kind;
        button.dataset.selectionId = candidate.id;

        const icon = document.createElement('span');
        icon.className = 'nearby-selection-icon';
        icon.style.color = getFactionColor(entity.faction);
        icon.textContent = candidate.kind === 'unit' ? getUnitIcon(entity) : (entity.icon || '⌂');

        const copy = document.createElement('span');
        copy.className = 'nearby-selection-copy';
        const name = document.createElement('strong');
        name.textContent = candidate.name;
        const detail = document.createElement('small');
        const typeLabel = candidate.kind === 'unit'
            ? uiText('Unit', '部队')
            : uiText('Installation', '设施');
        const status = localizedOperationalStatus(entity.status || entity.stance || '');
        const distance = candidate.distanceKm < 0.05
            ? uiText('same position', '同一位置')
            : uiText(`${candidate.distanceKm.toFixed(1)} km away`, `相距 ${candidate.distanceKm.toFixed(1)} km`);
        detail.textContent = [typeLabel, entity.faction, status, distance].filter(Boolean).join(' · ');
        copy.append(name, detail);

        button.append(icon, copy);
        button.setAttribute('aria-label', uiText(
            `Select ${typeLabel.toLowerCase()} ${candidate.name}, ${distance}`,
            `选择${typeLabel} ${candidate.name}，${distance}`
        ));
        button.addEventListener('click', () => selectMapObject(candidate.kind, candidate.id));
        list.appendChild(button);
    });

    panel.hidden = false;
    positionNearbySelectionMenu(event);
    requestAnimationFrame(() => positionNearbySelectionMenu(event));
    list.querySelector('button')?.focus({preventScroll: true});
}

function handleSelectableMarkerClick(kind, objectId, event) {
    L.DomEvent.stopPropagation(event);
    const entity = kind === 'unit' ? latestUnits[objectId] : latestInstallations[objectId];
    const longitude = Number(entity?.lon);
    const latitude = Number(entity?.lat);
    if (!entity || !Number.isFinite(longitude) || !Number.isFinite(latitude)) {
        fetchState();
        return;
    }
    const candidates = buildNearbyMapSelectionCandidates(
        latestUnits,
        latestInstallations,
        longitude,
        latitude,
        kind,
        objectId
    );
    if (candidates.length >= 2) {
        showNearbySelectionMenu(candidates, event);
        return;
    }
    selectMapObject(kind, objectId);
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
                handleSelectableMarkerClick('unit', uid, e);
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
        ? uiText(`${progress.toFixed(0)}% built`, `已完成 ${progress.toFixed(0)}%`)
        : uiText(`${(integrity / maximum * 100).toFixed(0)}% integrity`, `完整度 ${(integrity / maximum * 100).toFixed(0)}%`);
    return `<b>${escapeHtml(site.name)}</b><br>${escapeHtml(site.type_label)} · ${escapeHtml(site.faction)}<br>${escapeHtml(localizedOperationalStatus(site.status))} · ${condition}`;
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
                    const currentSite = latestInstallations[installationId] || site;
                    mapClickHandler({latlng: L.latLng(Number(currentSite.lat), Number(currentSite.lon))});
                    return;
                }
                handleSelectableMarkerClick('installation', installationId, event);
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
        container.innerHTML = logs.slice().reverse().map(log => `<div class="log-entry ${log.type === "combat" ? "log-combat" : (log.type === "move" ? "log-move" : "log-system")}">${escapeHtml(localizeEngineLogMessage(log.message))}</div>`).join('');
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
        effects.push(uiText(
            `Fort cover +${Math.round(cover * 100)}% for allied units within ${effectRadius.toFixed(1)} km`,
            `${effectRadius.toFixed(1)} km 内友军的工事掩护 +${Math.round(cover * 100)}%`
        ));
    }
    if (radarRange > 0) {
        effects.push(uiText(
            `Radar searches ${radarRange.toFixed(0)} km with recon power ${Number(site.radar_recon_power || 0).toFixed(2)}`,
            `雷达搜索 ${radarRange.toFixed(0)} km，侦察能力 ${Number(site.radar_recon_power || 0).toFixed(2)}`
        ));
    }
    return effects.length
        ? effects.join(' · ')
        : uiText(
            'No passive operational effect; this remains a physical military target.',
            '无被动运行效果；该设施仍是可攻击的实体军事目标。'
        );
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
        ? `<div class="data-row"><span class="data-label">${uiText('Builder:', '建造单位：')}</span> ${escapeHtml(latestUnits[site.builder_unit_id]?.name || site.builder_unit_id)}</div>`
        : '';
    const constructionBlock = site.status === 'UNDER_CONSTRUCTION'
        ? `<div class="installation-progress-label"><span>${uiText('Construction', '建造进度')}</span><strong>${constructionPercent.toFixed(0)}%</strong></div>
           <div class="installation-meter"><span style="width:${constructionPercent}%; background:#e3b341;"></span></div>
           <div class="installation-help">${uiText(
               'The assigned builder must remain nearby in CONSTRUCTING status. Work consumes supply and adds fatigue only while the timeline runs.',
               '指定建造单位必须停留在附近并保持“施工中”状态。仅当时间线运行时，施工才会消耗补给并增加疲劳。'
           )}</div>`
        : '';
    const targetingHelp = site.status === 'DESTROYED'
        ? uiText('This wreck has no active effect and cannot take further damage.', '该残骸没有运行效果，也无法继续承受伤害。')
        : uiText(
            'To attack this site: select a hostile-capable unit, choose Assault, Bombard Area, or Airstrike, then click this map symbol as the objective.',
            '要攻击此设施：先选择有攻击能力的部队，再选择“进攻”“区域炮击”或“空袭”，然后点击该设施。'
        );
    const detectedBy = Array.isArray(site.detected_by) && site.detected_by.length
        ? site.detected_by.map(escapeHtml).join(', ')
        : uiText('None recorded', '无记录');
    unitInfo.innerHTML = `
        <div class="installation-panel">
            <div class="installation-heading">
                <span><span class="installation-heading-icon" style="color:${factionColor};">${escapeHtml(site.icon || '⌂')}</span> ${escapeHtml(site.name)}</span>
                <button class="cmd-btn cmd-danger" onclick="deselectUnit()">❌ ${uiText('Release', '取消选择')}</button>
            </div>
            <div class="data-row"><span class="data-label">${uiText('Type:', '类型：')}</span> <span style="color:#58a6ff; font-weight:bold;">${escapeHtml(site.type_label || site.type_id)}</span></div>
            <div class="data-row"><span class="data-label">${uiText('Faction:', '阵营：')}</span> <span style="color:${factionColor}; font-weight:bold;">${escapeHtml(site.faction)}</span></div>
            <div class="data-row"><span class="data-label">${uiText('Status:', '状态：')}</span> <span style="color:${statusColor}; font-weight:bold;">${escapeHtml(localizedOperationalStatus(site.status))}</span></div>
            <div class="data-row"><span class="data-label">${uiText('Integrity:', '完整度：')}</span> ${integrity.toFixed(0)} / ${maximumIntegrity.toFixed(0)}</div>
            <div class="installation-meter" role="meter" aria-label="${uiText('Installation integrity', '设施完整度')}" aria-valuemin="0" aria-valuemax="${maximumIntegrity}" aria-valuenow="${integrity.toFixed(0)}"><span style="width:${integrityPercent}%; background:${statusColor};"></span></div>
            ${constructionBlock}
            ${builderRow}
            <div class="telemetry-box">
                <div class="telemetry-row"><span>${uiText('LON', '经度')}: ${Number(site.lon).toFixed(4)}</span><span>${uiText('LAT', '纬度')}: ${Number(site.lat).toFixed(4)}</span></div>
                <div style="text-align:center; border-top:1px dashed #58a6ff; padding-top:5px; margin-top:3px;">${uiText('Altitude', '海拔')} ${Math.floor(Number(site.altitude || 0))} m · ${escapeHtml(site.current_province || uiText('Unknown province', '未知省份'))}</div>
            </div>
            <div class="data-row"><span class="data-label">${uiText('Protection:', '防护：')}</span> ${uiText('Armor', '装甲')} ${Number(site.armor || 0).toFixed(0)} · ${uiText('Softness', '软目标系数')} ${Math.round(Number(site.softness || 0) * 100)}%</div>
            <div class="data-row"><span class="data-label">${uiText('Footprint:', '占地区域：')}</span> ${Number(site.radius || 0).toFixed(2)} km ${uiText('radius', '半径')}</div>
            <div class="data-row"><span class="data-label">${uiText('Detected By:', '发现者：')}</span> ${detectedBy}</div>
            <div class="panel-title installation-effect-title">⚙ ${uiText('Operational Effect', '运行效果')}</div>
            <div class="installation-effect ${site.status === 'OPERATIONAL' ? 'active' : 'inactive'}">${escapeHtml(site.status === 'OPERATIONAL' ? installationEffectSummary(site) : uiText('Inactive until construction is complete and integrity remains above zero.', '建造完成且完整度高于零后才会生效。'))}</div>
            <div class="panel-title installation-target-title">🎯 ${uiText('Military Target', '军事目标')}</div>
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
        preview.textContent = uiText('No installation profile selected.', '未选择设施配置。');
        return;
    }
    const effects = [];
    if (Number(profile.fortification_cover_bonus || 0) > 0) {
        effects.push(uiText(
            `+${Math.round(Number(profile.fortification_cover_bonus) * 100)}% allied cover within ${Number(profile.effect_radius_km).toFixed(1)} km`,
            `${Number(profile.effect_radius_km).toFixed(1)} km 内友军掩护 +${Math.round(Number(profile.fortification_cover_bonus) * 100)}%`
        ));
    }
    if (Number(profile.radar_range_km || 0) > 0) {
        effects.push(uiText(
            `${Number(profile.radar_range_km).toFixed(0)} km radar search`,
            `${Number(profile.radar_range_km).toFixed(0)} km 雷达搜索`
        ));
    }
    preview.textContent = uiText(
        `${profile.description} Build ${Number(profile.construction_hours).toFixed(1)} h · Total supply ${Number(profile.construction_supply_cost).toFixed(1)}%${effects.length ? ` · ${effects.join(' · ')}` : ''}.`,
        `${profile.description} 建造 ${Number(profile.construction_hours).toFixed(1)} 小时 · 总补给消耗 ${Number(profile.construction_supply_cost).toFixed(1)}%${effects.length ? ` · ${effects.join(' · ')}` : ''}。`
    );
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
            if (statusSpan) statusSpan.title = apiResponseMessage(result, '', '');
        }
    } catch (error) {
        alert(uiText('Construction rejected: ', '建造请求被拒绝：') + error.message);
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
        return `${quantityText}× ${escapeHtml(weapon.name || weapon.id)} · ${uiText('Gen', '代数')} ${Number(weapon.generation || 0)} · ${Number(weapon.max_range_km || 0).toFixed(1)} km`;
    }).join(' | ');
    const capabilities = new Set(u.effective_capabilities || u.capabilities || []);
    const missionCards = [];
    const supportBusy = isSupportMissionActive(u);
    const supportStatus = u.status === 'BOMBARDING'
        ? uiText(
            `BOMBARDING · ${Number(u.bombard_timer || 0).toFixed(2)} h remaining · ${Number(u.bombard_casualties || 0).toFixed(0)} estimated casualties · ${Number(u.bombard_installation_damage || 0).toFixed(0)} target integrity damage${Number(u.bombard_installations_destroyed || 0) > 0 ? ` · ${Number(u.bombard_installations_destroyed)} site(s) destroyed` : ''}`,
            `炮击中 · 剩余 ${Number(u.bombard_timer || 0).toFixed(2)} 小时 · 预计伤亡 ${Number(u.bombard_casualties || 0).toFixed(0)} 人 · 目标完整度损失 ${Number(u.bombard_installation_damage || 0).toFixed(0)}${Number(u.bombard_installations_destroyed || 0) > 0 ? ` · 已摧毁 ${Number(u.bombard_installations_destroyed)} 处设施` : ''}`
        )
        : (u.status === 'AIRSTRIKE_OUTBOUND'
            ? uiText('AIRSTRIKE OUTBOUND · flying to the selected impact area', '空袭出航 · 正在飞往指定打击区域')
            : (u.status === 'AIRSTRIKE_RTB'
                ? uiText('AIRSTRIKE RTB · returning to launch base', '空袭返航 · 正在返回起飞基地')
                : ''));
    const missionButton = (action, icon, label, meta, disabledReason) => {
        const disabled = Boolean(disabledReason);
        return `<div class="support-mission-card">
            <button class="cmd-btn cmd-warn support-mission-button" onclick="setTargetingMode('${action}')" ${disabled ? 'disabled' : ''} title="${escapeHtml(disabledReason || uiText(`Select a ${label.toLowerCase()} target on the map`, '在地图上选择目标'))}">${icon} ${escapeHtml(label)}</button>
            <div class="support-mission-meta">${escapeHtml(meta)}</div>
            <div class="support-mission-readiness ${disabled ? 'blocked' : 'ready'}">${escapeHtml(disabledReason || uiText('READY', '就绪'))}</div>
        </div>`;
    };
    if (capabilities.has(globalRules.missions?.bombard?.capability)) {
        const rules = globalRules.missions.bombard;
        const disabledReason = Number(u.bombard_range || 0) <= 0
            ? uiText('No battalion mounts an indirect bombard weapon', '没有营装备间接炮击武器')
            : (Number(u.personnel || 0) <= 0
            ? uiText('Unit is neutralized', '单位已失去战斗力')
            : (supportBusy
                ? uiText('Finish or halt the active support mission first', '请先完成或停止当前支援任务')
                : (Number(u.supply || 0) < Number(rules.minimum_supply_to_start)
                    ? uiText(
                        `Requires ${Number(rules.minimum_supply_to_start).toFixed(0)}% supply`,
                        `需要 ${Number(rules.minimum_supply_to_start).toFixed(0)}% 补给`
                    )
                    : '')));
        missionCards.push(missionButton(
            'bombard',
            '💥',
            uiText('Bombard Area', '区域炮击'),
            uiText(
                `Weapon-band range ${Number(u.bombard_range || 0).toFixed(1)} km · Effect radius ${Number(rules.blast_radius_km).toFixed(1)} km · ${Number(rules.duration_hours).toFixed(1)} h · Supply ${Number(rules.supply_per_hour).toFixed(1)}%/h`,
                `武器射程 ${Number(u.bombard_range || 0).toFixed(1)} km · 效果半径 ${Number(rules.blast_radius_km).toFixed(1)} km · ${Number(rules.duration_hours).toFixed(1)} 小时 · 补给 ${Number(rules.supply_per_hour).toFixed(1)}%/小时`
            ),
            disabledReason
        ));
    }
    if (capabilities.has(globalRules.missions?.airstrike?.capability)) {
        const rules = globalRules.missions.airstrike;
        const aircraft = airstrikePerformance(u);
        const disabledReason = !(aircraft.strike_weapon_ids || []).length
            ? uiText('No battalion mounts an airstrike weapon', '没有营装备空袭武器')
            : (Number(u.personnel || 0) <= 0
            ? uiText('Unit is neutralized', '单位已失去战斗力')
            : (supportBusy
                ? uiText('Finish or halt the active support mission first', '请先完成或停止当前支援任务')
                : (Number(u.supply || 0) < Number(aircraft.supply_cost)
                    ? uiText(
                        `Requires ${Number(aircraft.supply_cost).toFixed(0)}% supply`,
                        `需要 ${Number(aircraft.supply_cost).toFixed(0)}% 补给`
                    )
                    : '')));
        missionCards.push(missionButton(
            'airstrike',
            '✈️',
            uiText(`Launch Airstrike — ${aircraft.label}`, `发起空袭 — ${aircraft.label}`),
            uiText(
                `${aircraft.attack_profile} · Cruise ${Number(aircraft.cruise_speed_kmh).toFixed(0)} km/h · Range ${Number(aircraft.sortie_range_km).toFixed(0)} km · Effect radius ${Number(aircraft.blast_radius_km).toFixed(1)} km · Soft ×${Number(aircraft.soft_target_multiplier).toFixed(2)} / Hard ×${Number(aircraft.hard_target_multiplier).toFixed(2)} · Accuracy ×${Number(aircraft.accuracy_multiplier).toFixed(2)} · Unobserved ×${Number(aircraft.unobserved_targeting_multiplier).toFixed(2)} · Payload ×${Number(aircraft.payload_multiplier).toFixed(2)} · Cost ${Number(aircraft.supply_cost).toFixed(1)}% supply / ${Number(aircraft.fatigue_cost).toFixed(1)}% fatigue · AA exposure ×${Number(aircraft.aa_vulnerability_multiplier).toFixed(2)} · Max ${Math.round(Number(rules.maximum_casualty_fraction) * 100)}% loss/formation`,
                `${aircraft.attack_profile} · 巡航 ${Number(aircraft.cruise_speed_kmh).toFixed(0)} km/h · 航程 ${Number(aircraft.sortie_range_km).toFixed(0)} km · 效果半径 ${Number(aircraft.blast_radius_km).toFixed(1)} km · 软目标 ×${Number(aircraft.soft_target_multiplier).toFixed(2)} / 硬目标 ×${Number(aircraft.hard_target_multiplier).toFixed(2)} · 精度 ×${Number(aircraft.accuracy_multiplier).toFixed(2)} · 未观测 ×${Number(aircraft.unobserved_targeting_multiplier).toFixed(2)} · 载荷 ×${Number(aircraft.payload_multiplier).toFixed(2)} · 成本：补给 ${Number(aircraft.supply_cost).toFixed(1)}% / 疲劳 ${Number(aircraft.fatigue_cost).toFixed(1)}% · 防空暴露 ×${Number(aircraft.aa_vulnerability_multiplier).toFixed(2)} · 每编队最大损失 ${Math.round(Number(rules.maximum_casualty_fraction) * 100)}%`
            ),
            disabledReason
        ));
    }
    const weaponPanel = missionCards.length
        ? `<div class="panel-title support-mission-title">🎯 ${uiText('Support Mission', '支援任务')}</div>${supportStatus ? `<div class="support-mission-status">${escapeHtml(supportStatus)}</div>` : ''}<div class="support-mission-grid">${missionCards.join('')}</div>`
        : '';
    const currentStance = localizedStanceProfile(u.stance, globalRules.stances?.[u.stance] || {});
    const orderProfile = orderProfileForUnit(u);
    const activeOrderRole = Object.entries(globalRules.orders?.modes || {})
        .find(([, profile]) => profile.id === u.order_mode)?.[0]
        || globalRules.orders?.default_role
        || 'hold';
    const stanceOptions = Object.entries(globalRules.stances || {}).map(([stanceId, profile]) => {
        const localizedProfile = localizedStanceProfile(stanceId, profile);
        return `<option value="${escapeHtml(stanceId)}" ${stanceId === u.stance ? 'selected' : ''}>${escapeHtml(localizedProfile.label || stanceId)}</option>`;
    }).join('');
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
        constructionDisabledReason = uiText('Only ground-combat formations can build military installations', '只有地面战斗部队可以建造军事设施');
    } else if (Number(u.personnel || 0) <= 0) {
        constructionDisabledReason = uiText('A neutralized formation cannot construct', '失去战斗力的部队无法施工');
    } else if (u.status === 'CONSTRUCTING') {
        constructionDisabledReason = simulationPaused
            ? uiText('Work is queued; press Run to advance construction', '施工已排队；点击“运行”推进建造')
            : uiText('Construction is already progressing', '施工正在进行');
    } else if (['MOVING', 'BOMBARDING', 'AIRSTRIKE_OUTBOUND', 'AIRSTRIKE_RTB'].includes(u.status) || (u.waypoints || []).length > 0) {
        constructionDisabledReason = uiText('Halt movement or the active support mission before building', '建造前请停止移动或当前支援任务');
    } else if (activeProject && Number(u.supply || 0) <= Number(constructionRules.stop_supply_threshold || 0)) {
        constructionDisabledReason = uiText(
            `Supply must exceed ${Number(constructionRules.stop_supply_threshold || 0).toFixed(0)}% to resume work`,
            `补给必须超过 ${Number(constructionRules.stop_supply_threshold || 0).toFixed(0)}% 才能复工`
        );
    } else if (!activeProject && Number(u.supply || 0) < Number(constructionRules.minimum_supply_to_start || 0)) {
        constructionDisabledReason = uiText(
            `Requires ${Number(constructionRules.minimum_supply_to_start || 0).toFixed(0)}% supply to begin`,
            `开始施工需要 ${Number(constructionRules.minimum_supply_to_start || 0).toFixed(0)}% 补给`
        );
    }
    const constructionOptions = installationTypes.map(([typeId, profile]) =>
        `<option value="${escapeHtml(typeId)}" ${typeId === selectedBuildType ? 'selected' : ''}>${escapeHtml(profile.icon || '⌂')} ${escapeHtml(profile.label || typeId)}</option>`
    ).join('');
    const constructionProgress = Math.max(0, Math.min(100, Number(activeProject?.construction_progress || 0) * 100));
    const initialConstructionEffects = selectedBuildProfile
        ? installationEffectSummary(selectedBuildProfile)
        : '';
    const constructionActionLabel = activeProject
        ? uiText('Resume Construction', '恢复施工')
        : uiText('Build at Current Position', '在当前位置建造');
    const constructionStatus = activeProject
        ? uiText(
            `${escapeHtml(activeProject.name)} · ${constructionProgress.toFixed(0)}% complete${u.status === 'CONSTRUCTING' ? (simulationPaused ? ' · queued while paused' : ' · crews working') : ' · work paused'}`,
            `${escapeHtml(activeProject.name)} · 已完成 ${constructionProgress.toFixed(0)}%${u.status === 'CONSTRUCTING' ? (simulationPaused ? ' · 暂停时已排队' : ' · 施工人员作业中') : ' · 施工已暂停'}`
        )
        : uiText('No active construction project.', '没有进行中的建造项目。');
    const constructionPanel = installationTypes.length
        ? `<div class="panel-title construction-title">🏗 ${uiText('Military Construction', '军事建造')}</div>
           <div class="construction-panel">
               <div class="construction-distinction">${uiText(
                   '<strong>Build</strong> creates a persistent, separately targetable site. <strong>Fortify</strong> only prepares temporary fieldworks for this unit.',
                   '<strong>建造</strong>会创建可长期使用、也可被单独攻击的设施。<strong>加固阵地</strong>只会提高这支部队的临时防御。'
               )}</div>
               <div class="construction-status">${constructionStatus}</div>
               ${activeProject ? `<div class="installation-meter" role="meter" aria-label="${uiText('Construction progress', '建造进度')}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${constructionProgress.toFixed(0)}"><span style="width:${constructionProgress}%; background:#e3b341;"></span></div>` : ''}
               <div class="construction-controls">
                   <select id="construction-type-${u.id}" class="dark-input" aria-label="${uiText('Military installation type', '军事设施类型')}" onchange="updateConstructionPreview('${u.id}')" ${activeProject ? `disabled title="${uiText('Finish or lose the existing project before selecting another type', '完成或失去当前项目后才能选择其他类型')}"` : ''}>${constructionOptions}</select>
                   <button id="construction-start-${u.id}" class="cmd-btn construction-start" onclick="startInstallationConstruction('${u.id}')" ${constructionDisabledReason ? 'disabled' : ''}>${escapeHtml(constructionActionLabel)}</button>
               </div>
               <div id="construction-preview-${u.id}" class="construction-preview">${selectedBuildProfile ? uiText(
                   `${escapeHtml(selectedBuildProfile.description)} Build ${Number(selectedBuildProfile.construction_hours).toFixed(1)} h · Total supply ${Number(selectedBuildProfile.construction_supply_cost).toFixed(1)}% · ${escapeHtml(initialConstructionEffects)}.`,
                   `${escapeHtml(selectedBuildProfile.description)} 建造 ${Number(selectedBuildProfile.construction_hours).toFixed(1)} 小时 · 总补给消耗 ${Number(selectedBuildProfile.construction_supply_cost).toFixed(1)}% · ${escapeHtml(initialConstructionEffects)}。`
               ) : uiText('No installation type is configured.', '未配置设施类型。')}</div>
               <div class="support-mission-readiness ${constructionDisabledReason ? 'blocked' : 'ready'}">${escapeHtml(constructionDisabledReason || (simulationPaused
                   ? uiText('READY · construction will begin when the timeline runs', '就绪 · 时间线运行后开始施工')
                   : (activeProject ? uiText('READY TO RESUME', '可以复工') : uiText('READY TO BUILD HERE', '可以在此建造'))))}</div>
               ${activeProject && u.status === 'CONSTRUCTING' && simulationPaused ? `<button class="cmd-btn construction-run" onclick="sendCommand('play')">▶ ${uiText('Run Timeline to Build', '运行时间线以施工')}</button>` : ''}
           </div>`
        : '';
    let engagementSummary = uiText(
        'This unit cannot conduct direct ground combat.',
        '这支部队不能进行地面直接战斗。'
    );
    if (canPrepareGroundDefense) {
        const movementTaskWithholdsFire = (
            (activeOrderRole === 'relocate' && !globalRules.orders.relocate_allows_stance_fire)
            || (activeOrderRole === 'route' && !globalRules.orders.route_allows_stance_fire)
        );
        if (!currentStance.allows_ranged_fire) {
            engagementSummary = uiText(
                'Ranged fire is withheld by stance; close-contact self-defense remains active.',
                '当前战斗方式禁止远程开火；敌军逼近时仍会自卫。'
            );
        } else if (movementTaskWithholdsFire) {
            engagementSummary = activeOrderRole === 'relocate'
                ? uiText(
                    'Ranged fire is withheld; detected threats to the route trigger an automatic detour while close-contact self-defense remains active.',
                    '途中不会主动远程开火；发现敌军挡路时会自动绕行，敌军逼近时仍会自卫。'
                )
                : uiText(
                    'Ranged fire is withheld by the movement task; close-contact self-defense remains active.',
                    '移动途中不会主动远程开火；敌军逼近时仍会自卫。'
                );
        } else if (activeOrderRole === 'assault') {
            engagementSummary = uiText(
                'The unit seeks detected contact, fights within weapon range, and resumes its advance when clear.',
                '部队会主动寻找已经发现的敌军，在射程内开火，并在敌军被清除后继续前进。'
            );
        } else {
            engagementSummary = uiText(
                'The unit may engage detected enemies within weapon range while holding its task.',
                '部队会继续当前任务，并攻击射程内已经发现的敌军。'
            );
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
        ? `<div class="data-row" title="${escapeHtml(aircraft.description)}"><span class="data-label">${uiText('Aircraft Type:', '飞机类型：')}</span> <span style="color:#d2a8ff; font-weight:bold;">${escapeHtml(aircraft.label)}</span> · ${escapeHtml(aircraft.attack_profile)}</div>`
        : '';
    const remainingDistance = remainingRouteDistanceKm(u);
    const effectiveMovementSpeed = Math.max(0, Number(u.effective_movement_speed || 0));
    const movementEta = effectiveMovementSpeed > 0 ? remainingDistance / effectiveMovementSpeed : Number.NaN;
    const relocationAvoidance = u.relocation_avoidance || {};
    const avoidanceContacts = Array.isArray(relocationAvoidance.contacts) ? relocationAvoidance.contacts : [];
    const avoidanceNames = avoidanceContacts.slice(0, 3).map(contact => escapeHtml(contact.name || contact.id || uiText('contact', '目标'))).join(', ');
    const avoidanceActive = Boolean(relocationAvoidance.active && avoidanceContacts.length);
    const movementLabel = avoidanceActive
        ? uiText('CONTACT-AVOIDANCE ROUTE', '避敌路线')
        : uiText('EN ROUTE', '行进中');
    const avoidanceDetail = avoidanceActive
        ? uiText(
            ` · avoiding ${avoidanceNames}${avoidanceContacts.length > 3 ? ` +${avoidanceContacts.length - 3}` : ''}`,
            ` · 正在避开 ${avoidanceNames}${avoidanceContacts.length > 3 ? ` +${avoidanceContacts.length - 3}` : ''}`
        )
        : '';
    const movementExecution = u.status === 'MOVING' && remainingDistance > 0
        ? (simulationPaused
            ? `<div class="order-execution queued"><div><strong>${avoidanceActive ? uiText('CONTACT-AVOIDANCE ROUTE QUEUED', '避敌路线已排队') : uiText('ORDER QUEUED — TIMELINE PAUSED', '指令已排队 — 时间线已暂停')}</strong><span>${uiText(
                `${remainingDistance.toFixed(1)} km remains${avoidanceDetail}. Press Run to execute all queued orders.`,
                `剩余 ${remainingDistance.toFixed(1)} km${avoidanceDetail}。点击“运行”执行所有排队指令。`
            )}</span></div><button class="cmd-btn" onclick="sendCommand('play')">▶ ${uiText('Run', '运行')}</button></div>`
            : `<div class="order-execution active"><strong>${movementLabel}</strong><span>${uiText(
                `${remainingDistance.toFixed(1)} km remaining · ${effectiveMovementSpeed.toFixed(1)} km/h effective · ${formatSimulationDuration(movementEta)}${avoidanceDetail}`,
                `剩余 ${remainingDistance.toFixed(1)} km · 有效速度 ${effectiveMovementSpeed.toFixed(1)} km/h · ${formatSimulationDuration(movementEta)}${avoidanceDetail}`
            )}</span></div>`)
        : '';
    
    // 🟢 Dynamic HUD Color Based on Palette
    const uColor = getFactionColor(u.faction);

    const tacticalHud = document.getElementById('tactical-hud');
    const previousScrollTop = tacticalHud?.scrollTop || 0;
    unitInfo.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; border-bottom: 1px solid #1f6feb; padding-bottom: 5px;">
            <span style="color:#fff; font-size:15px; font-weight:bold;">${escapeHtml(u.name)}</span><button class="cmd-btn cmd-danger" style="padding: 3px 6px;" onclick="deselectUnit()">${uiText('❌ Release', '❌ 取消选择')}</button>
        </div>
        <div class="data-row"><span class="data-label">${uiText('Faction:', '阵营：')}</span> <span style="color:${uColor}">${escapeHtml(u.faction)}</span></div>
        <div class="data-row"><span class="data-label">${uiText('Status:', '状态：')}</span> <span style="color:#58a6ff; font-weight:bold;">${escapeHtml(localizedOperationalStatus(u.status))}</span></div>
        <div class="data-row" title="${uiText('Personnel currently alive after combat and mission losses', '扣除战斗和任务损失后的当前人数')}"><span class="data-label">${uiText('Personnel Alive:', '当前兵力：')}</span> ${Math.floor(Number(u.personnel))} ${uiText('Pers.', '人')}</div>
        <div class="data-row"><span class="data-label">${uiText('Morale:', '士气：')}</span> <span style="color:${moraleColor}; font-weight:bold;">${moralePercent.toFixed(0)}%</span></div>
        <div class="morale-meter" role="meter" aria-label="${uiText('Unit morale', '单位士气')}" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${moralePercent.toFixed(0)}"><span style="width:${moralePercent}%; background:${moraleColor};"></span></div>
        <div class="data-row"><span class="data-label">${uiText('Readiness:', '作战状态：')}</span> ${uiText('Supply', '补给')} ${Math.floor(u.supply ?? globalRules.unit_defaults.supply)}% | ${uiText('Fatigue', '疲劳')} ${Math.floor(u.fatigue ?? globalRules.unit_defaults.fatigue)}% | ${uiText('Supp.', '受压制')} ${Math.floor(u.suppression ?? globalRules.unit_defaults.suppression)}%</div>
        <div class="data-row"><span class="data-label">${uiText('Prepared Defense:', '临时防御：')}</span> ${entrenchmentPercent.toFixed(0)}%</div>
        <div style="height:6px; background:#161b22; border:1px solid #30363d; margin:2px 0 8px;"><div style="height:100%; width:${entrenchmentPercent}%; background:#3fb950;"></div></div>
        <div class="data-row"><span class="data-label">${uiText('Fort Cover:', '要塞掩护：')}</span> <span style="color:#7ee787; font-weight:bold;">+${Math.round(Number(u.installation_cover_bonus || 0) * 100)}%</span> ${uiText('from nearby operational sites', '来自附近运行中的设施')}</div>
        <div class="telemetry-box">
            <div class="telemetry-row"><span>${uiText('LON', '经度')}: ${parseFloat(u.lon).toFixed(4)}</span><span>${uiText('LAT', '纬度')}: ${parseFloat(u.lat).toFixed(4)}</span><span>${uiText('MOV', '移动')}: ${effectiveMovementSpeed.toFixed(1)} km/h</span></div>
            <div style="text-align:center; border-top:1px dashed #58a6ff; padding-top:5px; margin-top:3px;">${uiText('Real-time Altitude:', '实时海拔：')} <span style="color:#fff; font-size:14px; font-weight:bold;">${Math.floor(u.altitude || 0)}</span> m</div>
        </div>
        <div class="data-row"><span class="data-label">${uiText('Def. Radius:', '防御半径：')}</span> <span style="color:#7ee787; font-weight:bold;">${(u.radius || 0).toFixed(2)} km</span></div>
        <div class="data-row"><span class="data-label">${uiText('City Influence:', '城市影响：')}</span> <span style="color:#d2a8ff; font-weight:bold;">${u.city_name ? `${escapeHtml(u.city_name)} · ${Number(u.city_influence_rate || 0).toFixed(2)}` : uiText('None · 0.00', '无 · 0.00')}</span></div>
        <div class="data-row"><span class="data-label">${uiText('Effective Complexity:', '地形难度：')}</span> ${Number(u.effective_terrain_complexity || 0).toFixed(2)}</div>
        <div class="data-row"><span class="data-label">${uiText('OOB:', '部队编制：')}</span> <span style="color:#a5d6ff">${compStr || uiText('Non-Combat Unit', '非战斗单位')}</span></div>
        <div class="data-row"><span class="data-label">${uiText('Weapon Groups:', '武器：')}</span> <span style="color:#e3b341; font-weight:bold;">${weaponStr || uiText('Unarmed', '无武装')}</span></div>
        <div class="data-row"><span class="data-label">${uiText('Protection:', '防护：')}</span> ${uiText('Armor', '装甲')} ${Number(u.stats?.armor || 0).toFixed(1)} · ${uiText('Armor Gen', '装甲等级')} ${Number(u.stats?.armor_generation || 0).toFixed(1)}</div>
        ${aircraftDataRow}
        <div class="panel-title operational-order-title">📍 ${uiText('Operational Order', '部队命令')}</div>
        <div class="operational-order-panel" style="--order-color:${escapeHtml(orderProfile.color)}; border-color:${escapeHtml(orderProfile.color)};">
            <div class="order-section-label"><span>${uiText('Current Task', '当前任务')}</span><small>${uiText('WHAT &amp; WHERE', '做什么 / 去哪里')}</small></div>
            <div class="order-status-heading">
                <span>${escapeHtml(orderProfile.label)}</span>
                <span>${escapeHtml(orderProfile.summary)}</span>
            </div>
            <div class="order-status-description">${escapeHtml(orderProfile.description)}</div>
            ${movementExecution}

            <div class="order-divider"></div>
            <div class="order-section-label"><span>${uiText('Combat Stance', '战斗方式')}</span><small>${uiText('HOW TO EXECUTE', '如何行动')}</small></div>
            <div class="stance-control-row">
                <select id="stance-select-${u.id}" class="dark-input" aria-label="${uiText('Combat stance', '战斗方式')}">${stanceOptions}</select>
                <button class="cmd-btn stance-apply" onclick="sendCommand('stance ${u.id} ' + document.getElementById('stance-select-${u.id}').value)">${uiText('Set Stance', '应用')}</button>
            </div>
            <div class="stance-description" style="border-left-color:${escapeHtml(currentStance.color || '#8b949e')};">${escapeHtml(currentStance.description || '')}</div>
            <div class="order-metrics">
                <span>${uiText('Combat', '战斗力')} ×${combatMultiplier}</span>
                <span>${uiText('Speed', '速度')} ×${speedMultiplier}</span>
                <span>${uiText('Cover', '掩护')} ${coverPercent}%</span>
            </div>
            <div class="effective-behavior">${escapeHtml(engagementSummary)}</div>

            <div class="order-boundary-guide">${uiText(
                '<strong>Task</strong> sets the objective and contact policy. <strong>Stance</strong> sets fire discipline, speed, concealment, and combat modifiers. Changing either one keeps the other.',
                '<strong>任务</strong>决定部队去哪里，以及遇到敌军时是否主动交战；<strong>战斗方式</strong>决定开火、移动、隐蔽和战斗效果。修改一个不会改变另一个。'
            )}</div>

            <div class="order-divider"></div>
            <div class="order-section-label"><span>${uiText('Issue Task', '选择新任务')}</span><small>${uiText('STANCE WILL BE RETAINED', '战斗方式不变')}</small></div>
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
    if (!confirm(uiText(
        `Remove city influence area "${city?.name || selectedCityId}"?`,
        `删除城市影响区“${city?.name || selectedCityId}”？`
    ))) return;
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
        const control = values.contested
            ? uiText('CONTESTED', '争夺中')
            : (values.controller
                ? uiText(`Controlled by ${values.controller}`, `由 ${values.controller} 控制`)
                : uiText('No established control', '尚无稳定控制'));
        summary.textContent = uiText(
            `${control} · influence ${Number(values.influence || 0).toFixed(2)} · military presence ${Number(values.military_presence || 0).toFixed(2)}`,
            `${control} · 影响力 ${Number(values.influence || 0).toFixed(2)} · 军事存在 ${Number(values.military_presence || 0).toFixed(2)}`
        );
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
    if (!confirm(uiText(
        `Remove the ${selectedPoliticsFaction} political record for ${selectedPoliticsProvince}?`,
        `删除 ${selectedPoliticsProvince} 中 ${selectedPoliticsFaction} 的政治记录？`
    ))) return;
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
    const backupDownload = document.getElementById('backup-download-button');
    const backupImport = document.getElementById('backup-import-button');
    if (resetButton) resetButton.disabled = busy;
    if (backupDownload) backupDownload.disabled = busy;
    if (backupImport) backupImport.disabled = busy;
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
        ? {empty: '空', available: '可恢复', wrong_dlc: '其他剧本', incompatible_rules: '规则不兼容', invalid: '已损坏'}
        : {empty: 'Empty', available: 'Ready', wrong_dlc: 'Other DLC', incompatible_rules: 'Incompatible', invalid: 'Invalid'};
    state.textContent = stateLabels[slotInfo.condition] || slotInfo.condition;

    if (!slotInfo.exists) {
        meta.textContent = currentLang === 'zh' ? '此检查点尚未保存。' : 'Nothing has been saved here yet.';
    } else if (slotInfo.can_load) {
        const legacy = slotInfo.legacy
            ? (currentLang === 'zh' ? ' · 旧版存档，未记录剧本' : ' · legacy save; DLC not recorded')
            : '';
        const unitText = currentLang === 'zh' ? `${slotInfo.unit_count} 支部队` : `${slotInfo.unit_count} units`;
        const installationCount = Number(slotInfo.installation_count || 0);
        const installationText = currentLang === 'zh' ? `${installationCount} 处设施` : `${installationCount} military sites`;
        meta.textContent = `${formatSavedAt(slotInfo.saved_at_utc)} · ${formatCheckpointTime(slotInfo.game_hours)} · ${unitText} · ${installationText}${legacy}`;
    } else {
        const prefix = currentLang === 'zh' ? '无法恢复：' : 'Cannot restore: ';
        const checkpointFailureZh = {
            wrong_dlc: '此检查点属于其他剧本',
            incompatible_rules: '规则版本不兼容',
            invalid: '检查点无效或已损坏',
        };
        const reason = currentLang === 'zh'
            ? (checkpointFailureZh[slotInfo.condition] || slotInfo.message)
            : slotInfo.message;
        meta.textContent = prefix + reason;
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
            ? '剧本已恢复到作者设定的初始状态；未创建自动备份。'
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
        if (summary) summary.textContent = uiText(
            `Committee data unavailable: ${error.message}`,
            `无法获取委员会数据：${error.message}`
        );
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
        `<div class="committee-faction-row"><span>${escapeHtml(f.faction)}</span><span>${uiText(
            `${Number(f.active_personnel)} living personnel | morale ${Number(f.average_morale)}% | supply ${Number(f.average_supply)}% | sites ${Number(f.operational_installations || 0)} active / ${Number(f.construction_sites || 0)} building / ${Number(f.destroyed_installations || 0)} destroyed`,
            `当前兵力 ${Number(f.active_personnel)} | 士气 ${Number(f.average_morale)}% | 补给 ${Number(f.average_supply)}% | 设施：运行 ${Number(f.operational_installations || 0)} / 建造中 ${Number(f.construction_sites || 0)} / 已摧毁 ${Number(f.destroyed_installations || 0)}`
        )}</span></div>`
    ).join('');
    const rules = (c.rules_of_engagement || []).map(rule => `<li>${escapeHtml(rule)}</li>`).join('');
    const packageMetadata = c.package_metadata;
    const defaultFaction = globalRules.directives?.default_faction || 'GLOBAL';
    const objectives = Array.isArray(c.objectives) ? c.objectives : [];
    const events = Array.isArray(c.events) ? c.events : [];
    const packageInfo = packageMetadata ? `
        <div class="committee-section-title">${uiText('Scenario Package', '剧本包')}</div>
        <div class="committee-record">
            <b>${escapeHtml(packageMetadata.name || packageMetadata.id)}</b>
            <div>${escapeHtml(packageMetadata.id)} · ${uiText('Version', '版本')} ${escapeHtml(packageMetadata.version)}</div>
            ${packageMetadata.publisher ? `<div>${uiText('Publisher:', '发布者：')} ${escapeHtml(packageMetadata.publisher)}</div>` : ''}
            ${packageMetadata.description ? `<div style="white-space:pre-wrap;">${escapeHtml(packageMetadata.description)}</div>` : ''}
            ${packageMetadata.license ? `<small>${uiText('Content license:', '内容许可：')} ${escapeHtml(packageMetadata.license)}</small>` : ''}
        </div>` : '';
    const objectiveCards = objectives.map(objective => `
        <div class="committee-record">
            <b>${escapeHtml(objective.title)}</b>
            <div>${escapeHtml(objective.faction || defaultFaction)} · ${escapeHtml(objective.points ?? 0)} ${uiText('points · Chair-assessed', '分 · 由主席团评定')}</div>
            ${objective.description ? `<div style="white-space:pre-wrap;">${escapeHtml(objective.description)}</div>` : ''}
            <div style="white-space:pre-wrap;"><b>${uiText('Success criteria:', '成功标准：')}</b> ${escapeHtml(objective.success_criteria)}</div>
        </div>`).join('');
    const eventCards = events.map((event, index) => `
        <div class="committee-record">
            <b>${escapeHtml(event.title)}</b>
            <div style="white-space:pre-wrap;">${escapeHtml(event.body)}</div>
            <div style="white-space:pre-wrap;"><b>${uiText('When to consider:', '考虑时机：')}</b> ${escapeHtml(event.trigger_note)}</div>
            <small>${escapeHtml(event.faction || defaultFaction)} · ${event.public === false ? uiText('Private ruling', '私密裁定') : uiText('Public update', '公开更新')} · ${escapeHtml(localizedEffectType(event.effect_type || 'none'))} ${escapeHtml(event.value ?? 0)} · ${escapeHtml(event.duration_hours ?? globalRules.directives?.default_duration_hours ?? 12)} ${uiText('hours', '小时')}</small>
            <div style="margin-top:6px;"><button type="button" class="cmd-btn" data-committee-event-index="${index}">${uiText('Prepare ruling', '准备裁定')}</button></div>
        </div>`).join('');
    const scenarioCards = packageMetadata || objectives.length || events.length ? `
        <div class="committee-section-title">${uiText('Objectives', '目标')}</div>
        <div style="color:#8b949e;">${uiText('Chairs assess success and award points. Scores are not calculated automatically.', '主席团评定目标是否达成并授予分数；系统不会自动计算得分。')}</div>
        ${objectiveCards || `<div class="committee-record">${uiText('No objective cards configured.', '未配置目标卡。')}</div>`}
        <div class="committee-section-title">${uiText('Event Cards', '事件卡')}</div>
        <div style="color:#8b949e;">${uiText('Events never run automatically. Prepare a ruling, review the form, then click Apply Adjudication. Cards can be reused; the ruling log records actual approvals.', '事件不会自动触发。先准备裁定并检查表单，再点击“应用裁定”。事件卡可以重复使用，裁定日志会记录实际批准的内容。')}</div>
        ${eventCards || `<div class="committee-record">${uiText('No event cards configured.', '未配置事件卡。')}</div>`}
        <div id="committee-event-status" role="status" aria-live="polite" style="margin-top:8px;"></div>` : '';

    summary.innerHTML = `
        <div style="color:#fff; font-weight:bold; font-size:14px;">${escapeHtml(c.committee_name || committeeState.scenario)}</div>
        <div style="color:#8b949e;">${escapeHtml(c.committee_type || 'committee')} | ${escapeHtml(c.simulation_scope || 'crisis')} | ${escapeHtml(committeeState.game_time)}</div>
        <div style="margin-top:8px;">${escapeHtml(c.public_briefing || '')}</div>
        ${packageInfo}
        <div class="committee-section-title">${uiText('Rules of Engagement', '交战规则')}</div>
        <ul class="committee-rules">${rules || `<li>${uiText('No committee rules configured.', '未配置委员会规则。')}</li>`}</ul>
        <div class="committee-section-title">${uiText('Delegate Roles', '代表角色')}</div>
        <div class="committee-role-grid">${roles || `<div class="committee-role">${uiText('No roles configured.', '未配置角色。')}</div>`}</div>
        <div class="committee-section-title">${uiText('Faction Readiness', '阵营战备')}</div>
        ${factions || `<div style="color:#8b949e;">${uiText('No units loaded.', '未载入部队。')}</div>`}
        ${scenarioCards}
    `;
    summary.querySelectorAll('[data-committee-event-index]').forEach(button => {
        button.addEventListener('click', () => prepareCommitteeEvent(Number(button.dataset.committeeEventIndex)));
    });

    const recHtml = (committeeState.public_records || []).slice().reverse().map(rec =>
        `<div class="committee-record"><b>${escapeHtml(rec.timestamp)} - ${escapeHtml(rec.title)}</b><br><span>${escapeHtml(rec.body || '')}</span><br><small>${escapeHtml(rec.faction)} | ${escapeHtml(localizedEffectType(rec.effect_type))} ${Number(rec.value)} | ${uiText('affected', '受影响')} ${Number(rec.affected_units)}</small></div>`
    ).join('');
    records.innerHTML = `<div class="committee-section-title">${uiText('Public Crisis Updates', '公开危机更新')}</div>${recHtml || `<div style="color:#8b949e; font-size:12px;">${uiText('No public crisis updates yet.', '尚无公开危机更新。')}</div>`}`;
}

function prepareCommitteeEvent(index) {
    const status = document.getElementById('committee-event-status');
    try {
        const events = committeeState?.committee?.events;
        const event = Array.isArray(events) && Number.isInteger(index) && index >= 0 ? events[index] : null;
        if (!event) throw new Error(uiText('This event card is no longer available. Refresh the committee panel.', '此事件卡已不可用，请刷新委员会面板。'));

        const fields = Object.fromEntries(['title', 'body', 'faction', 'effect', 'value', 'duration', 'public']
            .map(name => [name, document.getElementById(`committee-${name}`)]));
        if (Object.values(fields).some(field => !field)) throw new Error(uiText('The adjudication form is unavailable.', '裁定表单不可用。'));

        const faction = event.faction ?? globalRules.directives?.default_faction ?? 'GLOBAL';
        const effect = event.effect_type ?? 'none';
        if (typeof faction !== 'string' || !faction.trim()) throw new Error(uiText('This card has no valid ruling faction.', '此事件卡没有有效的裁定阵营。'));
        for (const [name, value] of [['faction', faction], ['effect', effect]]) {
            if (fields[name].tagName === 'SELECT' && !Array.from(fields[name].options).some(option => option.value === value && !option.disabled)) {
                const fieldLabel = name === 'faction' ? uiText('faction', '阵营') : uiText('effect', '效果');
                throw new Error(uiText(
                    `This card's ${fieldLabel} (${value}) is unavailable in the adjudication form. No ruling was prepared.`,
                    `此事件卡的${fieldLabel}（${value}）在裁定表单中不可用，因此未准备裁定。`
                ));
            }
        }
        const value = event.value ?? 0;
        const duration = event.duration_hours ?? globalRules.directives?.default_duration_hours ?? 12;
        if (!Number.isFinite(value) || !Number.isFinite(duration) || duration <= 0) {
            throw new Error(uiText('This card has invalid effect values. No ruling was prepared.', '此事件卡的效果数值无效，因此未准备裁定。'));
        }

        fields.title.value = event.title ?? '';
        fields.body.value = event.body ?? '';
        fields.faction.value = faction;
        fields.effect.value = effect;
        fields.value.value = String(value);
        fields.duration.value = String(duration);
        fields.public.checked = event.public ?? true;
        if (status) {
            status.style.color = '#7ee787';
            status.textContent = uiText(
                `Prepared “${event.title}”. Review the form and click Apply Adjudication to approve it. No effects have been applied.`,
                `已准备“${event.title}”。请检查表单并点击“应用裁定”批准；当前尚未应用任何效果。`
            );
        }
        fields.title.focus();
        fields.title.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    } catch (error) {
        if (status) {
            status.style.color = '#ff7b72';
            status.textContent = error.message;
        } else {
            alert(error.message);
        }
    }
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
        alert(error.message || uiText('Adjudication failed', '裁定失败'));
    }
}

async function downloadSitrep() {
    try {
        const response = await fetch('/api/committee/sitrep');
        if (!response.ok) throw new Error(uiText(
            `SITREP export failed (${response.status}).`,
            `态势报告导出失败（${response.status}）。`
        ));
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
