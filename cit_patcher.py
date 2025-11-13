#!/usr/bin/env python3
"""
cit_patcher.py - updated

- Produces case "when" values like "Crafting Table_0"
- Rewrites model JSON texture targets that are relative/bare into
  "<generated_folder_name>:item/<texture_name>"
- Supports zip input, loads block list from minecraft_blocks.txt,
  and preserves previous functionality (merge cases, etc.)
"""

import os
import sys
import json
import shutil
import tempfile
import zipfile
import configparser
from pathlib import Path
import re

# ---------------------------
# Config & helpers
# ---------------------------

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read('config.ini')
    # provide sensible defaults if file or keys missing
    if 'DEFAULT' not in cfg:
        cfg['DEFAULT'] = {}
    return cfg

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def copy_root_files(src_root, dest_root):
    for item in os.listdir(src_root):
        if item.lower() == "assets":
            continue
        src_item = os.path.join(src_root, item)
        dest_item = os.path.join(dest_root, item)
        if os.path.isdir(src_item):
            if os.path.exists(dest_item):
                log(f"Skipping existing directory {dest_item}")
            else:
                try:
                    shutil.copytree(src_item, dest_item)
                    log(f"Copied directory {item} -> {dest_item}")
                except Exception as e:
                    log(f"Failed copying directory {item}: {e}")
        else:
            if os.path.exists(dest_item):
                log(f"Skipping existing file {dest_item}")
            else:
                shutil.copy2(src_item, dest_item)
                log(f"Copied file {item} -> {dest_item}")

def parse_properties(file_path):
    data = {}
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data

# Transform filename -> case "when" value (vanilla-like, spaces, capitalize)
def transform_name_to_vanilla(filename_no_ext):
    """
    Rules:
    - Split on underscores.
    - Capitalize each head word and join with spaces.
    - Detect first segment that contains a digit; everything from that segment
      onward (including underscores) is preserved exactly and appended to the head
      separated by a single underscore.
    Examples:
      crafting_table_0 -> "Crafting Table_0"
      apple_0 -> "Apple_0"
      birch_leaves_0_wall -> "Birch Leaves_0_wall"
      dark_oak -> "Dark Oak"
    """
    parts = filename_no_ext.split('_')
    idx = None
    for i, p in enumerate(parts):
        if any(ch.isdigit() for ch in p):
            idx = i
            break
    if idx is None:
        # No numeric segment: capitalize and join with spaces
        head = ' '.join(p.capitalize() for p in parts if p != '')
        return head
    else:
        head_parts = parts[:idx]
        tail_parts = parts[idx:]
        head = ' '.join(p.capitalize() for p in head_parts if p != '')
        tail = '_'.join(tail_parts)
        return f"{head}_{tail}" if head else tail

def load_block_names():
    block_file = "minecraft_blocks.txt"
    names = set()
    if os.path.exists(block_file):
        with open(block_file, "r", encoding="utf-8") as f:
            for line in f:
                n = line.strip()
                if n and not n.startswith("#"):
                    names.add(n)
        log(f"Loaded {len(names)} block names from {block_file}")
    else:
        log(f"Warning: {block_file} not found; defaulting to items-only fallback")
    return names

def safe_load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None

def write_json_pretty(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding='utf-8')

def log(msg):
    # prints only if verbose is enabled in config (set by main)
    if GLOBAL_CONFIG.get("verbose", True):
        print(msg)

# ---------------------------
# Item JSON merging (selector)
# ---------------------------

def merge_item_json(item_json_path, case_when, case_model_path, fallback_model):
    existing = safe_load_json(item_json_path)
    if existing and isinstance(existing, dict):
        try:
            model_block = existing.setdefault("model", {})
            model_block.setdefault("type", "minecraft:select")
            model_block.setdefault("property", "minecraft:component")
            model_block.setdefault("component", "minecraft:custom_name")
            cases = model_block.setdefault("cases", [])
            if any(c.get("when") == case_when for c in cases):
                log(f"Case '{case_when}' already present in {item_json_path}; skipping append")
            else:
                cases.append({
                    "when": case_when,
                    "model": {
                        "type": "minecraft:model",
                        "model": case_model_path
                    }
                })
            if isinstance(fallback_model, dict):
                # Directly use complex/special fallback definition
                model_block.setdefault("fallback", fallback_model)
            else:
                # Normal string fallback path
                model_block.setdefault("fallback", {
                    "type": "minecraft:model",
                    "model": fallback_model,
                    "tints": []
                })
            write_json_pretty(item_json_path, existing)
            return
        except Exception as e:
            log(f"Could not merge into existing {item_json_path}: {e}")

    # create new structure if we couldn't merge
    if isinstance(fallback_model, dict):
        fallback_block = fallback_model
    else:
        fallback_block = {
            "type": "minecraft:model",
            "model": fallback_model,
            "tints": []
        }

    new_obj = {
        "model": {
            "type": "minecraft:select",
            "property": "minecraft:component",
            "component": "minecraft:custom_name",
            "cases": [
                {
                    "when": case_when,
                    "model": {
                        "type": "minecraft:model",
                        "model": case_model_path
                    }
                }
            ],
            "fallback": fallback_block
        }
    }
    write_json_pretty(item_json_path, new_obj)

# ---------------------------
# Model JSON texture rewriting
# ---------------------------

def rewrite_model_textures_and_write(src_json_path, dest_json_path, generated_folder_name):
    try:
        data = json.loads(Path(src_json_path).read_text(encoding='utf-8'))
    except Exception as e:
        log(f"Couldn't parse JSON {src_json_path}: {e}. Copying raw file.")
        shutil.copy2(src_json_path, dest_json_path)
        return

    # --- Resolve parent display transforms ---
    data = resolve_model_parents(data, Path(src_json_path).parent)

    # --- Rewrite textures ---
    if isinstance(data, dict) and "textures" in data and isinstance(data["textures"], dict):
        textures = data["textures"]
        for key, val in list(textures.items()):
            if not isinstance(val, str):
                continue
            v = val.strip()
            if v.startswith("./") or v.startswith(".\\"):
                base = v[2:]
            else:
                base = v
            if ":" in base or "/" in base:
                continue
            if re.search(r"[A-Za-z_]", base):
                new_val = f"{generated_folder_name}:item/{base}"
                textures[key] = new_val
                log(f"Rewrote texture '{val}' -> '{new_val}' in {src_json_path}")

    write_json_pretty(dest_json_path, data)

def resolve_texture_references(textures):
    """
    Resolves texture key references like "#trapdoor" -> the actual texture path.
    Repeats until all references are expanded or no further resolution is possible.
    """
    resolved = dict(textures)
    changed = True
    while changed:
        changed = False
        for key, val in list(resolved.items()):
            if isinstance(val, str) and val.startswith("#"):
                ref_key = val[1:]
                if ref_key in resolved and resolved[ref_key] != val:
                    resolved[key] = resolved[ref_key]
                    changed = True
    return resolved

def resolve_model_parents(data, src_folder, visited=None):
    """
    Recursively resolves './parent' models in the same folder and merges *all* relevant fields.
    Child values always override parent values.
    """
    if not isinstance(data, dict):
        return data

    if visited is None:
        visited = set()

    parent_path = data.get("parent")
    if not parent_path or not parent_path.startswith("./"):
        return data

    parent_file = Path(src_folder) / (Path(parent_path).stem + ".json")

    # Prevent infinite loops
    if parent_file in visited:
        log(f"Cycle detected for {parent_file}, skipping")
        return data
    visited.add(parent_file)

    if not parent_file.exists():
        log(f"Parent {parent_file} not found")
        data.pop("parent", None)
        return data

    try:
        parent_data = json.loads(parent_file.read_text(encoding='utf-8'))
        parent_data = resolve_model_parents(parent_data, src_folder, visited)

        # --- Merge all relevant fields ---
        merged = dict(parent_data)  # start from parent copy
        merged.update({k: v for k, v in data.items() if k not in ("textures", "elements", "display")})

        # Merge textures (child overrides individual keys)
        if "textures" in parent_data or "textures" in data:
            merged["textures"] = dict(parent_data.get("textures", {}))
            merged["textures"].update(data.get("textures", {}))

        # Merge elements (child replaces entirely if present)
        if "elements" in data:
            merged["elements"] = data["elements"]
        elif "elements" in parent_data:
            merged["elements"] = parent_data["elements"]

        # Merge display (child replaces or extends)
        if "display" in parent_data or "display" in data:
            merged["display"] = dict(parent_data.get("display", {}))
            merged["display"].update(data.get("display", {}))

        # Ambient occlusion, etc.
        if "ambientocclusion" not in merged and "ambientocclusion" in parent_data:
            merged["ambientocclusion"] = parent_data["ambientocclusion"]

        # Remove parent to avoid unresolved reference
        merged.pop("parent", None)

        # Resolve #texture references after merging
        if "textures" in merged:
            merged["textures"] = resolve_texture_references(merged["textures"])

        return merged

    except Exception as e:
        log(f"Error resolving parent {parent_path}: {e}")
        data.pop("parent", None)
        return data

# ---------------------------
# CIT processing
# ---------------------------

# Correct fallbacks for special items/blocks
FALLBACK_OVERRIDES = {
    "cake": "minecraft:item/cake",  # standard item model
    "clock": "minecraft:item/clock",  # animated item

    # Shields – requires special renderer
    "shield": {
        "type": "minecraft:special",
        "base": "minecraft:item/shield",
        "model": {"type": "minecraft:shield"}
    },

    # Chests – block entity special model
    "chest": {
        "type": "minecraft:special",
        "base": "minecraft:item/chest",
        "model": {
            "type": "minecraft:chest",
            "texture": "minecraft:normal"
        }
    },

    # Ominous banner special variant
    "ominous_banner": {
        "type": "minecraft:special",
        "base": "minecraft:item/banner",
        "model": {"type": "minecraft:banner", "pattern_color": "black"}
    },
}

# Add all fence, trapdoor, and sign variants
for wood in ["oak", "spruce", "birch", "jungle", "acacia", "dark_oak",
             "mangrove", "cherry", "bamboo", "crimson", "warped",
             "nether_brick", "pale_oak"]:
    FALLBACK_OVERRIDES[f"{wood}_fence"] = f"minecraft:block/{wood}_fence_inventory"
    FALLBACK_OVERRIDES[f"{wood}_trapdoor"] = f"minecraft:block/{wood}_trapdoor_bottom"
    FALLBACK_OVERRIDES[f"{wood}_sign"] = f"minecraft:item/{wood}_sign"

# Add colored beds and banners (special renderers)
COLORS = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink",
          "gray", "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"]

for color in COLORS:
    # Beds use special block entity model
    FALLBACK_OVERRIDES[f"{color}_bed"] = {
        "type": "minecraft:special",
        "base": "minecraft:item/template_bed",
        "model": {
            "type": "minecraft:bed",
            "texture": f"minecraft:{color}"
        }
    }

    # Banners use special block entity model
    FALLBACK_OVERRIDES[f"{color}_banner"] = {
        "type": "minecraft:special",
        "base": "minecraft:item/template_banner",
        "model": {
            "type": "minecraft:banner",
            "color": color
        }
    }

# Mob heads (special block entity renderers)
for mob in ["zombie", "creeper", "player", "dragon", "piglin"]:
    FALLBACK_OVERRIDES[f"{mob}_head"] = {
        "type": "minecraft:special",
        "base": "minecraft:item/template_skull",
        "model": {"type": "minecraft:head", "kind": mob}
    }

for mob in ["skeleton", "wither_skeleton"]:
    FALLBACK_OVERRIDES[f"{mob}_skull"] = {
    "type": "minecraft:special",
    "base": "minecraft:item/template_skull",
    "model": {"type": "minecraft:head", "kind": mob}
}

def process_cit_file(src_path, dest_items_path, generated_asset_root, generated_folder_name, block_names):
    src_path = Path(src_path)
    lower = src_path.suffix.lower()
    if lower == ".properties":
        props = parse_properties(str(src_path))
        # matchItems can be missing variants - check multiple keys
        match_items_value = props.get("matchItems") or props.get("match_items") or props.get("matchitems")
        if not match_items_value:
            log(f"No matchItems in {src_path}; skipping")
            return
        # process each token
        tokens = re.split(r'\s+', match_items_value.strip())
        # model field
        model_field = props.get("model") or props.get("Model") or props.get("model-file")
        if not model_field:
            log(f"No model= in {src_path}; skipping")
            return
        model_name = Path(model_field).stem  # e.g., apple_0
        prop_stem = src_path.stem
        case_when = transform_name_to_vanilla(prop_stem)
        for tok in tokens:
            if not tok:
                continue
            if ':' in tok:
                ns, item_name = tok.split(':', 1)
            else:
                ns, item_name = 'minecraft', tok
            # decide fallback block/item via block_names set
            if item_name in FALLBACK_OVERRIDES:
                fallback = FALLBACK_OVERRIDES[item_name]
            elif item_name in block_names:
                fallback = f"minecraft:block/{item_name}"
            else:
                fallback = f"minecraft:item/{item_name}"
            item_json_path = os.path.join(dest_items_path, f"{item_name}.json")
            case_model_path = f"{generated_folder_name}:item/{model_name}"
            merge_item_json(item_json_path, case_when, case_model_path, fallback)
            log(f"Added/updated case '{case_when}' -> {case_model_path} to {item_json_path}")

    elif lower == ".png":
        dest = os.path.join(generated_asset_root, "textures", "item", src_path.name)
        if os.path.exists(dest):
            log(f"Skipping existing texture {dest}")
        else:
            shutil.copy2(str(src_path), dest)
            log(f"Copied PNG {src_path} -> {dest}")

    elif lower == ".json":
        # when copying model JSONs, rewrite textures if necessary
        dest = os.path.join(generated_asset_root, "models", "item", src_path.name)
        if os.path.exists(dest):
            log(f"Skipping existing model {dest}")
        else:
            rewrite_model_textures_and_write(str(src_path), dest, generated_folder_name)
            log(f"Copied/rewrote model JSON {src_path} -> {dest}")
    else:
        log(f"Ignored CIT file type: {src_path}")

# ---------------------------
# Main pack processing (zip or folder)
# ---------------------------

def process_pack(input_path, generated_folder_name, block_names):
    input_path = Path(input_path)
    base_name = input_path.stem
    output_name = f"Patched {base_name}"
    temp_dir = None

    # If zip: extract to temp folder
    if zipfile.is_zipfile(input_path):
        temp_dir = tempfile.mkdtemp(prefix="cit_unpack_")
        with zipfile.ZipFile(input_path, "r") as z:
            z.extractall(temp_dir)
        src_root = Path(temp_dir)
    else:
        src_root = input_path

    dest_root = input_path.parent / output_name
    assets_dir = dest_root / "assets"
    items_dir = assets_dir / "minecraft" / "items"
    generated_asset_root = assets_dir / generated_folder_name

    ensure_dir(items_dir)
    ensure_dir(generated_asset_root / "models" / "item")
    ensure_dir(generated_asset_root / "textures" / "item")

    # Copy root-level non-assets files/dirs
    copy_root_files(str(src_root), str(dest_root))

    # Walk CIT source
    cit_dir = src_root / "assets" / "minecraft" / "optifine" / "cit"
    if not cit_dir.exists():
        log(f"No CIT folder found at {cit_dir}; nothing to do.")
        # cleanup if zip input
        if temp_dir:
            shutil.rmtree(temp_dir)
        return

    for root, _, files in os.walk(str(cit_dir)):
        for f in files:
            src = Path(root) / f
            process_cit_file(str(src), str(items_dir), str(generated_asset_root), generated_folder_name, block_names)

    # If input was zip: pack back to zip and cleanup extracted folder and temporary dest folder
    if temp_dir:
        output_zip = str(dest_root) + ".zip"
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(str(dest_root)):
                for f in files:
                    absf = os.path.join(root, f)
                    relf = os.path.relpath(absf, str(dest_root))
                    z.write(absf, relf)
        # cleanup
        shutil.rmtree(temp_dir)
        shutil.rmtree(str(dest_root))
        log(f"Created patched zip: {output_zip}")
        print(f"Patched pack created: {output_zip}")
    else:
        log(f"Created patched folder: {dest_root}")
        print(f"Patched pack created: {dest_root}")

# ---------------------------
# Entry point
# ---------------------------

GLOBAL_CONFIG = {"verbose": True}

def main():
    global GLOBAL_CONFIG
    cfg = load_config()
    DEFAULT = cfg['DEFAULT']
    generated_folder_name = DEFAULT.get("generated_folder_name", "generated-resources")
    verbose = DEFAULT.get("verbose", "true").lower() in ("1", "true", "yes")
    GLOBAL_CONFIG["verbose"] = verbose

    block_names = load_block_names()

    # Accept argument path or prompt
    if len(sys.argv) >= 2:
        input_path = sys.argv[1]
    else:
        input_path = input("Enter path to resource pack (.zip or folder): ").strip().strip('"')

    if not input_path:
        print("No path provided. Exiting.")
        return
    if not os.path.exists(input_path):
        print("Path does not exist:", input_path)
        return

    process_pack(input_path, generated_folder_name, block_names)

if __name__ == "__main__":
    main()
