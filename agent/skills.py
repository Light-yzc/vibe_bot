from pathlib import Path


class SkillStore:
    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills = self._load_all()

    def _parse_skill(self, path: Path):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        skill_id = lines[0].replace("#", "").strip()
        description = ""
        sections = {}
        current = None
        buffer = []

        for line in lines[1:]:
            if line.startswith("description:"):
                description = line.split(":", 1)[1].strip()
                continue
            if line.startswith("## "):
                if current:
                    sections[current] = "\n".join(buffer).strip()
                current = line.replace("## ", "").strip()
                buffer = []
                continue
            buffer.append(line)

        if current:
            sections[current] = "\n".join(buffer).strip()

        return {
            "id": skill_id,
            "description": description,
            "sections": sections,
        }

    def _load_all(self):
        skills = {}
        for path in sorted(self.skills_dir.glob("*/skill.md")):
            skill = self._parse_skill(path)
            skills[skill["id"]] = skill
        return skills

    def build_catalog(self):
        lines = ["Available skills:"]
        for skill in self.skills.values():
            when = skill["sections"].get("When to use", "").splitlines()
            when = [line.strip("- ").strip() for line in when if line.strip()]
            when_hint = f" Use when: {when[0]}." if when else ""
            section_names = [name for name in skill["sections"].keys() if name != "When to use"]
            section_hint = f" Sections: {', '.join(section_names[:6])}" if section_names else ""
            if len(section_names) > 6:
                section_hint += ", ..."
            lines.append(f'- {skill["id"]}: {skill["description"]}{when_hint}{section_hint}')
        return "\n".join(lines)

    def list_skill_sections(self, skill_id: str):
        skill = self.skills.get(skill_id)
        if not skill:
            return {"error": f"unknown skill: {skill_id}"}

        sections = []
        for name, value in skill["sections"].items():
            preview = ""
            for line in value.splitlines():
                line = line.strip().lstrip("- ").strip()
                if line:
                    preview = line[:160]
                    break
            sections.append({"name": name, "preview": preview})

        return {
            "id": skill["id"],
            "description": skill["description"],
            "sections": sections,
        }

    def load_skill_section(self, skill_id: str, section_names=None):
        skill = self.skills.get(skill_id)
        if not skill:
            return {"error": f"unknown skill: {skill_id}"}

        if not section_names:
            section_names = ["Guidance", "Do", "Avoid"]

        loaded = {}
        for name in section_names:
            value = skill["sections"].get(name)
            if value:
                loaded[name] = value

        return {
            "id": skill["id"],
            "description": skill["description"],
            "sections": loaded,
        }
