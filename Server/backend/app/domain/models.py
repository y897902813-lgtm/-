from __future__ import annotations

import os
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

try:  # Pydantic 2 (the supported production dependency)
    from pydantic import ConfigDict, field_validator, model_validator

    PYDANTIC_V2 = True
except ImportError:  # Pydantic 1 compatibility for existing desktop environments
    from pydantic import root_validator, validator

    PYDANTIC_V2 = False


NumericExpression = float | int | str


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def strip_distance_pair_variables(variables: dict[str, Any], pair_names: Any) -> dict[str, Any]:
    """Remove legacy measurement-pair aliases from the custom-variable pool.

    V21.x historically injected every distance-pair name into
    ``custom_variables`` with a placeholder value.  Distance pairs are runtime
    measurements, not user parameters, so keeping those aliases in
    ``project.variables`` creates a second meaning for the same name and can
    pollute expression resolution/optimization.  Matching is whitespace
    normalized but otherwise case-sensitive to preserve legitimate variable
    names.
    """
    names = {str(name or "").strip() for name in (pair_names or []) if str(name or "").strip()}
    if not names:
        return dict(variables or {})
    return {
        str(name): value
        for name, value in dict(variables or {}).items()
        if str(name).strip() not in names
    }


if PYDANTIC_V2:
    class StrictModel(BaseModel):
        model_config = ConfigDict(extra="allow", validate_assignment=True)
else:
    class StrictModel(BaseModel):
        """Pydantic 1 shim retaining the Pydantic 2 API used by the app."""

        class Config:
            extra = "allow"
            validate_assignment = True

        def model_dump(self, *args, **kwargs):
            return self.dict(*args, **kwargs)

        def model_dump_json(self, *args, **kwargs):
            return self.json(*args, **kwargs)

        @classmethod
        def model_validate(cls, value):
            return cls.parse_obj(value)

        @classmethod
        def model_validate_json(cls, value):
            return cls.parse_raw(value)


class MeshSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("mesh"))
    filename: str
    collision: bool = False
    rgba: str = ""
    opacity: float = Field(default=1.0, ge=0.0, le=1.0)
    friction: float | None = Field(default=None, ge=0.0, description="碰撞切向摩擦系数；留空继承默认值")
    collision_margin_mm: float = Field(default=0.0, ge=0.0, le=100.0)
    mass_kg: float | None = Field(
        default=None, gt=0,
        description="数模最终目标质量（kg）；STL 未显式设置时默认 0.01 kg；有目标质量时 MJCF 直接写 mass，体积/参考 density 不再覆盖该 kg",
    )

    if PYDANTIC_V2:
        @model_validator(mode="after")
        def apply_default_stl_mass(self) -> "MeshSpec":
            if self.mass_kg is None and str(self.filename).lower().endswith(".stl"):
                object.__setattr__(self, "mass_kg", 0.01)
            return self
    else:
        @root_validator
        def apply_default_stl_mass(cls, values):
            if values.get("mass_kg") is None and str(values.get("filename", "")).lower().endswith(".stl"):
                values["mass_kg"] = 0.01
            return values


class JointSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("joint"))
    name: str = "joint1"
    type: Literal["rotation", "translation", "crank"] = "rotation"
    point: str = "0, 0, 0"
    axis: str = "0, 1, 0"
    crank_center: str = "0, 0, 0"
    crank_end: str = "0, 10, 0"
    rod_end: str = "30, 0, 0"
    slide_axis: str = "1, 0, 0"
    reverse: bool = False
    limited: bool = False
    range: list[float] = Field(default_factory=lambda: [-180.0, 180.0])
    damping: float = Field(default=0.1, ge=0.0)
    armature: float = Field(default=0.01, ge=0.0)
    frictionloss: float = Field(default=0.0, ge=0.0)
    stiffness: float = Field(default=0.0, ge=0.0)
    spring_reference: float = 0.0
    parameters: dict[str, Any] = Field(default_factory=dict)


class LayerSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("layer"))
    name: str = "layer"
    parent_id: str = "root"
    active: bool = True
    color: str = "0.72 0.75 0.80 1"
    position_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    mass_kg: float | None = Field(
        default=None, gt=0,
        description="层级目标总质量（kg）；扣除数模显式质量后按体积分配",
    )
    meshes: list[MeshSpec] = Field(default_factory=list)
    joints: list[JointSpec] = Field(default_factory=list)


class DriveSegmentSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("seg"))
    name: str = "seg1"
    start_mode: Literal["direct", "reference"] = "direct"
    start: NumericExpression = 0.0
    reference: str = ""
    reference_boundary: Literal["start", "end"] = "end"
    mode: Literal["duration", "speed"] = "duration"
    duration: NumericExpression = 1.0
    speed: NumericExpression = 30.0
    travel: NumericExpression = 30.0
    profile: Literal["s_curve", "smoothstep", "points", "external_csv", "mapping"] = "s_curve"
    ease_in: bool = True
    ease_out: bool = True
    easing_mode: Literal["time", "acceleration"] = "time"
    ease_in_time: NumericExpression | None = None
    ease_out_time: NumericExpression | None = None
    ease_in_acceleration: NumericExpression = 150.0
    ease_out_acceleration: NumericExpression = 150.0
    acceleration_time: NumericExpression = 0.2
    points: list[list[float]] = Field(default_factory=list)
    # CSV paths are legacy provenance only. Runtime/export must prefer the
    # embedded numeric point table so project JSON remains portable.
    csv_path: str = ""
    external_csv_name: str = ""
    external_csv_header: str = ""
    external_csv_source_metric: str = ""
    mapping_source_joint_id: str = ""
    mapping_csv_name: str = ""
    mapping_point_count: int = Field(default=0, ge=0)
    archive_start: bool = False
    archive_end: bool = False
    archive_start_time: bool = False
    archive_motion_value: bool = False
    archive_rate_value: bool = False
    gantt_travel_input_mode: Literal["travel", "end_position"] = "travel"
    # Raw exchange fields not understood by this Studio build. They are carried
    # through modeling-info import/export so newer/older generations do not lose
    # drive schedule information just because this version cannot edit it.
    exchange_extra: dict[str, Any] = Field(default_factory=dict)

    if PYDANTIC_V2:
        @field_validator("profile", mode="before")
        @classmethod
        def normalize_profile_label(cls, value: Any) -> Any:
            return {"S 曲线":"s_curve", "缓起缓停":"s_curve", "自定义点":"points", "外部 CSV":"external_csv", "映射电机":"mapping"}.get(value, value)
    else:
        @validator("profile", pre=True)
        def normalize_profile_label(cls, value):
            return {"S 曲线":"s_curve", "缓起缓停":"s_curve", "自定义点":"points", "外部 CSV":"external_csv", "映射电机":"mapping"}.get(value, value)


class DriveSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("drive"))
    name: str = "act1"
    joint_id: str
    role: str = ""
    enabled: bool = True
    dynamic_kp: float = Field(default=100.0, gt=0.0)
    dynamic_kv: float = Field(default=20.0, ge=0.0)
    dynamic_lock_force: float = Field(
        default=2000.0, ge=0.0,
        description="动力学驱动目标静止时的附加自锁/制动力上限；rotation 为 N·m，translation/crank 为 N；0 表示关闭",
    )
    exchange_extra: dict[str, Any] = Field(default_factory=dict)
    segments: list[DriveSegmentSpec] = Field(default_factory=list)


class ClosureEndpointSpec(StrictModel):
    layer_id: str
    point_mm: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])


class KinematicClosureSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("closure"))
    name: str = "closure1"
    enabled: bool = True
    kind: Literal["point"] = "point"
    endpoint_a: ClosureEndpointSpec
    endpoint_b: ClosureEndpointSpec
    solve_joint_ids: list[str] = Field(default_factory=list)
    tolerance_mm: float = Field(default=0.05, gt=0.0, le=1000.0)
    max_iterations: int = Field(default=40, ge=1, le=1000)
    damping: float = Field(default=1e-4, gt=0.0, le=1.0)
    max_angle_step_deg: float = Field(default=8.0, gt=0.0, le=180.0)
    max_slide_step_mm: float = Field(default=5.0, gt=0.0, le=10000.0)


class DistancePairSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("pair"))
    name: str = "distance1"
    objects_a: list[str] = Field(default_factory=list)
    objects_b: list[str] = Field(default_factory=list)
    strategy_spacing_mm: float = Field(default=12.0, gt=0)
    precise_spacing_mm: float = Field(default=2.0, gt=0)
    animation_spacing_mm: float = Field(default=2.0, gt=0)
    boundary_mm: float = Field(
        default=8.0,
        ge=0.0,
        description="快速寻优时该测距对必须严格大于的最小间隙（mm）。",
    )
    distmax_m: float = Field(default=0.1, gt=0)


class DistanceSamplingSettings(StrictModel):
    max_points_per_object: int = Field(
        default=400, ge=16, le=20_000,
        description="Viewer 中每个测距对象的最大撒点数；锐边与拐角优先占用预算",
    )
    corner_angle_degrees: float = Field(
        default=25.0, ge=1.0, le=179.0,
        description="相邻三角面夹角超过该值时作为优先撒点的锐边",
    )


if PYDANTIC_V2:
    class SimulationSettings(StrictModel):
        start_time: float = 0.0
        end_time: float = 12.0
        timestep: float = Field(default=0.01, gt=0)
        engine: Literal["analytical", "mujoco"] = "mujoco"
        gravity_m_s2: float = Field(default=9.81, ge=0.0, le=100.0)
        ground_enabled: bool = True
        ground_friction: float = Field(default=0.8, ge=0.0)
        ground_collision_margin_mm: float = Field(default=0.0, ge=0.0, le=100.0)
        contact_response_time_s: float = Field(default=0.025, gt=0.0, le=10.0)
        contact_damping_ratio: float = Field(default=2.0, gt=0.0, le=20.0)
        contact_impedance_min: float = Field(default=0.95, ge=0.0001, le=0.9999)
        contact_impedance_max: float = Field(default=0.99, ge=0.0001, le=0.9999)
        contact_impedance_width_m: float = Field(default=0.001, gt=0.0, le=1.0)

        @model_validator(mode="after")
        def check_times(self) -> "SimulationSettings":
            if self.end_time < self.start_time:
                raise ValueError("end_time must not be earlier than start_time")
            if (self.end_time - self.start_time) / self.timestep > 2_000_000:
                raise ValueError("time grid is too large")
            return self
else:
    class SimulationSettings(StrictModel):
        start_time: float = 0.0
        end_time: float = 12.0
        timestep: float = Field(default=0.01, gt=0)
        engine: Literal["analytical", "mujoco"] = "mujoco"
        gravity_m_s2: float = Field(default=9.81, ge=0.0, le=100.0)
        ground_enabled: bool = True
        ground_friction: float = Field(default=0.8, ge=0.0)
        ground_collision_margin_mm: float = Field(default=0.0, ge=0.0, le=100.0)
        contact_response_time_s: float = Field(default=0.025, gt=0.0, le=10.0)
        contact_damping_ratio: float = Field(default=2.0, gt=0.0, le=20.0)
        contact_impedance_min: float = Field(default=0.95, ge=0.0001, le=0.9999)
        contact_impedance_max: float = Field(default=0.99, ge=0.0001, le=0.9999)
        contact_impedance_width_m: float = Field(default=0.001, gt=0.0, le=1.0)

        @root_validator
        def check_times(cls, values):
            start_time = values.get("start_time", 0.0)
            end_time = values.get("end_time", 0.0)
            timestep = values.get("timestep", 1.0)
            if end_time < start_time:
                raise ValueError("end_time must not be earlier than start_time")
            if (end_time - start_time) / timestep > 2_000_000:
                raise ValueError("time grid is too large")
            return values


class VariableRange(StrictModel):
    name: str
    minimum: float
    maximum: float
    step: float = Field(gt=0)


class FilterRule(StrictModel):
    variable: str
    minimum: float | None = None
    maximum: float | None = None


class OptimizationSettings(StrictModel):
    mode: Literal["grid", "random"] = "grid"
    trials: int = Field(default=20, ge=1, le=100_000)
    seed: int = 42
    variables: list[VariableRange] = Field(default_factory=list)
    filters: list[FilterRule] = Field(default_factory=list)
    objective: str = "EndTime"
    direction: Literal["min", "max"] = "min"


class QuickOptimizationStep(StrictModel):
    id: str = Field(default_factory=lambda: new_id("quickopt"))
    drive_id: str
    segment_id: str
    field: Literal["start", "duration", "speed", "travel"]
    variable_name: str
    description: str = ""
    initial_value: float
    result_value: float | None = None
    mode: Literal["time", "speed", "travel"] = "time"
    speed_direction: Literal["decrease", "increase"] = "decrease"
    step_size: float | None = Field(default=None, gt=0)
    max_attempts: int = Field(default=200, ge=1, le=10_000)
    collapsed: bool = True
    status: str = "pending"
    last_constraints: list[dict[str, Any]] = Field(default_factory=list)


class QuickOptimizationSettings(StrictModel):
    version: int = 1
    enabled: bool = False
    name: str = "快速寻优工作流"
    steps: list[QuickOptimizationStep] = Field(default_factory=list)
    last_run: dict[str, Any] = Field(default_factory=dict)


class ResultCurveSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("curve"))
    source: str = ""
    label: str = "曲线"
    operation: Literal["raw", "integral", "d1", "d2", "d3", "sum"] = "raw"
    color: str = "#2563eb"


class ResultAxisSpec(StrictModel):
    id: str = Field(default_factory=lambda: new_id("axis"))
    name: str = "坐标系1"
    combine: Literal["none", "sum", "difference"] = "none"
    keep_operands: bool = False
    add_to_gantt: bool = False
    curves: list[ResultCurveSpec] = Field(default_factory=list)


class ResultLayoutPreset(StrictModel):
    id: str = Field(default_factory=lambda: new_id("layout"), max_length=128)
    name: str = Field(default="坐标系布局", min_length=1, max_length=128)
    kind: Literal["custom", "distance"] = "custom"
    axes: list[ResultAxisSpec] = Field(default_factory=list)


class ResultLayout(StrictModel):
    axes: list[ResultAxisSpec] = Field(default_factory=list)
    cursor_times: list[float] = Field(default_factory=list)
    height: int = Field(default=80, ge=40, le=1000)
    presets: list[ResultLayoutPreset] = Field(default_factory=list, max_length=50)
    active_preset_id: str = Field(default="", max_length=128)


class ViewerTrajectorySettings(StrictModel):
    expanded: bool = False
    selected_meshes: list[str] = Field(default_factory=list)
    recording: bool = False
    sample_hz: float = Field(default=20.0, ge=0.1, le=240.0)
    point_size: float = Field(default=1.0, ge=0.1, le=10.0)
    color: str = "#018c94"
    clear_revision: int = Field(default=0, ge=0)
    centroid_probe_revision: int = Field(default=0, ge=0)


class ViewerControlSettings(StrictModel):
    time_s: float = 0.0
    playing: bool = False
    direction: Literal[-1, 1] = 1
    speed: float = Field(default=1.0, ge=0.1, le=2.0)
    show_scatter: bool = True
    show_distance_lines: bool = True
    show_distance_labels: bool = True
    adaptive_display: bool = True
    adaptive_threshold_mm: float = Field(default=25.0, gt=0)
    motor_mode: bool = True
    motor_values: dict[str, float] = Field(default_factory=dict)
    decoupled_drive_ids: list[str] = Field(default_factory=list)
    axes_enabled: bool = False
    gantt_enabled: bool = False
    active_panel: Literal["control", "axes", "gantt"] = "control"
    axes_font_size: int = Field(default=10, ge=6, le=32)
    gantt_font_size: int = Field(default=10, ge=6, le=32)
    gantt_width_px: int = Field(default=960, ge=640, le=3000)
    gantt_row_height_px: int = Field(default=62, ge=44, le=120)
    axes_scale_x: float = Field(default=1.0, ge=0.25, le=4.0)
    axes_scale_y: float = Field(default=1.0, ge=0.25, le=4.0)
    gantt_scale_x: float = Field(default=1.0, ge=0.25, le=4.0)
    gantt_scale_y: float = Field(default=1.0, ge=0.25, le=4.0)
    axes_scale_controls_visible: bool = False
    gantt_scale_controls_visible: bool = False
    orthographic_view: bool = False
    camera_initial_pose: str = Field(
        default="", description="自由相机初始位置和朝向：px,py,pz,dx,dy,dz（位置 mm）",
    )
    trajectory: ViewerTrajectorySettings = Field(default_factory=ViewerTrajectorySettings)


class AgentSettings(StrictModel):
    base_url: str = Field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://yice.byd.com/ai-gate/v1/chat/completions"))
    model: str = Field(default_factory=lambda: os.getenv("LLM_MODEL", "DeepSeek-R1-Pro"))
    context_rounds: int = Field(default=20, ge=1, le=100)
    include_operation_log: bool = True
    include_artifacts: bool = True
    include_variables: bool = True


class AnimationHtmlSettings(StrictModel):
    fps: int = Field(default=20, ge=1, le=120)
    max_faces_per_mesh: int = Field(default=120_000, ge=1_000, le=2_000_000)
    distance_follow_damping: float = Field(default=0.35, ge=0.0, le=0.95)
    adaptive_threshold_mm: float = Field(default=25.0, gt=0.0, allow_inf_nan=False)
    watermark_text: str = "C项目-时序仿真组"
    watermark_position_mm: str = "0, 0, 0"
    watermark_size_mm: float = Field(default=150.0, gt=0)
    watermark_thickness_mm: float = Field(default=10.0, gt=0)
    watermark_color: str = "#B3B3B3"


class ProjectLifecycle(StrictModel):
    status: Literal["checked_in", "checked_out", "baseline"] = "checked_in"
    checked_in_at: str = ""
    checked_out_at: str = ""
    baseline_created_at: str = ""
    source_project_id: str = ""
    checked_out_by: str = ""
    lease_id: str = ""
    checked_out_session: str = Field(default="", exclude=True, repr=False)


class _ProjectSpecBase(StrictModel):
    schema_version: int = 5
    solver_mode: Literal["kinematic", "dynamic"] = "kinematic"
    id: str = Field(default_factory=lambda: new_id("project"))
    name: str = "New MuJoCo Project"
    description: str = ""
    category: str = "None"
    tags: list[str] = Field(default_factory=list)
    mesh_root: str = ""
    output_dir: str = ""
    template_scene: str = ""
    layers: list[LayerSpec] = Field(default_factory=list)
    drives: list[DriveSpec] = Field(default_factory=list)
    distance_pairs: list[DistancePairSpec] = Field(default_factory=list)
    distance_sampling: DistanceSamplingSettings = Field(default_factory=DistanceSamplingSettings)
    kinematic_closures: list[KinematicClosureSpec] = Field(default_factory=list)
    variables: dict[str, NumericExpression] = Field(default_factory=dict)
    parameter_aliases: dict[str, str] = Field(default_factory=dict)
    simulation: SimulationSettings = Field(default_factory=SimulationSettings)
    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings)
    quick_optimization: QuickOptimizationSettings = Field(default_factory=QuickOptimizationSettings)
    result_layout: ResultLayout = Field(default_factory=ResultLayout)
    viewer_control: ViewerControlSettings = Field(default_factory=ViewerControlSettings)
    animation_html: AnimationHtmlSettings = Field(default_factory=AnimationHtmlSettings)
    agent_settings: AgentSettings = Field(default_factory=AgentSettings)
    lifecycle: ProjectLifecycle = Field(default_factory=ProjectLifecycle)
    archive_order: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def demo(cls) -> "ProjectSpec":
        joint = JointSpec(name="joint1", type="rotation", axis="0, 1, 0")
        layer = LayerSpec(name="rotating_arm", joints=[joint])
        drive = DriveSpec(
            name="act1",
            joint_id=joint.id,
            segments=[
                DriveSegmentSpec(name="forward", start=0, duration=2, travel=90),
                DriveSegmentSpec(name="return", start=3, duration=2, travel=-90),
            ],
        )
        return cls(
            name="Demo rotary mechanism",
            description="API-first demo with a forward and return drive.",
            layers=[layer],
            drives=[drive],
            distance_pairs=[DistancePairSpec(name=f"distance{i}") for i in range(1, 6)],
            variables={"speed_scale": 1.0},
        )


# Migration compatibility: older UI snapshots sometimes serialized optional
# nested project sections as JSON null or left null placeholder rows. Pydantic
# 2 then raises an opaque "Input should be a valid dictionary ..." during
# simulation-worker ProjectSpec.model_validate, before simulation even starts.
# Reuse each schema field's existing default; never coerce a non-null invalid
# value (e.g. a string in layers) or turn an unknown nested object into one.
def normalize_legacy_null_project_fields(raw: Any) -> Any:
    if not isinstance(raw, dict):
        return raw
    value = dict(raw)
    root_lists = (
        'tags', 'layers', 'drives', 'distance_pairs', 'kinematic_closures',
        'archive_order',
    )
    root_maps = ('variables', 'parameter_aliases', 'metadata')
    root_objects = (
        'distance_sampling', 'simulation', 'optimization',
        'quick_optimization', 'result_layout', 'viewer_control',
        'animation_html', 'agent_settings', 'lifecycle',
    )

    def repair_fields(obj: Any, *, lists: tuple[str, ...] = (),
                      maps: tuple[str, ...] = (),
                      objects: tuple[str, ...] = ()) -> Any:
        if not isinstance(obj, dict):
            return obj
        result = dict(obj)
        for key in (*lists, *maps, *objects):
            if key in result and result[key] is None:
                # Missing uses the declared model default_factory/default.
                del result[key]
        for key in lists:
            if isinstance(result.get(key), list) and any(item is None for item in result[key]):
                result[key] = [item for item in result[key] if item is not None]
        return result

    value = repair_fields(value, lists=root_lists, maps=root_maps, objects=root_objects)

    def repair_list(items: Any, **kwargs: Any) -> Any:
        if not isinstance(items, list):
            return items
        return [repair_fields(item, **kwargs) for item in items]

    if 'layers' in value:
        value['layers'] = repair_list(value['layers'], lists=('meshes', 'joints'))
    if 'drives' in value:
        value['drives'] = repair_list(value['drives'], lists=('segments',))
        for drive in value['drives']:
            if isinstance(drive, dict) and isinstance(drive.get('segments'), list):
                drive['segments'] = repair_list(drive['segments'], lists=('points',), maps=('exchange_extra',))
    if isinstance(value.get('result_layout'), dict):
        result = repair_fields(value['result_layout'], lists=('axes','cursor_times','presets'))
        result['axes'] = repair_list(result.get('axes', []), lists=('curves',))
        value['result_layout'] = result
    if isinstance(value.get('viewer_control'), dict):
        value['viewer_control'] = repair_fields(
            value['viewer_control'], lists=('decoupled_drive_ids',),
            maps=('motor_values',), objects=('trajectory',),
        )
        if isinstance(value['viewer_control'].get('trajectory'), dict):
            value['viewer_control']['trajectory'] = repair_fields(
                value['viewer_control']['trajectory'], lists=('selected_meshes',),
            )
    for key, section_lists, section_maps in (
        ('optimization', ('variables','filters'), ()),
        ('quick_optimization', ('steps',), ('last_run',)),
    ):
        if isinstance(value.get(key), dict):
            value[key] = repair_fields(value[key], lists=section_lists, maps=section_maps)
    return value


if PYDANTIC_V2:
    class ProjectSpec(_ProjectSpecBase):
        @model_validator(mode="before")
        @classmethod
        def migrate_nullable_legacy_sections(cls, value: Any) -> Any:
            return normalize_legacy_null_project_fields(value)

        @field_validator("id")
        @classmethod
        def safe_project_id(cls, value: str) -> str:
            if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in value):
                raise ValueError("project id may contain only letters, numbers, '_' and '-'")
            return value

        @model_validator(mode="after")
        def remove_distance_pair_variables(self) -> "ProjectSpec":
            cleaned = strip_distance_pair_variables(self.variables, (pair.name for pair in self.distance_pairs))
            if cleaned != self.variables:
                object.__setattr__(self, "variables", cleaned)
            return self
else:
    class ProjectSpec(_ProjectSpecBase):
        @root_validator(pre=True)
        def migrate_nullable_legacy_sections(cls, values):
            return normalize_legacy_null_project_fields(values)

        @validator("id")
        def safe_project_id(cls, value: str) -> str:
            if not value or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in value):
                raise ValueError("project id may contain only letters, numbers, '_' and '-'")
            return value

        @root_validator
        def remove_distance_pair_variables(cls, values):
            pairs = values.get("distance_pairs", []) or []
            values["variables"] = strip_distance_pair_variables(
                values.get("variables", {}),
                (getattr(pair, "name", "") for pair in pairs),
            )
            return values
