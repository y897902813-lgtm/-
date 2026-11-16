"""Referential-integrity repairs for project entities.

Deletion is a semantic state change: dangling drive and mapping references must
not survive merely because the UI happened to remove a joint first.
"""
from __future__ import annotations

from .models import ProjectSpec


def repair_joint_references(project: ProjectSpec) -> dict[str, list[str]]:
    joint_ids = {joint.id for layer in project.layers for joint in layer.joints}
    # First remove drives whose explicit physical joint disappeared.  Only then
    # derive virtual-source reachability so a deleted target cannot keep an
    # otherwise orphaned empty-joint drive alive.
    candidates = [drive for drive in project.drives if not drive.joint_id or drive.joint_id in joint_ids]
    virtual_source_ids = {
        segment.mapping_source_joint_id[6:]
        for drive in candidates for segment in drive.segments
        if segment.profile == "mapping" and str(segment.mapping_source_joint_id).startswith("drive:")
    }
    # A drive with no physical joint is a first-class virtual mapping source.
    # Do not delete it merely because no follower currently references it; the
    # user may deliberately configure the source before wiring companions.
    kept = list(candidates)
    kept_ids = {drive.id for drive in kept}
    removed_drives = [drive.name for drive in project.drives if drive.id not in kept_ids]
    project.drives = kept

    cleared_mappings: list[str] = []
    for drive in project.drives:
        for segment in drive.segments:
            source = str(segment.mapping_source_joint_id or "")
            source_drive_id = source[6:] if source.startswith("drive:") else ""
            if source and source not in joint_ids and source_drive_id not in kept_ids:
                segment.mapping_source_joint_id = ""
                cleared_mappings.append(f"{drive.name}/{segment.name}")
    return {"removed_drives": removed_drives, "cleared_mappings": cleared_mappings}


def cascade_renamed_references(before: ProjectSpec, after: ProjectSpec) -> list[str]:
    """Repair display-name references while stable IDs keep joints/curves intact."""
    changed: list[str] = []
    old_drives = {drive.id: drive for drive in before.drives}
    for drive in after.drives:
        previous = old_drives.get(drive.id)
        if not previous:
            continue
        old_segments = {segment.id: segment for segment in previous.segments}
        for candidate in after.drives:
            for segment in candidate.segments:
                for current in drive.segments:
                    old = old_segments.get(current.id)
                    if not old:
                        continue
                    source = f"{previous.name}/{old.name}"
                    if segment.reference == source:
                        segment.reference = f"{drive.name}/{current.name}"
                        changed.append(source)
    return changed
