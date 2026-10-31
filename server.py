from flask import Flask, jsonify, request, render_template, Response, has_request_context
import threading
import os
import logging
import sys
import importlib.util
import math
import json
import re
from pathlib import Path
import tempfile
from copy import deepcopy
import ipaddress
import webbrowser
from urllib.request import urlopen
from werkzeug.exceptions import HTTPException

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Import core components and validated DLC packages
from app import MilitaryUnit
from engine import SimulationEngine
from gis import haversine_distance 
from scenario_package import safe_relative_path
from beta_backup import (
    BackupError, MAX_ARCHIVE_BYTES, create_backup, migrate_legacy_checkpoints, restore_backup,
)
from beta_runtime import (
    configure_runtime_logging, load_build_info, load_runtime_config,
    prepare_runtime_directories, public_health_payload, record_runtime_exception,
    support_diagnostics,
)
from dlc_loader import (
    DLCValidationError,
    PROJECT_ROOT,
    load_dlc_package,
    load_dlc_directory,
    scan_dlcs,
    validate_identifier,
)

BUILD_INFO = load_build_info()
RUNTIME_CONFIG = prepare_runtime_directories(load_runtime_config())
RUNTIME_LOGGER = configure_runtime_logging(
    RUNTIME_CONFIG, BUILD_INFO, logger_name="cdc_sim", console=not bool(getattr(sys, "frozen", False))
)

# Runtime failures are written to a rotating local JSON log.
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = RUNTIME_CONFIG.profile == "development"
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0 if RUNTIME_CONFIG.profile == "development" else 3600
app.config["MAX_CONTENT_LENGTH"] = MAX_ARCHIVE_BYTES + 1024 * 1024

# 🟢 Global variables: Engine and physics thread initialized as empty shells
engine = None
physics_thread = None
engine_guard = threading.RLock()
MANUAL_SAVE_SLOTS = ("slot_1", "slot_2", "slot_3")


class APIInputError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


_API_MESSAGE_ZH = {
    "This support action is available only from the local CDC Sim interface": "此支持操作只能从本机 CDC Sim 界面执行。",
    "Request body must be a JSON object": "请求内容必须是 JSON 对象。",
    "System is idling, please mount a campaign first": "系统当前处于待机状态，请先加载一个剧本。",
    "Choose manual checkpoint 1, 2, or 3": "请选择手动检查点 1、2 或 3。",
    "The scenario builder is unavailable.": "剧本生成器当前不可用。",
    "Editor draft exceeds the 16 MiB limit": "编辑器草稿超过 16 MiB 限制。",
    "Expected an application/json draft": "应提交 application/json 格式的草稿。",
    "Draft must be an object": "草稿必须是对象。",
    "Draft must contain scenario, units, battalions, weapons, rules, package, objectives and events": "草稿必须包含 scenario、units、battalions、weapons、rules、package、objectives 和 events。",
    "dem_dir must be maps/dem_tiles": "dem_dir 必须为 maps/dem_tiles。",
    "The package could not be checked.": "无法检查该剧本包。",
    "The scenario could not be opened.": "无法打开该剧本。",
    "Command is empty": "命令不能为空。",
    "Unit not found": "未找到该部队。",
    "A neutralized unit cannot receive movement orders": "已失去战斗力的部队无法接收移动命令。",
    "This unit type cannot receive a ground-assault order": "此部队类型无法接收地面进攻命令。",
    "Waypoints must be a list": "途经点必须是列表。",
    "Each waypoint must contain lon and lat": "每个途经点必须包含经度 lon 和纬度 lat。",
    "Target coordinates not provided": "未提供目标坐标。",
    "A neutralized unit cannot execute a support mission": "已失去战斗力的部队无法执行支援任务。",
    "This unit already has an active support mission; halt it before issuing another": "该部队已有正在执行的支援任务；请先停止任务再下达新任务。",
    "This unit has bombard capability but its battalions mount no indirect bombard weapon": "该部队具备炮击能力，但所属营没有装备间接火力武器。",
    "This unit has airstrike capability but its battalions mount no airstrike-role weapon": "该部队具备空袭能力，但所属营没有装备可执行空袭任务的武器。",
    "Unit lacks ammunition/supply for a fire mission": "该部队缺少执行火力任务所需的弹药或补给。",
    "Builder unit not found": "未找到执行建设的部队。",
    "A neutralized unit cannot build an installation": "已失去战斗力的部队无法建设军事设施。",
    "This unit type cannot construct a ground installation": "此部队类型无法建设地面军事设施。",
    "The builder must be stationary and free of an active support mission": "执行建设的部队必须保持静止，且不能有正在进行的支援任务。",
    "This unit has reached its active construction-project limit": "该部队正在进行的建设项目已达上限。",
    "A neutralized unit cannot prepare a defense": "已失去战斗力的部队无法构筑防御。",
    "This unit type cannot prepare a ground-defense position": "此部队类型无法构筑地面防御阵地。",
    "The command could not be completed.": "无法完成该命令。",
    "Unit name and faction are required": "必须填写部队名称和阵营。",
    "Unit name and faction cannot be empty": "部队名称和阵营不能为空。",
    "Unit ID conflict": "部队 ID 冲突。",
    "City not found": "未找到该城市。",
    "City action must be upsert or delete": "城市操作必须为保存或删除。",
    "City ID conflict": "城市 ID 冲突。",
    "Province and faction are required": "必须填写省份和阵营。",
    "Province faction record not found": "未找到该省份的阵营记录。",
    "Province politics action must be upsert or delete": "省份政治操作必须为保存或删除。",
    "Province faction record already exists": "该省份的阵营记录已存在。",
    "Original province faction record not found": "未找到原省份阵营记录。",
    "Both factions are required": "必须填写两个阵营。",
    "Diplomacy requires two different factions": "外交设置需要两个不同的阵营。",
    "allied must be true or false": "allied 必须为 true 或 false。",
    "Save at least one manual checkpoint before downloading a backup": "下载备份前，请至少保存一个手动检查点。",
    "Save uses an incompatible DLC rules schema": "存档使用的剧本规则版本不兼容。",
    "Autosave is disabled; choose a manual checkpoint": "自动保存已停用；请选择手动检查点。",
    "Backup scenario ID is invalid": "备份中的剧本 ID 无效。",
    "Expanded checkpoint data exceeds the backup limit": "展开后的检查点数据超过备份大小限制。",
    "Backup exceeds the archive limit": "备份超过压缩包大小限制。",
    "Backup file is empty or exceeds 64 MiB": "备份文件为空或超过 64 MiB。",
    "Backup contains duplicate or case-colliding names": "备份包含重复名称或仅大小写不同的冲突名称。",
    "Backup contains unsupported files": "备份包含不受支持的文件。",
    "Backup directories and encrypted entries are not supported": "不支持备份目录或加密条目。",
    "Backup links are not supported": "备份中不允许包含链接。",
    "Expanded backup exceeds 64 MiB": "展开后的备份超过 64 MiB。",
    "Backup is not a readable ZIP archive": "备份不是可读取的 ZIP 压缩包。",
    "Backup manifest format is unsupported": "备份清单格式不受支持。",
    "Backup belongs to a different scenario": "该备份属于另一个剧本。",
    "Backup creation time is invalid": "备份创建时间无效。",
    "Backup file inventory does not match its contents": "备份文件清单与实际内容不一致。",
    "Backup restorable-file inventory is invalid": "备份中可恢复文件的清单无效。",
    "Backup omitted-file inventory is invalid": "备份中省略文件的清单无效。",
    "Backup restore confirmation is required": "恢复备份前必须确认。",
    "Choose a CDC Sim backup ZIP": "请选择 CDC Sim 备份 ZIP 文件。",
    "Backup exceeds 64 MiB": "备份文件超过 64 MiB。",
    "The checkpoint could not be written.": "无法写入检查点。",
    "The backup could not be created.": "无法创建备份。",
    "The backup could not be restored.": "无法恢复备份。",
    "An unexpected error occurred.": "发生意外错误。",
    "Execution successful": "执行成功。",
    "Simulation paused": "推演已暂停。",
    "Simulation resumed": "推演已继续。",
    "Backup imported and simulation paused. Choose a compatible checkpoint and click Restore.": "备份已导入，推演已暂停。请选择兼容的检查点并点击“恢复”。",
    "Scenario reset to its DLC-authored starting state. Simulation is paused.": "剧本已恢复到作者设定的初始状态，推演已暂停。",
}

_API_MESSAGE_PREFIX_ZH = (
    ("Package rejected: ", "剧本包被拒绝："),
    ("Mount rejected: ", "加载剧本被拒绝："),
    ("Adjudication failed: ", "危机裁定失败："),
    ("Unit rejected: ", "部队数据被拒绝："),
    ("Unit update rejected: ", "部队更新被拒绝："),
    ("Save failed: ", "保存失败："),
    ("Usage: ", "用法："),
    ("Unknown command ", "未知命令 "),
    ("Unknown combat stance ", "未知战斗方式 "),
    ("Modifier type must be one of: ", "效果类型必须为以下选项之一："),
    ("A route may contain at most ", "一条路线允许的途经点上限为 "),
    ("Checkpoint ", "检查点 "),
    ("Manual checkpoint ", "手动检查点 "),
    ("Simulation speed set to ", "推演速度已设为 "),
    ("Construction started: ", "已开始建设："),
    ("Resumed ", "已继续："),
)

_API_FIELD_ZH = {
    "Longitude": "经度", "Latitude": "纬度", "Personnel": "兵力",
    "Equipment level": "装备水平", "Morale": "士气", "Supply": "补给",
    "Fatigue": "疲劳", "Suppression": "压制", "Speed multiplier": "速度倍率",
    "Modifier value": "效果倍率", "Modifier duration": "效果持续时间",
}


_API_CORE_TERM_ZH = {
    "Hold": "原地待命", "Relocate": "安全转移", "Planned Route": "按路线移动",
    "Assault": "进攻", "Defend Here": "原地防守", "Fortify": "加固阵地",
    "Aggressive": "进攻优先", "Defensive": "防守优先", "Stealth": "隐蔽行动",
    "Recon": "侦察优先", "Reserve": "休整待命", "Hold Fire": "禁止远程开火",
}


def api_message_zh(message, *, failure=True):
    """Return additive Chinese UI copy without changing stable English API messages."""
    text = str(message)
    exact = _API_MESSAGE_ZH.get(text)
    if exact:
        return exact
    if " Support ID: " in text:
        base, support_id = text.rsplit(" Support ID: ", 1)
        return f"{api_message_zh(base, failure=failure)} 支持编号：{support_id}"

    translated_tail = ""
    for suffix, translated in (
        ("; queued while paused — press Run to begin construction", "；推演已暂停，按“运行”后开始建设。"),
        ("; queued while the simulation is paused — press Run to begin movement", "；推演已暂停，按“运行”后开始移动。"),
        ("; contact-avoidance route calculated around detected hostiles", "；已计算绕开已发现敌军的规避路线。"),
    ):
        if text.endswith(suffix):
            text = text[:-len(suffix)]
            translated_tail = translated
            break

    def with_tail(translated):
        if translated_tail and translated.endswith("。") and translated_tail.startswith("；"):
            translated = translated[:-1]
        return translated + translated_tail

    exact = _API_MESSAGE_ZH.get(text)
    if exact:
        return with_tail(exact)

    dynamic_patterns = (
        (r"Checkpoint \[(.+?)\] already contains a save; confirm overwrite", lambda m: f"检查点 [{m.group(1)}] 已有存档；请确认覆盖。"),
        (r"Save belongs to DLC \[(.+?)\], current DLC is \[(.+?)\]", lambda m: f"存档属于剧本 [{m.group(1)}]，当前剧本为 [{m.group(2)}]。"),
        (r"Unsupported save format \[(.+?)\]", lambda m: f"不支持的存档格式 [{m.group(1)}]。"),
        (r"(.+?) uses unsupported save format \[(.+?)\]", lambda m: f"{m.group(1)} 使用了不支持的存档格式 [{m.group(2)}]。"),
        (r"(.+?) belongs to scenario \[(.+?)\]", lambda m: f"{m.group(1)} 属于剧本 [{m.group(2)}]。"),
        (r"Backup member \[(.+?)\] exceeds the limit", lambda m: f"备份条目 [{m.group(1)}] 超过大小限制。"),
        (r"Backup manifest (.+?) is invalid", lambda m: f"备份清单字段 {m.group(1)} 无效。"),
        (r"Backup hash for \[(.+?)\] is invalid", lambda m: f"备份文件 [{m.group(1)}] 的校验值无效。"),
        (r"Backup content changed \[(.+?)\]", lambda m: f"备份文件内容已改变 [{m.group(1)}]。"),
        (r"Unknown military installation type \[(.+?)\]", lambda m: f"未知军事设施类型 [{m.group(1)}]。"),
        (r"Building (.+?) requires capability \[(.+?)\]", lambda m: f"建设“{m.group(1)}”需要能力 [{m.group(2)}]。"),
        (r"(.+?) already has an unfinished (.+?) project", lambda m: f"{m.group(1)} 已有尚未完成的“{m.group(2)}”项目。"),
        (r"Construction requires at least (.+?)% supply", lambda m: f"开始建设至少需要 {m.group(1)}% 补给。"),
        (r"Another military installation is only (.+?) km away; minimum separation is (.+?) km", lambda m: f"另一处军事设施仅相距 {m.group(1)} 公里；最小间距为 {m.group(2)} 公里。"),
        (r"A route may contain at most (\d+) waypoints", lambda m: f"一条路线最多可包含 {m.group(1)} 个途经点。"),
        (r"([a-z]+) does not accept arguments", lambda m: f"{m.group(1)} 命令不接受参数。"),
        (r"([a-z]+) accepts one destination; use route for multiple waypoints", lambda m: f"{m.group(1)} 命令只能接受一个目的地；如需经过多个地点，请使用“按路线移动”。"),
        (r"This unit has no (.+?) capability in its DLC data", lambda m: f"该部队的剧本数据中没有 {m.group(1)} 能力。"),
        (r"Target is outside sortie range for (.+?) \((.+?)km > (.+?)km\)", lambda m: f"目标超出 {m.group(1)} 的出击范围（{m.group(2)} 公里 > {m.group(3)} 公里）。"),
        (r"(.+?) airstrike requires (.+?)% supply; this unit has (.+?)%", lambda m: f"{m.group(1)} 空袭需要 {m.group(2)}% 补给；该部队当前为 {m.group(3)}%。"),
        (r"Target is outside bombard range \((.+?)km > (.+?)km\)", lambda m: f"目标超出炮击范围（{m.group(1)} 公里 > {m.group(2)} 公里）。"),
        (r"Fortification requires at least (.+?)% supply", lambda m: f"构筑工事至少需要 {m.group(1)}% 补给。"),
        (r"Unknown combat stance \[(.*?)\]\. Choose: (.+)", lambda m: f"未知战斗方式 [{m.group(1)}]。请选择：{m.group(2)}"),
        (r"(.+?) order issued to (.+?) using (.+?) posture", lambda m: f"已向 {m.group(2)} 下达“{_API_CORE_TERM_ZH.get(m.group(1), m.group(1))}”命令，战斗方式为“{_API_CORE_TERM_ZH.get(m.group(3), m.group(3))}”。"),
        (r"(.+?) launched a (.+?) airstrike at (.+?) km", lambda m: f"{m.group(1)} 已发起“{m.group(2)}”空袭，目标距离 {m.group(3)} 公里。"),
        (r"(.+?) began a (.+?)-hour bombardment at (.+?) km", lambda m: f"{m.group(1)} 已开始持续 {m.group(2)} 小时的炮击，目标距离 {m.group(3)} 公里。"),
        (r"(.+?) is fortifying in (.+?) stance", lambda m: f"{m.group(1)} 正以“{_API_CORE_TERM_ZH.get(m.group(2), m.group(2))}”方式加固阵地。"),
        (r"(.+?) is defending in (.+?) stance", lambda m: f"{m.group(1)} 正以“{_API_CORE_TERM_ZH.get(m.group(2), m.group(2))}”方式原地防守。"),
        (r"(.+?) will execute (.+?) in (.+?) stance", lambda m: f"{m.group(1)} 将执行“{_API_CORE_TERM_ZH.get(m.group(2), m.group(2))}”，战斗方式为“{_API_CORE_TERM_ZH.get(m.group(3), m.group(3))}”。"),
        (r"(.+?) halted", lambda m: f"{m.group(1)} 已停止行动。"),
    )
    for pattern, translate in dynamic_patterns:
        match = re.fullmatch(pattern, text)
        if match:
            return with_tail(translate(match))

    for prefix, translated in _API_MESSAGE_PREFIX_ZH:
        if text.startswith(prefix):
            return with_tail(translated + text[len(prefix):])
    for suffix, translated in (
        (" must be a number", "必须是数字。"),
        (" must be finite", "必须是有限数值。"),
        (" must be at least ", "不得小于 "),
        (" must be at most ", "不得大于 "),
        (" must be an object", "必须是对象。"),
        (" exceeds the 8 MiB document limit", "超过 8 MiB 文档限制。"),
        (" must be an approved file under maps/", "必须是 maps/ 下已批准的文件。"),
    ):
        if suffix in text:
            label, detail = text.split(suffix, 1)
            return with_tail(f"{_API_FIELD_ZH.get(label, label)}{translated}{detail}")
    translated = f"操作未完成：{text}" if failure else text
    return with_tail(translated)


def api_error(message, status_code=400, *, support_id=None):
    payload = {"status": "error", "msg": str(message), "msg_zh": api_message_zh(message)}
    if support_id:
        payload["support_id"] = support_id
    if 400 <= status_code < 500 and has_request_context():
        RUNTIME_LOGGER.warning(
            "Request rejected",
            extra={
                "event": "request.rejected",
                "details": {"endpoint": request.endpoint or "unknown", "status": status_code},
            },
        )
    return jsonify(payload), status_code


def unexpected_api_error(exception, operation, message):
    support_id = record_runtime_exception(
        RUNTIME_LOGGER, exception, operation=operation, context={"endpoint": request.endpoint}
    )
    return api_error(f"{message} Support ID: {support_id}", 500, support_id=support_id)


def require_local_ui_request():
    try:
        loopback = ipaddress.ip_address(request.remote_addr or "").is_loopback
    except ValueError:
        loopback = False
    if not loopback or request.headers.get("X-CDC-Requested-With") != "CDC-Sim-UI":
        raise APIInputError("This support action is available only from the local CDC Sim interface", 403)


def json_object():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise APIInputError("Request body must be a JSON object")
    return data


def finite_number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise APIInputError(f"{label} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise APIInputError(f"{label} must be a number") from exc
    if not math.isfinite(number):
        raise APIInputError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise APIInputError(f"{label} must be at least {minimum:g}")
    if maximum is not None and number > maximum:
        raise APIInputError(f"{label} must be at most {maximum:g}")
    return number


def coordinates(lon, lat):
    return (
        finite_number(lon, "Longitude", -180.0, 180.0),
        finite_number(lat, "Latitude", -90.0, 90.0),
    )


def mounted_engine():
    active = engine
    if active is None:
        raise APIInputError("System is idling, please mount a campaign first", 409)
    return active


def manual_save_slot(data, default="slot_1"):
    slot = data.get("slot", default)
    if slot not in MANUAL_SAVE_SLOTS:
        raise APIInputError("Choose manual checkpoint 1, 2, or 3")
    return slot


def clear_support_mission_state(unit):
    """Remove transient support-mission data when another order supersedes it."""
    for attribute in ("bombard_timer", "_bombard_effective_hours", "_bombard_completion_reason"):
        if hasattr(unit, attribute):
            delattr(unit, attribute)
    unit.bombard_casualties = 0.0
    unit.bombard_installation_damage = 0.0
    unit.bombard_installations_destroyed = 0
    unit.base_lon = None
    unit.base_lat = None
    if hasattr(unit, "clear_relocation_avoidance"):
        unit.clear_relocation_avoidance()

def start_physics_thread(target_engine=None):
    """Delay activation of the physics timeline after mounting a DLC"""
    global physics_thread
    target_engine = target_engine or engine
    if target_engine is None:
        raise RuntimeError("Cannot start physics without an engine")
    if physics_thread is None or not physics_thread.is_alive():
        def run_physics():
            print("⚙️ [Physics Engine] Core heartbeat thread activated, theater timeline is now flowing.")
            target_engine.run_clock()
            
        physics_thread = threading.Thread(target=run_physics, daemon=True)
        physics_thread.start()

# ==========================================
# 1. Frontend Page Routing
# ==========================================
@app.route('/')
def index():
    return render_template('index.html', build=BUILD_INFO.public_dict())

@app.route('/zh')
def index_zh():
    return render_template('index.html', force_lang='zh', build=BUILD_INFO.public_dict())

@app.route('/status')
def status_page():
    return render_template('status.html', build=BUILD_INFO.public_dict())

@app.route('/editor')
def editor_page():
    return render_template('cdc_editor.html')


@app.route('/api/editor_template', methods=['GET'])
def editor_template():
    """Serve battle data separately from the core command doctrine."""
    try:
        package = load_dlc_package("_template", RUNTIME_CONFIG.content_dir)
        return jsonify({
            "status": "ok",
            "scenario": package.scenario,
            "units": package.units,
            "battalions": package.battalions,
            "weapons": package.weapons,
            "rules": package.source_rules,
            "package": package.manifest,
            "objectives": package.objectives,
            "events": package.events,
            "doctrine": {
                "orders": package.rules["orders"],
                "stances": package.rules["stances"],
            },
        })
    except DLCValidationError as exc:
        return unexpected_api_error(exc, "editor.template_invalid", "The scenario builder is unavailable.")

@app.route('/api/editor_validate', methods=['POST'])
def validate_editor_package():
    """Validate draft JSON in temporary storage without mounting or applying it."""
    try:
        limit = 16 * 1024 * 1024
        if request.content_length is not None and request.content_length > limit:
            return api_error("Editor draft exceeds the 16 MiB limit", 413)
        # Bound this endpoint on Flask 3.0 too, including streamed requests.
        raw = request.stream.read(limit + 1)
        if len(raw) > limit:
            return api_error("Editor draft exceeds the 16 MiB limit", 413)
        if not request.is_json:
            raise APIInputError("Expected an application/json draft")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise APIInputError("Draft must be an object")
        names = {
            "scenario": "scenario.json", "units": "units.json", "battalions": "battalions.json",
            "weapons": "weapons.json", "rules": "rules.json", "package": "package.json",
            "objectives": "objectives.json", "events": "events.json",
        }
        if set(data) != set(names):
            raise APIInputError("Draft must contain scenario, units, battalions, weapons, rules, package, objectives and events")
        with tempfile.TemporaryDirectory(prefix="cdc-editor-") as temporary:
            directory = Path(temporary)
            for key, name in names.items():
                value = deepcopy(data[key])
                if not isinstance(value, dict):
                    raise APIInputError(f"{key} must be an object")
                if key == "package":
                    # Uploaded JSON is an authoring draft, not a signed release.
                    value.pop("content_hashes", None)
                if key == "scenario":
                    if isinstance(value.get("committee"), dict):
                        for derived in ("package_metadata", "objectives", "events"):
                            value["committee"].pop(derived, None)
                    # Uploaded map bytes are not sent to this JSON-only preview.
                    # Validate their authored paths here, then defer file/decoder checks
                    # to the release builder which sees the complete directory.
                    map_config = value.get("map_config")
                    if isinstance(map_config, dict):
                        suffixes = {
                            "dem_file": {".tif", ".tiff", ".hgt"},
                            "roads_file": {".tif", ".tiff", ".geojson", ".json"},
                            "rivers_file": {".geojson", ".json"},
                            "provinces_file": {".geojson", ".json"},
                        }
                        for field, allowed in suffixes.items():
                            authored = map_config.get(field, "")
                            if authored:
                                safe_relative_path(authored)
                                authored_path = Path(authored)
                                if not authored.startswith("maps/") or authored_path.suffix.lower() not in allowed:
                                    raise APIInputError(f"{field} must be an approved file under maps/")
                                map_config[field] = ""
                        dem_dir = map_config.get("dem_dir", "")
                        if dem_dir:
                            safe_relative_path(dem_dir)
                            if dem_dir != "maps/dem_tiles":
                                raise APIInputError("dem_dir must be maps/dem_tiles")
                            map_config["dem_dir"] = ""
                text = json.dumps(value, ensure_ascii=False, allow_nan=False)
                if len(text.encode("utf-8")) > 8 * 1024 * 1024:
                    raise APIInputError(f"{key} exceeds the 8 MiB document limit", 413)
                (directory / name).write_text(text, encoding="utf-8")
            package = load_dlc_directory(directory, "editor_preview")
        return jsonify({"status": "ok", "package_id": package.manifest["id"], "version": package.manifest["version"], "scope": "json_only"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (DLCValidationError, ValueError, TypeError, RecursionError, OverflowError) as exc:
        return api_error(f"Package rejected: {exc}", 400)
    except OSError as exc:
        return unexpected_api_error(exc, "editor.validation_failed", "The package could not be checked.")


@app.route('/chair_guide')
def chair_guide_page():
    return render_template('chair_guide.html')

@app.route('/chair_guide_zh')
def chair_guide_zh_page():
    return render_template('chair_guide_zh.html')

def runtime_checks():
    packages = ("flask", "numpy", "PIL", "rasterio")
    return {
        "dependencies": all(importlib.util.find_spec(package) is not None for package in packages),
        "content": RUNTIME_CONFIG.content_dir.is_dir() and os.access(RUNTIME_CONFIG.content_dir, os.R_OK),
        "data_storage": RUNTIME_CONFIG.data_dir.is_dir() and os.access(RUNTIME_CONFIG.data_dir, os.W_OK),
    }


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify(public_health_payload(BUILD_INFO, checks=runtime_checks()))


@app.route('/api/version', methods=['GET'])
def version_info():
    return jsonify({"status": "ok", "build": BUILD_INFO.public_dict()})


@app.route('/api/support_diagnostics', methods=['POST'])
def support_diagnostics_api():
    try:
        require_local_ui_request()
        return jsonify({"status": "ok", "diagnostics": support_diagnostics(
            RUNTIME_CONFIG, BUILD_INFO, checks=runtime_checks()
        )})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)


# ==========================================
# 2. DLC Bootloader
# ==========================================
@app.route('/api/list_dlcs', methods=['GET'])
def list_dlcs():
    """Scan the dlc folder to retrieve all campaign modules"""
    return jsonify(scan_dlcs(RUNTIME_CONFIG.content_dir))

@app.route('/api/mount_dlc', methods=['POST'])
def mount_dlc():
    """Ignition: Mount the specified DLC, inject physical laws, and start the heartbeat"""
    global engine, physics_thread
    try:
        data = json_object()
        dlc_id = data.get("dlc_id")
        package = load_dlc_package(dlc_id, RUNTIME_CONFIG.content_dir)

        # Separate immutable scenario content from per-release customer state.
        storage_key = (
            f"{package.manifest['id']}--{package.manifest['version']}"
            if package.manifest else package.dlc_id
        )
        storage_dir = (RUNTIME_CONFIG.session_dir / storage_key).resolve()
        try:
            storage_dir.relative_to(RUNTIME_CONFIG.session_dir.resolve())
        except ValueError as exc:
            raise DLCValidationError("Scenario storage key is unsafe") from exc
        migrate_legacy_checkpoints(PROJECT_ROOT, storage_dir, package.dlc_id)

        # Build completely before disturbing the currently running committee.
        candidate = SimulationEngine(
            package.dlc_id, package=package, storage_dir=storage_dir
        )
        with engine_guard:
            previous_engine = engine
            previous_thread = physics_thread
            if previous_engine is not None:
                previous_engine.stop()
            if previous_thread is not None and previous_thread.is_alive():
                previous_thread.join(timeout=2.0)
            engine = candidate
            physics_thread = None
            start_physics_thread(candidate)

        factions = sorted({unit.faction for unit in candidate.units.values()})
        gis_status = candidate.get_gis_status()
        mount_warnings = [
            feature["warning"]
            for feature in gis_status["features"]
            if feature.get("warning")
        ]
        RUNTIME_LOGGER.info(
            "Scenario mounted",
            extra={
                "event": "scenario.mounted",
                "details": {
                    "versioned_package": package.manifest is not None,
                    "rules_schema_version": candidate.rules["schema_version"],
                },
            },
        )
        return jsonify({
            "status": "ok", 
            "config": {
                "name": candidate.scenario_data.get("scenario_name"),
                "center": candidate.scenario_data["map_center"],
                "zoom": candidate.scenario_data["map_zoom"],
                "factions": factions,
                "warnings": mount_warnings,
                "gis": gis_status,
                "rules_schema_version": candidate.rules["schema_version"],
            }
        })
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except DLCValidationError as exc:
        return api_error(f"Mount rejected: {exc}", 400)
    except Exception as exc:
        return unexpected_api_error(exc, "scenario.mount_failed", "The scenario could not be opened.")

# ==========================================
# 3. Geography and Dashboard State Synchronization
# ==========================================
@app.route('/geojson')
def get_geojson():
    active = engine
    if not active:
        return jsonify({"type": "FeatureCollection", "features": []})
    # Dynamically read the province boundaries of the current DLC
    prov_file = active.map_config.get("provinces_file", "")
    if os.path.exists(prov_file):
        try:
            with open(prov_file, 'r', encoding='utf-8') as f:
                import json
                geojson = json.load(f)
            name_property = active.map_config.get("province_name_property", "")
            for feature in geojson.get("features", []):
                properties = feature.setdefault("properties", {})
                name = properties.get(name_property) if name_property else None
                if not name:
                    name = next((value for value in properties.values() if isinstance(value, str) and value.strip()), "Unknown")
                properties["cdc_name"] = str(name)
            return jsonify(geojson)
        except (OSError, ValueError):
            RUNTIME_LOGGER.exception("Mounted province file could not be read", extra={"event": "gis.province_read_failed"})
    return jsonify({"type": "FeatureCollection", "features": []})

@app.route('/api/registry', methods=['GET'])
def get_registry():
    active = engine
    return jsonify({
        "weapons": active.weapon_registry if active else {},
        "battalions": active.battalion_registry if active else {},
        "rules": active.rules if active else {},
    })


@app.route('/api/gis_status', methods=['GET'])
def get_gis_status():
    active = engine
    if not active:
        return jsonify({"status": "unmounted", "enabled_count": 0, "features": []})
    return jsonify({"status": "ok", **active.get_gis_status()})

@app.route('/api/state', methods=['GET'])
def get_state():
    active = engine
    if not active:
        return jsonify({"status": "unmounted"})
    with active.lock:
        # Presence is positional, not time-based. Keep province tooltips correct
        # even when the simulation is paused or a unit was just edited/loaded.
        active.refresh_province_presence()
        units_data = {}
        for unit_id, unit in active.units.items():
            unit_data = unit.to_dict()
            city_context = active.get_city_context(unit.lon, unit.lat)
            effective_terrain = active.get_terrain_complexity(unit.lon, unit.lat)
            unit_data["city_id"] = city_context["id"]
            unit_data["city_name"] = city_context["name"]
            unit_data["city_influence_rate"] = city_context["influence_rate"]
            unit_data["effective_terrain_complexity"] = effective_terrain
            unit_data["effective_movement_speed"] = unit.get_effective_movement_speed(effective_terrain)
            unit_data["installation_cover_bonus"] = active.get_installation_cover_bonus(unit)
            project = active.get_builder_project(unit_id)
            unit_data["active_construction"] = project.to_dict() if project else None
            units_data[unit_id] = unit_data
        return jsonify({
            "status": "ok",
            "time": {
                "day": int(active.game_hours // 24),
                "hour": int(active.game_hours % 24),
                "minute": int((active.game_hours * 60) % 60),
                "second": int((active.game_hours * 3600) % 60),
                "multiplier": active.time_multiplier,
                "paused": active.is_paused,
            },
            "units": units_data,
            "installations": active.get_installation_state(),
            "cities": active.get_city_state(),
            "province_politics": active.get_province_politics_state(),
            "latest_logs": active.structured_logs[-int(active.rules["state_limits"]["state_feed_logs"]):],
        })

@app.route('/api/logs', methods=['GET'])
def get_logs():
    active = engine
    if not active:
        return jsonify({"logs": []})
    with active.lock:
        return jsonify({"logs": list(active.structured_logs)})

@app.route('/api/committee', methods=['GET'])
def get_committee_state():
    active = engine
    if not active:
        return jsonify({"status": "unmounted"})
    with active.lock:
        return jsonify(active.get_committee_state())

@app.route('/api/committee/adjudicate', methods=['POST'])
def adjudicate_committee_directive():
    try:
        active = mounted_engine()
        data = json_object()
        with active.lock:
            record = active.adjudicate_directive(data)
        return jsonify({"status": "ok", "record": record})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Adjudication failed: {exc}", 400)

@app.route('/api/committee/sitrep', methods=['GET'])
def export_committee_sitrep():
    active = engine
    if not active:
        return jsonify({"status": "unmounted"})
    include_private = request.args.get("private", "0") in ["1", "true", "yes"]
    with active.lock:
        markdown = active.build_sitrep_markdown(include_private=include_private)
    return Response(markdown, mimetype="text/markdown")

@app.route('/api/terrain', methods=['GET'])
def get_terrain():
    try:
        active = mounted_engine()
        lon, lat = coordinates(request.args.get('lon'), request.args.get('lat'))
        natural = active.map_engine.get_terrain_complexity(lon, lat)
        city = active.get_city_context(lon, lat)
        effective = active.get_terrain_complexity(lon, lat)
        return jsonify({
            "status": "ok",
            "complexity": round(effective, 2),
            "natural_complexity": round(natural, 2),
            "city": city,
        })
    except APIInputError as exc:
        return jsonify({"status": "error", "msg": str(exc), "msg_zh": api_message_zh(exc), "complexity": 0.0}), exc.status_code

@app.route('/api/roads_overlay')
def get_roads_overlay():
    active = engine
    if not active:
        return jsonify({"type": "FeatureCollection", "features": []})
    return jsonify(active.map_engine.export_road_geojson())

# ==========================================
# 4. Tactical Commands and Backend Intervention Core
# ==========================================
@app.route('/api/command', methods=['POST'])
def execute_command():
    try:
        active = mounted_engine()
        data = json_object()
        command_text = data.get("command")
        if not isinstance(command_text, str) or not command_text.strip():
            raise APIInputError("Command is empty")
        parts = command_text.strip().split()
        requested_cmd = parts[0].lower()
        # Relocate is the canonical order name. `move` remains an API alias so
        # older clients and macros continue to work without creating two modes.
        cmd = "relocate" if requested_cmd == "move" else requested_cmd
        waypoints_data = data.get("waypoints", [])
        message = "Execution successful"
        queued = False

        with active.lock:
            if cmd in {"play", "pause"}:
                if len(parts) != 1:
                    raise APIInputError(f"{cmd} does not accept arguments")
                active.is_paused = cmd == "pause"
                message = "Simulation paused" if active.is_paused else "Simulation resumed"
                active.log_event(
                    "⏸️ [System] Suspending simulation." if active.is_paused else "▶️ [System] Resuming simulation.",
                    faction="SYSTEM",
                    msg_type="system",
                )

            elif cmd == "speed":
                if len(parts) != 2:
                    raise APIInputError("Usage: speed <multiplier>")
                clock_rules = active.rules["clock"]
                multiplier = finite_number(
                    parts[1],
                    "Speed multiplier",
                    float(clock_rules["speed_multiplier_min"]),
                    float(clock_rules["speed_multiplier_max"]),
                )
                active.time_multiplier = multiplier
                message = f"Simulation speed set to {multiplier:g}x"
                active.log_event(f"[System] Simulation speed set to {multiplier:g}x.", faction="SYSTEM", msg_type="system")

            elif cmd == "build":
                if len(parts) != 3:
                    raise APIInputError("Usage: build <unit_id> <installation_type>")
                try:
                    installation, resumed = active.start_installation_construction(
                        parts[1], parts[2]
                    )
                except ValueError as exc:
                    raise APIInputError(str(exc)) from exc
                message = (
                    f"Resumed {installation.name}"
                    if resumed
                    else f"Construction started: {installation.name}"
                )
                queued = active.is_paused
                if queued:
                    message += "; queued while paused — press Run to begin construction"

            elif cmd in {"relocate", "attack", "route"}:
                if len(parts) < 2:
                    raise APIInputError(f"Usage: {cmd} <unit_id> <longitude> <latitude>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                unit = active.units[unit_id]
                if unit.personnel <= 0:
                    raise APIInputError("A neutralized unit cannot receive movement orders")
                if cmd == "attack" and not active.rules["unit_types"][unit.unit_type]["can_direct_combat"]:
                    raise APIInputError("This unit type cannot receive a ground-assault order")

                targets = []
                if waypoints_data:
                    if not isinstance(waypoints_data, list):
                        raise APIInputError("Waypoints must be a list")
                    max_waypoints = int(active.rules["movement"]["max_route_waypoints"])
                    if len(waypoints_data) > max_waypoints:
                        raise APIInputError(f"A route may contain at most {max_waypoints} waypoints")
                    if cmd != "route" and len(waypoints_data) > 1:
                        raise APIInputError(f"{cmd} accepts one destination; use route for multiple waypoints")
                    for waypoint in waypoints_data:
                        if not isinstance(waypoint, dict):
                            raise APIInputError("Each waypoint must contain lon and lat")
                        targets.append(coordinates(waypoint.get("lon"), waypoint.get("lat")))
                elif len(parts) == 4:
                    targets.append(coordinates(parts[2], parts[3]))
                else:
                    raise APIInputError("Target coordinates not provided")
                if not targets:
                    raise APIInputError("Target coordinates not provided")

                full_path = []
                current_lon, current_lat = unit.lon, unit.lat
                for target_lon, target_lat in targets:
                    segment = active.map_engine.find_path(
                        start_lon=current_lon,
                        start_lat=current_lat,
                        target_lon=target_lon,
                        target_lat=target_lat,
                        unit_composition=unit.composition,
                        unit_capabilities=unit.get_capabilities(),
                    )
                    if not isinstance(segment, list):
                        raise RuntimeError("Pathfinder returned an invalid route")
                    parsed_segment = [coordinates(point[0], point[1]) for point in segment if isinstance(point, (list, tuple)) and len(point) == 2]
                    if len(parsed_segment) > 1 and haversine_distance(current_lon, current_lat, parsed_segment[0][0], parsed_segment[0][1]) < float(active.rules["movement"]["arrival_distance_km"]):
                        parsed_segment.pop(0)
                    full_path.extend(parsed_segment)
                    current_lon, current_lat = target_lon, target_lat
                if not full_path:
                    full_path = [targets[-1]]

                unit.waypoints = full_path
                unit.target_lon, unit.target_lat = targets[-1]
                unit.status = "MOVING"
                unit.set_order_role({"relocate": "relocate", "route": "route", "attack": "assault"}[cmd])
                unit.entrenchment = float(active.rules["unit_defaults"]["entrenchment"])
                clear_support_mission_state(unit)
                order_profile = active.rules["orders"]["modes"][unit.order_role()]
                posture_label = active.rules["stances"][unit.stance]["label"]
                message = f"{order_profile['label']} order issued to {unit.name} using {posture_label} posture"
                queued = active.is_paused
                if queued:
                    message += "; queued while the simulation is paused — press Run to begin movement"
                if cmd == "attack":
                    detail = (
                        f"⚔️ [Assault Queued] {unit.name} will advance through ranged contact when the timeline resumes and halt only at close ground contact."
                        if queued else
                        f"⚔️ [Assault] {unit.name} is advancing through ranged contact and will halt only at close ground contact."
                    )
                    active.log_event(detail, faction=unit.faction, msg_type="combat")
                elif cmd == "route":
                    detail = (
                        f"🗺️ [Planned Route Queued] {unit.name} will follow {len(targets)} holding-fire waypoint(s) when the timeline resumes."
                        if queued else
                        f"🗺️ [Planned Route] {unit.name} received a holding-fire route with {len(targets)} waypoints."
                    )
                    active.log_event(detail, faction=unit.faction, msg_type="move")
                else:
                    detail = (
                        f"📍 [Relocate Queued] {unit.name} will move to the objective when the timeline resumes and reroute around detected threats."
                        if queued else
                        f"🚀 [Relocate] {unit.name} is moving to the objective without initiating ranged combat and will reroute around detected threats."
                    )
                    active.log_event(detail, faction=unit.faction, msg_type="move")
                    if active.refresh_relocation_route(unit, force=True):
                        message += "; contact-avoidance route calculated around detected hostiles"

            elif cmd in {"airstrike", "bombard"}:
                if len(parts) != 4:
                    raise APIInputError(f"Usage: {cmd} <unit_id> <longitude> <latitude>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                target_lon, target_lat = coordinates(parts[2], parts[3])
                unit = active.units[unit_id]
                if unit.personnel <= 0:
                    raise APIInputError("A neutralized unit cannot execute a support mission")
                if unit.status in {"BOMBARDING", "AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"}:
                    raise APIInputError("This unit already has an active support mission; halt it before issuing another")

                if cmd == "airstrike":
                    airstrike_rules = active.rules["missions"]["airstrike"]
                    capability = airstrike_rules["capability"]
                    if not unit.has_capability(capability):
                        raise APIInputError(f"This unit has no {capability} capability in its DLC data")
                    aircraft = unit.get_airstrike_parameters()
                    if not aircraft["strike_weapon_ids"]:
                        raise APIInputError(
                            "This unit has airstrike capability but its battalions mount no airstrike-role weapon"
                        )
                    sortie_distance = haversine_distance(unit.lon, unit.lat, target_lon, target_lat)
                    sortie_range = float(aircraft["sortie_range_km"])
                    if sortie_distance > sortie_range:
                        raise APIInputError(
                            f"Target is outside sortie range for {aircraft['label']} "
                            f"({sortie_distance:.1f}km > {sortie_range:.1f}km)"
                        )
                    supply_cost = float(aircraft["supply_cost"])
                    if unit.supply < supply_cost:
                        raise APIInputError(
                            f"{aircraft['label']} airstrike requires {supply_cost:g}% supply; "
                            f"this unit has {unit.supply:.1f}%"
                        )
                    clear_support_mission_state(unit)
                    unit.base_lon, unit.base_lat = unit.lon, unit.lat
                    unit.target_lon, unit.target_lat = target_lon, target_lat
                    unit.waypoints = [(target_lon, target_lat)]
                    unit.status = "AIRSTRIKE_OUTBOUND"
                    unit.set_order_role("hold")
                    resources = active.rules["resources"]
                    unit.supply = max(float(resources["minimum"]), unit.supply - supply_cost)
                    unit.fatigue = min(float(resources["maximum"]), unit.fatigue + float(aircraft["fatigue_cost"]))
                    unit.entrenchment = float(active.rules["unit_defaults"]["entrenchment"])
                    message = f"{unit.name} launched a {aircraft['label']} airstrike at {sortie_distance:.1f} km"
                    active.log_event(
                        f"🛫 [Airstrike] {unit.name} ({aircraft['label']}; {aircraft['attack_profile']}) launched for "
                        f"coordinates {target_lon:.4f}, {target_lat:.4f} ({sortie_distance:.1f} km); "
                        f"munitions committed and profile-adjusted AA exposure active.",
                        faction=unit.faction,
                        msg_type="combat",
                    )
                else:
                    bombard_rules = active.rules["missions"]["bombard"]
                    if not unit.has_capability(bombard_rules["capability"]):
                        raise APIInputError("This unit has no bombard capability in its DLC data")
                    if unit.bombard_range <= 0:
                        raise APIInputError(
                            "This unit has bombard capability but its battalions mount no indirect bombard weapon"
                        )
                    fire_dist = haversine_distance(unit.lon, unit.lat, target_lon, target_lat)
                    if fire_dist > unit.bombard_range:
                        raise APIInputError(f"Target is outside bombard range ({fire_dist:.1f}km > {unit.bombard_range:.1f}km)")
                    if unit.supply < float(bombard_rules["minimum_supply_to_start"]):
                        raise APIInputError("Unit lacks ammunition/supply for a fire mission")
                    clear_support_mission_state(unit)
                    unit.waypoints = []
                    unit.target_lon, unit.target_lat = target_lon, target_lat
                    unit.status = "BOMBARDING"
                    unit.bombard_timer = float(bombard_rules["duration_hours"])
                    unit.set_order_role("hold")
                    message = f"{unit.name} began a {unit.bombard_timer:g}-hour bombardment at {fire_dist:.1f} km"
                    active.log_event(
                        f"☄️ [Bombardment] {unit.name} opened a {unit.bombard_timer:g}-hour fire mission on coordinates {target_lon:.4f}, {target_lat:.4f} ({fire_dist:.1f} km).",
                        faction=unit.faction,
                        msg_type="combat",
                    )

            elif cmd in {"defend", "fortify"}:
                if len(parts) != 2:
                    raise APIInputError(f"Usage: {cmd} <unit_id>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                unit = active.units[unit_id]
                if unit.personnel <= 0:
                    raise APIInputError("A neutralized unit cannot prepare a defense")
                if not active.rules["unit_types"][unit.unit_type]["can_direct_combat"]:
                    raise APIInputError("This unit type cannot prepare a ground-defense position")

                defense = active.rules["defense"]
                if cmd == "fortify" and unit.supply < float(defense["minimum_supply_to_start"]):
                    raise APIInputError(
                        f"Fortification requires at least {float(defense['minimum_supply_to_start']):g}% supply"
                    )

                unit.waypoints = []
                unit.target_lon = None
                unit.target_lat = None
                unit.set_order_role(cmd)
                order_rules = active.rules["orders"]
                unit.status = order_rules["fortifying_status"] if cmd == "fortify" else order_rules["defending_status"]
                stance_label = active.rules["stances"][unit.stance]["label"]
                clear_support_mission_state(unit)
                if cmd == "fortify":
                    message = f"{unit.name} is fortifying in {stance_label} stance"
                    active.log_event(
                        f"🛠️ [Fortify] {unit.name} began accelerated fieldwork construction in {stance_label} stance; supply and fatigue costs are active.",
                        faction=unit.faction,
                        msg_type="move",
                    )
                else:
                    message = f"{unit.name} is defending in {stance_label} stance"
                    active.log_event(
                        f"🛡️ [Defend] {unit.name} began preparing its position in {stance_label} stance.",
                        faction=unit.faction,
                        msg_type="move",
                    )

            elif cmd == "stance":
                if len(parts) != 3:
                    raise APIInputError("Usage: stance <unit_id> <stance_id>")
                unit_id = parts[1]
                if unit_id not in active.units:
                    raise APIInputError("Unit not found", 404)
                unit = active.units[unit_id]
                requested_stance = parts[2]
                stance_id = next(
                    (
                        candidate
                        for candidate in active.rules["stances"]
                        if candidate.casefold() == requested_stance.casefold()
                    ),
                    None,
                )
                if stance_id is None:
                    allowed = ", ".join(active.rules["stances"])
                    raise APIInputError(f"Unknown combat stance [{requested_stance}]. Choose: {allowed}")
                unit.stance = stance_id
                stance_label = active.rules["stances"][stance_id]["label"]
                order_label = active.rules["orders"]["modes"][unit.order_role()]["label"]
                message = f"{unit.name} will execute {order_label} in {stance_label} stance"
                active.log_event(
                    f"🧭 [Stance] {unit.name} changed to {stance_label} while retaining its {order_label} order.",
                    faction=unit.faction,
                    msg_type="move",
                )

            elif cmd == "halt":
                if len(parts) != 2 or parts[1] not in active.units:
                    raise APIInputError("Usage: halt <unit_id>")
                unit = active.units[parts[1]]
                unit.waypoints = []
                unit.target_lon = None
                unit.target_lat = None
                unit.set_order_role("hold")
                unit.status = "IDLE"
                clear_support_mission_state(unit)
                message = f"{unit.name} halted"

            else:
                raise APIInputError(f"Unknown command [{cmd}]")

            response_paused = active.is_paused

        return jsonify({"status": "ok", "msg": message, "msg_zh": api_message_zh(message, failure=False), "paused": response_paused, "queued": queued})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except Exception as exc:
        return unexpected_api_error(exc, "command.execution_failed", "The command could not be completed.")

@app.route('/api/edit_unit', methods=['POST'])
def edit_unit():
    try:
        active = mounted_engine()
        data = json_object()
        try:
            unit_id = validate_identifier(data.get("id"), "Unit ID")
        except DLCValidationError as exc:
            raise APIInputError(str(exc)) from exc
        name = str(data.get("name", "")).strip()
        faction = str(data.get("faction", "")).strip()
        if not name or not faction:
            raise APIInputError("Unit name and faction are required")
        center = active.scenario_data["map_center"]
        lon, lat = coordinates(data.get("lon", center[1]), data.get("lat", center[0]))
        primary_weapon = data.get("primary_weapon") or next(iter(active.weapon_registry), None)
        defaults = active.rules["unit_defaults"]
        resources = active.rules["resources"]
        resource_min = float(resources["minimum"])
        resource_max = float(resources["maximum"])
        unit_data = {
            "name": name,
            "faction": faction,
            "icon": str(data.get("icon", "")),
            "personnel": finite_number(data.get("personnel", defaults["personnel"]), "Personnel", 1),
            "equipment_level": finite_number(data.get("equipment_level", defaults["equipment_level"]), "Equipment level", 0),
            "lon": lon,
            "lat": lat,
            "unit_type": str(data.get("unit_type", defaults["unit_type"])),
            "aircraft_type": data.get("aircraft_type"),
            "capabilities": data.get("capabilities", []),
            "composition": data.get("composition", {}),
            "primary_weapon": primary_weapon,
            "morale": finite_number(data.get("morale", defaults["morale"]), "Morale", resource_min, resource_max),
            "stance": str(data.get("stance", defaults["stance"])),
            "supply": finite_number(data.get("supply", defaults["supply"]), "Supply", resource_min, resource_max),
            "fatigue": finite_number(data.get("fatigue", defaults["fatigue"]), "Fatigue", resource_min, resource_max),
            "suppression": finite_number(data.get("suppression", defaults["suppression"]), "Suppression", resource_min, resource_max),
        }
        new_unit = MilitaryUnit(unit_id, unit_data, active.weapon_registry, active.battalion_registry, active.rules)
        new_unit.altitude = active.map_engine.get_elevation(new_unit.lon, new_unit.lat)
        new_unit.current_province = active.prov_engine.get_province(new_unit.lon, new_unit.lat)
        with active.lock:
            if unit_id in active.units:
                raise APIInputError("Unit ID conflict", 409)
            active.units[unit_id] = new_unit
            active.log_event(
                f"🚩 [Armed Mobilization] {new_unit.name} (Equipment: {new_unit.weapon_name}) arrived in the theater at {int(new_unit.altitude)} meters.",
                faction=new_unit.faction,
                msg_type="system",
            )
        return jsonify({"status": "ok", "unit": new_unit.to_dict()})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Unit rejected: {exc}", 400)

@app.route('/api/admin_edit', methods=['POST'])
def admin_edit():
    try:
        active = mounted_engine()
        data = json_object()
        original_id = data.get("original_id")
        new_id = data.get("id", original_id)
        try:
            new_id = validate_identifier(new_id, "Unit ID")
        except DLCValidationError as exc:
            raise APIInputError(str(exc)) from exc
        with active.lock:
            if original_id not in active.units:
                raise APIInputError("Unit not found", 404)
            if new_id != original_id and new_id in active.units:
                raise APIInputError("Unit ID conflict", 409)
            current = active.units[original_id]
            candidate_data = current.to_dict()
            for field in (
                "name", "faction", "icon", "unit_type", "aircraft_type",
                "composition", "capabilities", "primary_weapon", "stance",
            ):
                if field in data:
                    candidate_data[field] = data[field]
            resource_min = float(active.rules["resources"]["minimum"])
            resource_max = float(active.rules["resources"]["maximum"])
            for field, minimum, maximum in (
                ("personnel", 0, None),
                ("equipment_level", 0, None),
                ("supply", resource_min, resource_max),
                ("fatigue", resource_min, resource_max),
                ("suppression", resource_min, resource_max),
                ("morale", resource_min, resource_max),
            ):
                if field in data:
                    candidate_data[field] = finite_number(data[field], field.replace("_", " ").title(), minimum, maximum)
            if "lon" in data or "lat" in data:
                candidate_data["lon"], candidate_data["lat"] = coordinates(data.get("lon", current.lon), data.get("lat", current.lat))
            if not str(candidate_data.get("name", "")).strip() or not str(candidate_data.get("faction", "")).strip():
                raise APIInputError("Unit name and faction cannot be empty")

            replacement = MilitaryUnit(new_id, candidate_data, active.weapon_registry, active.battalion_registry, active.rules)
            replacement.altitude = active.map_engine.get_elevation(replacement.lon, replacement.lat)
            replacement.current_province = active.prov_engine.get_province(replacement.lon, replacement.lat)

            if original_id != new_id:
                active.units.pop(original_id)
                if original_id in active.detected_units:
                    active.detected_units[new_id] = active.detected_units.pop(original_id)
            active.units[new_id] = replacement
            active.log_event(f"[Chair Override] {replacement.name} was updated by crisis staff.", faction="COMMITTEE", msg_type="system")
        return jsonify({"status": "ok", "unit": replacement.to_dict()})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Unit update rejected: {exc}", 400)

@app.route('/api/modifier', methods=['POST'])
def add_modifier():
    try:
        active = mounted_engine()
        data = json_object()
        unit_id = data.get('id')
        mod_type = str(data.get('type', '')).lower()
        modifier_rules = active.rules["modifiers"]
        allowed_types = modifier_rules["allowed_types"]
        if mod_type not in allowed_types:
            raise APIInputError(f"Modifier type must be one of: {', '.join(allowed_types)}")
        value = finite_number(
            data.get('value', modifier_rules["default_value"]),
            "Modifier value",
            float(modifier_rules["value_minimum"]),
            float(modifier_rules["value_maximum"]),
        )
        duration = finite_number(
            data.get('duration', modifier_rules["default_duration_hours"]),
            "Modifier duration",
            float(modifier_rules["duration_minimum_hours"]),
            float(modifier_rules["duration_maximum_hours"]),
        )
        name = str(data.get('name') or modifier_rules["default_name"]).strip()[:120]
        with active.lock:
            if unit_id not in active.units:
                raise APIInputError("Unit not found", 404)
            unit = active.units[unit_id]
            unit.modifiers.append({"name": name, "type": mod_type, "value": value, "duration": duration})
            active.log_event(f"[Chair Override] {name} applied to {unit.name}: {mod_type} x{value:g} for {duration:g} hours.", faction="COMMITTEE", msg_type="system")
        return jsonify({"status": "ok"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)


@app.route('/api/city', methods=['POST'])
def edit_city():
    """Allow Chairs to add, update, or remove city influence during play."""
    try:
        active = mounted_engine()
        data = json_object()
        action = str(data.get("action", "upsert")).strip().lower()
        original_id = data.get("original_id") or data.get("id")
        try:
            original_id = validate_identifier(original_id, "City ID")
        except DLCValidationError as exc:
            raise APIInputError(str(exc)) from exc

        with active.lock:
            existing_index = next((index for index, city in enumerate(active.cities) if city["id"] == original_id), None)
            if action == "delete":
                if existing_index is None:
                    raise APIInputError("City not found", 404)
                removed = active.cities.pop(existing_index)
                active.log_event(
                    f"[Chair Override] City influence area [{removed['name']}] was removed.",
                    faction="COMMITTEE",
                    msg_type="system",
                )
                return jsonify({"status": "ok", "city": removed})
            if action != "upsert":
                raise APIInputError("City action must be upsert or delete")

            try:
                city = active.validate_city(data)
            except ValueError as exc:
                raise APIInputError(str(exc)) from exc
            conflict = next(
                (item for item in active.cities if item["id"] == city["id"] and item["id"] != original_id),
                None,
            )
            if conflict:
                raise APIInputError("City ID conflict", 409)
            if existing_index is None:
                active.cities.append(city)
                verb = "added"
            else:
                active.cities[existing_index] = city
                verb = "updated"
            active.log_event(
                f"[Chair Override] City [{city['name']}] {verb}: area {city['area_km2']:g} km², influence {city['influence_rate']:g}.",
                faction="COMMITTEE",
                msg_type="system",
            )
        return jsonify({"status": "ok", "city": dict(city, radius_km=active.city_radius_km(city))})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

@app.route('/api/province_politics', methods=['POST'])
@app.route('/api/set_influence', methods=['POST'])
def set_province_politics():
    try:
        active = mounted_engine()
        data = json_object()
        action = str(data.get("action", "upsert")).strip().lower()
        original_province = str(data.get("original_province") or data.get("province", "")).strip()
        original_faction = str(data.get("original_faction") or data.get("faction", "")).strip()
        if not original_province or not original_faction:
            raise APIInputError("Province and faction are required")
        with active.lock:
            if action == "delete":
                if not active.remove_province_politics(original_province, original_faction):
                    raise APIInputError("Province faction record not found", 404)
                active.log_event(
                    f"[Chair Override] Political record for [{original_faction}] in [{original_province}] was removed.",
                    faction="COMMITTEE",
                    msg_type="system",
                )
                return jsonify({"status": "ok"})
            if action != "upsert":
                raise APIInputError("Province politics action must be upsert or delete")
            try:
                entry = active.validate_province_politics_entry(data)
            except ValueError as exc:
                raise APIInputError(str(exc)) from exc

            is_rename = (entry["province"], entry["faction"]) != (original_province, original_faction)
            target_state = active.province_politics.get(entry["province"], {}).get("factions", {})
            if is_rename and entry["faction"] in target_state:
                raise APIInputError("Province faction record already exists", 409)
            original_exists = original_faction in active.province_politics.get(original_province, {}).get("factions", {})
            if ("original_province" in data or "original_faction" in data) and not original_exists:
                raise APIInputError("Original province faction record not found", 404)
            if is_rename and original_exists:
                active.remove_province_politics(original_province, original_faction)
            active.set_province_politics(entry)
            active.log_event(
                f"[Chair Override] Civilian sentiment toward [{entry['faction']}] in [{entry['province']}] set to {entry['civilian_sentiment']:g}; occupation {entry['occupation']:g}.",
                faction="COMMITTEE",
                msg_type="system",
            )
            province_state = active.get_province_politics_state()[entry["province"]]
        return jsonify({"status": "ok", "entry": entry, "province_state": province_state})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

@app.route('/api/diplomacy', methods=['POST'])
def set_diplomacy():
    try:
        active = mounted_engine()
        data = json_object()
        faction_one = str(data.get('f1', '')).strip()
        faction_two = str(data.get('f2', '')).strip()
        allied = data.get('allied')
        if not faction_one or not faction_two:
            raise APIInputError("Both factions are required")
        if faction_one == faction_two:
            raise APIInputError("Diplomacy requires two different factions")
        if not isinstance(allied, bool):
            raise APIInputError("allied must be true or false")
        with active.lock:
            active.set_alliance(faction_one, faction_two, allied)
            action = "signed" if allied else "abrogated"
            active.log_event(f"🤝 [Diplomatic Radar] {faction_one} and {faction_two} {action} a bilateral non-aggression pact.", faction="SYSTEM")
        return jsonify({"status": "ok"})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

@app.route('/api/save_slots', methods=['GET'])
def save_slots_api():
    try:
        active = mounted_engine()
        slots = [active.save_slot_metadata(slot) for slot in MANUAL_SAVE_SLOTS]
        return jsonify({"status": "ok", "manual_only": True, "slots": slots})
    except APIInputError as exc:
        return api_error(exc, exc.status_code)


@app.route('/api/save_game', methods=['POST'])
def save_game_api():
    try:
        active = mounted_engine()
        data = json_object()
        slot = manual_save_slot(data)
        with active.lock:
            if active.save_slot_metadata(slot)["exists"] and data.get("overwrite") is not True:
                raise APIInputError(f"Checkpoint [{slot}] already contains a save; confirm overwrite", 409)
            active.save_game(slot)
        RUNTIME_LOGGER.info(
            "Checkpoint saved",
            extra={"event": "checkpoint.saved", "details": {"slot": slot}},
        )
        return jsonify({
            "status": "ok",
            "msg": f"Manual checkpoint [{slot}] saved.",
            "msg_zh": f"手动检查点 [{slot}] 已保存。",
            "slot": active.save_slot_metadata(slot),
        })
    except APIInputError as exc:
        return api_error(exc, exc.status_code)
    except (TypeError, ValueError) as exc:
        return api_error(f"Save failed: {exc}", 400)
    except OSError as exc:
        return unexpected_api_error(exc, "checkpoint.save_failed", "The checkpoint could not be written.")

@app.route('/api/load_game', methods=['POST'])
def load_game_api():
    try:
        active = mounted_engine()
        slot = manual_save_slot(json_object())
        success, msg = active.load_game(slot)
        if not success:
            return api_error(msg, 400)
        RUNTIME_LOGGER.info(
            "Checkpoint restored",
            extra={"event": "checkpoint.restored", "details": {"slot": slot}},
        )
        return jsonify({
            "status": "ok",
            "msg": f"Manual checkpoint [{slot}] restored. Simulation is paused.",
            "msg_zh": f"手动检查点 [{slot}] 已恢复，推演已暂停。",
        })
    except APIInputError as exc:
        return api_error(exc, exc.status_code)


@app.route('/api/session_backup', methods=['POST'])
def session_backup_api():
    try:
        require_local_ui_request()
        active = mounted_engine()
        with active.lock:
            artifact = create_backup(
                active.storage_dir,
                active.dlc_id,
                active.scenario_data.get("scenario_name", active.dlc_id),
                BUILD_INFO.version,
            )
        RUNTIME_LOGGER.info(
            "External backup created",
            extra={"event": "backup.created", "details": {"bytes": len(artifact.data)}},
        )
        return Response(
            artifact.data,
            mimetype="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{artifact.filename}"',
                "Cache-Control": "no-store",
            },
        )
    except (APIInputError, BackupError) as exc:
        status = exc.status_code if isinstance(exc, APIInputError) else 400
        return api_error(exc, status)
    except Exception as exc:
        return unexpected_api_error(exc, "backup.export_failed", "The backup could not be created.")


@app.route('/api/session_backup/restore', methods=['POST'])
def session_backup_restore_api():
    try:
        require_local_ui_request()
        active = mounted_engine()
        if request.form.get("confirmation") != "RESTORE":
            raise APIInputError("Backup restore confirmation is required")
        upload = request.files.get("backup")
        if upload is None:
            raise APIInputError("Choose a CDC Sim backup ZIP")
        data = upload.stream.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) > MAX_ARCHIVE_BYTES:
            raise APIInputError("Backup exceeds 64 MiB", 413)
        with active.lock:
            active.is_paused = True
            restored = restore_backup(active.storage_dir, data, active.dlc_id)
        RUNTIME_LOGGER.info(
            "External backup imported",
            extra={"event": "backup.imported", "details": {"checkpoint_count": len(restored)}},
        )
        return jsonify({
            "status": "ok",
            "restored": restored,
            "msg": "Backup imported and simulation paused. Choose a compatible checkpoint and click Restore.",
            "msg_zh": _API_MESSAGE_ZH["Backup imported and simulation paused. Choose a compatible checkpoint and click Restore."],
        })
    except (APIInputError, BackupError) as exc:
        status = exc.status_code if isinstance(exc, APIInputError) else 400
        return api_error(exc, status)
    except Exception as exc:
        return unexpected_api_error(exc, "backup.restore_failed", "The backup could not be restored.")


@app.route('/api/reset_scenario', methods=['POST'])
def reset_scenario_api():
    try:
        active = mounted_engine()
        active.load_initial_scenario()
        RUNTIME_LOGGER.info("Scenario reset", extra={"event": "scenario.reset"})
        return jsonify({
            "status": "ok",
            "msg": "Scenario reset to its DLC-authored starting state. Simulation is paused.",
            "msg_zh": _API_MESSAGE_ZH["Scenario reset to its DLC-authored starting state. Simulation is paused."],
        })
    except APIInputError as exc:
        return api_error(exc, exc.status_code)

def schedule_browser_open():
    if not RUNTIME_CONFIG.open_browser:
        return
    browser_host = "127.0.0.1" if RUNTIME_CONFIG.host in {"0.0.0.0", "::"} else RUNTIME_CONFIG.host
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    status_url = f"http://{browser_host}:{RUNTIME_CONFIG.port}/status"
    health_url = f"http://{browser_host}:{RUNTIME_CONFIG.port}/api/health"

    def open_when_ready():
        for _ in range(120):
            try:
                with urlopen(health_url, timeout=0.5):
                    webbrowser.open(status_url)
                    return
            except OSError:
                threading.Event().wait(0.25)
        RUNTIME_LOGGER.error(
            "Browser was not opened because the local server did not become ready",
            extra={"event": "startup.browser_timeout"},
        )

    threading.Thread(target=open_when_ready, daemon=True, name="cdc-browser-launch").start()


def run_development_server():
    schedule_browser_open()
    RUNTIME_LOGGER.info(
        "CDC Sim runtime starting",
        extra={"event": "startup.ready", "details": {"profile": RUNTIME_CONFIG.profile}},
    )
    print(f"\n{BUILD_INFO.product} {BUILD_INFO.version} ({BUILD_INFO.channel})")
    print(f"Opening local readiness check on port {RUNTIME_CONFIG.port}.")
    app.run(
        host=RUNTIME_CONFIG.host,
        port=RUNTIME_CONFIG.port,
        debug=False,
        use_reloader=False,
    )


@app.after_request
def apply_beta_response_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("X-CDC-Sim-Version", BUILD_INFO.version)
    return response


@app.errorhandler(Exception)
def handle_unexpected_exception(exception):
    if isinstance(exception, HTTPException):
        if request.path.startswith("/api/"):
            return api_error(exception.name, exception.code or 500)
        return exception
    return unexpected_api_error(exception, "http.unhandled_exception", "An unexpected error occurred.")


if __name__ == "__main__":
    run_development_server()
