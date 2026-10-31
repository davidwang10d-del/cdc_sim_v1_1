// Run with: node tests/tactical_localization.test.cjs
// Exercises language helpers without starting Leaflet or a browser.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'static/js/tactical_engine.js'), 'utf8');
const runtimeMarker = '// 🟢 1. Global Variable Registration';
const helperSource = source.slice(0, source.indexOf(runtimeMarker));
assert(helperSource.length > 0, 'The localization helper boundary must remain available.');

const context = vm.createContext({
    localStorage: {getItem: key => key === 'cdc_lang' ? 'zh' : null},
});

vm.runInContext(`${helperSource}
const globalRules = {
    orders: {
        default_role: 'hold',
        modes: {
            hold: {id:'HOLD', label:'Hold', summary:'STOP', description:'Remain in place.', color:'#888'},
            assault: {id:'ASSAULT', label:'Assault', summary:'MOVE', description:'Seek contact.', color:'#d97706'}
        }
    }
};
globalThis.localizationResults = {
    apiMessage: apiResponseMessage({msg:'English response', msg_zh:'中文响应'}, 'fallback'),
    combatEffect: localizedEffectType('combat_modifier'),
    speedEffect: localizedEffectType('speed_modifier'),
    defendingStatus: localizedOperationalStatus('DEFENDING'),
    neutralizedStatus: localizedOperationalStatus('NEUTRALIZED'),
    emojiLog: localizeEngineLogMessage('⚔️ [Assault] Alpha One advanced.'),
    plainLog: localizeEngineLogMessage('[Relocate] Alpha One moved.'),
    systemLog: localizeEngineLogMessage('🔄 [System] Initial tactical scenario [Operation Sunrise] loaded successfully.'),
    intelLog: localizeEngineLogMessage('👁️ [Intel] Alpha One saw through concealment and acquired Bravo Two.'),
    crisisLog: localizeEngineLogMessage('[Public Crisis Update] Ceasefire proposed (GLOBAL, 3 units affected)'),
    authoredBracketLog: localizeEngineLogMessage('[Public Crisis Update] Debate [System] (GLOBAL, 1 units affected)'),
    saveLog: localizeEngineLogMessage('💾 [System] Battle state manually saved to: [slot_1].'),
    destroyedTargetLog: localizeEngineLogMessage('💥 [Military Target Destroyed] Hill Fort was destroyed by Alpha One (direct fire).'),
    fireMissionLog: localizeEngineLogMessage('🛑 [Fire Mission] Red Battery ceased fire: planned duration elapsed; estimated casualties 12; military-target integrity damage 30.'),
    closeCombatLog: localizeEngineLogMessage('⚔️ [Close Combat] Alpha One and Bravo Two entered direct combat.'),
    unknownLog: localizeEngineLogMessage('Alpha One held position.'),
    assaultProfile: orderProfileByRole('assault'),
    stanceProfile: localizedStanceProfile('DEFENSIVE', {label:'Defensive', description:'English doctrine', combat_multiplier:1})
};`, context, {filename:'tactical_engine.helpers.js'});

const result = context.localizationResults;
assert.equal(result.apiMessage, '中文响应');
assert.equal(result.combatEffect, '战斗倍率');
assert.equal(result.speedEffect, '移动速度倍率');
assert.equal(result.defendingStatus, '防御中');
assert.equal(result.neutralizedStatus, '失去战斗力');
assert.equal(result.emojiLog, '⚔️ [进攻] Alpha One advanced.');
assert.equal(result.plainLog, '[安全转移] Alpha One moved.');
assert.equal(result.systemLog, '🔄 [系统] 初始战术剧本 [Operation Sunrise] 已成功载入。');
assert.equal(result.intelLog, '👁️ [情报] Alpha One 识破了 Bravo Two 的隐蔽并发现该部队。');
assert.equal(result.crisisLog, '[公开危机更新] Ceasefire proposed（GLOBAL，影响 3 支部队）');
assert.equal(result.authoredBracketLog, '[公开危机更新] Debate [System]（GLOBAL，影响 1 支部队）', 'Authored bracketed title text stays unchanged.');
assert.equal(result.saveLog, '💾 [系统] 战斗状态已手动保存到：[slot_1]。');
assert.equal(result.destroyedTargetLog, '💥 [摧毁军事目标] Hill Fort 已被 Alpha One 摧毁（直接火力）。');
assert.equal(result.fireMissionLog, '🛑 [火力任务] Red Battery 已停止射击：计划持续时间已结束；预计伤亡 12 人；军事目标完整度损失 30。');
assert.equal(result.closeCombatLog, '⚔️ [近距离交战] Alpha One 与 Bravo Two 已开始近距离交战。');
assert.equal(result.unknownLog, 'Alpha One held position.', 'Authored or unrecognized log text stays unchanged.');
assert.equal(result.assaultProfile.label, '进攻');
assert.equal(result.assaultProfile.id, 'ASSAULT', 'Localization must preserve the engine order ID.');
assert.equal(result.stanceProfile.label, '防守优先');
assert.equal(result.stanceProfile.combat_multiplier, 1, 'Localization must preserve stance mechanics.');

assert.match(source, /uiText\('Operational Order', '部队命令'\)/);
assert.match(source, /uiText\('Public Crisis Updates', '公开危机更新'\)/);
assert.match(source, /uiText\('Set Stance', '应用'\)/);
assert.match(source, /遇到敌军时是否主动交战/);
assert.doesNotMatch(source, /接触政策|射击纪律|战术授权/);

console.log('Tactical localization checks passed: API copy, effects, statuses, doctrine, logs, and critical panels.');
