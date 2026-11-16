from __future__ import annotations
import re
from pathlib import Path
from typing import Any

IMAGE_EXTENSIONS={".png",".jpg",".jpeg",".webp"}
PREVIEW_STEMS=("preview","thumbnail","thumb")
PREVIEW_PRIORITY={".webp":0,".png":1,".jpg":2,".jpeg":3}
MAP_ALIASES={
    "base_color_map": ("basecolor","base_color","albedo","diffuse","color","colour"),
    "normal_map": ("normalogl","normal_ogl","openglnormal","normalopengl","normal"),
    "roughness_map": ("roughness","rough"),
    "metallic_map": ("metallic","metalness","metal"),
    "ao_map": ("ambientocclusion","ambient_occlusion","occlusion","ao"),
}
IGNORED_HINTS=("height","displace","displacement","bump","specular","glossiness","gloss")
CATEGORY_HINTS={
    "bare_metal": ("metal","steel","iron","aluminium","aluminum","brass","copper","chrome","金属","钢","铁","铝","铜","黄铜","不锈钢"),
    "plastic": ("plastic","polymer","abs","pvc","nylon","塑料","塑胶","工程塑料","树脂","尼龙"),
    "leather": ("leather","hide","皮革","真皮","人造革","哑光"),
    "rubber": ("rubber","silicone","橡胶","硅胶"),
}
CATEGORY_DEFAULTS={
    "bare_metal":{"label":"金属","material":"bare_metal","metallic":1.0,"roughness":.28,"specular":.72,"clearcoat":.05,"clearcoat_roughness":.16,"texture_scale_mm":120.0,"texture_scale":1.0,"texture_rotation_deg":0.0,"normal_strength":1.0,"ao_strength":1.0},
    "plastic":{"label":"塑胶","material":"plastic","metallic":.0,"roughness":.48,"specular":.46,"clearcoat":.14,"clearcoat_roughness":.22,"texture_scale_mm":100.0,"texture_scale":1.0,"texture_rotation_deg":0.0,"normal_strength":.8,"ao_strength":1.0},
    "leather":{"label":"皮革 / 哑光","material":"matte","metallic":.0,"roughness":.72,"specular":.28,"clearcoat":.01,"clearcoat_roughness":.38,"texture_scale_mm":180.0,"texture_scale":1.0,"texture_rotation_deg":0.0,"normal_strength":1.25,"ao_strength":1.15},
    "rubber":{"label":"橡胶","material":"rubber","metallic":.0,"roughness":.82,"specular":.22,"clearcoat":.0,"clearcoat_roughness":.35,"texture_scale_mm":120.0,"texture_scale":1.0,"texture_rotation_deg":0.0,"normal_strength":.9,"ao_strength":1.0},
    "generic":{"label":"通用 / 未分类","material":"matte","metallic":.0,"roughness":.55,"specular":.42,"clearcoat":.04,"clearcoat_roughness":.25,"texture_scale_mm":120.0,"texture_scale":1.0,"texture_rotation_deg":0.0,"normal_strength":1.0,"ao_strength":1.0},
}

def is_preview_file(path:Path)->bool:
    return path.stem.lower() in PREVIEW_STEMS and path.suffix.lower() in IMAGE_EXTENSIONS

def _preview_for(files:list[Path])->Path|None:
    candidates=[p for p in files if is_preview_file(p)]
    return sorted(candidates,key=lambda p:(PREVIEW_PRIORITY.get(p.suffix.lower(),9),p.name.lower()))[0] if candidates else None

def _tokenize(name:str)->str:
    return re.sub(r"[^a-z0-9]+","",name.lower())

def _category(name:str)->str:
    # Keep Unicode folder names for Chinese material libraries. 0.2.7.x only
    # tokenized ASCII, so folders such as “皮革”/“塑料” silently fell through to
    # the generic painted-metal profile.
    raw=str(name or "").lower()
    token=_tokenize(raw)
    for category,hints in CATEGORY_HINTS.items():
        for hint in hints:
            h=str(hint).lower()
            if (any(ord(ch)>127 for ch in h) and h in raw) or (_tokenize(h) and _tokenize(h) in token):
                return category
    return "generic"

def _score_map(filename:str, aliases:tuple[str,...], field:str)->int:
    raw=Path(filename).stem.lower()
    compact=_tokenize(raw)
    words=[w for w in re.split(r"[^a-z0-9]+",raw) if w]
    score=-1
    for i,alias in enumerate(aliases):
        a=alias.lower()
        compact_alias=_tokenize(a)
        # Short generic aliases such as "metal", "ao" and "color" must be
        # semantic filename tokens, not substrings of a material name (Metal01).
        if compact_alias in {"metal","ao","color","rough","normal"}:
            hit=compact_alias in words or raw.endswith("_"+compact_alias) or raw.endswith("-"+compact_alias)
        else:
            hit=compact_alias in compact
        if hit: score=max(score,100-i)
    if field=="normal_map":
        if "normalogl" in compact or "openglnormal" in compact: score+=40
        if "normaldx" in compact or "directx" in compact: score-=80
    if any(_tokenize(x) in compact for x in IGNORED_HINTS) and score<0: return -1
    return score

def _set_name(root:Path, path:Path)->str:
    rel=path.parent.relative_to(root)
    return rel.as_posix() if rel.parts else Path(path.name).stem

def discover_material_presets(textures_root:Path)->list[dict[str,Any]]:
    textures_root.mkdir(parents=True,exist_ok=True)
    groups:dict[str,list[Path]]={}
    for path in sorted(textures_root.rglob("*")):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
            key=_set_name(textures_root,path)
            groups.setdefault(key,[]).append(path)
    presets=[]
    for folder,files in groups.items():
        preview=_preview_for(files)
        texture_files=[p for p in files if not is_preview_file(p)]
        maps={}
        for field,aliases in MAP_ALIASES.items():
            ranked=sorted(((_score_map(p.name,aliases,field),p) for p in texture_files),key=lambda x:(x[0],x[1].name.lower()),reverse=True)
            if ranked and ranked[0][0]>=0:
                maps[field]=ranked[0][1].relative_to(textures_root).as_posix()
        # A material set must have at least one meaningful PBR map.
        if not maps: continue
        # Category is inferred from the set/folder name, not map filenames; otherwise
        # a plastic set containing "*_metallic" would be misclassified as metal.
        category=_category(folder)
        defaults=dict(CATEGORY_DEFAULTS[category])
        present=[k for k,v in maps.items() if v]
        presets.append({
            "id":"auto:"+folder,
            "name":Path(folder).name,
            "folder":folder,
            "category":category,
            "category_label":defaults.pop("label"),
            "maps":maps,
            "preview":preview.relative_to(textures_root).as_posix() if preview else "",
            "recommended":defaults,
            "detected_maps":present,
            "file_count":len(files),
        })
    return presets
