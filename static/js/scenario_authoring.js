/* Data-only scenario pack authoring. Simulation behavior remains in the engine. */
const SCENARIO_PACKAGE_FILES = Object.freeze({
    scenario: 'scenario.json', rules: 'rules.json', units: 'units.json',
    weapons: 'weapons.json', battalions: 'battalions.json',
    objectives: 'objectives.json', events: 'events.json'
});
const SCENARIO_CARD_EFFECTS = Object.freeze(['none', 'morale', 'supply', 'fatigue', 'combat_modifier', 'speed_modifier']);
function authoringIsChinese() {
    return typeof editorIsChinese === 'function' && editorIsChinese();
}

function authoringText(en, zh) {
    return authoringIsChinese() ? zh : en;
}

function authoringMessage(check) {
    if (!authoringIsChinese()) return check.msg;
    if (check.msg_zh) return check.msg_zh;
    return typeof editorValidationChinese === 'function' ? editorValidationChinese(check.msg) : check.msg;
}

function initializePackageAuthoring(data) {
    data.package = data.package || {
        schema_version: 1, id: 'my-scenario', version: '1.0.0',
        name: data.scenario.scenario_name || 'My Scenario', description: '',
        publisher: '', license: '', engine_api_version: 1,
        required_capabilities: ['chair_objectives.v1', 'chair_events.v1'],
        files: {...SCENARIO_PACKAGE_FILES}
    };
    data.objectives = data.objectives || {schema_version: 1, objectives: []};
    data.events = data.events || {schema_version: 1, events: []};
    // Hashes belong to the final release builder; editing invalidates a previous seal.
    delete data.package.content_hashes;
    return data;
}

function packageInput(label, path, value, options={}) {
    const type = options.type || 'text';
    const attrs = type === 'number'
        ? `step="any" min="${options.min ?? 0}" max="${options.max ?? 1000000}"`
        : `maxlength="${options.maxLength || 160}"`;
    return `<div><label>${esc(label)}</label><input type="${type}" ${attrs} value="${esc(value)}" onchange="setPath(db, '${path}', this.type === 'number' ? (this.value.trim() ? Number(this.value) : NaN) : this.value)"></div>`;
}

function packageText(label, path, value, maxLength=4000) {
    return `<div style="grid-column:1/-1;"><label>${esc(label)}</label><textarea maxlength="${maxLength}" onchange="setPath(db, '${path}', this.value)">${esc(value)}</textarea></div>`;
}

function renderMetadata() {
    const p = db.package;
    return `<div class="section"><h2>${authoringText('Package Metadata', '剧本包信息')}</h2>
        <p class="hint">${authoringText("Give this pack a stable ID and a release version. Use a new version whenever you publish changed content. Your scenario content can be created and distributed without changing engine code.", "为剧本包设置稳定的 ID 和发布版本。每次发布变更后的内容时都应使用新版本。创建和分发剧本内容无需修改引擎代码。")}</p>
        <div class="grid">
            ${packageInput(authoringText('Package ID (letters, numbers, _, -, .)', '剧本包 ID（字母、数字、_、-、.）'), 'package.id', p.id, {maxLength:64})}
            ${packageInput(authoringText('Version (for example 1.0.0)', '版本（例如 1.0.0）'), 'package.version', p.version, {maxLength:32})}
            ${packageInput(authoringText('Pack display name', '剧本包显示名称'), 'package.name', p.name)}
            ${packageInput(authoringText('Publisher / author', '发布者 / 作者'), 'package.publisher', p.publisher)}
            ${packageText(authoringText('Pack description', '剧本包简介'), 'package.description', p.description, 2000)}
            ${packageText(authoringText('Content license / permitted use', '内容许可 / 允许用途'), 'package.license', p.license, 1000)}
        </div>
        <p class="hint" style="margin-top:12px;">${authoringText("The license field records your content terms. It does not collect payment, grant an entitlement, or restrict who can open an exported pack.", "许可字段用于记录内容使用条款，不会收取费用、授予权益，也不会限制谁能打开导出的剧本包。")}</p>
    </div>`;
}

function scenarioCardFactions(data=db) {
    const factions = new Set([data.rules?.directives?.default_faction || 'GLOBAL']);
    for (const unit of Object.values(data.units || {})) if (unit.faction) factions.add(unit.faction);
    for (const role of data.scenario.committee?.delegate_roles || []) if (role.faction) factions.add(role.faction);
    for (const bloc of data.scenario.diplomacy_blocs || []) for (const member of bloc.members || []) factions.add(member);
    return [...factions];
}

function cardFactionInput(path, value) {
    const factions = scenarioCardFactions();
    if (value && !factions.includes(value)) factions.push(value);
    return `<div><label>${authoringText('Faction', '阵营')}</label><select onchange="setPath(db, '${path}', this.value)">${factions.map(f => `<option value="${esc(f)}" ${value === f ? 'selected' : ''}>${esc(f)}</option>`).join('')}</select></div>`;
}

function scenarioEffectLabel(effect) {
    const labels = {
        none: ['No mechanical effect', '无数值效果'],
        morale: ['Morale change', '士气变化'],
        supply: ['Supply change', '补给变化'],
        fatigue: ['Fatigue change', '疲劳变化'],
        combat_modifier: ['Combat modifier', '战斗倍率'],
        speed_modifier: ['Speed modifier', '速度倍率']
    };
    const label = labels[effect];
    return label ? authoringText(label[0], label[1]) : effect.replaceAll('_', ' ');
}

function nextCardId(kind) {
    const existing = new Set(db[kind][kind].map(card => card.id));
    const prefix = kind === 'objectives' ? 'objective' : 'event';
    let next = 1;
    while (existing.has(`${prefix}_${next}`)) next++;
    return `${prefix}_${next}`;
}

function addScenarioCard(kind) {
    if (!['objectives', 'events'].includes(kind)) return;
    if (db[kind][kind].length >= 500) { alert(authoringText('A pack can contain at most 500 cards of each type.', '每种卡片在一个剧本包中最多可有 500 张。')); return; }
    const common = {id: nextCardId(kind), title: '', faction: db.rules?.directives?.default_faction || 'GLOBAL'};
    const card = kind === 'objectives'
        ? {...common, title: 'New objective', description: '', success_criteria: '', points: 0}
        : {...common, title: 'New event', body: '', trigger_note: '', effect_type: 'none', value: 0, duration_hours: db.rules?.directives?.default_duration_hours || 12, public: true};
    db[kind][kind].push(card);
    const capability = kind === 'objectives' ? 'chair_objectives.v1' : 'chair_events.v1';
    if (!db.package.required_capabilities.includes(capability)) db.package.required_capabilities.push(capability);
    render();
}

function renderObjectives() {
    const cards = db.objectives.objectives;
    return `<div class="section"><h2>${authoringText('Objectives', '目标')}</h2>
        <p class="hint">${authoringText("Define outcomes for chairs to review during the committee. Success criteria and points are guidance: the engine does not automatically detect completion or award scores.", "定义供主席团在委员会期间审核的目标。成功标准和分数仅供参考；引擎不会自动判定完成情况或计分。")}</p>
        <div class="toolbar"><button class="btn secondary" onclick="addScenarioCard('objectives')" ${cards.length >= 500 ? 'disabled' : ''}>${authoringText("Add objective", "添加目标")}</button><span class="small">${cards.length} / 500</span></div>
        ${cards.length ? cards.map((card, i) => `<div class="card">
            <div class="card-title"><b>${esc(card.title || authoringText('Untitled objective', '未命名目标'))}</b><button class="btn danger" onclick="db.objectives.objectives.splice(${i}, 1); render()">${authoringText("Delete", "删除")}</button></div>
            <div class="grid">
                ${packageInput(authoringText('Objective ID', '目标 ID'), `objectives.objectives.${i}.id`, card.id, {maxLength:64})}
                ${packageInput(authoringText('Title', '标题'), `objectives.objectives.${i}.title`, card.title)}
                ${cardFactionInput(`objectives.objectives.${i}.faction`, card.faction)}
                ${packageInput(authoringText('Suggested points', '建议分值'), `objectives.objectives.${i}.points`, card.points, {type:'number'})}
                ${packageText(authoringText('Description / chair context', '说明 / 主席团背景'), `objectives.objectives.${i}.description`, card.description)}
                ${packageText(authoringText('Success criteria for chair review', '供主席团审核的成功标准'), `objectives.objectives.${i}.success_criteria`, card.success_criteria)}
            </div></div>`).join('') : `<div class="card small">${authoringText("No objective cards. Existing committee victory conditions remain available.", "尚未添加目标卡；仍可使用委员会现有的胜利条件。")}</div>`}
    </div>`;
}

function setScenarioEventEffect(index, effect) {
    if (!SCENARIO_CARD_EFFECTS.includes(effect)) return;
    db.events.events[index].effect_type = effect;
    db.events.events[index].value = effect.endsWith('_modifier') ? 1 : 0;
    render();
}

function renderEvents() {
    const cards = db.events.events;
    const allowed = SCENARIO_CARD_EFFECTS.filter(effect => (db.rules?.directives?.allowed_effects || []).includes(effect));
    return `<div class="section"><h2>${authoringText('Chair Event Cards', '主席事件卡')}</h2>
        <p class="hint">${authoringText("Write reusable crisis injections and suggested directive effects. A chair reviews the trigger note and chooses when to issue each event. There are no automatic triggers or executable scripts.", "编写可复用的危机注入和建议指令效果。主席审核触发说明并决定何时发布事件；系统不会自动触发事件，也不执行脚本。")}</p>
        <div class="toolbar"><button class="btn secondary" onclick="addScenarioCard('events')" ${cards.length >= 500 ? 'disabled' : ''}>${authoringText("Add event", "添加事件")}</button><span class="small">${cards.length} / 500</span></div>
        ${cards.length ? cards.map((card, i) => {
            const effects = allowed.includes(card.effect_type) ? allowed : [...allowed, card.effect_type];
            const multiplier = ['combat_modifier', 'speed_modifier'].includes(card.effect_type);
            return `<div class="card">
            <div class="card-title"><b>${esc(card.title || authoringText('Untitled event', '未命名事件'))}</b><button class="btn danger" onclick="db.events.events.splice(${i}, 1); render()">${authoringText("Delete", "删除")}</button></div>
            <div class="grid">
                ${packageInput(authoringText('Event ID', '事件 ID'), `events.events.${i}.id`, card.id, {maxLength:64})}
                ${packageInput(authoringText('Title', '标题'), `events.events.${i}.title`, card.title)}
                ${cardFactionInput(`events.events.${i}.faction`, card.faction)}
                <div><label>${authoringText("Suggested effect", "建议效果")}</label><select onchange="setScenarioEventEffect(${i}, this.value)">${effects.map(effect => `<option value="${esc(effect)}" ${effect === card.effect_type ? 'selected' : ''}>${esc(scenarioEffectLabel(effect))}</option>`).join('')}</select></div>
                ${packageInput(multiplier ? authoringText('Effect multiplier (1 = unchanged)', '效果倍率（1 表示不变）') : authoringText('Effect amount (ignored for none)', '效果数值（无效果时忽略）'), `events.events.${i}.value`, card.value, {type:'number', min:multiplier ? 0 : -1000000, max:multiplier ? 100 : 1000000})}
                ${packageInput(authoringText('Effect duration in simulation hours', '效果持续时间（推演小时）'), `events.events.${i}.duration_hours`, card.duration_hours, {type:'number', min:0.001, max:87600})}
                ${packageText(authoringText('Event text / directive body', '事件文本 / 指令正文'), `events.events.${i}.body`, card.body)}
                ${packageText(authoringText('When a chair should consider this event', '主席应考虑发布此事件的时机'), `events.events.${i}.trigger_note`, card.trigger_note)}
                <div><label><input style="width:auto;" type="checkbox" ${card.public ? 'checked' : ''} onchange="db.events.events[${i}].public=this.checked"> ${authoringText("Publish the directive when a chair issues this card", "主席发布此卡时公开该指令")}</label></div>
            </div></div>`;
        }).join('') : `<div class="card small">${authoringText("No event cards. Chairs can continue issuing ordinary directives during play.", "尚未添加事件卡；主席仍可在推演中发布普通指令。")}</div>`}
    </div>`;
}

function authoringValidationChinese(message) {
    const fixed = {
        'Package uses the supported format and engine content API': '剧本包使用受支持的格式和引擎内容 API',
        'Package has a safe ID of at most 64 characters': '剧本包 ID 安全且不超过 64 个字符',
        'Package version is major.minor.patch (for example 1.0.0)': '剧本包版本采用 主版本.次版本.修订号 格式（例如 1.0.0）',
        'Package name is present and at most 160 characters': '剧本包名称已填写且不超过 160 个字符',
        'Package publisher is present and at most 160 characters': '剧本包发布者已填写且不超过 160 个字符',
        'Package description is at most 2000 characters': '剧本包简介不超过 2000 个字符',
        'Package has content license terms of at most 1000 characters': '剧本包已填写不超过 1000 个字符的内容许可条款',
        'Package references its seven canonical content files': '剧本包引用了全部七个标准内容文件',
        'Package capabilities form a unique list': '剧本包能力列表没有重复项',
        'objectives use format 1 and contain at most 500 cards': '目标文件使用格式 1 且最多包含 500 张卡片',
        'events use format 1 and contain at most 500 cards': '事件文件使用格式 1 且最多包含 500 张卡片',
        'objectives have unique IDs': '所有目标 ID 均不重复',
        'events have unique IDs': '所有事件 ID 均不重复',
        'Package declares support for objectives': '剧本包声明支持目标卡',
        'Package declares support for events': '剧本包声明支持事件卡'
    };
    if (fixed[message]) return fixed[message];
    return message
        .replace(/^objectives card (\d+)/, '目标卡 $1')
        .replace(/^events card (\d+)/, '事件卡 $1')
        .replace(' is a card object', ' 是有效的卡片对象')
        .replace(' has a safe ID', ' 使用安全的 ID')
        .replace(' has a title of at most 160 characters', ' 已填写标题且不超过 160 个字符')
        .replace(' references an existing faction or the all-factions token', ' 引用了现有阵营或全阵营标记')
        .replace(' has success criteria; both text fields are at most 4000 characters', ' 已填写成功标准，且两个文本字段均不超过 4000 个字符')
        .replace(' points are between 0 and 1000000', ' 的分值介于 0 到 1000000')
        .replace(' has event text and chair guidance of at most 4000 characters each', ' 已填写事件文本与主席指引，且各不超过 4000 个字符')
        .replace(' uses an effect allowed by simulation rules', ' 使用推演规则允许的效果')
        .replace(' has a valid multiplier (0 to 100)', ' 的倍率有效（0 到 100）')
        .replace(' has a valid effect amount (-1000000 to 1000000)', ' 的效果数值有效（-1000000 到 1000000）')
        .replace(' duration is positive and at most 87600 hours', ' 的持续时间大于 0 且不超过 87600 小时')
        .replace(' defines whether the issued directive is public', ' 已指定发布后的指令是否公开');
}
function validateScenarioAuthoring(data=db) {
    const checks = [];
    const check = (ok, msg) => checks.push({ok: Boolean(ok), msg, msg_zh: authoringValidationChinese(msg)});
    const boundedText = (value, maximum, required=false) => typeof value === 'string' && value.length <= maximum && (!required || Boolean(value.trim()));
    const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}$/.test(value);
    const p = data.package || {};
    check(p.schema_version === 1 && p.engine_api_version === 1, 'Package uses the supported format and engine content API');
    check(safeId(p.id), 'Package has a safe ID of at most 64 characters');
    check(typeof p.version === 'string' && /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(p.version), 'Package version is major.minor.patch (for example 1.0.0)');
    for (const field of ['name', 'publisher']) check(boundedText(p[field], 160, true), `Package ${field} is present and at most 160 characters`);
    check(boundedText(p.description, 2000), 'Package description is at most 2000 characters');
    check(boundedText(p.license, 1000, true), 'Package has content license terms of at most 1000 characters');
    check(p.files && Object.keys(p.files).length === 7 && Object.entries(SCENARIO_PACKAGE_FILES).every(([key, path]) => p.files[key] === path), 'Package references its seven canonical content files');
    check(Array.isArray(p.required_capabilities) && new Set(p.required_capabilities).size === p.required_capabilities.length, 'Package capabilities form a unique list');
    const factions = new Set(scenarioCardFactions(data));
    for (const kind of ['objectives', 'events']) {
        const document = data[kind];
        const cards = Array.isArray(document?.[kind]) ? document[kind] : [];
        check(document?.schema_version === 1 && Array.isArray(document?.[kind]) && cards.length <= 500, `${kind} use format 1 and contain at most 500 cards`);
        check(new Set(cards.map(card => card?.id)).size === cards.length, `${kind} have unique IDs`);
        const capability = kind === 'objectives' ? 'chair_objectives.v1' : 'chair_events.v1';
        check(!cards.length || (p.required_capabilities || []).includes(capability), `Package declares support for ${kind}`);
        cards.forEach((card, i) => {
            const label = `${kind} card ${i + 1}`;
            if (!card || typeof card !== 'object') { check(false, `${label} is a card object`); return; }
            check(safeId(card.id), `${label} has a safe ID`);
            check(boundedText(card.title, 160, true), `${label} has a title of at most 160 characters`);
            check(factions.has(card.faction), `${label} references an existing faction or the all-factions token`);
            if (kind === 'objectives') {
                check(boundedText(card.description, 4000) && boundedText(card.success_criteria, 4000, true), `${label} has success criteria; both text fields are at most 4000 characters`);
                check(Number.isFinite(card.points) && card.points >= 0 && card.points <= 1000000, `${label} points are between 0 and 1000000`);
            } else {
                check(boundedText(card.body, 4000, true) && boundedText(card.trigger_note, 4000, true), `${label} has event text and chair guidance of at most 4000 characters each`);
                check(SCENARIO_CARD_EFFECTS.includes(card.effect_type) && (data.rules?.directives?.allowed_effects || []).includes(card.effect_type), `${label} uses an effect allowed by simulation rules`);
                const multiplier = ['combat_modifier', 'speed_modifier'].includes(card.effect_type);
                check(Number.isFinite(card.value) && card.value >= (multiplier ? 0 : -1000000) && card.value <= (multiplier ? 100 : 1000000), `${label} has a valid ${multiplier ? 'multiplier (0 to 100)' : 'effect amount (-1000000 to 1000000)'}`);
                check(Number.isFinite(card.duration_hours) && card.duration_hours > 0 && card.duration_hours <= 87600, `${label} duration is positive and at most 87600 hours`);
                check(typeof card.public === 'boolean', `${label} defines whether the issued directive is public`);
            }
        });
    }
    return checks;
}

function prepareScenarioExport(data=db, attachments=mapFiles) {
    const documents = {};
    for (const key of ['package', ...Object.keys(SCENARIO_PACKAGE_FILES)]) documents[key] = JSON.parse(JSON.stringify(data[key]));
    delete documents.package.content_hashes;
    const files = [];
    const paths = new Set();
    const addMap = (file, directory, extensions) => {
        const name = file?.name || '';
        if (!name || /[\\/:*?"<>|\x00-\x1f]/.test(name) || /[. ]$/.test(name) || /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name) || !extensions.some(ext => name.toLowerCase().endsWith(ext))) {
            throw new Error(authoringText(`Map attachment has an unsupported or unsafe filename: ${name || '(empty)'}`, `地图附件的文件名不受支持或不安全：${name || '（空）'}`));
        }
        const path = `${directory}/${name}`;
        if (paths.has(path.toLowerCase())) throw new Error(authoringText(`Two map attachments use the same filename: ${name}. Rename one before exporting.`, `两个地图附件使用了相同文件名：${name}。请重命名其中一个后再导出。`));
        paths.add(path.toLowerCase());
        files.push({path, file});
        return path;
    };
    const map = documents.scenario.map_config;
    for (const kind of ['roads', 'rivers', 'provinces']) {
        const extensions = kind === 'roads' ? ['.tif', '.tiff', '.geojson', '.json'] : ['.geojson', '.json'];
        map[`${kind}_file`] = attachments[kind] ? addMap(attachments[kind], 'maps', extensions) : '';
    }
    map.dem_file = '';
    map.dem_dir = attachments.dem.length ? 'maps/dem_tiles' : '';
    for (const file of attachments.dem) addMap(file, 'maps/dem_tiles', ['.tif', '.tiff']);
    return {documents, files};
}

async function validateScenarioOnServer(documents) {
    const response = await fetch('/api/editor_validate', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(documents)
    });
    const result = await response.json();
    if (!response.ok || result.status !== 'ok') throw new Error((authoringIsChinese() && result.msg_zh) || result.msg || result.error || authoringText(`Package validation failed (${response.status})`, `剧本包验证失败（${response.status}）`));
}

async function checkScenarioPackage() {
    if (!db) return;
    try {
        const failures = validateDlc(false).filter(check => !check.ok);
        if (failures.length) throw new Error(failures.map(authoringMessage).join('\n'));
        const prepared = prepareScenarioExport();
        await validateScenarioOnServer(prepared.documents);
        alert(authoringText('Package checks passed. Metadata, content references, objective cards and event cards are valid. Attached map paths are checked; map contents are validated when the release is built.', '剧本包检查通过。元数据、内容引用、目标卡和事件卡均有效。附件地图路径已检查；地图内容将在构建发布包时验证。')); 
    } catch (error) {
        alert(authoringText('Package needs attention:\n', '剧本包需要处理以下问题：\n') + error.message);
    }
}

let scenarioExportInProgress = false;
async function exportScenarioPackage() {
    if (!db || scenarioExportInProgress) return;
    scenarioExportInProgress = true;
    try {
        const failures = validateDlc(false).filter(check => !check.ok);
        if (failures.length) throw new Error(failures.map(authoringMessage).join('\n'));
        if (typeof JSZip === 'undefined') throw new Error(authoringText('ZIP library unavailable. Reload the editor or repair the installation.', 'ZIP 库不可用。请重新载入编辑器或修复安装。')); 
        const prepared = prepareScenarioExport();
        await validateScenarioOnServer(prepared.documents);
        const zip = new JSZip();
        zip.file('package.json', JSON.stringify(prepared.documents.package, null, 2));
        for (const [key, path] of Object.entries(SCENARIO_PACKAGE_FILES)) zip.file(path, JSON.stringify(prepared.documents[key], null, 2));
        for (const attachment of prepared.files) zip.file(attachment.path, attachment.file);
        const blob = await zip.generateAsync({type:'blob'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `${prepared.documents.package.id}-${prepared.documents.package.version}.zip`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    } catch (error) {
        alert(authoringText('Export stopped. Fix the package before trying again:\n', '导出已停止。请修复剧本包后重试：\n') + error.message);
    } finally {
        scenarioExportInProgress = false;
    }
}
