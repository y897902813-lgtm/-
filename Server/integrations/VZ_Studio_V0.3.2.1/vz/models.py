from __future__ import annotations
import re
import math
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import uuid4

ID_RE=re.compile(r"^[A-Za-z0-9_-]+$")
MESH_EXTENSIONS={".stl",".obj"}
RENDER_MATERIALS={"painted_metal","bare_metal","plastic","rubber","glass","matte"}
NORMAL_MODES={"crease","smooth","flat"}
RENDER_IMAGE_EXTENSIONS={".png",".jpg",".jpeg",".webp"}
SCENE_PRESETS={"classic","bright_studio","automotive_interior"}
RENDER_MAP_FIELDS=("base_color_map","normal_map","roughness_map","metallic_map","ao_map")

def default_render_config()->dict[str,Any]:
    return {
        "material_preset_id":"",
        "normal_mode":"crease",
        "crease_angle_deg":35.0,
        "material":"painted_metal",
        "metallic":0.15,
        "roughness":0.38,
        "specular":0.55,
        "clearcoat":0.18,
        "clearcoat_roughness":0.12,
        "environment_strength":1.0,
        "base_color_map":"",
        "normal_map":"",
        "roughness_map":"",
        "metallic_map":"",
        "ao_map":"",
        "texture_scale_mm":120.0,
        "texture_scale":1.0,
        "texture_rotation_deg":0.0,
        "normal_strength":1.0,
        "ao_strength":1.0,
    }

def default_render_scene()->dict[str,Any]:
    return {
        # Scene space and lighting preset. New projects default to a brighter
        # studio scene, while older persisted values remain backward-compatible
        # through normalize_render_scene.
        "scene_preset":"bright_studio",
        # Fast HTML rendering profile.
        "fast_environment_map":"",
        "fast_fps":10,
        "fast_max_faces_per_mesh":120000,
        # High-quality HTML rendering profile. Existing scene keys stay at the
        # top level for backward compatibility with 0.2.13.1 model files.
        "environment_map":"",
        "perfect_fps":10,
        "perfect_max_faces_per_mesh":120000,
        "environment_intensity":1.28,
        "environment_rotation_deg":0.0,
        "exposure":1.16,
        "shadow_strength":0.72,
        "shadow_softness":1.5,
        "directional_light_intensity":1.55,
        "directional_light_yaw_deg":-52.0,
        "directional_light_pitch_deg":54.0,
    }

def _render_resource(value:Any,name:str)->str:
    raw=str(value or "").replace("\\","/").strip()
    if not raw:return ""
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/",raw):raise ValueError(f"{name}必须使用后台渲染素材库中的相对路径")
    parts=[part for part in raw.split("/") if part not in {"","."}]
    if not parts or any(part==".." for part in parts):raise ValueError(f"{name}路径非法")
    normalized="/".join(parts)
    if Path(normalized).suffix.lower() not in RENDER_IMAGE_EXTENSIONS:raise ValueError(f"{name}仅支持 PNG/JPG/JPEG/WebP")
    return normalized[:512]

def normalize_render_scene(value:Any)->dict[str,Any]:
    src=value if isinstance(value,dict) else {}
    cfg={**default_render_scene(),**src}
    cfg["scene_preset"]=str(cfg.get("scene_preset","classic") or "classic")
    if cfg["scene_preset"] not in SCENE_PRESETS:raise ValueError("场景预设必须是 classic、bright_studio 或 automotive_interior")
    cfg["fast_environment_map"]=_render_resource(cfg.get("fast_environment_map","") ,"快速渲染环境图")
    cfg["environment_map"]=_render_resource(cfg.get("environment_map","") ,"高质量渲染环境图")
    cfg["fast_fps"]=int(round(number(cfg.get("fast_fps",10),"快速渲染帧率",1)))
    if cfg["fast_fps"]>120:raise ValueError("快速渲染帧率不得大于 120 FPS")
    cfg["fast_max_faces_per_mesh"]=int(round(number(cfg.get("fast_max_faces_per_mesh",120000),"快速渲染单网格最大面数",1000)))
    if cfg["fast_max_faces_per_mesh"]>2_500_000:raise ValueError("快速渲染单网格最大面数不得大于 2500000")
    cfg["perfect_fps"]=int(round(number(cfg.get("perfect_fps",10),"高质量渲染帧率",1)))
    if cfg["perfect_fps"]>120:raise ValueError("高质量渲染帧率不得大于 120 FPS")
    cfg["perfect_max_faces_per_mesh"]=int(round(number(cfg.get("perfect_max_faces_per_mesh",120000),"高质量渲染单网格最大面数",1000)))
    if cfg["perfect_max_faces_per_mesh"]>2_500_000:raise ValueError("高质量渲染单网格最大面数不得大于 2500000")
    cfg["environment_intensity"]=number(cfg.get("environment_intensity",1),"环境反射强度",0)
    if cfg["environment_intensity"]>4:raise ValueError("环境反射强度不得大于 4")
    cfg["environment_rotation_deg"]=number(cfg.get("environment_rotation_deg",0),"环境旋转角")
    cfg["exposure"]=number(cfg.get("exposure",1),"曝光",0.05)
    if cfg["exposure"]>8:raise ValueError("曝光不得大于 8")
    cfg["shadow_strength"]=number(cfg.get("shadow_strength",.82),"阴影强度",0)
    if cfg["shadow_strength"]>1:raise ValueError("阴影强度不得大于 1")
    cfg["shadow_softness"]=number(cfg.get("shadow_softness",1),"阴影柔化",0)
    if cfg["shadow_softness"]>4:raise ValueError("阴影柔化不得大于 4")
    cfg["directional_light_intensity"]=number(cfg.get("directional_light_intensity",1.55),"平行光强度",0)
    if cfg["directional_light_intensity"]>4:raise ValueError("平行光强度不得大于 4")
    cfg["directional_light_yaw_deg"]=number(cfg.get("directional_light_yaw_deg",-52),"平行光水平角")
    cfg["directional_light_pitch_deg"]=number(cfg.get("directional_light_pitch_deg",54),"平行光俯仰角",-89)
    if cfg["directional_light_pitch_deg"]>89:raise ValueError("平行光俯仰角不得大于 89°")
    return cfg

def normalize_render_config(value:Any)->dict[str,Any]:
    src=value if isinstance(value,dict) else {}
    cfg={**default_render_config(),**src}
    cfg["material_preset_id"]=str(cfg.get("material_preset_id","") or "")[:512]
    cfg["normal_mode"]=str(cfg.get("normal_mode","crease"))
    if cfg["normal_mode"] not in NORMAL_MODES:raise ValueError("法线模式必须是 crease、smooth 或 flat")
    cfg["crease_angle_deg"]=number(cfg.get("crease_angle_deg",35),"硬边夹角",0)
    if cfg["crease_angle_deg"]>180:raise ValueError("硬边夹角不得大于 180°")
    cfg["material"]=str(cfg.get("material","painted_metal"))
    if cfg["material"] not in RENDER_MATERIALS:raise ValueError("渲染材质预设无效")
    for key,label in (("metallic","金属度"),("roughness","粗糙度"),("specular","高光强度"),("clearcoat","清漆层"),("clearcoat_roughness","清漆粗糙度"),("normal_strength","法线强度"),("ao_strength","AO 强度")):
        cfg[key]=number(cfg.get(key,default_render_config()[key]),label,0)
        if key not in {"normal_strength","ao_strength"} and cfg[key]>1:raise ValueError(f"{label}不得大于 1")
        if key in {"normal_strength","ao_strength"} and cfg[key]>4:raise ValueError(f"{label}不得大于 4")
    cfg["environment_strength"]=number(cfg.get("environment_strength",1),"环境光强度",0)
    if cfg["environment_strength"]>4:raise ValueError("环境光强度不得大于 4")
    cfg["texture_scale_mm"]=number(cfg.get("texture_scale_mm",120),"贴图物理尺寸",0.1)
    if cfg["texture_scale_mm"]>100000:raise ValueError("贴图物理尺寸过大")
    cfg["texture_scale"]=number(cfg.get("texture_scale",1),"纹理缩放",0.1)
    if cfg["texture_scale"]>20:raise ValueError("纹理缩放不得大于 20")
    cfg["texture_rotation_deg"]=number(cfg.get("texture_rotation_deg",0),"纹理旋转")%360.0
    for key in RENDER_MAP_FIELDS:cfg[key]=_render_resource(cfg.get(key,""),key)
    return cfg
def new_id(prefix:str)->str:return f"{prefix}_{uuid4().hex[:10]}"
def text(value:Any,name:str,maximum:int=160)->str:
    result=str(value or "").strip()
    if not result:raise ValueError(f"{name}不能为空")
    if len(result)>maximum:raise ValueError(f"{name}最长 {maximum} 个字符")
    return result
def number(value:Any,name:str,minimum:float|None=None)->float:
    try:result=float(value)
    except (TypeError,ValueError) as exc:raise ValueError(f"{name}必须是数字或可求值表达式") from exc
    if minimum is not None and result<minimum:raise ValueError(f"{name}不得小于 {minimum}")
    return result
def vector(value:Any,name:str)->list[float]:
    if isinstance(value,dict):
        lowered={str(k).lower():v for k,v in value.items()}
        if all(k in lowered for k in ("x","y","z")):value=[lowered["x"],lowered["y"],lowered["z"]]
        else:
            nested=next((value.get(k) for k in ("point","value","values","xyz") if k in value),None)
            if nested is not None:value=nested
            elif len(value)==3:value=list(value.values())
    if isinstance(value,tuple):value=list(value)
    if isinstance(value,str):
        raw=value.strip();raw=re.sub(r"(?i)^\s*(?:point|vector3?|vec3|xyz)\s*", "", raw).strip();raw=raw.strip("()[]{}（）【】 ")
        parts=[x for x in re.split(r"[,，;；\s]+",raw) if x]
        numeric_parts=len(parts)==3
        if numeric_parts:
            try:[float(x) for x in parts]
            except (TypeError,ValueError):numeric_parts=False
        if not numeric_parts:
            labels=dict(re.findall(r"(?i)\b([xyz])\s*[:=]\s*([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)",raw))
            if all(k in labels for k in ("x","y","z")):parts=[labels["x"],labels["y"],labels["z"]]
        value=parts
    if not isinstance(value,list) or len(value)!=3:raise ValueError(f"{name}必须包含三个数字")
    return [number(x,name) for x in value]
def optional_vector(value:Any,name:str)->list[float]|None:
    if value is None:return None
    if isinstance(value,str) and not value.strip():return None
    if isinstance(value,(list,tuple)) and len(value)==0:return None
    result=vector(value,name)
    if any(not math.isfinite(x) for x in result):raise ValueError(f"{name}必须是有限数字")
    return result

def normalize_scene_coordinates(value:Any)->dict[str,Any]:
    src=value if isinstance(value,dict) else {}
    return {
        "hard_point_mm":optional_vector(src.get("hard_point_mm"),"硬点坐标"),
        "h_point_mm":optional_vector(src.get("h_point_mm"),"H 点坐标"),
    }

def ident(item:dict[str,Any],prefix:str)->str:
    value=str(item.get("id") or new_id(prefix))
    if not ID_RE.fullmatch(value):raise ValueError(f"{prefix} ID 非法")
    item["id"]=value;return value
def unique(items:list[dict[str,Any]],label:str,prefix:str)->set[str]:
    ids=[ident(x,prefix) for x in items]
    if len(ids)!=len(set(ids)):raise ValueError(f"{label} ID 不得重复")
    return set(ids)

def make_demo_model()->dict[str,Any]:
    base,arm,joint=new_id("layer"),new_id("layer"),new_id("joint")
    return {"id":"demo_arm","name":"演示旋转机构","description":"VZ MuJoCo 运动学演示","revision":1,
      "assets":[],"variables":{"cycle_scale":1},"simulation":{"start_time":0,"end_time":6,"timestep":.01},
      "layers":[
        {"id":base,"name":"固定底座","parent_id":"root","active":True,"color":"0.56 0.65 0.74 1","position_mm":[0,0,0],"meshes":[],"joints":[]},
        {"id":arm,"name":"旋转臂","parent_id":base,"active":True,"color":"0.18 0.48 0.90 1","position_mm":[0,0,45],"meshes":[],"joints":[{"id":joint,"name":"主旋转副","type":"rotation","point":"0, 0, 0","axis":"0, 0, 1","reverse":False,"limited":True,"range":[-90,90]}]},
      ],
      "kinematic_closures":[],
      "activity_parts":[{"id":"part_demo","name":"旋转臂","enabled":True,"motions":[{"id":"motion_forward","name":"展开","joint_id":joint,"position_0_percent":-90,"position_100_percent":90,"mode":"ease","rated_speed":60,"enabled":True}]}],
      "drives":[{"id":"drive_demo","name":"主电机","joint_id":joint,"enabled":True,"rated_speed":60,"reverse_limit":-90,"forward_limit":90,"zero_at":"reverse","segments":[
        {"id":"seg_forward","name":"seg1","start_mode":"direct","start":0,"reference":"","reference_boundary":"end","mode":"duration","duration":2,"speed":60,"travel":90,"profile":"s_curve","ease_in":True,"ease_out":True,"easing_mode":"time","ease_in_time":.2,"ease_out_time":.2,"points":[]},
        {"id":"seg_return","name":"seg2","start_mode":"direct","start":3,"reference":"","reference_boundary":"end","mode":"duration","duration":2,"speed":60,"travel":-90,"profile":"s_curve","ease_in":True,"ease_out":True,"easing_mode":"time","ease_in_time":.2,"ease_out_time":.2,"points":[]},
      ]}],
      "presets":[],"memories":[]}

def _normalize_legacy(model:dict[str,Any])->None:
    layers=model.setdefault("layers",[]);top=model.pop("joints",[])
    for layer in layers:
        layer.setdefault("joints",[])
        if not layer["joints"]:
            layer["joints"]=[{**j,"point":", ".join(map(str,j.get("point_mm",[0,0,0]))),"axis":", ".join(map(str,j.get("axis",[0,0,1])))} for j in top if j.get("child_layer_id")==layer.get("id")]
        layer.setdefault("meshes",[])
        if not layer["meshes"] and layer.get("asset_id"):
            asset=next((x for x in model.get("assets",[]) if x.get("id")==layer["asset_id"]),None)
            if asset:layer["meshes"]=[{"id":new_id("mesh"),"filename":asset["name"],"asset_id":asset["id"],"rgba":"","opacity":1,"collision":False}]
    closures=model.pop("closures",[])
    model.setdefault("kinematic_closures",[])
    if closures and not model["kinematic_closures"]:
        model["kinematic_closures"]=[{**c,"endpoint_a":{"layer_id":c.get("layer_a_id"),"point_mm":c.get("point_a_mm",[0,0,0])},"endpoint_b":{"layer_id":c.get("layer_b_id"),"point_mm":c.get("point_b_mm",[0,0,0])}} for c in closures]
    for drive in model.setdefault("drives",[]):
        if "segments" not in drive:
            drive["segments"]=[{"id":new_id("seg"),"name":a.get("name",f"seg{i+1}"),"start_mode":"direct","start":i,"reference":"","reference_boundary":"end","mode":"duration","duration":1,"speed":drive.get("rated_speed",30),"travel":a.get("target",0),"profile":"s_curve","ease_in":True,"ease_out":True,"easing_mode":"time","ease_in_time":.2,"ease_out_time":.2,"points":[]} for i,a in enumerate(drive.get("actions",[]))]
    if "activity_parts" not in model:
        model["activity_parts"]=[{"id":new_id("part"),"name":drive.get("name",f"活动部位{i+1}"),"enabled":drive.get("enabled",True),"motions":[{"id":seg.get("id") or new_id("motion"),"name":seg.get("name",f"动作{j+1}"),"joint_id":drive.get("joint_id",""),"position_0_percent":drive.get("initial_position",drive.get("reverse_limit",0)),"position_100_percent":float(drive.get("initial_position",drive.get("reverse_limit",0)))+float(seg.get("travel",0)),"mode":"mapping" if seg.get("profile")=="mapping" else "ease","rated_speed":seg.get("speed",drive.get("rated_speed",30)),"enabled":True} for j,seg in enumerate(drive.get("segments",[]))]} for i,drive in enumerate(model["drives"])]

def _activity_drives(parts:list[dict[str,Any]])->list[dict[str,Any]]:
    grouped:dict[str,dict[str,Any]]={}
    order:list[str]=[]
    for part in parts:
        for motion in part["motions"]:
            p0=float(motion["position_0_percent"]);p100=float(motion["position_100_percent"]);lo=min(p0,p100);hi=max(p0,p100)
            if hi==lo:hi=lo+1e-6
            exchange_id=str(motion.get("exchange_drive_id") or "").strip()
            key=exchange_id or f"drive_{motion['id']}"
            if key not in grouped:
                base=deepcopy(motion.get("exchange_drive_extra")) if isinstance(motion.get("exchange_drive_extra"),dict) else {}
                base.pop("segments",None);base.pop("exchange_extra",None)
                base.update({"id":key,"activity_part_id":part["id"],"motion_id":motion["id"],"name":str(motion.get("exchange_drive_name") or f"{part['name']} / {motion['name']}"),"joint_id":motion["joint_id"],"role":str(motion.get("exchange_drive_role") or ""),"enabled":part["enabled"] and motion["enabled"],"rated_speed":motion["rated_speed"],"reverse_limit":lo,"forward_limit":hi,"zero_at":"reverse" if p0<=p100 else "forward","initial_position":p0,"position_0_percent":p0,"position_100_percent":p100,"actions":[],"segments":[],"exchange_extra":deepcopy(motion.get("exchange_drive_extra")) if isinstance(motion.get("exchange_drive_extra"),dict) else {}})
                grouped[key]=base
                order.append(key)
            drive=grouped[key]
            drive["enabled"]=bool(drive["enabled"] and part["enabled"] and motion["enabled"])
            drive["reverse_limit"]=min(float(drive["reverse_limit"]),lo)
            drive["forward_limit"]=max(float(drive["forward_limit"]),hi)
            drive["rated_speed"]=max(float(drive["rated_speed"]),float(motion["rated_speed"]))
            drive["actions"].append({"id":motion["id"],"name":motion["name"],"target":p100})
            preserved=motion.get("exchange_segment") if isinstance(motion.get("exchange_segment"),dict) else None
            snapshot=motion.get("exchange_motion_snapshot") if isinstance(motion.get("exchange_motion_snapshot"),dict) else None
            current_core={"name":motion["name"],"joint_id":motion["joint_id"],"position_0_percent":p0,"position_100_percent":p100,"mode":motion["mode"],"rated_speed":float(motion["rated_speed"]),"enabled":bool(motion["enabled"])}
            snapshot_matches=bool(snapshot) and all(snapshot.get(k)==v or (k in {"position_0_percent","position_100_percent","rated_speed"} and abs(float(snapshot.get(k,0))-float(v))<1e-12) for k,v in current_core.items())
            rebuilt={"id":motion["id"],"name":motion["name"],"start_mode":"direct","start":0,"reference":"","reference_boundary":"end","mode":"speed","duration":max(abs(p100-p0)/max(float(motion["rated_speed"]),1e-6),0.001),"speed":motion["rated_speed"],"travel":p100-p0,"profile":"mapping" if motion["mode"]=="mapping" else "s_curve","ease_in":motion["mode"]!="mapping","ease_out":motion["mode"]!="mapping","easing_mode":"time","ease_in_time":.2,"ease_out_time":.2,"points":[]}
            if preserved:
                segment=deepcopy(preserved)
                if not snapshot_matches:segment.update(rebuilt)
                segment["id"]=str(segment.get("id") or motion["id"])
                segment["name"]=str(segment.get("name") or motion["name"])
            else:
                segment=rebuilt
            drive["segments"].append(segment)
    return [grouped[key] for key in order]

def validate_model(payload:Any,expected_id:str|None=None,*,deduplicate_layer_assets:bool=False)->dict[str,Any]:
    if not isinstance(payload,dict):raise ValueError("模型必须是 JSON 对象")
    model=deepcopy(payload);_normalize_legacy(model)
    model_id=text(model.get("id"),"模型 ID",80)
    if not ID_RE.fullmatch(model_id):raise ValueError("模型 ID 仅允许字母、数字、下划线和连字符")
    if expected_id and model_id!=expected_id:raise ValueError("模型 ID 不允许修改")
    model["id"]=model_id;model["name"]=text(model.get("name"),"模型名称");model["description"]=str(model.get("description",""))[:1000];model["revision"]=max(1,int(model.get("revision",1)))
    model["render_scene"]=normalize_render_scene(model.get("render_scene"))
    model["scene_coordinates"]=normalize_scene_coordinates(model.get("scene_coordinates"))
    assets=model.setdefault("assets",[]);layers=model.setdefault("layers",[]);drives=model.setdefault("drives",[]);closures=model.setdefault("kinematic_closures",[])
    for value,label in ((assets,"数模"),(layers,"层级"),(drives,"驱动"),(closures,"闭链")):
        if not isinstance(value,list):raise ValueError(f"{label}必须是列表")
    asset_ids=unique(assets,"数模","asset");layer_ids=unique(layers,"层级","layer");unique(closures,"闭链","closure")
    for asset in assets:
        asset["name"]=text(asset.get("name"),"数模名称");asset["stored_name"]=Path(str(asset.get("stored_name",""))).name
        if Path(asset["name"]).suffix.lower() not in MESH_EXTENSIONS:raise ValueError("仅支持 STL/OBJ 数模")
        asset["render_config"]=normalize_render_config(asset.get("render_config"))
    joint_ids:set[str]=set()
    for layer in layers:
        layer["name"]=text(layer.get("name"),"层级名称");layer["parent_id"]=str(layer.get("parent_id","root"));layer["active"]=bool(layer.get("active",True));layer["color"]=str(layer.get("color","0.72 0.75 0.80 1"));layer["position_mm"]=vector(layer.get("position_mm",[0,0,0]),"层级位置")
        if layer["parent_id"]!="root" and layer["parent_id"] not in layer_ids:raise ValueError(f"层级“{layer['name']}”父级不存在")
        meshes=layer.setdefault("meshes",[]);joints=layer.setdefault("joints",[])
        unique(meshes,"数模引用","mesh");ids=unique(joints,"运动副","joint")
        if joint_ids&ids:raise ValueError("运动副 ID 不得重复")
        joint_ids|=ids
        seen_layer_assets:set[str]=set();normalized_meshes=[]
        for mesh in meshes:
            aid=str(mesh.get("asset_id","")).strip()
            if aid and aid in seen_layer_assets:
                if deduplicate_layer_assets:continue
                asset=next((x for x in assets if x["id"]==aid),None)
                asset_name=(asset or {}).get("source_path") or (asset or {}).get("name") or aid
                raise ValueError(f"层级“{layer['name']}”不能重复添加同一个数模“{asset_name}”")
            if aid:seen_layer_assets.add(aid)
            normalized_meshes.append(mesh)
        if len(normalized_meshes)!=len(meshes):
            layer["meshes"]=meshes=normalized_meshes
        for mesh in meshes:
            aid=str(mesh.get("asset_id",""))
            if aid and aid not in asset_ids:raise ValueError(f"层级“{layer['name']}”引用的数模不存在")
            asset=next((x for x in assets if x["id"]==aid),None);mesh["filename"]=asset["name"] if asset else str(mesh.get("filename",""));mesh["rgba"]=str(mesh.get("rgba",""));mesh["opacity"]=number(mesh.get("opacity",1),"透明度",0)
            if mesh["opacity"]>1:raise ValueError("透明度不得大于 1")
            mesh["collision"]=bool(mesh.get("collision",False))
            if "render_config" in mesh:
                mesh["render_config"]=normalize_render_config(mesh.get("render_config"))
            if "material_slots" in mesh:
                slots=mesh.get("material_slots")
                if not isinstance(slots,dict):raise ValueError("Material Slot 配置必须是对象")
                normalized_slots={}
                for slot_name,slot_config in slots.items():
                    name=str(slot_name or "").strip()[:80]
                    if not name:raise ValueError("Material Slot 名称不能为空")
                    normalized_slots[name]=normalize_render_config(slot_config)
                mesh["material_slots"]=normalized_slots
        for joint in joints:
            joint["name"]=text(joint.get("name"),"运动副名称");joint["type"]=str(joint.get("type","rotation"))
            if joint["type"] not in {"rotation","translation","crank"}:raise ValueError("运动副类型无效")
            joint["axis"]=", ".join(map(str,vector(joint.get("axis","1, 0, 0" if joint["type"]=="translation" else "0, 1, 0"),"轴矢量")));joint["point"]=", ".join(map(str,vector(joint.get("point","0, 0, 0"),"世界坐标点")))
            joint["reverse"]=bool(joint.get("reverse",False));joint["limited"]=bool(joint.get("limited",False));rng=joint.get("range",[-180,180])
            if not isinstance(rng,list) or len(rng)!=2:raise ValueError("运动副范围必须包含两个值")
            joint["range"]=[number(rng[0],"范围下限"),number(rng[1],"范围上限")]
            if joint["limited"] and joint["range"][0]>=joint["range"][1]:raise ValueError(f"运动副“{joint['name']}”范围下限必须小于上限")
    parents={x["id"]:x["parent_id"] for x in layers}
    for lid in layer_ids:
        seen=set();cur=lid
        while cur!="root":
            if cur in seen:raise ValueError("层级关系存在循环")
            seen.add(cur);cur=parents.get(cur,"root")
    variables=model.setdefault("variables",{})
    if not isinstance(variables,dict):raise ValueError("自定义变量必须是对象")
    simulation=model.setdefault("simulation",{});simulation["start_time"]=number(simulation.get("start_time",0),"仿真开始");simulation["end_time"]=number(simulation.get("end_time",6),"仿真结束");simulation["timestep"]=number(simulation.get("timestep",.01),"仿真步长",.000001)
    if simulation["end_time"]<=simulation["start_time"]:raise ValueError("仿真结束时间必须晚于开始时间")
    parts=model.setdefault("activity_parts",[])
    if not isinstance(parts,list):raise ValueError("活动部位必须是列表")
    unique(parts,"活动部位","part");motion_ids:set[str]=set()
    for pi,part in enumerate(parts):
        part["name"]=text(part.get("name"),"活动部位名称");part["enabled"]=bool(part.get("enabled",True));motions=part.setdefault("motions",[])
        if not isinstance(motions,list):raise ValueError(f"活动部位“{part['name']}”的动作必须是列表")
        ids=unique(motions,"动作","motion")
        if motion_ids&ids:raise ValueError("动作 ID 不得重复")
        motion_ids|=ids
        for mi,motion in enumerate(motions):
            motion["name"]=text(motion.get("name"),"动作名称");motion["joint_id"]=str(motion.get("joint_id",""));motion["enabled"]=bool(motion.get("enabled",True))
            if motion["joint_id"] not in joint_ids:raise ValueError(f"动作“{motion['name']}”必须选择有效运动副")
            motion["position_0_percent"]=number(motion.get("position_0_percent",0),"电机 0% 对应位置");motion["position_100_percent"]=number(motion.get("position_100_percent",100),"电机 100% 对应位置")
            if motion["position_0_percent"]==motion["position_100_percent"]:raise ValueError(f"动作“{motion['name']}”的 0% 与 100% 位置不得相同")
            motion["mode"]=str(motion.get("mode","ease"))
            if motion["mode"] not in {"ease","mapping"}:raise ValueError("动作模式必须是缓起缓停或映射")
            motion["rated_speed"]=number(motion.get("rated_speed",30),"额定速度",.000001)
    model["drives"]=drives=_activity_drives(parts);unique(drives,"驱动","drive")
    for drive in drives:
        drive["name"]=text(drive.get("name"),"驱动名称");drive["joint_id"]=str(drive.get("joint_id",""));drive["enabled"]=bool(drive.get("enabled",True))
        if drive["joint_id"] and drive["joint_id"] not in joint_ids:raise ValueError(f"驱动“{drive['name']}”引用的运动副不存在")
        drive["rated_speed"]=number(drive.get("rated_speed",30),"额定速度",.000001);drive["reverse_limit"]=number(drive.get("reverse_limit",-180),"反转极限");drive["forward_limit"]=number(drive.get("forward_limit",180),"正转极限")
        if drive["reverse_limit"]>=drive["forward_limit"]:raise ValueError("反转极限必须小于正转极限")
        drive["zero_at"]=drive.get("zero_at","reverse")
        segments=drive.setdefault("segments",[]);unique(segments,"运动段","seg")
        for seg in segments:
            seg["name"]=text(seg.get("name"),"运动段名称");seg["start_mode"]=seg.get("start_mode","direct");seg["mode"]=seg.get("mode","duration");seg["profile"]=seg.get("profile","s_curve")
            if seg["start_mode"] not in {"direct","reference"} or seg["mode"] not in {"duration","speed"} or seg["profile"] not in {"s_curve","smoothstep","points","external_csv","mapping"}:raise ValueError("运动段枚举值无效")
            for key,default in (("start",0),("duration",1),("speed",30),("travel",30)):seg.setdefault(key,default)
            seg.setdefault("reference","");seg.setdefault("reference_boundary","end");seg.setdefault("ease_in",True);seg.setdefault("ease_out",True);seg.setdefault("easing_mode","time");seg.setdefault("ease_in_time",.2);seg.setdefault("ease_out_time",.2);seg.setdefault("points",[])
    for closure in closures:
        closure["name"]=text(closure.get("name"),"闭链名称");closure["enabled"]=bool(closure.get("enabled",True))
        for side in ("a","b"):
            endpoint=closure.get(f"endpoint_{side}",{})
            if endpoint.get("layer_id") not in layer_ids:raise ValueError(f"闭链“{closure['name']}”端点层级不存在")
            endpoint["point_mm"]=vector(endpoint.get("point_mm",[0,0,0]),"闭链端点");closure[f"endpoint_{side}"]=endpoint
        closure["solve_joint_ids"]=[str(x) for x in closure.get("solve_joint_ids",[]) if str(x)]
        if any(x not in joint_ids for x in closure["solve_joint_ids"]):raise ValueError(f"闭链“{closure['name']}”包含无效运动副")
        if closure["enabled"] and not closure["solve_joint_ids"]:raise ValueError(f"闭链“{closure['name']}”必须选择至少一个从动运动副")
        closure["tolerance_mm"]=number(closure.get("tolerance_mm",.05),"闭链容差",1e-9);closure["max_iterations"]=int(number(closure.get("max_iterations",40),"最大迭代",1));closure["damping"]=number(closure.get("damping",1e-4),"闭链阻尼",1e-12);closure["max_angle_step_deg"]=number(closure.get("max_angle_step_deg",8),"最大角步",1e-9);closure["max_slide_step_mm"]=number(closure.get("max_slide_step_mm",5),"最大滑步",1e-9)
    model.setdefault("presets",[]);model.setdefault("memories",[])
    return model
