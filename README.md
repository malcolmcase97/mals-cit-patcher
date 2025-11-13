# Mal's CIT Resource Pack Patcher

A Python script to patch **Custom Item Textures (CIT)** in Minecraft resource packs for compatibility with Minecraft 1.21.5+.

Should be used on CIT resource packs that require Optifine on older Minecraft versions.

Requires *no* mods to use! All patched resource packs should be vanilla friendly!

It merges item models, rewrites textures, and handles special fallbacks automatically.

## Usage

1. **Open a terminal** in the folder containing `cit_patcher.py`.
2. Run the script:

```bash
python cit_patcher.py
```

3. The script will prompt you to enter the path to the resource pack (folder or .zip file).
4. The script will then ask for a custom generated asset folder name.
5. Patched pack is outputted as "Patched <original_pack_name>" (folder or zip).

## Configuration

Some settings can be modified within the config.ini file, described as follows:

+ generated_folder_name – Folder name for generated models and textures. This shouldn't be important but should probably be unique between packs.
+ patched_prefix – Prefix for output pack. For example: "Patched Mizuno's CIT Pack". This is unimportant, just here for preference.
+ verbose – Show log messages. True by default.
+ prompt_for_generated_name – Prompts user for folder name if true.

## TODO

+ This patcher is a work in progress and has only been tested to work with Mizuno's CIT Pack! If you find any issues with this pack, or any other CIT packs, please open an issue or contact me at [malcolm.case.97@gmail.com](mailto:malcolm.case.97@gmail.com).
+ Add compatibility with [Fast Item Frames](https://modrinth.com/mod/fast-item-frames), my preferred item invisible item frame mod. Currently, CIT models will clip into other blocks due to Fast Item Frame's imposed offset when hiding item frames.
+ Shield CIT models seem to have incorrect rotation, unlike all other models. They can simply be rotated to correct position, so I've ignored this for now.
+ Improve user experience by adding a simple GUI to the patcher.
+ Emissive textures don't work, will look into adding compatibility later on.

## Special Thanks

Thank you very much to [coolbot100s](https://modrinth.com/user/coolbot100s) and mars from the Garden Gals discord for helping me with this script! ❤️