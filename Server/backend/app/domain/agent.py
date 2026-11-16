from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import Field

from .models import ProjectSpec, StrictModel
from .llm import ConversationStore, LLMCredentialStore, chat_completion, parse_json_object
from .optimization import run_optimization
from .project_store import ProjectStore
from .simulation import run_project_simulation
from .validation import has_errors, validate_project
from .xml_generator import generate_project


class SkillStep(StrictModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    continue_on_error: bool = False


class SkillDefinition(StrictModel):
    id: str
    name: str
    description: str
    steps: list[SkillStep]
    max_steps: int = Field(default=20, ge=1, le=100)


BUILTIN_SKILLS = [
    SkillDefinition(
        id="validate-generate",
        name="检查项目并生成模型",
        description="检查层级、运动副、驱动和模型文件；确认无阻断错误后生成 MuJoCo XML 与驱动配置。",
        steps=[SkillStep(tool="validate_project"), SkillStep(tool="generate_project")],
    ),
    SkillDefinition(
        id="simulate-report",
        name="运行仿真并整理结果",
        description="依次检查项目、生成模型并运行轨迹仿真，产出关节曲线、测距结果和可下载文件。",
        steps=[SkillStep(tool="validate_project"), SkillStep(tool="generate_project"), SkillStep(tool="run_simulation")],
    ),
    SkillDefinition(
        id="optimize-schedule",
        name="优化驱动时序",
        description="检查项目后按照批量优化页配置的变量范围、目标和方向搜索更优的驱动时序。",
        steps=[SkillStep(tool="validate_project"), SkillStep(tool="run_optimization")],
    ),
]


@dataclass
class AgentContext:
    project: ProjectSpec
    store: ProjectStore
    result_root: Path
    progress: Callable[[float, str], None]
    should_cancel: Callable[[], bool]
    current_project: Callable[[], ProjectSpec]
    operation_log: Callable[[], list[dict[str, Any]]]
    artifact_context: Callable[[], list[dict[str, Any]]]
    resolved_variables: Callable[[], dict[str, Any]]
    conversation: ConversationStore


class SkillStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[SkillDefinition]:
        skills = {skill.id: skill for skill in BUILTIN_SKILLS}
        for path in self.root.glob("*.json"):
            try:
                item = SkillDefinition.model_validate_json(path.read_text("utf-8"))
                skills[item.id] = item
            except (OSError, ValueError):
                continue
        return list(skills.values())

    def get(self, skill_id: str) -> SkillDefinition:
        for item in self.list():
            if item.id == skill_id:
                return item
        raise KeyError(skill_id)

    def save(self, skill: SkillDefinition) -> SkillDefinition:
        if skill.id in {item.id for item in BUILTIN_SKILLS}:
            raise ValueError("built-in skills cannot be overwritten")
        if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in skill.id):
            raise ValueError("skill id may contain only letters, numbers, '-' and '_'")
        (self.root / f"{skill.id}.json").write_text(skill.model_dump_json(indent=2), encoding="utf-8")
        return skill


class AgentRunner:
    ALLOWED_TOOLS = {"validate_project", "generate_project", "run_simulation", "run_optimization", "save_project"}

    def __init__(self, skill_store: SkillStore, credentials: LLMCredentialStore):
        self.skill_store = skill_store
        self.credentials = credentials

    def plan_with_llm(self, context: AgentContext, goal: str, skill: SkillDefinition, history: list[dict[str, str]]) -> list[SkillStep]:
        project = context.current_project()
        settings = project.agent_settings
        api_key = self.credentials.api_key()
        if not api_key or not settings.model:
            return skill.steps
        realtime: dict[str, Any] = {"project": project.model_dump()}
        if settings.include_variables:
            realtime["resolved_variables"] = context.resolved_variables()
        if settings.include_operation_log:
            realtime["recent_operation_log"] = context.operation_log()
        if settings.include_artifacts:
            realtime["recent_artifacts"] = context.artifact_context()
        prompt = {
            "goal": goal,
            "skill": skill.model_dump(),
            "allowed_tools": sorted(self.ALLOWED_TOOLS),
            "realtime_software_context": realtime,
            "instruction": "只返回一个 JSON 对象，其中 steps 是 {tool, arguments, continue_on_error} 数组。只能使用 allowed_tools，不能超过 max_steps。根据实时变量、操作日志和产物判断，但任何写操作仍必须走允许的工具。",
        }
        messages = [
            {"role": "system", "content": "你是 MuJoCo Studio 的安全工程智能体。你能读取实时状态、事件日志和产物，但不得虚构工具或绕过命令/白名单。"},
            *history,
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ]
        parsed = parse_json_object(chat_completion(settings, api_key, messages))
        raw_steps = parsed.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("大模型计划缺少 steps 数组")
        return [SkillStep.model_validate(item) for item in raw_steps][: skill.max_steps]

    def run(self, context: AgentContext, skill_id: str, goal: str = "") -> dict[str, Any]:
        skill = self.skill_store.get(skill_id)
        settings = context.current_project().agent_settings
        history = context.conversation.context(settings.context_rounds)
        context.conversation.append("user", goal or f"执行 Skill：{skill.name}", skill_id=skill.id)
        try:
            steps = self.plan_with_llm(context, goal, skill, history)
            planning_mode = "llm" if self.credentials.api_key() and settings.model else "deterministic"
        except Exception as exc:  # fall back to safe deterministic skill
            steps = skill.steps
            planning_mode = f"deterministic_fallback: {exc}"
        if len(steps) > skill.max_steps:
            raise ValueError("agent plan exceeds the skill step limit")
        records: list[dict[str, Any]] = []
        for index, step in enumerate(steps):
            if context.should_cancel():
                raise InterruptedError("agent run cancelled")
            if step.tool not in self.ALLOWED_TOOLS:
                raise ValueError(f"tool is not allowed: {step.tool}")
            context.project = context.current_project()
            context.progress(index / max(len(steps), 1), f"Agent: {step.tool}")
            try:
                result = self._execute_tool(context, step)
                records.append({"step": index + 1, "tool": step.tool, "status": "completed", "result": result})
            except Exception as exc:
                records.append({"step": index + 1, "tool": step.tool, "status": "failed", "error": str(exc)})
                if not step.continue_on_error:
                    break
        context.progress(1.0, "Agent workflow complete")
        result = {"skill": skill.model_dump(), "goal": goal, "planning_mode": planning_mode, "steps": records}
        summary = f"已按“{skill.name}”完成规划与执行：{sum(item['status'] == 'completed' for item in records)}/{len(records)} 步成功；模式 {planning_mode}。"
        context.conversation.append("assistant", summary, skill_id=skill.id, planning_mode=planning_mode)
        result["assistant_message"] = summary
        return result

    def _execute_tool(self, context: AgentContext, step: SkillStep) -> Any:
        if step.tool == "validate_project":
            issues = validate_project(context.project, check_files=bool(step.arguments.get("check_files", True)))
            if has_errors(issues):
                raise ValueError("; ".join(issue.message for issue in issues if issue.severity == "error"))
            return [issue.model_dump() for issue in issues]
        if step.tool == "generate_project":
            return generate_project(context.project, context.store.outputs(context.project.id), check_files=bool(step.arguments.get("check_files", True)))
        if step.tool == "run_simulation":
            return run_project_simulation(context.project, context.result_root / "simulation", progress=context.progress, should_cancel=context.should_cancel)
        if step.tool == "run_optimization":
            return run_optimization(context.project, context.result_root / "optimization", progress=context.progress, should_cancel=context.should_cancel)
        if step.tool == "save_project":
            return context.store.save(context.project).model_dump()
        raise ValueError(f"unsupported tool: {step.tool}")
