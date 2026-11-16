"""Protocol routes shared by the browser, scripts and LLM clients."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

from fastapi import APIRouter, Body, HTTPException, Query, WebSocket, WebSocketDisconnect

from .manager import KernelManager
from .planner import Planner
from .state_tree import StateTree
from .tool_registry import ToolRegistry
from ..auth import active_identity, require_project_access, reset_active_identity, set_active_identity


def create_core_router(
    manager: KernelManager,
    websocket_identity: Callable[[WebSocket], Any] | None = None,
    lifecycle_handler: Callable[[str, dict[str, Any], Any], dict[str, Any]] | None = None,
    write_activity: Callable[[str, Any, str], None] | None = None,
) -> APIRouter:
    router = APIRouter(tags=["state-command-core"])
    registry = ToolRegistry()
    registry.discover("app.tools")
    planner = Planner(registry)

    def kernel(project_id: str):
        try:
            instance = manager.get(project_id)
            require_project_access(instance.project())
            return instance
        except (KeyError, ValueError) as exc:
            raise HTTPException(404, "Project not found") from exc

    def tool(tool_id: str):
        try:
            return registry.get(tool_id)
        except KeyError as exc:
            raise HTTPException(404, f"Unknown tool: {tool_id}") from exc

    @router.get("/api/tools")
    def list_tools() -> dict[str, Any]:
        return {"tools": registry.catalog(), "llm_functions": registry.llm_functions()}

    @router.get("/api/tools/{tool_id}")
    def get_tool(tool_id: str) -> dict[str, Any]:
        return tool(tool_id).as_registry_entry()

    @router.get("/api/tools/{tool_id}/schema")
    def tool_schema(tool_id: str) -> dict[str, Any]:
        item = tool(tool_id)
        return {"input_schema": item.input_schema(), "output_schema": item.output_schema()}

    @router.get("/api/tools/{tool_id}/ui-schema")
    def tool_ui_schema(tool_id: str) -> dict[str, Any]:
        return tool(tool_id).ui_schema()

    @router.post("/api/tools/{tool_id}/validate")
    def validate_tool(tool_id: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        return tool(tool_id).validate(payload).__dict__

    @router.post("/api/projects/{project_id}/tools/{tool_id}/dry-run")
    def dry_run_tool(project_id: str, tool_id: str,
                     payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        with manager.acquire(project_id) as instance:
            require_project_access(instance.project())
            result = instance.bus.dry_run({"tool_id": tool_id, "params": payload})
            return result.to_dict()

    def execute(project_id: str, command: dict[str, Any], confirmed: bool) -> dict[str, Any]:
        selected = tool(str(command.get("tool_id", "")))
        if selected.effect == "write" and not confirmed:
            raise HTTPException(409, "Write commands require dry-run review and confirmed=true")
        command = dict(command)
        if selected.id == "project.lifecycle" and lifecycle_handler is not None:
            identity = active_identity()
            command["actor"] = identity.username
            command["params"] = {
                **dict(command.get("params", {})), "actor": identity.username,
                "lease_id": identity.lease_id,
            }
            return lifecycle_handler(project_id, command, identity)
        with manager.acquire(project_id) as instance:
            require_project_access(instance.project())
            if selected.effect == "write":
                identity = require_project_access(instance.project(), write=True)
                command["actor"] = identity.username
            result = instance.bus.dispatch(command)
            if not result.ok:
                raise HTTPException(422, result.errors)
            if selected.effect == "write" and write_activity is not None:
                write_activity(project_id, active_identity(), selected.id)
            return result.to_dict()


    @router.post("/api/projects/{project_id}/commands")
    def project_command(project_id: str, body: dict[str, Any] = Body(...),
                        confirmed: bool = Query(False)) -> dict[str, Any]:
        command = body.get("command", body)
        return execute(project_id, command, bool(body.get("confirmed", confirmed)))

    @router.post("/api/commands")
    def generic_command(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        project_id = str(body.get("project_id", ""))
        if not project_id:
            raise HTTPException(422, "project_id is required")
        return execute(project_id, body.get("command", body), bool(body.get("confirmed", False)))

    def event_payload(instance, since: int) -> dict[str, Any]:
        return {
            "cursor": instance.events.cursor(),
            "events": [{**event.to_dict(), "undone": instance.events.is_undone(event.event_id)}
                       for event in instance.events.since(since)],
        }

    @router.get("/api/projects/{project_id}/events")
    def project_events(project_id: str, since: int = 0) -> dict[str, Any]:
        return event_payload(kernel(project_id), max(0, since))

    @router.get("/api/events")
    def generic_events(project_id: str, since: int = 0) -> dict[str, Any]:
        return event_payload(kernel(project_id), max(0, since))

    @router.websocket("/api/events/stream")
    async def event_stream(websocket: WebSocket, project_id: str, since: int = 0) -> None:
        identity = websocket_identity(websocket) if websocket_identity else None
        if identity is None:
            await websocket.close(code=4401, reason="authentication required")
            return
        identity_token = set_active_identity(identity)
        await websocket.accept()
        cursor = max(0, since)
        try:
            # TODO(S5): pin/stream ownership is intentionally deferred to the bounded WebSocket work.
            instance = kernel(project_id)
            while True:
                if instance.events.cursor() > cursor:
                    payload = event_payload(instance, cursor)
                    cursor = payload["cursor"]
                    await websocket.send_json(payload)
                await asyncio.sleep(0.2)
        except WebSocketDisconnect:
            return
        finally:
            reset_active_identity(identity_token)

    @router.get("/api/projects/{project_id}/state")
    def project_state(project_id: str, detail: str = Query("full")) -> dict[str, Any]:
        instance = kernel(project_id)
        # The editor already receives ProjectSpec from /edit-session. Send UI
        # state only, rather than serializing the same large project twice.
        if detail == "ui":
            return {"state": {"ui": instance.state.peek("ui")}, "cursor": instance.events.cursor()}
        if detail != "full":
            raise HTTPException(422, "state detail must be full or ui")
        return {"state": instance.state.snapshot(), "cursor": instance.events.cursor()}

    @router.post("/api/projects/{project_id}/undo")
    def project_undo(project_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        if not body.get("confirmed", False):
            raise HTTPException(409, "Undo requires confirmed=true")
        with manager.acquire(project_id) as instance:
            require_project_access(instance.project(), write=True)
            result = instance.bus.undo(client=body.get("client", "human_ui"))
            if not result.ok:
                raise HTTPException(409, result.errors)
            if write_activity is not None:
                write_activity(project_id, active_identity(), "history.undo")
            return result.to_dict()

    @router.post("/api/projects/{project_id}/redo")
    def project_redo(project_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        if not body.get("confirmed", False):
            raise HTTPException(409, "Redo requires confirmed=true")
        with manager.acquire(project_id) as instance:
            require_project_access(instance.project(), write=True)
            result = instance.bus.redo(client=body.get("client", "human_ui"))
            if not result.ok:
                raise HTTPException(409, result.errors)
            if write_activity is not None:
                write_activity(project_id, active_identity(), "history.redo")
            return result.to_dict()

    @router.get("/api/projects/{project_id}/changesets")
    def list_changesets(project_id: str) -> dict[str, Any]:
        return {"changesets": kernel(project_id).changesets.list()}

    @router.post("/api/projects/{project_id}/changesets", status_code=201)
    def create_changeset(project_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            with manager.acquire(project_id) as instance:
                require_project_access(instance.project(), write=True)
                item = instance.changesets.create(
                    body.get("title", "未命名提案"), body.get("commands", []),
                    source=body.get("source", "human_ui"), rationale=body.get("rationale"),
                )
                return item.to_dict()
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/api/projects/{project_id}/changesets/{change_id}")
    def get_changeset(project_id: str, change_id: str) -> dict[str, Any]:
        try:
            return kernel(project_id).changesets.get(change_id).to_dict()
        except KeyError as exc:
            raise HTTPException(404, "ChangeSet not found") from exc

    @router.put("/api/projects/{project_id}/changesets/{change_id}")
    def update_changeset(project_id: str, change_id: str,
                         body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            with manager.acquire(project_id) as instance:
                require_project_access(instance.project(), write=True)
                return instance.changesets.update_commands(change_id, body.get("commands", [])).to_dict()
        except KeyError as exc:
            raise HTTPException(404, "ChangeSet not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/projects/{project_id}/changesets/{change_id}/dry-run")
    def dry_run_changeset(project_id: str, change_id: str) -> dict[str, Any]:
        try:
            with manager.acquire(project_id) as instance:
                require_project_access(instance.project())
                return instance.changesets.dry_run(change_id, instance.bus)
        except KeyError as exc:
            raise HTTPException(404, "ChangeSet not found") from exc

    @router.post("/api/projects/{project_id}/changesets/{change_id}/commit")
    def commit_changeset(project_id: str, change_id: str,
                         body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        if not body.get("confirmed", False):
            raise HTTPException(409, "ChangeSet commit requires confirmed=true")
        try:
            with manager.acquire(project_id) as instance:
                require_project_access(instance.project(), write=True)
                result = instance.changesets.commit(change_id, instance.bus)
        except KeyError as exc:
            raise HTTPException(404, "ChangeSet not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not result.get("ok"):
            raise HTTPException(422, result.get("errors", []))
        if write_activity is not None:
            write_activity(project_id, active_identity(), "changeset.commit")
        return result

    @router.post("/api/projects/{project_id}/ai/generate-changeset")
    def generate_changeset(project_id: str, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
        instance = kernel(project_id)
        proposal = planner.plan(str(body.get("goal", "")), instance.state)
        return instance.changesets.create(proposal["title"], proposal["commands"],
                                          source="llm_agent", rationale=proposal["rationale"]).to_dict()

    @router.get("/api/projects/{project_id}/core-artifacts")
    def list_core_artifacts(project_id: str) -> dict[str, Any]:
        return {"artifacts": kernel(project_id).artifacts.list()}

    @router.get("/api/projects/{project_id}/core-artifacts/{handle}")
    def get_core_artifact(project_id: str, handle: str) -> Any:
        try:
            return kernel(project_id).artifacts.get(handle)
        except KeyError as exc:
            raise HTTPException(404, "Artifact not found") from exc

    @router.post("/api/projects/{project_id}/diff")
    def project_diff(project_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        instance = kernel(project_id)
        left = instance.state.snapshot()
        version_id = body.get("base_version")
        if version_id:
            try:
                left = {"project": manager.store.get_version(project_id, version_id).model_dump(),
                        "ui": instance.state.get("ui")}
            except (KeyError, ValueError) as exc:
                raise HTTPException(404, "Project version not found") from exc
        right = instance.state.snapshot()
        watched = body.get("watched_paths") or []
        if not watched:
            watched = ["project.name", "project.mesh_root", "project.layers", "project.drives",
                       "project.distance_pairs", "project.variables", "project.simulation",
                       "project.optimization", "project.result_layout"]
        left_tree, right_tree = StateTree(left), StateTree(right)
        differences = []
        for path in watched:
            try:
                before = left_tree.get(path)
            except Exception:  # noqa: BLE001
                before = None
            try:
                after = right_tree.get(path)
            except Exception:  # noqa: BLE001
                after = None
            if before != after:
                differences.append({"path": path, "before": before, "after": after})
        return {"base_version": version_id, "watched_paths": watched, "differences": differences}

    return router
