from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class TechStack:
    technology: str
    build_tool: str
    port: int


class UnsupportedTechStackError(ValueError):
    pass


def detect_tech_stack(files: Mapping[str, str]) -> TechStack:
    """Detect a supported application stack from repository file names and content."""
    names = {name.replace("\\", "/").lstrip("./") for name in files}

    if "pom.xml" in names:
        return TechStack("SPRING_BOOT", "MAVEN", 8080)

    if "build.gradle" in names or "build.gradle.kts" in names:
        return TechStack("SPRING_BOOT", "GRADLE", 8080)

    package_json = files.get("package.json", "")
    if "package.json" in names:
        if '"react"' in package_json or '"@vitejs/plugin-react"' in package_json:
            return TechStack("REACT", "NPM", 3000)
        return TechStack("NODE_JS", "NPM", 3000)

    if "requirements.txt" in names or "pyproject.toml" in names:
        return TechStack("PYTHON", "PIP", 8000)

    raise UnsupportedTechStackError(
        "Unable to detect a supported stack. Expected pom.xml, build.gradle, "
        "package.json, requirements.txt, or pyproject.toml."
    )
