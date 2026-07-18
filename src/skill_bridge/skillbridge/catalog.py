import os
from collections import defaultdict
from skillbridge.models import InstanceState, EntryType, AgentSkillInstance, SkillRow, SkillMatrix, AgentConfig
from skillbridge.database import get_source_selection, upsert_source_selection


def determine_instance_state(
    instance: dict,
    source_path: str,
    source_fingerprint: str,
) -> InstanceState:
    entry_type = instance["entry_type"]
    path = instance["path"]

    if entry_type == "BROKEN_LINK":
        return InstanceState.BROKEN_LINK
    if entry_type == "INVALID":
        return InstanceState.INVALID

    if source_path and path == source_path:
        return InstanceState.SOURCE_LOCAL

    if entry_type == "JUNCTION":
        resolved = instance.get("resolved_target", "")
        if source_path and resolved and os.path.normpath(resolved) == os.path.normpath(source_path):
            return InstanceState.SHARED_LINK
        return InstanceState.BROKEN_LINK

    if entry_type == "REAL_DIR":
        if not source_path:
            return InstanceState.LOCAL_COPY
        if instance["fingerprint"] == source_fingerprint and source_fingerprint:
            return InstanceState.LOCAL_COPY
        return InstanceState.CONFLICT

    return InstanceState.INVALID


def infer_source(instances: list[dict]) -> tuple[str, str]:
    real_dirs = [i for i in instances if i["entry_type"] == "REAL_DIR"]

    if not real_dirs:
        return ("", "")

    if len(real_dirs) == 1:
        return (real_dirs[0]["path"], real_dirs[0]["agent_id"])

    if len(real_dirs) > 1:
        fingerprints = set(i.get("fingerprint", "") for i in real_dirs)
        if len(fingerprints) == 1:
            return (real_dirs[0]["path"], real_dirs[0]["agent_id"])

    return ("", "")


def build_skill_matrix(agents: list[AgentConfig], scan_data: list[dict]) -> SkillMatrix:
    by_skill: dict[str, list[dict]] = defaultdict(list)
    for entry in scan_data:
        by_skill[entry["skill_name"]].append(entry)

    skills = []
    for skill_name, instances in by_skill.items():
        selection = get_source_selection(skill_name)
        source_path = selection["source_path"] if selection else ""
        source_agent_id = selection["source_agent_id"] if selection else ""

        if not source_path:
            source_path, source_agent_id = infer_source(instances)
            if source_path and source_agent_id:
                upsert_source_selection(skill_name, source_agent_id, source_path)

        source_fingerprint = ""
        for i in instances:
            if i["path"] == source_path:
                source_fingerprint = i.get("fingerprint", "")
                break

        instance_objs = []
        description = ""
        for i in instances:
            state = determine_instance_state(i, source_path, source_fingerprint)
            agent_config = next((a for a in agents if a.id == i["agent_id"]), None)
            instance_objs.append(AgentSkillInstance(
                agent_id=i["agent_id"],
                agent_name=agent_config.name if agent_config else i["agent_id"],
                skill_name=i["skill_name"],
                path=i["path"],
                entry_type=i["entry_type"],
                resolved_target=i.get("resolved_target", ""),
                fingerprint=i.get("fingerprint", ""),
                state=state,
                has_skill_md=i.get("has_skill_md", False),
                description=i.get("description", ""),
                validation_errors=i.get("validation_errors", []),
            ))
            if i.get("description"):
                description = i["description"]

        instances_by_agent = {inst.agent_id: inst for inst in instance_objs}

        for agent in agents:
            if agent.id not in instances_by_agent:
                missing = AgentSkillInstance(
                    agent_id=agent.id,
                    agent_name=agent.name,
                    skill_name=skill_name,
                    path="",
                    entry_type=EntryType.REAL_DIR,
                    state=InstanceState.MISSING,
                )
                instance_objs.append(missing)
                instances_by_agent[agent.id] = missing

        skills.append(SkillRow(
            skill_name=skill_name,
            description=description,
            source_agent_id=source_agent_id or None,
            instances=instance_objs,
            instances_by_agent=instances_by_agent,
        ))

    skills.sort(key=lambda s: s.skill_name)
    return SkillMatrix(skills=skills, agents=agents)
