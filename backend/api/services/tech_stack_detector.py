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
    # Match against both full paths and basenames so nested files are found
    names = {name.replace("\\", "/").lstrip("./") for name in files}
    basenames = {name.split("/")[-1] for name in names}

    if "pom.xml" in names or "pom.xml" in basenames:
        return TechStack("SPRING_BOOT", "MAVEN", 8080)

    if "build.gradle" in names or "build.gradle" in basenames or \
       "build.gradle.kts" in names or "build.gradle.kts" in basenames:
        return TechStack("SPRING_BOOT", "GRADLE", 8080)

    package_json_key = next(
        (k for k in files if k.replace("\\", "/").split("/")[-1] == "package.json"), None
    )
    if package_json_key is not None:
        package_json = files[package_json_key]
        if '"react"' in package_json or '"@vitejs/plugin-react"' in package_json:
            return TechStack("REACT", "NPM", 3000)
        return TechStack("NODE_JS", "NPM", 3000)

    if "requirements.txt" in names or "requirements.txt" in basenames or \
       "pyproject.toml" in names or "pyproject.toml" in basenames:
        return TechStack("PYTHON", "PIP", 8000)

    raise UnsupportedTechStackError(
        "Unable to detect a supported stack. Expected pom.xml, build.gradle, "
        "package.json, requirements.txt, or pyproject.toml."
    )


# ---------------------------------------------------------------------------
# Frontend detection for Vercel deployment
# ---------------------------------------------------------------------------

# Directories that commonly contain frontend code in full-stack repos
_FRONTEND_DIRS = ("frontend", "client", "web", "app", "src")


def _find_package_json_in_dir(files: Mapping[str, str], dir_name: str) -> str | None:
    """Return the path to a package.json inside dir_name, or None."""
    target = f"{dir_name}/package.json"
    for key in files:
        if key.replace("\\", "/") == target:
            return key
    return None


def detect_frontend_stack(
    files: Mapping[str, str],
    *,
    tree: list[dict] | None = None,
) -> dict:
    """
    Detect the frontend application in a repository for Vercel deployment.

    Returns a dict with keys:
        technology       — e.g. "REACT", "NEXTJS", "NODE_JS"
        framework        — Vercel framework slug: "vite", "nextjs", "create-react-app", etc.
        build_command    — e.g. "npm run build"
        install_command  — e.g. "npm install"
        output_directory — e.g. "dist", ".next", or None (Vercel default)
        root_directory   — e.g. "frontend", "client", or None (repo root)
        start_command    — e.g. "npm start" (used by Render, ignored by Vercel)
        port             — e.g. 3000
    """
    import json as _json

    names = {name.replace("\\", "/").lstrip("./") for name in files}

    # ── Step 1: Find the root package.json ──────────────────────────────
    root_pkg_key = next(
        (k for k in files if k.replace("\\", "/") == "package.json"), None,
    )

    # ── Step 2: If root has pom.xml / build.gradle AND a sub-directory
    #            has package.json, prefer the sub-directory (full-stack repo).
    has_java_root = any(
        n in names for n in ("pom.xml", "build.gradle", "build.gradle.kts")
    )

    frontend_pkg_key = root_pkg_key
    frontend_root_dir = None

    if has_java_root:
        # Java backend at root — look for frontend in known sub-dirs
        for d in _FRONTEND_DIRS:
            candidate = _find_package_json_in_dir(files, d)
            if candidate:
                frontend_pkg_key = candidate
                frontend_root_dir = d
                break

    if frontend_pkg_key is None:
        # No package.json anywhere — cannot deploy a JS frontend to Vercel
        return {
            "technology": "UNKNOWN",
            "framework": None,
            "build_command": None,
            "install_command": None,
            "output_directory": None,
            "root_directory": None,
            "start_command": None,
            "port": 3000,
        }

    # ── Step 3: Parse package.json to detect framework ──────────────────
    pkg_text = files[frontend_pkg_key]
    try:
        pkg = _json.loads(pkg_text)
    except (_json.JSONDecodeError, AttributeError):
        pkg = {}

    scripts = pkg.get("scripts", {})
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    build_cmd = scripts.get("build")
    start_cmd = scripts.get("start")
    install_cmd = None

    # Detect package manager from lockfiles
    lockfiles = {k.split("/")[-1] for k in names}
    if "pnpm-lock.yaml" in lockfiles:
        install_cmd = "pnpm install"
    elif "yarn.lock" in lockfiles:
        install_cmd = "yarn install --frozen-lockfile"
    elif "bun.lock" in lockfiles or "bun.lockb" in lockfiles:
        install_cmd = "bun install"
    else:
        install_cmd = "npm install"

    # Detect framework
    technology = "NODE_JS"
    framework = None  # Vercel framework slug
    output_dir = None
    port = 3000

    if "next" in deps:
        technology = "NEXTJS"
        framework = "nextjs"
        if not build_cmd:
            build_cmd = "next build"
        output_dir = None  # Vercel handles Next.js output automatically
        port = 3000
    elif "@vitejs/plugin-react" in deps or "vite" in deps:
        technology = "REACT"
        framework = "vite"
        if not build_cmd:
            build_cmd = "vite build"
        output_dir = "dist"
        port = 5173
    elif "react" in deps:
        technology = "REACT"
        framework = "create-react-app"
        if not build_cmd:
            build_cmd = "react-scripts build"
        output_dir = "build"
        port = 3000
    elif "vue" in deps or "@vue/cli" in deps:
        technology = "VUE"
        framework = "vue"
        if not build_cmd:
            build_cmd = "vue-cli-service build"
        output_dir = "dist"
        port = 8080
    elif "@angular/core" in deps:
        technology = "ANGULAR"
        framework = "angular"
        if not build_cmd:
            build_cmd = "ng build"
        output_dir = "dist"
        port = 4200
    else:
        # Generic Node.js — try `npm run build` if script exists
        if build_cmd:
            build_cmd = f"npm run {scripts['build']}" if scripts.get("build") else None
        technology = "NODE_JS"
        framework = None

    return {
        "technology": technology,
        "framework": framework,
        "build_command": build_cmd,
        "install_command": install_cmd,
        "output_directory": output_dir,
        "root_directory": frontend_root_dir,
        "start_command": start_cmd,
        "port": port,
    }
