// Run with: node tests/tactical_selection.test.cjs
// Exercises nearby map-icon selection without starting Leaflet or a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/js/tactical_engine.js'), 'utf8');
const runtimeMarker = '// 🟢 1. Global Variable Registration';
const helperSource = source.slice(0, source.indexOf(runtimeMarker));
assert(helperSource.length > 0, 'The tactical helper boundary must remain available.');

const context = vm.createContext({
    localStorage: {getItem: () => 'en'},
});

vm.runInContext(`${helperSource}
const units = {
    builder: {name:'Builder Army', personnel:1000, lon:120, lat:30},
    nearby: {name:'Nearby Army', personnel:800, lon:120.035, lat:30},
    neutralized: {name:'Neutralized Army', personnel:0, lon:120, lat:30},
    distant: {name:'Distant Army', personnel:900, lon:120.08, lat:30},
};
const installations = {
    fort: {name:'Forward Fort', status:'UNDER_CONSTRUCTION', lon:120, lat:30},
    invalid: {name:'Invalid Site', lon:'unknown', lat:30},
};
globalThis.selectionResults = {
    fromFort: buildNearbyMapSelectionCandidates(units, installations, 120, 30, 'installation', 'fort'),
    tightRadius: buildNearbyMapSelectionCandidates(units, installations, 120, 30, 'unit', 'builder', 1),
};`, context, {filename: 'tactical_engine.selection_helpers.js'});

const fromFort = Array.from(context.selectionResults.fromFort, candidate => ({
    kind: candidate.kind,
    id: candidate.id,
    distanceKm: candidate.distanceKm,
}));
assert.equal(fromFort.length, 3, 'Only visible unit/installation icons within 5 km are selectable.');
assert.deepEqual(
    fromFort.map(candidate => `${candidate.kind}:${candidate.id}`),
    ['installation:fort', 'unit:builder', 'unit:nearby'],
    'The clicked icon stays first, with other icons sorted by distance.'
);
assert(fromFort[2].distanceKm > 3 && fromFort[2].distanceKm < 5);

const tightRadius = Array.from(context.selectionResults.tightRadius, candidate => `${candidate.kind}:${candidate.id}`);
assert.deepEqual(tightRadius, ['unit:builder', 'installation:fort']);
assert.equal(source.includes("handleSelectableMarkerClick('unit', uid, e)"), true);
assert.equal(source.includes("handleSelectableMarkerClick('installation', installationId, event)"), true);
assert.equal(source.includes('mapClickHandler({latlng:'), true, 'Installation targeting must remain available.');

const handlerStart = source.indexOf('function handleSelectableMarkerClick');
const handlerEnd = source.indexOf('\nfunction refreshUnitsSmoothly', handlerStart);
assert(handlerStart > 0 && handlerEnd > handlerStart, 'The shared marker handler must remain independently testable.');
const handlerSource = source.slice(handlerStart, handlerEnd);
const interactionContext = vm.createContext({
    localStorage: {getItem: () => 'en'},
    interaction: {stopped: 0, menuCandidates: null, directSelection: null, refreshed: 0},
    L: {DomEvent: {stopPropagation: () => { interactionContext.interaction.stopped += 1; }}},
});
vm.runInContext(`${helperSource}
let latestUnits = {builder: {name:'Builder Army', personnel:1000, lon:120, lat:30}};
let latestInstallations = {fort: {name:'Forward Fort', lon:120, lat:30}};
function showNearbySelectionMenu(candidates) { interaction.menuCandidates = candidates.map(item => item.kind + ':' + item.id); }
function selectMapObject(kind, id) { interaction.directSelection = kind + ':' + id; }
function fetchState() { interaction.refreshed += 1; }
${handlerSource}
handleSelectableMarkerClick('installation', 'fort', {});
latestInstallations = {};
handleSelectableMarkerClick('unit', 'builder', {});`, interactionContext, {filename: 'tactical_engine.marker_handler.js'});
assert.equal(interactionContext.interaction.stopped, 2, 'Both marker clicks stop the underlying map click.');
assert.deepEqual(
    Array.from(interactionContext.interaction.menuCandidates),
    ['installation:fort', 'unit:builder'],
    'Clicking a fort over its builder opens the chooser with both icons.'
);
assert.equal(interactionContext.interaction.directSelection, 'unit:builder', 'A single nearby icon keeps one-click selection.');
assert.equal(interactionContext.interaction.refreshed, 0);

console.log('Tactical selection checks passed: 5 km filtering, ordering, overlapping marker clicks, and direct single-icon selection.');
