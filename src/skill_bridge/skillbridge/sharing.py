import os, json
from datetime import datetime
from skillbridge.database import log_operation, update_operation_status
from skillbridge.platform.windows import (
    create_junction, remove_junction, backup_real_directory,
    is_junction, is_real_directory, resolve_junction_target, move_directory,
    batch_check_paths
)
from skillbridge.security import normalize_path
from skillbridge.config import BACKUP_DIR_NAME


def enable_sharing(skill_name: str, source_path: str, target_agent_root: str, target_agent_id: str) -> dict:
    op_id = None
    backup_dir = ""
    try:
        norm_source = normalize_path(source_path)
        norm_target_root = normalize_path(target_agent_root)

        if not os.path.isdir(norm_source):
            return {"success": False, "error": f"Source directory does not exist: {norm_source}"}
        if not os.path.isdir(norm_target_root):
            return {"success": False, "error": f"Target agent root does not exist: {norm_target_root}"}

        target_path = os.path.join(norm_target_root, skill_name)

        op_id = log_operation("ENABLE_SHARE", skill_name, target_agent_id, "IN_PROGRESS",
                              {"source": norm_source, "target": target_path})

        if os.path.exists(target_path):
            # Batch is_junction + resolve_junction_target + is_real_directory into one PowerShell call
            batch = batch_check_paths([target_path])
            if batch:
                chk = batch[0]
                if chk.get("is_junction"):
                    resolved = chk.get("resolved", "")
                    if resolved and resolved != "BROKEN" and os.path.normpath(resolved) == os.path.normpath(norm_source):
                        update_operation_status(op_id, "SUCCESS")
                        return {"success": True, "message": "Already shared"}
                    ok, err = remove_junction(target_path)
                    if not ok:
                        update_operation_status(op_id, "FAILED", err)
                        return {"success": False, "error": f"Failed to remove old junction: {err}"}
                elif chk.get("is_real_dir"):
                    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    backup_dir = os.path.join(norm_target_root, BACKUP_DIR_NAME, timestamp, skill_name)
                    ok, err = backup_real_directory(target_path, backup_dir)
                    if not ok:
                        update_operation_status(op_id, "FAILED", err)
                        return {"success": False, "error": f"Failed to backup: {err}"}
                else:
                    update_operation_status(op_id, "FAILED", "Target exists but is neither junction nor directory")
                    return {"success": False, "error": "Target exists in unknown state"}

        ok, err = create_junction(target_path, norm_source)
        if not ok:
            if backup_dir:
                move_directory(backup_dir, target_path)
            update_operation_status(op_id, "FAILED", err)
            return {"success": False, "error": f"Failed to create junction: {err}"}

        update_operation_status(op_id, "SUCCESS")
        result = {"success": True, "message": f"Shared {skill_name} to {target_agent_id}"}
        if backup_dir:
            result["backup_path"] = backup_dir
        return result

    except Exception as e:
        if op_id:
            update_operation_status(op_id, "FAILED", str(e))
        return {"success": False, "error": str(e)}


def disable_sharing(skill_name: str, source_path: str, target_agent_root: str, target_agent_id: str) -> dict:
    op_id = None
    try:
        norm_target_root = normalize_path(target_agent_root)
        target_path = os.path.join(norm_target_root, skill_name)

        if not os.path.exists(target_path):
            log_operation("DISABLE_SHARE", skill_name, target_agent_id, "SUCCESS",
                          {"message": "Target did not exist"})
            return {"success": True, "message": "Nothing to remove"}

        # Batch is_junction + resolve_junction_target into one PowerShell call
        batch = batch_check_paths([target_path])
        if not batch or not batch[0].get("is_junction"):
            return {"success": False, "error": "Target is a real directory, not a junction. Use backup + manual handling."}

        resolved_target = batch[0].get("resolved", "")
        if source_path and resolved_target and resolved_target != "BROKEN" and os.path.normpath(resolved_target) != os.path.normpath(source_path):
            return {"success": False, "error": f"Junction points to {resolved_target}, not the expected source {source_path}"}

        op_id = log_operation("DISABLE_SHARE", skill_name, target_agent_id, "IN_PROGRESS",
                              {"target": target_path, "source": resolved_target if resolved_target not in ("BROKEN", "") else ""})

        ok, err = remove_junction(target_path)
        if not ok:
            update_operation_status(op_id, "FAILED", err)
            return {"success": False, "error": err}

        update_operation_status(op_id, "SUCCESS")
        return {"success": True, "message": f"Removed junction for {skill_name}"}

    except Exception as e:
        if op_id:
            update_operation_status(op_id, "FAILED", str(e))
        return {"success": False, "error": str(e)}


def rollback_operation(op_id: int) -> dict:
    from skillbridge.database import get_db
    with get_db() as db:
        row = db.execute("SELECT * FROM operations WHERE id = ?", (op_id,)).fetchone()
    if not row:
        return {"success": False, "error": "Operation not found"}
    op = dict(row)
    if op["status"] != "SUCCESS":
        return {"success": False, "error": f"Cannot rollback operation with status '{op['status']}'"}

    action = op["action"]
    skill_name = op["skill_name"]
    details = json.loads(op.get("details", "{}"))
    backup_path = op.get("backup_path", "")

    try:
        if action == "ENABLE_SHARE":
            target = details.get("target", "")
            if target and os.path.exists(target) and is_junction(target):
                ok, err = remove_junction(target)
                if not ok:
                    return {"success": False, "error": f"Failed to remove junction: {err}"}
            if backup_path and os.path.isdir(backup_path):
                ok, err = move_directory(backup_path, target)
                if not ok:
                    return {"success": False, "error": f"Failed to restore backup: {err}"}
            update_operation_status(op_id, "ROLLED_BACK")
            return {"success": True, "message": f"Rolled back ENABLE_SHARE for {skill_name}"}

        elif action == "DISABLE_SHARE":
            source = details.get("source", "")
            target = details.get("target", "")
            if not source or not target:
                from skillbridge.database import get_source_selection
                sel = get_source_selection(skill_name)
                if sel:
                    source = sel["source_path"]
            if source and target:
                ok, err = create_junction(target, source)
                if not ok:
                    return {"success": False, "error": f"Failed to recreate junction: {err}"}
                update_operation_status(op_id, "ROLLED_BACK")
                return {"success": True, "message": f"Rolled back DISABLE_SHARE for {skill_name}"}
            return {"success": False, "error": "Insufficient info to rollback DISABLE_SHARE"}

        else:
            return {"success": False, "error": f"No rollback handler for action '{action}'"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def migrate_source(skill_name: str, new_agent_id: str, new_source_path: str) -> dict:
    """Change source and rebuild all existing junctions."""
    from skillbridge.database import get_source_selection, upsert_source_selection, get_all_agents, get_scan_cache
    old_sel = get_source_selection(skill_name)
    old_source = old_sel["source_path"] if old_sel else ""

    upsert_source_selection(skill_name, new_agent_id, new_source_path)

    agents = get_all_agents()
    scan_data = get_scan_cache()
    migrated = 0
    errors = []

    for agent in agents:
        if not agent.get("enabled"):
            continue
        agent_id = agent["id"]
        if agent_id == new_agent_id:
            continue

        target_path = os.path.join(normalize_path(agent["skill_root"]), skill_name)
        if not os.path.exists(target_path):
            continue
        if not is_junction(target_path):
            continue

        resolved = resolve_junction_target(target_path)
        if old_source and resolved and os.path.normpath(resolved) == os.path.normpath(old_source):
            ok, err = remove_junction(target_path)
            if not ok:
                errors.append(f"{agent_id}: failed to remove old junction: {err}")
                continue
            ok, err = create_junction(target_path, normalize_path(new_source_path))
            if not ok:
                errors.append(f"{agent_id}: failed to recreate junction: {err}")
                continue
            migrated += 1

    if errors:
        return {"success": True, "message": f"Source migrated. {migrated} junctions rebuilt.", "errors": errors}
    return {"success": True, "message": f"Source set to {new_agent_id}. {migrated} junctions rebuilt."}
