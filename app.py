import math
import json
import os
import random

# Global dictionaries, initially empty. Will be hot-injected when mounting a DLC.
WEAPON_REGISTRY = {}
BATTALION_REGISTRY = {}

def clamp(value, low, high):
    return max(low, min(high, value))


def finite_float(value, label, minimum=None, maximum=None):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} must be at most {maximum}")
    return number

def load_dlc_registries(dlc_path):
    """Load both registries atomically and activate them for legacy callers."""
    global WEAPON_REGISTRY, BATTALION_REGISTRY
    w_path = os.path.join(dlc_path, 'weapons.json')
    b_path = os.path.join(dlc_path, 'battalions.json')

    with open(w_path, 'r', encoding='utf-8') as f:
        weapons = json.load(f)
    with open(b_path, 'r', encoding='utf-8') as f:
        battalions = json.load(f)
    if not isinstance(weapons, dict) or not isinstance(battalions, dict):
        raise ValueError("DLC registries must contain JSON objects")

    # Do not clear the active registries until both replacement files parsed.
    WEAPON_REGISTRY.clear()
    WEAPON_REGISTRY.update(weapons)
    BATTALION_REGISTRY.clear()
    BATTALION_REGISTRY.update(battalions)
    return dict(weapons), dict(battalions)

# 🟢 Fix 1: Restored the accidentally deleted spherical distance formula (used for calculating march speed and range)
def haversine_distance(lon1, lat1, lon2, lat2):
    R = 6371.0
    dLat = math.radians(lat2 - lat1)
    dLon = math.radians(lon2 - lon1)
    a = math.sin(dLat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ==========================================
# 1. Military Entity Core Class
# ==========================================
class MilitaryUnit:
    def __init__(self, unit_id, data, weapon_registry=None, battalion_registry=None, rules=None):
        if not isinstance(rules, dict):
            raise ValueError(f"Unit [{unit_id}] requires a validated DLC rule set")
        self.rules = rules
        defaults = rules["unit_defaults"]
        resources = rules["resources"]
        resource_min = float(resources["minimum"])
        resource_max = float(resources["maximum"])
        self.weapon_registry = weapon_registry if weapon_registry is not None else WEAPON_REGISTRY
        self.battalion_registry = battalion_registry if battalion_registry is not None else BATTALION_REGISTRY
        self.id = unit_id
        self.name = data["name"]
        self.faction = data["faction"]
        
        self.personnel = finite_float(data.get("personnel", defaults["personnel"]), f"Unit [{unit_id}] personnel", 0.0)
        self.equipment_level = finite_float(data.get("equipment_level", defaults["equipment_level"]), f"Unit [{unit_id}] equipment level", 0.0)
        
        self.lon = finite_float(data["lon"], f"Unit [{unit_id}] longitude", -180.0, 180.0)
        self.lat = finite_float(data["lat"], f"Unit [{unit_id}] latitude", -90.0, 90.0)
        
        requested_type = str(data.get("unit_type", defaults["unit_type"]))
        self.unit_type = next(
            (type_id for type_id in rules["unit_types"] if type_id.casefold() == requested_type.casefold()),
            requested_type,
        )
        raw_capabilities = data.get("capabilities", [])
        if not isinstance(raw_capabilities, list) or not all(isinstance(item, str) for item in raw_capabilities):
            raise ValueError(f"Unit [{unit_id}] capabilities must be a list of strings")
        self.capabilities = list(dict.fromkeys(raw_capabilities))
        raw_composition = data.get("composition", {})
        if not isinstance(raw_composition, dict):
            raise ValueError(f"Unit [{unit_id}] composition must be an object")
        self.composition = {}
        for battalion_id, count in raw_composition.items():
            numeric_count = finite_float(count, f"Unit [{unit_id}] battalion count [{battalion_id}]", 0.0)
            if numeric_count > 0:
                self.composition[battalion_id] = numeric_count

        self.primary_weapon = data.get("primary_weapon")
        if self.primary_weapon is not None and self.primary_weapon not in self.weapon_registry:
            raise ValueError(f"Unit [{unit_id}] references unknown weapon [{self.primary_weapon}]")
        self.weapon_name = "Unarmed"
        self.icon = data.get("icon", "")  # customize icon
        self.morale = finite_float(data.get("morale", defaults["morale"]), f"Unit [{unit_id}] morale", resource_min)
        self.status = str(data.get("status", defaults["status"]))
        legacy_routing = self.status == "ROUTING"
        
        self.waypoints = []
        for waypoint in data.get("waypoints", []):
            if not isinstance(waypoint, (list, tuple)) or len(waypoint) != 2:
                raise ValueError(f"Unit [{unit_id}] contains an invalid waypoint")
            lon = finite_float(waypoint[0], f"Unit [{unit_id}] waypoint longitude", -180.0, 180.0)
            lat = finite_float(waypoint[1], f"Unit [{unit_id}] waypoint latitude", -90.0, 90.0)
            self.waypoints.append((lon, lat))
        self.target_lon = finite_float(data["target_lon"], f"Unit [{unit_id}] target longitude", -180.0, 180.0) if data.get("target_lon") is not None else None
        self.target_lat = finite_float(data["target_lat"], f"Unit [{unit_id}] target latitude", -90.0, 90.0) if data.get("target_lat") is not None else None
        # Routing was removed in v3. Existing saves are migrated in place: the
        # unit stays at its saved coordinates and receives no invented retreat.
        if legacy_routing:
            self.status = str(defaults["status"])
            self.waypoints = []
            self.target_lon = None
            self.target_lat = None
        
        self.current_province = str(data.get("current_province", "Unknown"))
        requested_stance = str(data.get("stance", defaults["stance"]))
        self.stance = next(
            (stance_id for stance_id in rules["stances"] if stance_id.casefold() == requested_stance.casefold()),
            requested_stance,
        )
        if self.stance not in rules["stances"]:
            raise ValueError(f"Unit [{unit_id}] has unsupported stance [{self.stance}]")
        self.base_lon = finite_float(data["base_lon"], f"Unit [{unit_id}] base longitude", -180.0, 180.0) if data.get("base_lon") is not None else None
        self.base_lat = finite_float(data["base_lat"], f"Unit [{unit_id}] base latitude", -90.0, 90.0) if data.get("base_lat") is not None else None
        
        self.dynamic_eq_modifier = 1.0
        self.entrenchment = finite_float(data.get("entrenchment", defaults["entrenchment"]), f"Unit [{unit_id}] entrenchment", 0.0)
        raw_modifiers = data.get("modifiers", [])
        if not isinstance(raw_modifiers, list):
            raise ValueError(f"Unit [{unit_id}] modifiers must be a list")
        self.modifiers = []
        for modifier in raw_modifiers:
            if not isinstance(modifier, dict):
                raise ValueError(f"Unit [{unit_id}] contains an invalid modifier")
            self.modifiers.append({
                "name": str(modifier.get("name", defaults["modifier_name"])),
                "type": str(modifier.get("type", "")),
                "value": finite_float(modifier.get("value", defaults["modifier_value"]), f"Unit [{unit_id}] modifier value", 0.0),
                "duration": finite_float(modifier.get("duration", defaults["modifier_duration_hours"]), f"Unit [{unit_id}] modifier duration", 0.0),
            })
        allowed_modifier_types = set(rules["modifiers"]["allowed_types"])
        if any(modifier["type"] not in allowed_modifier_types for modifier in self.modifiers):
            raise ValueError(f"Unit [{unit_id}] contains an unsupported modifier type")
        self.supply = finite_float(data.get("supply", defaults["supply"]), f"Unit [{unit_id}] supply", resource_min, resource_max)
        self.fatigue = finite_float(data.get("fatigue", defaults["fatigue"]), f"Unit [{unit_id}] fatigue", resource_min, resource_max)
        self.suppression = finite_float(data.get("suppression", defaults["suppression"]), f"Unit [{unit_id}] suppression", resource_min, resource_max)
        
        attack_move = data.get("is_attack_move", False)
        if not isinstance(attack_move, bool):
            raise ValueError(f"Unit [{unit_id}] is_attack_move must be true or false")
        order_modes = rules["orders"]["modes"]
        requested_order = order_modes[rules["orders"]["default_role"]]["id"] if legacy_routing else data.get("order_mode")
        if requested_order is None:
            if attack_move:
                requested_order = order_modes["assault"]["id"]
            elif self.status == "MOVING":
                requested_order = order_modes["relocate"]["id"]
            else:
                requested_order = order_modes[rules["orders"]["default_role"]]["id"]
        requested_order = str(requested_order)
        self.order_mode = next(
            (
                profile["id"]
                for profile in order_modes.values()
                if profile["id"].casefold() == requested_order.casefold()
            ),
            requested_order,
        )
        valid_order_ids = {profile["id"] for profile in order_modes.values()}
        if self.order_mode not in valid_order_ids:
            raise ValueError(f"Unit [{unit_id}] has unsupported order mode [{self.order_mode}]")
        self.is_attack_move = self.has_order_role("assault")
        raw_avoidance = data.get("relocation_avoidance", {})
        if raw_avoidance is None:
            raw_avoidance = {}
        if not isinstance(raw_avoidance, dict):
            raise ValueError(f"Unit [{unit_id}] relocation_avoidance must be an object")
        raw_contacts = raw_avoidance.get("contacts", [])
        if not isinstance(raw_contacts, list):
            raise ValueError(f"Unit [{unit_id}] relocation avoidance contacts must be a list")
        self.relocation_avoidance_contacts = []
        for contact_index, contact in enumerate(raw_contacts):
            if not isinstance(contact, dict):
                raise ValueError(
                    f"Unit [{unit_id}] relocation avoidance contact [{contact_index}] must be an object"
                )
            contact_id = str(contact.get("id", "")).strip()
            if not contact_id:
                raise ValueError(
                    f"Unit [{unit_id}] relocation avoidance contact [{contact_index}] requires an id"
                )
            self.relocation_avoidance_contacts.append({
                "id": contact_id,
                "name": str(contact.get("name", contact_id)),
                "radius_km": finite_float(
                    contact.get("radius_km", 0.0),
                    f"Unit [{unit_id}] relocation avoidance contact [{contact_index}] radius",
                    0.0,
                ),
            })
        self.relocation_reroute_count = int(
            finite_float(
                raw_avoidance.get("reroute_count", 0),
                f"Unit [{unit_id}] relocation reroute count",
                0.0,
            )
        )
        self._relocation_avoidance_signature = None
        self._relocation_last_reroute_hour = -math.inf
        self.active_fire_range = 0.0
        
        # Physical footprint radius (km)
        self.radius = float(rules["footprint"]["minimum_radius_km"])
        self.altitude = finite_float(data.get("altitude", defaults["altitude_m"]), f"Unit [{unit_id}] altitude")
        if data.get("bombard_timer") is not None:
            self.bombard_timer = finite_float(data["bombard_timer"], f"Unit [{unit_id}] bombard timer", 0.0)
        self.bombard_casualties = finite_float(
            data.get("bombard_casualties", 0.0),
            f"Unit [{unit_id}] bombard casualties",
            0.0,
        )
        self.bombard_installation_damage = finite_float(
            data.get("bombard_installation_damage", 0.0),
            f"Unit [{unit_id}] bombard installation damage",
            0.0,
        )
        self.bombard_installations_destroyed = int(
            finite_float(
                data.get("bombard_installations_destroyed", 0),
                f"Unit [{unit_id}] bombard installations destroyed",
                0.0,
            )
        )

        # Aircraft performance belongs to the mounted DLC.  Saves and editor
        # payloads keep only the profile ID; all derived sortie values are
        # recalculated from the current, validated ruleset.
        requested_aircraft_type = data.get("aircraft_type")
        self.aircraft_type = None if requested_aircraft_type is None else str(requested_aircraft_type)

        # Invalid legacy mission state must not strand a unit forever or crash
        # the simulation loop when the target coordinates are missing.
        if self.status == "BOMBARDING" and (self.target_lon is None or self.target_lat is None):
            self.status = str(defaults["status"])
            if hasattr(self, "bombard_timer"):
                delattr(self, "bombard_timer")
            self.bombard_casualties = 0.0
            self.bombard_installation_damage = 0.0
            self.bombard_installations_destroyed = 0

        self.parse_composition()
        airstrike_rules = self.rules["missions"]["airstrike"]
        if self.has_capability(airstrike_rules["capability"]) or self.aircraft_type is not None:
            requested_aircraft_type = self.aircraft_type or str(airstrike_rules["default_aircraft_type"])
            canonical_aircraft_type = next(
                (
                    profile_id
                    for profile_id in airstrike_rules["aircraft_types"]
                    if profile_id.casefold() == requested_aircraft_type.casefold()
                ),
                None,
            )
            if canonical_aircraft_type is None:
                raise ValueError(f"Unit [{unit_id}] references unknown aircraft type [{requested_aircraft_type}]")
            self.aircraft_type = canonical_aircraft_type

    def parse_composition(self):
        unit_types = self.rules["unit_types"]
        if self.unit_type not in unit_types:
            raise ValueError(f"Unit [{self.id}] has unsupported unit type [{self.unit_type}]")
        profile = unit_types[self.unit_type]

        footprint = self.rules["footprint"]
        if self.personnel > 0:
            self.radius = max(
                float(footprint["minimum_radius_km"]),
                math.sqrt(self.personnel) * float(footprint["personnel_sqrt_scale"]),
            )
        else:
            self.radius = float(footprint["zero_personnel_radius_km"])
        if profile["radius_mode"] == "fixed":
            self.radius = float(profile["radius_km"])

        total_bats = 0.0
        nominal_personnel = 0.0
        speeds = []
        defense, breakthrough, org_sum, armor_sum, terrain_sum = 0, 0, 0, 0, 0
        softness_sum = 0.0
        armor_generation_weight = 0.0
        armor_generation_basis = 0.0
        self.weapon_loadout = {}
        self.armor_generation_breakdown = []

        for b_type, count in self.composition.items():
            if count <= 0:
                continue
            if b_type not in self.battalion_registry:
                raise ValueError(f"Unit [{self.id}] references unknown battalion [{b_type}]")

            reg = self.battalion_registry[b_type]
            total_bats += count
            nominal_personnel += float(reg["size"]) * count
            armor_value = float(reg["armor"])
            armor_generation = float(reg["armor_generation"])
            speeds.append(float(reg["speed"]))
            defense += float(reg["defense"]) * count
            breakthrough += float(reg["breakthrough"]) * count
            org_sum += float(reg["org"]) * count
            armor_sum += armor_value * count
            terrain_sum += float(reg["terrain"]) * count
            softness_sum += clamp(float(reg["softness"]), 0.0, 1.0) * count
            if armor_value > 0:
                armor_generation_weight += armor_generation * armor_value * count
                armor_generation_basis += armor_value * count
            self.armor_generation_breakdown.append({
                "battalion_id": b_type,
                "count": count,
                "armor": armor_value,
                "armor_generation": armor_generation,
            })
            for weapon_id, weapons_per_battalion in reg.get("weapons", {}).items():
                if weapon_id not in self.weapon_registry:
                    raise ValueError(f"Battalion [{b_type}] references unknown weapon [{weapon_id}]")
                quantity = float(weapons_per_battalion) * count
                if quantity > 0:
                    self.weapon_loadout[weapon_id] = self.weapon_loadout.get(weapon_id, 0.0) + quantity

        divisor = total_bats if total_bats > 0 else 1.0
        self.nominal_personnel = nominal_personnel
        self.armor_generation = armor_generation_weight / armor_generation_basis if armor_generation_basis > 0 else 0.0

        # A primary weapon is a display preference only.  Offensive power is
        # always generated by the battalion weapon loadout above.
        if self.primary_weapon not in self.weapon_loadout:
            self.primary_weapon = self._dominant_weapon_id()
        self.weapon_name = (
            str(self.weapon_registry[self.primary_weapon].get("name", self.primary_weapon))
            if self.primary_weapon is not None
            else "Unarmed"
        )
        self.direct_fire_range = self.get_max_weapon_range({"direct_fire"})
        self.bombard_range = self.get_max_weapon_range({"bombard"}, require_indirect=True)
        self.airstrike_weapon_range = self.get_max_weapon_range({"airstrike"})
        self.indirect_fire = any(
            bool(self.weapon_registry[weapon_id]["indirect_fire"])
            for weapon_id in self.weapon_loadout
            if {"direct_fire", "bombard"}.intersection(self.weapon_registry[weapon_id]["roles"])
        )
        if profile["fire_range_mode"] == "fixed":
            self.active_fire_range = float(profile["fire_range_km"])
        else:
            self.active_fire_range = max(self.direct_fire_range, self.bombard_range)

        close_attack = self.get_weapon_attack_totals(0.0)
        self.base_soft_attack = close_attack["soft_attack"]
        self.base_hard_attack = close_attack["hard_attack"]
        self.ap = close_attack["armor_piercing"]

        if profile["stats_source"] == "fixed":
            stats = profile["fixed_stats"]
            eq_mod = self.equipment_level * self.dynamic_eq_modifier if profile["fixed_stats_apply_equipment"] else 1.0
            self.speed = float(stats["speed_kmh"])
            self.base_defense = float(stats["defense"]) * eq_mod
            self.base_breakthrough = float(stats["breakthrough"]) * eq_mod
            self.max_org = float(stats["organization"])
            self.armor = float(stats["armor"]) * eq_mod
            self.softness = float(stats["softness"])
            self.terrain_mod = float(stats["terrain_modifier"])
            return

        self.speed = min(speeds) if speeds else 0.0
        eq_mod = self.equipment_level * self.dynamic_eq_modifier
        self.base_defense = defense * eq_mod
        self.base_breakthrough = breakthrough * eq_mod
        self.max_org = max(float(self.rules["composition"]["minimum_organization"]), org_sum / divisor)
        self.armor = (armor_sum / divisor) * eq_mod
        self.softness = softness_sum / divisor
        self.terrain_mod = terrain_sum / divisor

    def _weapon_equipment_multiplier(self):
        profile = self.rules["unit_types"][self.unit_type]
        if profile["stats_source"] == "fixed" and not profile["fixed_stats_apply_equipment"]:
            return 1.0
        return self.equipment_level * self.dynamic_eq_modifier

    @staticmethod
    def _weapon_band_at_range(weapon, distance_km):
        distance = max(0.0, float(distance_km))
        for band in weapon["range_bands"]:
            if distance <= float(band["max_range_km"]):
                return band
        return None

    def _dominant_weapon_id(self):
        best_id = None
        best_power = -1.0
        for weapon_id, quantity in self.weapon_loadout.items():
            band = self._weapon_band_at_range(self.weapon_registry[weapon_id], 0.0)
            if band is None:
                continue
            power = quantity * (float(band["soft_attack"]) + float(band["hard_attack"]))
            if power > best_power:
                best_id = weapon_id
                best_power = power
        return best_id

    def get_max_weapon_range(self, roles=None, require_indirect=None):
        requested_roles = set(roles or [])
        maximum = 0.0
        for weapon_id, quantity in self.weapon_loadout.items():
            if quantity <= 0:
                continue
            weapon = self.weapon_registry[weapon_id]
            if requested_roles and not requested_roles.intersection(weapon["roles"]):
                continue
            if require_indirect is not None and bool(weapon["indirect_fire"]) != require_indirect:
                continue
            maximum = max(maximum, float(weapon["range_bands"][-1]["max_range_km"]))
        return maximum

    def has_weapon_role(self, role):
        return self.get_max_weapon_range({role}) > 0.0

    def get_weapon_attack_totals(self, distance_km=0.0, roles=None, require_indirect=None):
        requested_roles = set(roles or [])
        equipment_multiplier = self._weapon_equipment_multiplier()
        result = {"soft_attack": 0.0, "hard_attack": 0.0, "armor_piercing": 0.0, "weapons_used": []}
        for weapon_id, quantity in self.weapon_loadout.items():
            weapon = self.weapon_registry[weapon_id]
            if requested_roles and not requested_roles.intersection(weapon["roles"]):
                continue
            if require_indirect is not None and bool(weapon["indirect_fire"]) != require_indirect:
                continue
            band = self._weapon_band_at_range(weapon, distance_km)
            if band is None:
                continue
            result["soft_attack"] += float(band["soft_attack"]) * quantity * equipment_multiplier
            result["hard_attack"] += float(band["hard_attack"]) * quantity * equipment_multiplier
            result["armor_piercing"] = max(
                result["armor_piercing"],
                float(band["armor_piercing"]) * equipment_multiplier,
            )
            result["weapons_used"].append(weapon_id)
        return result

    def calculate_weapon_attack(
        self,
        distance_km,
        target_softness,
        target_armor,
        failed_penetration_multiplier,
        roles=None,
        require_indirect=None,
        soft_multiplier=1.0,
        hard_multiplier=1.0,
        indirect_without_los_multiplier=1.0,
        has_line_of_sight=True,
        engaged_personnel=None,
    ):
        """Calculate fire weapon by weapon so range and penetration stay local."""
        requested_roles = set(roles or [])
        target_softness = clamp(float(target_softness), 0.0, 1.0)
        target_hardness = 1.0 - target_softness
        equipment_multiplier = self._weapon_equipment_multiplier()
        operating_fraction = self.get_weapon_operating_fraction(engaged_personnel)
        result = {
            "effective_attack": 0.0,
            "soft_component": 0.0,
            "hard_component": 0.0,
            "direct_component": 0.0,
            "indirect_component": 0.0,
            "weapons_used": [],
        }
        for weapon_id, quantity in self.weapon_loadout.items():
            weapon = self.weapon_registry[weapon_id]
            if requested_roles and not requested_roles.intersection(weapon["roles"]):
                continue
            is_indirect = bool(weapon["indirect_fire"])
            if require_indirect is not None and is_indirect != require_indirect:
                continue
            if not has_line_of_sight and not is_indirect:
                continue
            band = self._weapon_band_at_range(weapon, distance_km)
            if band is None:
                continue
            quantity_factor = quantity * equipment_multiplier * operating_fraction
            soft_component = (
                float(band["soft_attack"])
                * quantity_factor
                * target_softness
                * float(soft_multiplier)
            )
            hard_component = (
                float(band["hard_attack"])
                * quantity_factor
                * target_hardness
                * float(hard_multiplier)
            )
            penetration = float(band["armor_piercing"]) * equipment_multiplier
            if hard_component > 0 and penetration < float(target_armor):
                hard_component *= float(failed_penetration_multiplier)
            weapon_attack = soft_component + hard_component
            if is_indirect and not has_line_of_sight:
                weapon_attack *= float(indirect_without_los_multiplier)
                soft_component *= float(indirect_without_los_multiplier)
                hard_component *= float(indirect_without_los_multiplier)
            result["effective_attack"] += weapon_attack
            result["soft_component"] += soft_component
            result["hard_component"] += hard_component
            component_key = "indirect_component" if is_indirect else "direct_component"
            result[component_key] += weapon_attack
            result["weapons_used"].append(weapon_id)
        return result

    def get_weapon_operating_fraction(self, engaged_personnel=None):
        """Return the share of mounted weapon groups that can currently be crewed."""
        if self.personnel <= 0 or self.nominal_personnel <= 0:
            return 0.0
        available_personnel = self.personnel
        if engaged_personnel is not None:
            available_personnel = min(available_personnel, max(0.0, float(engaged_personnel)))
        return clamp(available_personnel / self.nominal_personnel, 0.0, 1.0)

    def get_weapon_loadout_records(self):
        records = []
        for weapon_id, quantity in self.weapon_loadout.items():
            weapon = self.weapon_registry[weapon_id]
            records.append({
                "id": weapon_id,
                "name": str(weapon.get("name", weapon_id)),
                "generation": int(weapon["generation"]),
                "quantity": quantity,
                "max_range_km": float(weapon["range_bands"][-1]["max_range_km"]),
                "roles": list(weapon["roles"]),
                "indirect_fire": bool(weapon["indirect_fire"]),
            })
        return records

    def get_mod_multiplier(self, mod_type):
        mult = 1.0
        for mod in self.modifiers:
            if mod.get("type") == mod_type:
                mult *= float(mod.get("value", 1.0))
        return mult

    def has_capability(self, capability):
        """Return whether the unit receives a named capability from its DLC."""
        return capability in self.get_capabilities()

    def get_capabilities(self):
        capabilities = set(self.capabilities)
        capabilities.update(self.rules["unit_types"][self.unit_type]["capabilities"])
        for battalion_id, count in self.composition.items():
            if count <= 0:
                continue
            battalion = self.battalion_registry.get(battalion_id, {})
            capabilities.update(battalion.get("capabilities", []))
        return capabilities

    def get_aircraft_profile(self):
        """Return the DLC aircraft-type profile used by this unit's sorties."""
        airstrike = self.rules["missions"]["airstrike"]
        requested_type = self.aircraft_type or str(airstrike["default_aircraft_type"])
        canonical_type = next(
            (
                profile_id
                for profile_id in airstrike["aircraft_types"]
                if profile_id.casefold() == requested_type.casefold()
            ),
            None,
        )
        if canonical_type is None:
            raise ValueError(f"Unit [{self.id}] references unknown aircraft type [{requested_type}]")
        return canonical_type, airstrike["aircraft_types"][canonical_type]

    def get_airstrike_parameters(self):
        """Resolve the campaign baseline through this aircraft type's factors."""
        airstrike = self.rules["missions"]["airstrike"]
        aircraft_type, profile = self.get_aircraft_profile()
        strike_totals = self.get_weapon_attack_totals(0.0, {"airstrike"})
        strike_generations = [
            int(self.weapon_registry[weapon_id]["generation"])
            for weapon_id in strike_totals["weapons_used"]
        ]
        return {
            "aircraft_type": aircraft_type,
            "label": str(profile["label"]),
            "description": str(profile["description"]),
            "attack_profile": str(profile["attack_profile"]),
            "cruise_speed_kmh": self.speed * float(profile["cruise_speed_multiplier"]),
            "sortie_range_km": float(airstrike["sortie_range_km"]) * float(profile["sortie_range_multiplier"]),
            "blast_radius_km": float(airstrike["blast_radius_km"]) * float(profile["blast_radius_multiplier"]),
            "soft_strike_power": strike_totals["soft_attack"] * float(profile["soft_target_multiplier"]),
            "hard_strike_power": strike_totals["hard_attack"] * float(profile["hard_target_multiplier"]),
            "strike_weapon_ids": list(strike_totals["weapons_used"]),
            "weapon_generation": max(strike_generations, default=0),
            "soft_target_multiplier": float(profile["soft_target_multiplier"]),
            "hard_target_multiplier": float(profile["hard_target_multiplier"]),
            "accuracy_multiplier": float(profile["accuracy_multiplier"]),
            "unobserved_targeting_multiplier": float(profile["unobserved_targeting_multiplier"]),
            "payload_multiplier": float(profile["payload_multiplier"]),
            "morale_shock_multiplier": float(profile["morale_shock_multiplier"]),
            "suppression_multiplier": float(profile["suppression_multiplier"]),
            "supply_cost": float(airstrike["supply_cost"]) * float(profile["supply_cost_multiplier"]),
            "fatigue_cost": float(airstrike["fatigue_cost"]) * float(profile["fatigue_cost_multiplier"]),
            "aa_vulnerability_multiplier": float(profile["aa_vulnerability_multiplier"]),
        }

    def order_id(self, role):
        """Return the core-doctrine identifier for a semantic order role."""
        return self.rules["orders"]["modes"][role]["id"]

    def order_role(self):
        """Return the semantic role represented by the unit's current order."""
        for role, profile in self.rules["orders"]["modes"].items():
            if profile["id"] == self.order_mode:
                return role
        return self.rules["orders"]["default_role"]

    def has_order_role(self, role):
        return self.order_mode == self.order_id(role)

    def set_order_role(self, role):
        profile = self.rules["orders"]["modes"][role]
        self.order_mode = profile["id"]
        self.is_attack_move = role == "assault"
        if role != "relocate" and hasattr(self, "relocation_avoidance_contacts"):
            self.clear_relocation_avoidance()

    def clear_relocation_avoidance(self):
        self.relocation_avoidance_contacts = []
        self.relocation_reroute_count = 0
        self._relocation_avoidance_signature = None
        self._relocation_last_reroute_hour = -math.inf

    def uses_prepared_defense(self):
        """A stationary unit can use fieldworks without changing its stance."""

        moving_statuses = {"MOVING", "AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"}
        return not self.waypoints and self.status not in moving_statuses

    def get_readiness(self):
        config = self.rules["readiness"]["combat"]
        resource_min = float(self.rules["resources"]["minimum"])
        resource_max = float(self.rules["resources"]["maximum"])
        span = max(resource_max - resource_min, 1e-9)
        supply_ratio = clamp((self.supply - resource_min) / span, 0.0, 1.0)
        fatigue_ratio = clamp((self.fatigue - resource_min) / span, 0.0, 1.0)
        suppression_ratio = clamp((self.suppression - resource_min) / span, 0.0, 1.0)
        supply_floor = float(config["supply_floor"])
        supply_factor = supply_floor + (1.0 - supply_floor) * supply_ratio
        fatigue_factor = 1.0 - float(config["fatigue_penalty"]) * fatigue_ratio
        suppression_factor = 1.0 - float(config["suppression_penalty"]) * suppression_ratio
        return max(float(config["minimum"]), supply_factor * fatigue_factor * suppression_factor)

    def get_speed_readiness(self):
        config = self.rules["readiness"]["movement"]
        resource_min = float(self.rules["resources"]["minimum"])
        resource_max = float(self.rules["resources"]["maximum"])
        span = max(resource_max - resource_min, 1e-9)
        supply_ratio = clamp((self.supply - resource_min) / span, 0.0, 1.0)
        fatigue_ratio = clamp((self.fatigue - resource_min) / span, 0.0, 1.0)
        suppression_ratio = clamp((self.suppression - resource_min) / span, 0.0, 1.0)
        supply_floor = float(config["supply_floor"])
        supply_factor = supply_floor + (1.0 - supply_floor) * supply_ratio
        fatigue_factor = 1.0 - float(config["fatigue_penalty"]) * fatigue_ratio
        suppression_factor = 1.0 - float(config["suppression_penalty"]) * suppression_ratio
        return max(float(config["minimum"]), supply_factor * fatigue_factor * suppression_factor)

    def get_effective_movement_speed(self, terrain_complexity):
        """Return current map speed after terrain, readiness, stance, and orders."""
        type_profile = self.rules["unit_types"][self.unit_type]
        stance_profile = self.rules["stances"][self.stance]
        terrain_factor = 1.0 if type_profile["ignores_movement_terrain"] else (
            1.0 - (float(terrain_complexity) * (1.0 - min(1.0, self.terrain_mod)))
        )
        actual_speed = (
            self.speed
            * max(0.0, terrain_factor)
            * self.get_speed_readiness()
            * float(stance_profile["movement_multiplier"])
            * self.get_mod_multiplier("speed")
        )
        if self.status in {"AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"}:
            _aircraft_type, aircraft_profile = self.get_aircraft_profile()
            actual_speed *= float(aircraft_profile["cruise_speed_multiplier"])
        if self.status == "MOVING" and self.has_order_role("assault"):
            actual_speed *= float(self.rules["orders"]["assault_speed_multiplier"])
        return max(0.0, actual_speed)

    def get_terrain_efficiency(self, terrain_complexity):
        type_profile = self.rules["unit_types"][self.unit_type]
        stance_profile = self.rules["stances"][self.stance]
        if type_profile["terrain_efficiency_mode"] == "fixed":
            actual_eff = float(type_profile["terrain_efficiency_multiplier"])
        else:
            actual_eff = max(
                float(self.rules["readiness"]["combat"]["minimum"]),
                1.0 - (terrain_complexity * (1.0 - self.terrain_mod)),
            )
        if type_profile["applies_stance_combat"]:
            actual_eff *= float(stance_profile["combat_multiplier"])
            if self.uses_prepared_defense():
                actual_eff *= 1.0 + self.entrenchment

        morale_floor = float(self.rules["readiness"]["morale_floor"])
        morale_scale = float(self.rules["readiness"]["morale_scale"])
        modifier = self.get_mod_multiplier("combat") if type_profile["applies_combat_modifiers"] else 1.0
        morale_factor = (max(morale_floor, self.morale) / morale_scale) if type_profile["applies_morale"] else 1.0
        return actual_eff * modifier * self.get_readiness() * morale_factor

    def update_position(self, delta_time_hours, engine):
        if self.personnel <= 0: 
            return

        self.parse_composition() 
        resources = self.rules["resources"]
        resource_min = float(resources["minimum"])
        resource_max = float(resources["maximum"])
        recovery = self.rules["recovery"]
        movement = self.rules["movement"]
        orders = self.rules["orders"]
        defense = self.rules["defense"]
        stance_profile = self.rules["stances"][self.stance]
        type_profile = self.rules["unit_types"][self.unit_type]
        
        if self.current_province == "Unknown": 
            self.current_province = engine.prov_engine.get_province(self.lon, self.lat)
        
        self.supply = clamp(self.supply, resource_min, resource_max)
        self.fatigue = clamp(self.fatigue, resource_min, resource_max)
        self.suppression = max(resource_min, self.suppression - float(recovery["suppression_decay_per_hour"]) * delta_time_hours)

        self.modifiers = [m for m in self.modifiers if (m["duration"] - delta_time_hours) > 0]
        for m in self.modifiers: 
            m["duration"] -= delta_time_hours

        defending_status = orders["defending_status"]
        fortifying_status = orders["fortifying_status"]
        if self.waypoints and self.status in ["IDLE", defending_status, fortifying_status]:
            self.status = "MOVING"

        if self.status in ["IDLE", defending_status]:
            recovery_mod = float(stance_profile["recovery_multiplier"])
            if self.morale < self.max_org:
                morale_gain = float(recovery["idle_morale_per_hour"]) * recovery_mod * self.get_mod_multiplier("morale") * delta_time_hours
                self.morale = min(self.max_org, self.morale + morale_gain)
            self.fatigue = max(resource_min, self.fatigue - float(recovery["idle_fatigue_per_hour"]) * recovery_mod * delta_time_hours)
            self.supply = min(resource_max, self.supply + float(recovery["idle_supply_per_hour"]) * recovery_mod * delta_time_hours)
            if self.status == defending_status:
                build_rate = float(recovery["entrenchment_per_hour"])
                build_rate *= float(defense["defend_entrenchment_multiplier"])
                resource_span = max(1.0, resource_max - resource_min)
                suppression_ratio = (self.suppression - resource_min) / resource_span
                build_rate *= max(0.0, 1.0 - suppression_ratio * float(defense["suppression_build_penalty"]))
                self.entrenchment = min(
                    float(recovery["maximum_entrenchment"]),
                    self.entrenchment + build_rate * delta_time_hours,
                )
        elif self.status == fortifying_status:
            if self.supply <= float(defense["stop_supply_threshold"]):
                self.set_order_role(orders["fortify_completion_role"])
                self.status = defending_status
                engine.log_event(
                    f"[Fortification] {self.name} suspended construction because field supplies are low and shifted to defense.",
                    faction=self.faction,
                    msg_type="move",
                )
            else:
                resource_span = max(1.0, resource_max - resource_min)
                suppression_ratio = (self.suppression - resource_min) / resource_span
                build_rate = float(defense["fortify_entrenchment_per_hour"]) * max(
                    0.0,
                    1.0 - suppression_ratio * float(defense["suppression_build_penalty"]),
                )
                maximum_entrenchment = float(recovery["maximum_entrenchment"])
                supply_rate = float(defense["fortify_supply_per_hour"])
                affordable_hours = delta_time_hours
                if supply_rate > 0:
                    affordable_hours = min(
                        affordable_hours,
                        max(0.0, self.supply - float(defense["stop_supply_threshold"])) / supply_rate,
                    )
                work_hours = affordable_hours
                if build_rate > 0:
                    work_hours = min(work_hours, max(0.0, maximum_entrenchment - self.entrenchment) / build_rate)
                self.entrenchment = min(
                    maximum_entrenchment,
                    self.entrenchment + build_rate * work_hours,
                )
                self.supply = max(
                    resource_min,
                    self.supply - supply_rate * work_hours,
                )
                self.fatigue = min(
                    resource_max,
                    self.fatigue + float(defense["fortify_fatigue_per_hour"]) * work_hours,
                )
                if self.entrenchment >= maximum_entrenchment:
                    self.set_order_role(orders["fortify_completion_role"])
                    self.status = defending_status
                    engine.log_event(
                        f"[Fortification] {self.name} completed its prepared position and is ready to defend.",
                        faction=self.faction,
                        msg_type="move",
                    )
                elif affordable_hours < delta_time_hours:
                    self.set_order_role(orders["fortify_completion_role"])
                    self.status = defending_status
                    engine.log_event(
                        f"[Fortification] {self.name} exhausted construction supplies and shifted to defense.",
                        faction=self.faction,
                        msg_type="move",
                    )
        elif self.status in ["MOVING", "AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"]:
            self.entrenchment = float(self.rules["unit_defaults"]["entrenchment"])

        if self.status == "BOMBARDING":
            bombard = self.rules["missions"]["bombard"]
            if not hasattr(self, 'bombard_timer'):
                self.bombard_timer = float(bombard["duration_hours"])
            remaining_hours = max(0.0, float(self.bombard_timer))
            supply_rate = float(bombard["supply_per_hour"])
            stop_supply = float(bombard["stop_supply_threshold"])
            if supply_rate > 0:
                affordable_hours = max(0.0, self.supply - stop_supply) / supply_rate
            else:
                affordable_hours = math.inf
            active_hours = min(delta_time_hours, remaining_hours, affordable_hours)
            self._bombard_effective_hours = max(0.0, active_hours)
            self.bombard_timer = max(0.0, remaining_hours - active_hours)
            self.fatigue = min(resource_max, self.fatigue + float(bombard["fatigue_per_hour"]) * active_hours)
            self.supply = max(resource_min, self.supply - supply_rate * active_hours)
            if self.bombard_timer <= 0:
                self._bombard_completion_reason = "planned duration elapsed"
            elif self.supply <= stop_supply:
                self._bombard_completion_reason = "ammunition reserve reached"
            return

        if self.status not in ["MOVING", "AIRSTRIKE_OUTBOUND", "AIRSTRIKE_RTB"] or not self.waypoints:
            return

        if (
            self.status == "MOVING"
            and self.has_order_role("relocate")
            and hasattr(engine, "refresh_relocation_route")
        ):
            engine.refresh_relocation_route(self)

        current_target_lon, current_target_lat = self.waypoints[0]
        dist_km = haversine_distance(self.lon, self.lat, current_target_lon, current_target_lat)
        
        if dist_km < float(movement["arrival_distance_km"]):
            self.lon = current_target_lon
            self.lat = current_target_lat
            self.waypoints.pop(0) 
            
            if not self.waypoints:
                if self.status == "MOVING": 
                    self.status = "IDLE"
                    self.set_order_role(orders["arrival_role"])
                    self.clear_relocation_avoidance()
                    engine.log_event(f"📡 [Maneuver] {self.name} reached designated coordinates.", faction=self.faction, msg_type="move")
                elif self.status == "AIRSTRIKE_OUTBOUND": 
                    result = engine.resolve_airstrike_impact(self) if hasattr(engine, "resolve_airstrike_impact") else {
                        "targets_hit": 0,
                        "casualties": 0.0,
                        "morale_loss": 0.0,
                        "suppression": 0.0,
                    }
                    aircraft_label = str(result.get("aircraft_label", self.get_airstrike_parameters()["label"]))
                    targets_hit = int(result.get("targets_hit", 0))
                    casualties = float(result.get("casualties", 0.0))
                    morale_loss = float(result.get("morale_loss", 0.0))
                    suppression = float(result.get("suppression", 0.0))
                    installations_hit = int(result.get("installations_hit", 0))
                    installation_damage = float(result.get("installation_damage", 0.0))
                    installations_destroyed = int(result.get("installations_destroyed", 0))
                    effects = []
                    if targets_hit:
                        effects.append(
                            f"affected {targets_hit} hostile formation(s); estimated personnel losses {casualties:.0f}, "
                            f"morale -{morale_loss:.1f}, suppression +{suppression:.1f}"
                        )
                    if installations_hit:
                        installation_effect = (
                            f"hit {installations_hit} military target(s) for "
                            f"{installation_damage:.0f} integrity damage"
                        )
                        if installations_destroyed:
                            installation_effect += f"; destroyed {installations_destroyed}"
                        effects.append(installation_effect)
                    impact_summary = "; ".join(effects) if effects else (
                        "completed the strike with no eligible hostile ground target inside the effect area"
                    )
                    if self.base_lon is None or self.base_lat is None:
                        self.status = "IDLE"
                        self.target_lon = self.target_lat = None
                        engine.log_event(
                            f"[Airstrike] {self.name} ({aircraft_label}) {impact_summary}, but no return base was recorded.",
                            faction=self.faction,
                            msg_type="system",
                        )
                    else:
                        self.status = "AIRSTRIKE_RTB"
                        self.waypoints = [(self.base_lon, self.base_lat)]
                        engine.log_event(
                            f"💥 [Airstrike] {self.name} ({aircraft_label}) {impact_summary} and is returning to base.",
                            faction=self.faction,
                            msg_type="combat",
                        )
                elif self.status == "AIRSTRIKE_RTB": 
                    self.status = "IDLE"
                    self.target_lon = self.target_lat = None
                    self.base_lon = self.base_lat = None
                    engine.log_event(f"🛬 [Air Force RTB] {self.name} returned to base.", faction=self.faction, msg_type="move")
                return
            else:
                current_target_lon, current_target_lat = self.waypoints[0]
                dist_km = haversine_distance(self.lon, self.lat, current_target_lon, current_target_lat)

        tp = engine.get_terrain_complexity(self.lon, self.lat)
        self.altitude = engine.map_engine.get_elevation(self.lon, self.lat)
        actual_speed = self.get_effective_movement_speed(tp)
        
        # Assaults close through ranged contact while firing. Stopping at the
        # longest mounted weapon range made a formation with organic artillery
        # freeze tens of kilometres from its objective. Only a detected hostile
        # physically blocking the advance at close ground contact halts it.
        if self.has_order_role("assault") and self.status == "MOVING" and orders["assault_halts_at_contact"]:
            contact_distance = float(self.rules["combat"]["direct"]["minimum_engagement_distance_km"])
            for other in engine.units.values():
                if other.personnel > 0 and not engine.is_allied(self.faction, other.faction):
                    edge_dist = max(0.0, haversine_distance(self.lon, self.lat, other.lon, other.lat) - self.radius - other.radius)
                    can_see = engine._is_detected_by(self.faction, other.id) if hasattr(engine, "_is_detected_by") else other.id in engine.detected_units
                    enemy_is_ahead = (
                        haversine_distance(other.lon, other.lat, current_target_lon, current_target_lat)
                        < dist_km
                    )
                    if can_see and enemy_is_ahead and edge_dist <= contact_distance:
                        actual_speed = 0.0
                        break

        step_km = actual_speed * delta_time_hours
        ratio = min(1.0, step_km / dist_km) if dist_km > 0 else 1.0
        
        self.lon += (current_target_lon - self.lon) * ratio
        self.lat += (current_target_lat - self.lat) * ratio
        travel_hours = min(delta_time_hours, dist_km / actual_speed) if actual_speed > 0 else 0.0
        if travel_hours > 0:
            self.fatigue = min(
                resource_max,
                self.fatigue + (float(movement["base_fatigue_per_hour"]) + tp * float(movement["terrain_fatigue_per_hour"])) * travel_hours,
            )
            battalion_supply_cost = sum(
                float(self.battalion_registry[battalion_id]["movement_supply_cost"]) * count
                for battalion_id, count in self.composition.items()
            )
            self.supply = max(
                resource_min,
                self.supply - (float(movement["base_supply_per_hour"]) + battalion_supply_cost) * travel_hours,
            )
        
        airstrike_capability = self.rules["missions"]["airstrike"]["capability"]
        air_defense = self.rules["missions"]["air_defense"]
        if self.has_capability(airstrike_capability) and self.status.startswith("AIRSTRIKE") and self.personnel > 0:
            aircraft_parameters = self.get_airstrike_parameters()
            for other in engine.units.values():
                if (
                    other.personnel > 0
                    and not engine.is_allied(self.faction, other.faction)
                    and other.has_capability(air_defense["capability"])
                    and other.equipment_level >= float(air_defense["minimum_equipment_level"])
                ):
                    if max(0.0, haversine_distance(self.lon, self.lat, other.lon, other.lat) - self.radius - other.radius) <= float(air_defense["range_km"]):
                        probability = min(
                            1.0,
                            float(air_defense["kill_probability_per_hour"])
                            * float(aircraft_parameters["aa_vulnerability_multiplier"])
                            * delta_time_hours,
                        )
                        if random.random() < probability:
                            self.personnel = 0
                            self.status = "NEUTRALIZED"
                            self.waypoints = []
                            self.target_lon = self.target_lat = None
                            self.base_lon = self.base_lat = None
                            engine.log_event(
                                f"💥 [AA Net] {self.name} ({aircraft_parameters['label']}) was shot down by {other.name}'s anti-air fire net.",
                                faction=self.faction,
                                msg_type="combat",
                            )
                            break

        new_prov = engine.prov_engine.get_province(self.lon, self.lat)
        if new_prov != self.current_province and self.current_province != "Unknown" and not stance_profile["conceals_border_crossing"]:
            engine.log_event(f"🚨 [Zone Alert] {self.name} crossed the border into {new_prov}.", faction=self.faction, msg_type="move")
        self.current_province = new_prov
        # Real-time synchronization of local physical altitude (meters)
        self.altitude = engine.map_engine.get_elevation(self.lon, self.lat)

    def to_dict(self):
        airstrike_capability = self.rules["missions"]["airstrike"]["capability"]
        airstrike_profile = self.get_airstrike_parameters() if self.has_capability(airstrike_capability) else None
        return {
            "id": self.id,
            "name": self.name, 
            "faction": self.faction, 
            "icon": getattr(self, 'icon', ""),
            "personnel": self.personnel,
            "lon": self.lon, 
            "lat": self.lat, 
            "speed": self.speed,
            "equipment_level": self.equipment_level, 
            "unit_type": self.unit_type, 
            "aircraft_type": self.aircraft_type,
            "airstrike_profile": airstrike_profile,
            "capabilities": self.capabilities,
            "effective_capabilities": sorted(self.get_capabilities()),
            "composition": self.composition,
            "primary_weapon": self.primary_weapon,
            "weapon_name": self.weapon_name,
            "weapon_loadout": self.get_weapon_loadout_records(),
            "morale": self.morale, 
            "stance": self.stance,
            "entrenchment": self.entrenchment, 
            "supply": self.supply,
            "fatigue": self.fatigue,
            "suppression": self.suppression,
            "modifiers": self.modifiers,
            "waypoints": self.waypoints, 
            "target_lon": self.target_lon, 
            "target_lat": self.target_lat,
            "base_lon": self.base_lon,
            "base_lat": self.base_lat,
            "status": self.status,
            "order_mode": self.order_mode,
            "is_attack_move": self.is_attack_move,
            "relocation_avoidance": {
                "active": bool(
                    self.status == "MOVING"
                    and self.has_order_role("relocate")
                    and self.relocation_avoidance_contacts
                ),
                "contacts": list(self.relocation_avoidance_contacts),
                "reroute_count": self.relocation_reroute_count,
            },
            "active_fire_range": self.active_fire_range,
            "direct_fire_range": self.direct_fire_range,
            "bombard_range": self.bombard_range,
            "weapon_operating_fraction": self.get_weapon_operating_fraction(),
            "indirect_fire": self.indirect_fire,
            "radius": self.radius, # Export physical radius for frontend circle rendering
            "altitude": getattr(self, 'altitude', 0.0), # Export altitude
            "current_province": self.current_province,
            "bombard_timer": getattr(self, "bombard_timer", None),
            "bombard_casualties": self.bombard_casualties,
            "bombard_installation_damage": self.bombard_installation_damage,
            "bombard_installations_destroyed": self.bombard_installations_destroyed,
            "stats": {
                "soft": self.base_soft_attack, 
                "hard": self.base_hard_attack, 
                "armor": self.armor, 
                "ap": self.ap, 
                "softness": self.softness,
                "armor_generation": self.armor_generation
            }
        }
