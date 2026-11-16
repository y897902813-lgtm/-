from __future__ import annotations

import copy
import json
import math
import re
import shutil
import unicodedata
from pathlib import Path
from xml.dom import minidom
from xml.etree import ElementTree as ET

from .models import JointSpec, ProjectSpec
from .crank import crank_displacement, crank_meta
from .mass_properties import resolve_mass_properties
from .motion import ResolvedSegment, resolve_schedule
from .validation import has_errors, validate_project


def safe_name(text: str, prefix: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9_]+", "_", normalized).strip("_")
    if not value:
        value = prefix
    if value[0].isdigit():
        value = f"{prefix}_{value}"
    return value


def stable_xml_name(display_name: str, stable_id: str, prefix: str) -> str:
    """Keep readable ASCII names while giving non-ASCII labels a stable alias."""
    candidate = safe_name(display_name, prefix)
    if candidate == prefix and any(ord(char) > 127 for char in str(display_name)):
        return safe_name(f"{prefix}_{stable_id}", prefix)
    return candidate


def _rgba_with_opacity(rgba: str, opacity: float) -> str:
    values = [item for item in re.split(r"[\s,]+", str(rgba).strip()) if item]
    if len(values) < 3:
        values = ["0.72", "0.75", "0.80"]
    try:
        alpha = float(values[3]) if len(values) >= 4 else 1.0
    except (TypeError, ValueError):
        alpha = 1.0
    alpha = min(max(alpha * float(opacity), 0.0), 1.0)
    return " ".join(values[:3] + [f"{alpha:.12g}"])


def parse_vector(text: str, scale: float = 1.0) -> tuple[float, float, float]:
    value = str(text).translate(str.maketrans({"（":"(", "）":")", "，":",", "；":";"}))
    value = re.sub(r"^\s*point\s*", "", value, flags=re.IGNORECASE)
    values = [part for part in re.split(r"[\s,()]+", value) if part]
    if len(values) != 3:
        raise ValueError(f"Expected a 3D vector, got: {text}")
    return tuple(float(value) * scale for value in values)  # type: ignore[return-value]


def _format_vector(values: tuple[float, float, float] | list[float]) -> str:
    return " ".join(f"{float(value):.12g}" for value in values)


def _pretty_xml(root: ET.Element) -> str:
    raw = ET.tostring(root, encoding="utf-8")
    return minidom.parseString(raw).toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")


def _merge_scene_template(scene_model: ET.Element, template_path: str) -> bool:
    """Merge a self-contained server scene around generated mechanism bodies."""
    value = str(template_path or "").strip()
    if not value:
        return False
    source = Path(value)
    if not source.is_file():
        raise ValueError(f"服务端 XML 场景不存在：{source}")
    try:
        template = ET.parse(source).getroot()
    except (ET.ParseError, OSError) as exc:
        raise ValueError(f"服务端 XML 场景无法解析：{source}：{exc}") from exc
    if template.tag != "mujoco" or template.findall(".//include") or any(node.get("file") for node in template.iter()):
        raise ValueError("服务端 XML 场景必须是单文件、自包含的 <mujoco> 场景")
    template_option = template.find("option")
    scene_option = scene_model.find("option")
    if template_option is not None and scene_option is not None:
        scene_option.attrib.update(template_option.attrib)
    for tag in ("visual", "statistic", "size"):
        existing = scene_model.find(tag)
        incoming = template.find(tag)
        if incoming is not None:
            if existing is not None:
                scene_model.remove(existing)
            scene_model.append(copy.deepcopy(incoming))
    scene_asset = scene_model.find("asset")
    template_asset = template.find("asset")
    if scene_asset is not None and template_asset is not None:
        for child in template_asset:
            scene_asset.append(copy.deepcopy(child))
    scene_worldbody = scene_model.find("worldbody")
    template_worldbody = template.find("worldbody")
    if scene_worldbody is not None and template_worldbody is not None:
        for child in list(scene_worldbody):
            if child.tag != "body":
                scene_worldbody.remove(child)
        for child in template_worldbody:
            scene_worldbody.insert(0, copy.deepcopy(child))
    return True


def _joint_xml_range(joint: JointSpec) -> tuple[float, float]:
    """Return the configured joint range in MJCF authoring units.

    The generated compiler uses ``angle=degree``.  Hinge ranges therefore stay
    in Studio degrees, while slide/crank ranges are emitted in metres.
    """
    if joint.type == "crank":
        meta = crank_meta(joint)
        values = sorted(crank_displacement(meta, value) * 0.001 for value in joint.range)
        return float(values[0]), float(values[1])
    if joint.type == "translation":
        return float(joint.range[0]) * 0.001, float(joint.range[1]) * 0.001
    return float(joint.range[0]), float(joint.range[1])


def _actuator_ctrl_range(joint: JointSpec) -> tuple[float, float]:
    """Return position-servo control bounds in MuJoCo runtime units.

    Position controls use actuator transmission length.  For hinge joints that
    is the joint angle in radians at runtime; slide/crank controls use metres.
    This deliberately does not reuse the MJCF hinge range representation.
    """
    if joint.type == "crank":
        meta = crank_meta(joint)
        values = sorted(crank_displacement(meta, value) * 0.001 for value in joint.range)
        return float(values[0]), float(values[1])
    if joint.type == "translation":
        return float(joint.range[0]) * 0.001, float(joint.range[1]) * 0.001
    return math.radians(float(joint.range[0])), math.radians(float(joint.range[1]))


def _position_actuator_attributes(
    joint: JointSpec, *, name: str, joint_name: str, kp: float, kv: float,
) -> dict[str, str]:
    """Compile one generic dynamic position actuator from project state.

    A previous reference model used ``inheritrange=1`` together with many
    ``range=-1 1`` joints.  That is a model-specific convenience, not a Studio
    product rule.  V2.5.1 therefore emits an explicit ctrlrange only when the
    Studio joint itself is limited, and derives it from the *current* editable
    JointSpec range.  Unlimited joints intentionally keep unlimited actuator
    targets.
    """
    attributes = {
        "name": name,
        "joint": joint_name,
        "kp": f"{float(kp):.12g}",
        "kv": f"{float(kv):.12g}",
    }
    if joint.limited:
        lower, upper = _actuator_ctrl_range(joint)
        attributes["ctrllimited"] = "true"
        attributes["ctrlrange"] = f"{lower:.12g} {upper:.12g}"
    else:
        # Be explicit so compiler autolimits or a future default class cannot
        # accidentally turn a template convention into a Studio restriction.
        attributes["ctrllimited"] = "false"
    return attributes

def _joint_xml(
    parent: ET.Element, joint: JointSpec, names: set[str], *, dynamic: bool = False,
    body_world_origin_mm: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> str:
    base = stable_xml_name(joint.name, joint.id, "joint")
    name = base
    counter = 2
    while name in names:
        name = f"{base}_{counter}"
        counter += 1
    names.add(name)
    meta = crank_meta(joint) if joint.type == "crank" else None
    axis = list(meta["slide_axis"] if meta else parse_vector(joint.axis))
    if joint.reverse and meta is None:
        axis = [-value for value in axis]
    kind = "slide" if joint.type in {"translation", "crank"} else "hinge"
    attributes = {"name": name, "type": kind, "axis": _format_vector(axis)}
    if dynamic:
        attributes.update({
            "damping": f"{float(joint.damping):.12g}",
            "armature": f"{float(joint.armature):.12g}",
            "frictionloss": f"{float(joint.frictionloss):.12g}",
        })
        if float(joint.stiffness) > 0:
            attributes["stiffness"] = f"{float(joint.stiffness):.12g}"
            springref = float(joint.spring_reference) * (0.001 if kind == "slide" else 1.0)
            attributes["springref"] = f"{springref:.12g}"
    if kind == "hinge":
        # JointSpec.point is authored/displayed as a world-coordinate point in
        # millimetres, while MJCF joint pos is local to the body containing the
        # joint.  Convert at the qpos0 reference configuration before m->mm.
        point_world_mm = parse_vector(joint.point)
        point_local_mm = [
            float(point_world_mm[index]) - float(body_world_origin_mm[index])
            for index in range(3)
        ]
        attributes["pos"] = _format_vector([value * 0.001 for value in point_local_mm])
    if joint.limited:
        attributes["limited"] = "true"
        lower, upper = _joint_xml_range(joint)
        attributes["range"] = f"{lower:.12g} {upper:.12g}"
    ET.SubElement(parent, "joint", attributes)
    return name




def _runtime_closure_payload(project: ProjectSpec, joint_map: dict[str, str]) -> list[dict[str, object]]:
    """Return closures as consumed by generated runtime metadata.

    ``solve_joint_ids`` only drives the pure-kinematic DLS solver.  Keep dynamic
    metadata lossless because MuJoCo equality/connect ignores this list.  For
    kinematic runtime, however, filter the list to joints that were actually
    emitted into the active MJCF tree and whose Studio type is supported by the
    scalar closure solver.  Validation guarantees at least one effective joint
    for every enabled kinematic closure.
    """
    joint_types = {joint.id: joint.type for layer in project.layers for joint in layer.joints}
    payload: list[dict[str, object]] = []
    for closure in project.kinematic_closures:
        row = closure.model_dump()
        if project.solver_mode == "kinematic" and closure.enabled:
            row["solve_joint_ids"] = [
                joint_id for joint_id in closure.solve_joint_ids
                if joint_id in joint_map and joint_types.get(joint_id) in {"rotation", "translation"}
            ]
        payload.append(row)
    return payload

def generate_project(project: ProjectSpec, output_dir: Path, *, check_files: bool = True) -> dict[str, str]:
    issues = validate_project(project, check_files=check_files)
    if has_errors(issues):
        messages = "; ".join(issue.message for issue in issues if issue.severity == "error")
        raise ValueError(f"Project validation failed: {messages}")
    output_dir.mkdir(parents=True, exist_ok=True)
    variables, schedule = resolve_schedule(project)
    mass_properties = resolve_mass_properties(project)
    if mass_properties["errors"]:
        raise ValueError("; ".join(item["message"] for item in mass_properties["errors"]))

    dynamic_mode = project.solver_mode == "dynamic"
    model = ET.Element("mujoco", {"model": safe_name(project.name, "model")})
    ET.SubElement(model, "compiler", {"angle": "degree", "coordinate": "local", "meshdir": "meshes", "autolimits": "true"})
    option = ET.SubElement(model, "option", {
        "timestep": f"{project.simulation.timestep:.12g}",
        "gravity": f"0 0 {-float(project.simulation.gravity_m_s2 if dynamic_mode else 0.0):.12g}",
        "integrator": "implicitfast", "cone": "elliptic", "impratio": "10",
    })
    default = ET.SubElement(model, "default")
    ET.SubElement(default, "joint", {"damping": "0.1", "armature": "0.01"})
    ET.SubElement(default, "geom", {
        "density": "1000", "friction": "0.8 0.1 0.1",
        "solref": f"{float(project.simulation.contact_response_time_s):.12g} {float(project.simulation.contact_damping_ratio):.12g}",
        "solimp": f"{float(project.simulation.contact_impedance_min):.12g} {float(project.simulation.contact_impedance_max):.12g} {float(project.simulation.contact_impedance_width_m):.12g} 0.5 2",
    })
    asset = ET.SubElement(model, "asset")
    worldbody = ET.SubElement(model, "worldbody")
    ET.SubElement(worldbody, "light", {"pos": "0 0 4", "dir": "0 0 -1", "diffuse": "0.8 0.8 0.8"})
    if project.simulation.ground_enabled:
        ET.SubElement(worldbody, "geom", {
            "name": "ground", "type": "plane", "size": "5 5 0.1", "rgba": "0.16 0.18 0.22 1",
            "contype": "1" if dynamic_mode else "0", "conaffinity": "1" if dynamic_mode else "0",
            "friction": f"{float(project.simulation.ground_friction):.12g} 0.1 0.1",
            "margin": f"{float(project.simulation.ground_collision_margin_mm) * 0.001:.12g}",
        })

    mesh_dir = output_dir / "meshes"
    mesh_dir.mkdir(exist_ok=True)
    mesh_assets: dict[str, str] = {}
    mesh_manifest: dict[str, list[str]] = {}
    mesh_mass_manifest: dict[str, dict[str, object]] = {}
    used_names: set[str] = set()
    joint_map: dict[str, str] = {}
    layer_body_map: dict[str, str] = {}
    asset_index = 0
    for layer in project.layers:
        if not layer.active:
            continue
        for mesh in layer.meshes:
            asset_index += 1
            name = stable_xml_name(mesh.filename, mesh.id, "mesh")
            original = name
            index = 2
            while name in used_names:
                name = f"{original}_{index}"
                index += 1
            used_names.add(name)
            mesh_assets[mesh.id] = name
            source = Path(project.mesh_root) / mesh.filename if project.mesh_root else Path(mesh.filename)
            suffix = Path(mesh.filename).suffix.lower() or ".stl"
            target = mesh_dir / f"asset_{asset_index:05d}{suffix}"
            if source.is_file():
                shutil.copy2(source, target)
            # The Studio and legacy tool use millimetres for imported CAD/STL
            # coordinates, while MuJoCo's world unit is metres.
            ET.SubElement(asset, "mesh", {
                "name": name, "file": target.name, "scale": "0.001 0.001 0.001",
            })

    bodies: dict[str, ET.Element] = {"root": worldbody}
    # Reference world origins are only the accumulated static LayerSpec
    # translations.  Layer bodies have no independent static orientation field,
    # and qpos0 for hinge/slide joints is zero, so this is the exact authoring
    # transform needed to convert world-authored rotation anchors to MJCF local.
    body_world_origins_mm: dict[str, tuple[float, float, float]] = {
        "root": (0.0, 0.0, 0.0)
    }
    body_names: set[str] = set()
    remaining = [layer for layer in project.layers if layer.active]
    while remaining:
        progress = False
        for layer in list(remaining):
            if layer.parent_id not in bodies:
                continue
            body_base = stable_xml_name(layer.name, layer.id, "body")
            body_name = body_base
            if body_name in body_names:
                body_name = safe_name(f"{body_base}_{layer.id}", "body")
            body_names.add(body_name)
            parent_world_origin_mm = body_world_origins_mm[layer.parent_id]
            body_world_origin_mm = tuple(
                float(parent_world_origin_mm[index]) + float(layer.position_mm[index])
                for index in range(3)
            )
            body = ET.SubElement(
                bodies[layer.parent_id],
                "body",
                {"name": body_name, "pos": _format_vector([value * 0.001 for value in layer.position_mm])},
            )
            bodies[layer.id] = body
            body_world_origins_mm[layer.id] = body_world_origin_mm
            layer_body_map[layer.id] = body_name
            for joint in layer.joints:
                joint_map[joint.id] = _joint_xml(
                    body, joint, used_names, dynamic=dynamic_mode,
                    body_world_origin_mm=body_world_origin_mm,
                )
            if layer.meshes:
                for mesh in layer.meshes:
                    geom_name = safe_name(f"geom_{mesh.id}", "geom")
                    attrs = {
                        "name": geom_name,
                        "type": "mesh",
                        "mesh": mesh_assets[mesh.id],
                        "rgba": _rgba_with_opacity(mesh.rgba or layer.color, mesh.opacity),
                        "contype": "1" if (dynamic_mode and mesh.collision) else "0",
                        "conaffinity": "1" if (dynamic_mode and mesh.collision) else "0",
                    }
                    if mesh.collision:
                        attrs["friction"] = f"{float(mesh.friction if mesh.friction is not None else 0.8):.12g} 0.1 0.1"
                        attrs["margin"] = f"{float(mesh.collision_margin_mm) * 0.001:.12g}"
                    mass_row = mass_properties["meshes"].get(mesh.id, {})
                    density = mass_row.get("density_kg_m3")
                    resolved_mass = mass_row.get("resolved_mass_kg")
                    mass_application = str(mass_row.get("mass_application", "density"))
                    if mass_application == "direct_mass" and resolved_mass is not None:
                        # Target kg is the product truth.  Let MuJoCo use its own
                        # actual mesh volume/shape only to infer a consistent
                        # density and inertia; never let a Studio-side volume
                        # estimate turn the target mass back into a density that
                        # can produce a different compiled mass.
                        attrs["mass"] = f"{float(resolved_mass):.12g}"
                    elif density is not None:
                        attrs["density"] = f"{float(density):.12g}"
                    ET.SubElement(body, "geom", attrs)
                    mesh_manifest.setdefault(mesh.filename, []).append(geom_name)
                    mesh_mass_manifest[geom_name] = {
                        "mesh_id": mesh.id,
                        "filename": mesh.filename,
                        "mass_kg": resolved_mass,
                        "density_kg_m3": density,
                        "volume_m3": mass_row.get("volume_m3"),
                        "source": mass_row.get("source", "default"),
                        "mass_application": mass_application,
                    }
            elif layer.joints or layer.mass_kg is not None:
                # A jointed MuJoCo body still needs positive inertia, but an
                # inertial element is non-visual and does not invent geometry.
                ET.SubElement(body, "inertial", {
                    "pos": "0 0 0", "mass": f"{float(layer.mass_kg or 0.001):.12g}",
                    "diaginertia": "0.000001 0.000001 0.000001",
                })
            remaining.remove(layer)
            progress = True
        if not progress:
            raise ValueError("Unable to generate layer hierarchy")

    # V2.5.11: an empty drive joint selection is represented in generated
    # runtime artifacts by a tiny transparent, non-colliding geom at the world
    # origin.  This is deliberately not a ProjectSpec Layer/Joint and does not
    # create a synthetic physical DOF; it only gives downstream consumers an
    # explicit action target instead of an empty object reference.
    drive_target_map: dict[str, dict[str, object]] = {}
    proxy_names: set[str] = set()
    for drive in project.drives:
        if drive.joint_id:
            drive_target_map[drive.id] = {
                "kind": "joint",
                "name": joint_map.get(drive.joint_id, ""),
                "joint_id": drive.joint_id,
                "generated_proxy": False,
            }
            continue
        base = f"__mjs_drive_proxy_{safe_name(drive.id, 'drive')}"
        proxy_name = base
        suffix = 2
        while proxy_name in proxy_names or proxy_name in used_names:
            proxy_name = f"{base}_{suffix}"
            suffix += 1
        proxy_names.add(proxy_name)
        used_names.add(proxy_name)
        ET.SubElement(worldbody, "geom", {
            "name": proxy_name,
            "type": "sphere",
            "size": "0.0005",
            "pos": "0 0 0",
            "rgba": "0 0 0 0",
            "contype": "0",
            "conaffinity": "0",
            "group": "5",
        })
        drive_target_map[drive.id] = {
            "kind": "geom",
            "name": proxy_name,
            "joint_id": "",
            "generated_proxy": True,
        }

    closure_site_map: dict[str, dict[str, str]] = {}
    for closure in project.kinematic_closures:
        if not closure.enabled:
            continue
        names = {"a": f"__mjs_closure_{safe_name(closure.id, 'closure')}_a", "b": f"__mjs_closure_{safe_name(closure.id, 'closure')}_b"}
        for side, endpoint in (("a", closure.endpoint_a), ("b", closure.endpoint_b)):
            body = bodies.get(endpoint.layer_id)
            if body is None:
                raise ValueError(f"kinematic_closure_missing_layer_body: {closure.id}/{endpoint.layer_id}")
            ET.SubElement(body, "site", {
                "name": names[side], "pos": _format_vector([float(v) * 0.001 for v in endpoint.point_mm]),
                "type": "sphere", "size": "0.0005", "rgba": "0 0 0 0", "group": "5",
            })
        closure_site_map[closure.id] = names

    if dynamic_mode and closure_site_map:
        equality = ET.SubElement(model, "equality")
        for closure in project.kinematic_closures:
            if not closure.enabled or closure.id not in closure_site_map:
                continue
            names = closure_site_map[closure.id]
            ET.SubElement(equality, "connect", {
                "name": safe_name(f"closure_{closure.id}", "closure"),
                "site1": names["a"], "site2": names["b"],
                "solref": f"{float(project.simulation.contact_response_time_s):.12g} {float(project.simulation.contact_damping_ratio):.12g}",
                "solimp": f"{float(project.simulation.contact_impedance_min):.12g} {float(project.simulation.contact_impedance_max):.12g} {float(project.simulation.contact_impedance_width_m):.12g}",
            })

    actuator_map: dict[str, str] = {}
    if dynamic_mode:
        driven = {}
        for drive in project.drives:
            if drive.enabled and drive.joint_id in joint_map and drive.joint_id:
                driven.setdefault(drive.joint_id, []).append(drive)
        if driven:
            actuator = ET.SubElement(model, "actuator")
            joint_lookup = {joint.id: joint for layer in project.layers for joint in layer.joints}
            for joint_id, drives in driven.items():
                name = safe_name(f"pos_{joint_id}", "pos")
                kp = max(float(item.dynamic_kp) for item in drives)
                kv = max(float(item.dynamic_kv) for item in drives)
                ET.SubElement(
                    actuator,
                    "position",
                    _position_actuator_attributes(
                        joint_lookup[joint_id], name=name, joint_name=joint_map[joint_id], kp=kp, kv=kv,
                    ),
                )
                actuator_map[joint_id] = name

    # Viewer scene: preserve the old application's proven visual setup while
    # keeping the physical validation model independent. Prescribed playback
    # uses zero gravity; background, ground, camera and lighting affect only
    # generated_scene.xml.
    scene_model = copy.deepcopy(model)
    custom_scene = _merge_scene_template(scene_model, project.template_scene)
    scene_compiler = scene_model.find("compiler")
    if scene_compiler is not None:
        scene_compiler.set("autolimits", "true")
    scene_option = scene_model.find("option")
    if scene_option is not None:
        scene_option.attrib.update({
            "gravity": "0 0 0", "integrator": "implicitfast",
            "cone": "elliptic", "impratio": "10",
        })
    # Do not force a fixed statistic center/extent. MuJoCo computes these from
    # the actual imported meshes and the native viewer can then frame arbitrary
    # custom CAD geometry correctly.
    if not custom_scene:
        visual = ET.SubElement(scene_model, "visual")
        ET.SubElement(visual, "headlight", {
            "diffuse": "0.6 0.6 0.6", "ambient": "0.1 0.1 0.1", "specular": "0.9 0.9 0.9",
        })
        ET.SubElement(visual, "rgba", {"haze": "0.15 0.25 0.35 1"})
        ET.SubElement(visual, "global", {"azimuth": "140", "elevation": "-20"})
    scene_asset = scene_model.find("asset")
    if scene_asset is not None and not custom_scene:
        ET.SubElement(scene_asset, "texture", {
            "type": "skybox", "builtin": "gradient", "rgb1": "0.3 0.5 0.7",
            "rgb2": "0 0 0", "width": "512", "height": "3072",
        })
        ET.SubElement(scene_asset, "texture", {
            "type": "2d", "name": "groundplane_texture", "builtin": "checker", "mark": "edge",
            "rgb1": "0.2 0.3 0.4", "rgb2": "0.1 0.2 0.3", "markrgb": "0.8 0.8 0.8",
            "width": "300", "height": "300",
        })
        ET.SubElement(scene_asset, "material", {
            "name": "groundplane_material", "texture": "groundplane_texture", "texuniform": "true",
            "texrepeat": "5 5", "reflectance": "0.1",
        })
    scene_worldbody = scene_model.find("worldbody")
    if scene_worldbody is not None and not custom_scene:
        ground = scene_worldbody.find("geom[@name='ground']")
        if ground is not None:
            ground.set("material", "groundplane_material")
            ground.attrib.pop("rgba", None)
        ET.SubElement(scene_worldbody, "camera", {
            "mode": "fixed", "name": "Customizedview", "pos": "0.35 -0.2 0.6",
            "quat": "-0.5 -0.5 0.5 0.5",
        })

    generated_model = output_dir / "generated_model.xml"
    generated_scene = output_dir / "generated_scene.xml"
    generated_drives = output_dir / "generated_drives.json"
    generated_config = output_dir / "generated_config.json"
    generated_model.write_text(_pretty_xml(model), encoding="utf-8")
    generated_scene.write_text(_pretty_xml(scene_model), encoding="utf-8")
    generated_config.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    drive_payload = {
        "schema_version": 4,
        "project_id": project.id,
        "solver_mode": project.solver_mode,
        "simulation": project.simulation.model_dump(),
        "variables": variables,
        "joint_map": joint_map,
        "joint_types": {joint.id: joint.type for layer in project.layers for joint in layer.joints},
        "layer_body_map": layer_body_map,
        "closure_site_map": closure_site_map,
        "kinematic_closures": _runtime_closure_payload(project, joint_map),
        "actuator_map": actuator_map,
        "drive_target_map": drive_target_map,
        "mesh_manifest": mesh_manifest,
        "mesh_mass_manifest": mesh_mass_manifest,
        "mass_properties": mass_properties,
        "distance_pairs": [pair.model_dump() for pair in project.distance_pairs],
        "distance_sampling": project.distance_sampling.model_dump(),
        "result_layout": project.result_layout.model_dump(),
        "viewer_control": project.viewer_control.model_dump(),
        "drives": [
            {
                "id": drive.id, "name": drive.name, "joint_id": drive.joint_id, "enabled": drive.enabled,
                "target": drive_target_map.get(drive.id, {}),
                "joint_type": next((joint.type for layer in project.layers for joint in layer.joints if joint.id == drive.joint_id), "virtual" if not drive.joint_id else "rotation"),
                "unit": "value" if not drive.joint_id else ("mm" if next((joint.type for layer in project.layers for joint in layer.joints if joint.id == drive.joint_id), "rotation") == "translation" else "°"),
                "crank_meta": next((crank_meta(joint) for layer in project.layers for joint in layer.joints if joint.id == drive.joint_id and joint.type == "crank"), None),
                "dynamic_kp": drive.dynamic_kp, "dynamic_kv": drive.dynamic_kv,
                "dynamic_lock_force": drive.dynamic_lock_force,
            }
            for drive in project.drives
        ],
        "segments": [_segment_payload(segment, joint_map) for segment in schedule],
    }
    generated_drives.write_text(json.dumps(drive_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "directory": str(output_dir),
        "model": str(generated_model),
        "scene": str(generated_scene),
        "drives": str(generated_drives),
        "config": str(generated_config),
    }


def _segment_payload(segment: ResolvedSegment, joint_map: dict[str, str]) -> dict[str, object]:
    payload = dict(segment.__dict__)
    payload["joint_name"] = joint_map.get(segment.joint_id, "")
    payload["end"] = segment.end
    payload["points"] = [list(item) for item in segment.points]
    return payload


def load_with_mujoco(xml_path: str) -> dict[str, object]:
    try:
        import mujoco  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "当前 Python 环境未安装 MuJoCo。请使用启动 Studio 的同一个解释器执行："
            "python -m pip install \"mujoco>=3.1,<4\"；"
            "安装后重启 Studio。"
        ) from exc
    from .simulation import load_generated_mujoco_model

    model = load_generated_mujoco_model(xml_path, mujoco)
    return {"nq": int(model.nq), "nv": int(model.nv), "nbody": int(model.nbody), "ngeom": int(model.ngeom), "njnt": int(model.njnt)}
