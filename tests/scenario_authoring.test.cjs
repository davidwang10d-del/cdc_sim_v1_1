// Run with: node tests/scenario_authoring.test.cjs
// Exercises data boundaries and export behavior without requiring browser packages.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/js/scenario_authoring.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'templates/cdc_editor.html'), 'utf8');
const inline = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match => match[1]).join('\n').replace(/render\(\);\s*loadTemplate\(false\);\s*$/, '');
const data = Object.fromEntries(['package', 'scenario', 'rules', 'units', 'weapons', 'battalions', 'objectives', 'events'].map(key => [key, JSON.parse(fs.readFileSync(path.join(root, `dlc/_template/${key}.json`), 'utf8'))]));
data.doctrine = {stances: {[data.rules.unit_defaults.stance]: {label:'Default'}}};
const alerts = [], requests = [], archives = [], downloads = [];
let rejectValidation = false;
let storedLanguage = 'en';
const context = vm.createContext({
    inputData: data, console,
    localStorage: {
        getItem: key => key === 'cdc_lang' ? storedLanguage : null,
        setItem: (key, value) => { if (key === 'cdc_lang') storedLanguage = value; }
    },
    alert: message => alerts.push(message), confirm: () => true,
    document: {
        documentElement: {lang: 'en'},
        body: {classList: {toggle() {}}},
        getElementById: () => ({innerHTML:''}), querySelectorAll: () => [],
        createElement: () => ({click() { downloads.push(this.download); }})
    },
    URL: {createObjectURL: () => 'blob:test', revokeObjectURL: () => {}},
    setTimeout: callback => callback(),
    fetch: async (url, options) => {
        requests.push({url, body: JSON.parse(options.body)});
        return {ok: !rejectValidation, status: rejectValidation ? 400 : 200, json: async () => rejectValidation ? {status:'error', msg:'Content reference rejected'} : {status:'ok'}};
    },
    JSZip: class {
        constructor() { this.files = {}; archives.push(this.files); }
        file(name, value) { this.files[name] = value; }
        async generateAsync() { return {}; }
    }
});
vm.runInContext(source, context, {filename:'scenario_authoring.js'});
vm.runInContext(inline, context, {filename:'cdc_editor.inline.js'});
vm.runInContext('db = initializePackageAuthoring(inputData)', context);
const run = code => vm.runInContext(code, context);
const failures = () => run('validateScenarioAuthoring(db).filter(check => !check.ok).map(check => check.msg)');

assert.equal(failures().length, 0, 'The server starter has valid package metadata.');
assert.equal(run('validateDlc(false).filter(check => !check.ok).length'), 0, 'Existing scenario checks still pass with package checks.');
storedLanguage = 'zh';
assert.equal(run("tr('English', '中文')"), '中文', 'The editor reads the saved Chinese locale.');
assert.equal(run("localizedDoctrineLabel('order', 'assault', {label:'Assault'})"), '进攻');
assert.equal(run("localizedDoctrineLabel('stance', 'DEFENSIVE', {label:'Defensive'})"), '防守优先');
assert.equal(run("editorCheckMessage({msg:'Scenario has a name'})"), '已填写剧本名称');
assert.equal(run("authoringMessage({msg:'Content reference rejected', msg_zh:'内容引用被拒绝'})"), '内容引用被拒绝');
storedLanguage = 'en';
run("addScenarioCard('objectives'); addScenarioCard('events')");
assert(failures().some(message => message.includes('success criteria')), 'An unfinished objective cannot be exported.');
assert(failures().some(message => message.includes('chair guidance')), 'An unfinished event cannot be exported.');
run("db.objectives.objectives[0].success_criteria = 'A chair confirms a negotiated ceasefire.'; db.events.events[0].body = 'Supply routes reopen.'; db.events.events[0].trigger_note = 'Consider after a signed agreement.'");
assert.equal(failures().length, 0);
run("db.events.events[0].title = '<img src=x onerror=alert(1)>'");
assert(!run('renderEvents()').includes('<img src=x'), 'Card text is escaped before rendering.');
run("db.events.events[0].title = 'Supply routes reopen'; db.events.events[0].faction = 'UNKNOWN_FACTION'");
assert(failures().some(message => message.includes('existing faction')));
run("db.events.events[0].faction = db.rules.directives.default_faction; setScenarioEventEffect(0, 'speed_modifier')");
assert.equal(run('db.events.events[0].value'), 1);
run('db.events.events[0].value = 101');
assert(failures().some(message => message.includes('multiplier')));
run('db.events.events[0].value = 1; db.events.events[0].duration_hours = Infinity');
assert(failures().some(message => message.includes('duration')));
run("db.events.events[0].duration_hours = 12; db.events.events[0].effect_type = 'script'");
assert(failures().some(message => message.includes('effect allowed')));
run("db.events.events[0].effect_type = 'none'; db.package.version = '1.0.0-beta'");
assert(failures().some(message => message.includes('major.minor.patch')));
run("db.package.version = '1.0.0'; db.package.id = '../escape'");
assert(failures().some(message => message.includes('Package has a safe ID')));
run("db.package.id = 'new-crisis'; db.events.events.push({...db.events.events[0]})");
assert(failures().some(message => message.includes('unique IDs')));
run('db.events.events.pop()');
run("db.package.required_capabilities = ['chair_objectives.v1']");
assert(failures().some(message => message.includes('declares support for events')));
run("db.package.required_capabilities.push('chair_events.v1'); db.package.content_hashes = {'scenario.json':'stale'}");
assert.equal(failures().length, 0);
assert.equal(run("Object.hasOwn(prepareScenarioExport().documents.package, 'content_hashes')"), false);
assert.equal(run("Object.hasOwn(db.package, 'content_hashes')"), true, 'Export prepares a copy without mutating authoring data.');
assert.equal(run('Object.keys(prepareScenarioExport().documents).length'), 8);

run("mapFiles.roads = {name:'map.geojson'}; mapFiles.rivers = {name:'MAP.geojson'}");
assert.throws(() => run('prepareScenarioExport()'), /same filename/);
run("mapFiles.rivers = null; mapFiles.roads = {name:'../escape.geojson'}");
assert.throws(() => run('prepareScenarioExport()'), /unsafe filename/);
run("mapFiles.roads = {name:'NUL.json'}");
assert.throws(() => run('prepareScenarioExport()'), /unsafe filename/);
run("mapFiles.roads = {name:'roads.py'}");
assert.throws(() => run('prepareScenarioExport()'), /unsafe filename/);
run("mapFiles.roads = {name:'roads.geojson'}; mapFiles.dem = [{name:'terrain.tif'}, {name:'TERRAIN.tif'}]");
assert.throws(() => run('prepareScenarioExport()'), /same filename/);
run("mapFiles.dem = [{name:'terrain.tif'}]");
assert.equal(run('prepareScenarioExport().documents.scenario.map_config.roads_file'), 'maps/roads.geojson');
assert.equal(run('prepareScenarioExport().documents.scenario.map_config.dem_dir'), 'maps/dem_tiles');
assert.equal(run('db.scenario.map_config.roads_file'), '', 'Map attachment paths do not mutate the editor scenario.');

(async () => {
    rejectValidation = true;
    await run('exportAll()');
    assert.equal(archives.length, 0, 'A server rejection must prevent ZIP creation.');
    assert.match(alerts.at(-1), /Content reference rejected/);
    rejectValidation = false;
    await run('exportAll()');
    assert.equal(archives.length, 1);
    assert.deepEqual(Object.keys(requests.at(-1).body).sort(), ['package','scenario','rules','units','weapons','battalions','objectives','events'].sort());
    assert.equal(requests.at(-1).url, '/api/editor_validate');
    assert.equal(downloads[0], 'new-crisis-1.0.0.zip');
    assert.deepEqual(Object.keys(archives[0]).sort(), ['package.json','scenario.json','rules.json','units.json','weapons.json','battalions.json','objectives.json','events.json','maps/roads.geojson','maps/dem_tiles/terrain.tif'].sort());
    assert.equal(JSON.parse(archives[0]['package.json']).content_hashes, undefined);
    run("db.package.id = '../invalid'");
    await run('exportAll()');
    assert.equal(archives.length, 1, 'Invalid local metadata must prevent a second export.');
    console.log('Scenario editor checks passed: metadata, cards, references, escaped rendering, safe map paths, eight JSON files and fail-closed export.');
})().catch(error => { console.error(error); process.exitCode = 1; });
