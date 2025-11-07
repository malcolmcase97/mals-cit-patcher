#!/usr/bin/env python3
import os
import sys
import json
import shutil
import re
from pathlib import Path

def load_config(script_dir):
    cfg_path = Path(script_dir) / "config.json"
    if not cfg_path.exists():
        default = {
            "prompt_for_generated_name": True,
            "generated_name_default": "generated-resources",
            "patched_prefix": "Patched ",
            "clean_mode": "B",
            "verbose": True
        }
        cfg_path.write_text(json.dumps(default, indent=2))
        return default
    return json.loads(cfg_path.read_text())

def log(msg):
    if config.get("verbose", True):
        print(msg)

def is_numeric_segment(s):
    return any(ch.isdigit() for ch in s)

def properties_when_name_from_filename(filename_no_ext):
    parts = filename_no_ext.split('_')
    idx = None
    for i, p in enumerate(parts):
        if is_numeric_segment(p):
            idx = i
            break
    if idx is None:
        return ' '.join([p.capitalize() for p in parts if p != ''])
    else:
        head_parts = parts[:idx]
        tail_parts = parts[idx:]
        head = ' '.join([p.capitalize() for p in head_parts if p != ''])
        tail = '_'.join(tail_parts)
        return f"{head}_{tail}" if head else tail

def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def parse_properties_file(path):
    data = {}
    for raw in Path(path).read_text(encoding='utf-8', errors='ignore').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or line.startswith('!'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            data[k.strip()] = v.strip()
    return data

def safe_load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception:
        return None

def write_json_pretty(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False))

def add_case_to_item_json(item_json_path, case_when, case_model_path, fallback_model):
    base_obj = safe_load_json(item_json_path)
    if base_obj and isinstance(base_obj, dict):
        try:
            model_block = base_obj.setdefault("model", {})
            model_block.setdefault("type", "minecraft:select")
            model_block.setdefault("property", "minecraft:component")
            model_block.setdefault("component", "minecraft:custom_name")
            cases = model_block.setdefault("cases", [])
            if any(c.get("when") == case_when for c in cases):
                log(f"Case '{case_when}' already exists in {item_json_path}; skipping append.")
            else:
                cases.append({
                    "when": case_when,
                    "model": {
                        "type": "minecraft:model",
                        "model": case_model_path
                    }
                })
            model_block.setdefault("fallback", {
                "type": "minecraft:model",
                "model": fallback_model,
                "tints": []
            })
            write_json_pretty(item_json_path, base_obj)
            return
        except Exception as e:
            log(f"Warning: couldn't merge into existing {item_json_path}: {e}")
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
            "fallback": {
                "type": "minecraft:model",
                "model": fallback_model,
                "tints": []
            }
        }
    }
    write_json_pretty(item_json_path, new_obj)

if __name__ == "__main__":
    script_dir = Path(__file__).parent
    config = load_config(script_dir)

    if len(sys.argv) < 2:
        print("Usage: python cit_patcher.py /path/to/original_pack")
        sys.exit(1)

    original_pack_path = Path(sys.argv[1]).resolve()
    if not original_pack_path.exists() or not original_pack_path.is_dir():
        print(f"Original pack path not found or not a directory: {original_pack_path}")
        sys.exit(1)

    generated_name = config.get("generated_name_default", "generated-resources")
    if config.get("prompt_for_generated_name", True):
        ans = input(f"Enter name for the generated resources folder (default: {generated_name}): ").strip()
        if ans:
            generated_name = ans

    patched_prefix = config.get("patched_prefix", "Patched ")
    patched_pack_name = f"{patched_prefix}{original_pack_path.name}"
    patched_pack_path = original_pack_path.parent / patched_pack_name

    log(f"Original pack: {original_pack_path}")
    log(f"Patched pack:  {patched_pack_path}")
    log(f"Generated resources folder: {generated_name}")

    ensure_dir(patched_pack_path)

    for item in original_pack_path.iterdir():
        if item.name.lower() == "assets":
            continue
        dest = patched_pack_path / item.name
        if item.is_dir():
            if dest.exists():
                log(f"Skipping existing directory {dest}")
            else:
                try:
                    shutil.copytree(item, dest)
                    log(f"Copied directory {item.name} -> {dest}")
                except Exception as e:
                    log(f"Could not copy directory {item}: {e}")
        else:
            if dest.exists():
                log(f"Skipping existing file {dest}")
            else:
                shutil.copy2(item, dest)
                log(f"Copied file {item.name} -> {dest}")

    assets_dir = patched_pack_path / "assets"
    ensure_dir(assets_dir)
    items_dir = assets_dir / "minecraft" / "items"
    ensure_dir(items_dir)
    generated_models_item_dir = assets_dir / generated_name / "models" / "item"
    generated_textures_item_dir = assets_dir / generated_name / "textures" / "item"
    ensure_dir(generated_models_item_dir)
    ensure_dir(generated_textures_item_dir)

    source_cit_dir = original_pack_path / "assets" / "minecraft" / "optifine" / "cit"
    if not source_cit_dir.exists():
        log(f"No CIT folder found at {source_cit_dir}.")
        sys.exit(0)

    for root, dirs, files in os.walk(source_cit_dir):
        root_path = Path(root)
        for fname in files:
            src_path = root_path / fname
            lower = fname.lower()
            if lower.endswith('.png'):
                dest = generated_textures_item_dir / fname
                if dest.exists():
                    log(f"Skipping existing texture {dest.name}")
                else:
                    shutil.copy2(src_path, dest)
                    log(f"Copied PNG: {src_path} -> {dest}")
            elif lower.endswith('.json'):
                dest = generated_models_item_dir / fname
                if dest.exists():
                    log(f"Skipping existing model json {dest.name}")
                else:
                    shutil.copy2(src_path, dest)
                    log(f"Copied JSON model: {src_path} -> {dest}")
            elif lower.endswith('.properties'):
                props = parse_properties_file(src_path)
                model_field = props.get("model") or props.get("Model") or props.get("model-file")
                if not model_field:
                    log(f"No 'model' entry found in {src_path}; skipping.")
                    continue
                model_name = Path(model_field).stem
                prop_stem = Path(src_path).stem
                case_when = properties_when_name_from_filename(prop_stem)

                match_items_value = props.get("matchItems") or props.get("match_items") or props.get("matchitems")
                if not match_items_value:
                    log(f"No 'matchItems' in {src_path}; skipping.")
                    continue

                tokens = re.split(r'\s+', match_items_value.strip())
                for tok in tokens:
                    if not tok:
                        continue
                    if ':' in tok:
                        namespace, item_name = tok.split(':', 1)
                    else:
                        namespace, item_name = 'minecraft', tok
                    item_json_filename = f"{item_name}.json"
                    item_json_path = items_dir / item_json_filename
                    case_model_path = f"{generated_name}:item/{model_name}"
                    fallback_model = f"{namespace}:item/{item_name}"
                    add_case_to_item_json(item_json_path, case_when, case_model_path, fallback_model)
                    log(f"Updated item JSON for {item_name} with case '{case_when}' -> model {case_model_path}")
            else:
                log(f"Ignored file type: {src_path}")

    log("Done. Patched pack created/updated at: " + str(patched_pack_path))
