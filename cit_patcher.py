import os
import json
import shutil
import tempfile
import zipfile
import configparser

def load_config():
    config = configparser.ConfigParser()
    config.read('config.ini')
    return config

def ensure_dir(path):
    os.makedirs(path, exist_ok=True)

def copy_root_files(src_root, dest_root):
    for item in os.listdir(src_root):
        src_item = os.path.join(src_root, item)
        dest_item = os.path.join(dest_root, item)
        if os.path.isfile(src_item) and item != "assets":
            shutil.copy2(src_item, dest_item)

def parse_properties(file_path):
    data = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data

def transform_name(base_name):
    parts = base_name.split("_")
    result_parts = []
    for i, part in enumerate(parts):
        if part.isdigit():
            result_parts.append(part)
        elif i > 0 and parts[i - 1].isdigit():
            result_parts.append(part)
        else:
            result_parts.append(part.capitalize())
    return "_".join(result_parts)

def load_block_names():
    block_file = "minecraft_blocks.txt"
    block_names = set()
    if os.path.exists(block_file):
        with open(block_file, "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name and not name.startswith("#"):
                    block_names.add(name)
        print(f"Loaded {len(block_names)} block names from {block_file}.")
    else:
        print(f"Warning: {block_file} not found. Defaulting to item models only.")
    return block_names

def merge_item_json(json_path, case_entry, fallback_model):
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            item_json = json.load(f)
    else:
        item_json = {
            "model": {
                "type": "minecraft:select",
                "property": "minecraft:component",
                "component": "minecraft:custom_name",
                "cases": [],
                "fallback": {
                    "type": "minecraft:model",
                    "model": fallback_model,
                    "tints": []
                }
            }
        }

    existing_cases = item_json["model"]["cases"]
    existing_names = [c["when"] for c in existing_cases]
    if case_entry["when"] not in existing_names:
        existing_cases.append(case_entry)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(item_json, f, indent=2)

def process_cit_file(file_path, dest_items_path, dest_generated_item_models, generated_folder_name, block_names):
    if file_path.endswith(".properties"):
        prop_data = parse_properties(file_path)
        match_item = prop_data.get("matchItems", "").replace("minecraft:", "").split()[0]
        model_ref = prop_data.get("model", "")
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        transformed_name = transform_name(base_name)

        # Determine if fallback is block or item
        if match_item in block_names:
            fallback_model = f"minecraft:block/{match_item}"
        else:
            fallback_model = f"minecraft:item/{match_item}"

        json_output_path = os.path.join(dest_items_path, f"{match_item}.json")
        case_entry = {
            "when": transformed_name,
            "model": {
                "type": "minecraft:model",
                "model": f"{generated_folder_name}:item/{os.path.splitext(model_ref)[0]}"
            }
        }
        merge_item_json(json_output_path, case_entry, fallback_model)

    elif file_path.endswith(".png"):
        shutil.copy2(file_path, os.path.join(dest_generated_item_models, "textures", "item", os.path.basename(file_path)))
    elif file_path.endswith(".json"):
        shutil.copy2(file_path, os.path.join(dest_generated_item_models, "models", "item", os.path.basename(file_path)))

def process_pack(input_path, generated_folder_name, block_names):
    base_name = os.path.basename(os.path.splitext(input_path)[0])
    output_name = f"Patched {base_name}"
    temp_dir = None

    if zipfile.is_zipfile(input_path):
        temp_dir = tempfile.mkdtemp(prefix="cit_unpack_")
        with zipfile.ZipFile(input_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)
        src_root = temp_dir
    else:
        src_root = input_path

    dest_root = os.path.join(os.path.dirname(input_path), output_name)
    assets_minecraft_path = os.path.join(dest_root, "assets", "minecraft")
    dest_items_path = os.path.join(assets_minecraft_path, "items")
    dest_generated_item_models = os.path.join(dest_root, "assets", generated_folder_name)

    ensure_dir(os.path.join(dest_generated_item_models, "models", "item"))
    ensure_dir(os.path.join(dest_generated_item_models, "textures", "item"))
    ensure_dir(dest_items_path)

    copy_root_files(src_root, dest_root)

    cit_path = os.path.join(src_root, "assets", "minecraft", "optifine", "cit")
    if not os.path.exists(cit_path):
        print(f"Warning: No CIT folder found at {cit_path}")
        return

    for root, _, files in os.walk(cit_path):
        for file in files:
            file_path = os.path.join(root, file)
            process_cit_file(file_path, dest_items_path, dest_generated_item_models, generated_folder_name, block_names)

    if temp_dir:
        output_zip_path = f"{dest_root}.zip"
        with zipfile.ZipFile(output_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(dest_root):
                for file in files:
                    abs_path = os.path.join(root, file)
                    rel_path = os.path.relpath(abs_path, dest_root)
                    zipf.write(abs_path, rel_path)
        shutil.rmtree(temp_dir)
        shutil.rmtree(dest_root)
        print(f"Patched pack created: {output_zip_path}")
    else:
        print(f"Patched pack created: {dest_root}")

def main():
    config = load_config()
    generated_folder_name = config["DEFAULT"].get("generated_folder_name", "generated-resources")
    block_names = load_block_names()

    input_path = input("Enter path to resource pack (.zip or folder): ").strip().strip('"')
    if not os.path.exists(input_path):
        print("Invalid path.")
        return

    process_pack(input_path, generated_folder_name, block_names)

if __name__ == "__main__":
    main()
