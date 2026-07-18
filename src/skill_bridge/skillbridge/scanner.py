import os
import json
import hashlib
from pathlib import Path
from skillbridge.platform.windows import batch_check_paths


def parse_skill_md(skill_dir: str) -> dict:
    md_path = os.path.join(skill_dir, "SKILL.md")
    if not os.path.isfile(md_path):
        return {"name": os.path.basename(skill_dir), "description": "", "has_skill_md": False}
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()
        name = os.path.basename(skill_dir)
        description = ""
        lines = content.split("\n")
        in_frontmatter = False
        frontmatter_lines = []
        for line in lines:
            if line.strip() == "---":
                if not in_frontmatter:
                    in_frontmatter = True
                else:
                    break
            elif in_frontmatter:
                frontmatter_lines.append(line)
        for line in frontmatter_lines:
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip().strip('"').strip("'")
                if key == "name":
                    name = value
                elif key == "description":
                    description = value
        return {"name": name, "description": description, "has_skill_md": True}
    except Exception:
        return {"name": os.path.basename(skill_dir), "description": "", "has_skill_md": False}


def compute_fingerprint(skill_dir: str) -> str:
    try:
        entries = []
        for root, dirs, files in os.walk(skill_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".git") and d != "__pycache__" and d != "node_modules"]
            for f in files:
                fpath = os.path.join(root, f)
                try:
                    stat = os.stat(fpath)
                    rel = os.path.relpath(fpath, skill_dir)
                    entries.append((rel, stat.st_size, int(stat.st_mtime)))
                except OSError:
                    pass
        entries.sort(key=lambda x: x[0])
        data = json.dumps(entries, sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    except Exception:
        return ""


def check_directory_available(path: str) -> tuple[bool, str]:
    """Check if directory exists and is accessible."""
    if not os.path.exists(path):
        return False, "Directory does not exist"
    if not os.path.isdir(path):
        return False, "Path is not a directory"
    if not os.access(path, os.R_OK):
        return False, "No read permission"
    try:
        os.listdir(path)
    except PermissionError:
        return False, "No read permission"
    except OSError as e:
        return False, f"Access error: {e}"
    return True, ""


def scan_agent_skills(agent_id: str, skill_root: str, ignore_patterns: list[str]) -> list[dict]:
    ok, err = check_directory_available(skill_root)
    if not ok:
        return []
    entries = []
    for entry in os.listdir(skill_root):
        if entry == "skillbridge-backups":
            continue
        if any(Path(entry).match(p) for p in ignore_patterns):
            continue
        entry_path = os.path.join(skill_root, entry)
        if not os.path.isdir(entry_path):
            continue
        entries.append((entry, entry_path))

    if not entries:
        return []

    # Single batch PowerShell call for all path type checks
    batch_paths = [p for _, p in entries]
    batch_results = batch_check_paths(batch_paths)
    path_map = {r["path"]: r for r in batch_results}

    results = []
    for entry, entry_path in entries:
        info = parse_skill_md(entry_path)
        skill_name = info["name"]
        if not skill_name:
            continue

        check = path_map.get(entry_path, {})
        is_junction = check.get("is_junction", False)
        is_real_dir = check.get("is_real_dir", False)
        resolved = check.get("resolved", "")

        entry_type = "UNKNOWN"
        resolved_target = ""
        fingerprint = ""
        state = "UNKNOWN"
        validation_errors = []

        if is_junction:
            entry_type = "JUNCTION"
            resolved_target = resolved
            if resolved_target in ("BROKEN", ""):
                entry_type = "BROKEN_LINK"
                state = "BROKEN_LINK"
            else:
                if os.path.isdir(resolved_target):
                    fingerprint = compute_fingerprint(resolved_target)
                state = "SHARED_LINK"
            if not info["has_skill_md"]:
                validation_errors.append("SKILL.md not found at junction target")
        elif is_real_dir:
            entry_type = "REAL_DIR"
            fingerprint = compute_fingerprint(entry_path)
            state = "LOCAL_COPY"
        else:
            entry_type = "INVALID"
            state = "INVALID"
            validation_errors.append("Cannot determine directory type")

        if not info["has_skill_md"] and "INVALID" not in state:
            state = "INVALID"
            if "SKILL.md" not in str(validation_errors):
                validation_errors.append("Missing SKILL.md")

        results.append({
            "agent_id": agent_id,
            "skill_name": skill_name,
            "path": entry_path,
            "entry_type": entry_type,
            "resolved_target": resolved_target,
            "fingerprint": fingerprint,
            "state": state,
            "has_skill_md": info["has_skill_md"],
            "description": info["description"],
            "validation_errors": validation_errors,
        })
    return results
