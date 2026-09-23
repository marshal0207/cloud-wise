from dataclasses import dataclass
import json
import re
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

    # ── Step 2: If repo has a backend at root AND a sub-directory
    #            has package.json, prefer the sub-directory (full-stack repo).
    #            Check ALL file paths (not just root) so backend/pom.xml is found.
    has_backend_root = any(
        n in names for n in ("pom.xml", "build.gradle", "build.gradle.kts",
                              "requirements.txt", "pyproject.toml", "manage.py",
                              "Cargo.toml", "go.mod")
    ) or any(
        n.endswith("/pom.xml") or n.endswith("/build.gradle") or n.endswith("/build.gradle.kts")
        or n.endswith("/requirements.txt") or n.endswith("/pyproject.toml")
        or n.endswith("/manage.py")
        for n in names
    )

    frontend_pkg_key = root_pkg_key
    frontend_root_dir = None

    if has_backend_root:
        # Backend at root — look for frontend in known sub-dirs
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
        # Generic Node.js — use the build script value directly if it looks
        # like a full command (contains spaces or starts with a known tool),
        # otherwise prefix with "npm run ".
        if build_cmd and ' ' not in build_cmd and not build_cmd.startswith(('./', 'npx', 'node')):
            build_cmd = f"npm run {build_cmd}"
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


# ---------------------------------------------------------------------------
# Structured repository analysis (frontend / backend / database / env / type)
# ---------------------------------------------------------------------------

# Environment template files that may be scanned for variable NAMES only.
# Sensitive files (.env, .env.local, .env.production, ...) are never read.
ENV_TEMPLATE_FILENAMES = ('.env.example', '.env.sample', '.env.template')

# Directories that typically contain a frontend application.
FRONTEND_DIRECTORIES = ('frontend', 'client', 'web', 'app')

# Directories that typically contain a backend application.
BACKEND_DIRECTORIES = ('backend', 'server', 'api')

# Files that mark a backend application when found at the repository root.
BACKEND_MARKER_FILENAMES = (
    'pom.xml',
    'build.gradle',
    'build.gradle.kts',
    'requirements.txt',
    'pyproject.toml',
    'manage.py',
    'go.mod',
    'Cargo.toml',
)

# Canonical output order for detected package managers.
PACKAGE_MANAGER_ORDER = ('npm', 'pnpm', 'yarn', 'bun', 'maven', 'gradle', 'pip')

_ENV_NAME_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _normalize_path(path: str) -> str:
    normalized = str(path).replace('\\', '/')
    while normalized.startswith('./'):
        normalized = normalized[2:]
    return normalized


def _basename(path: str) -> str:
    return _normalize_path(path).split('/')[-1]


def _first_segment(path: str) -> str:
    parts = _normalize_path(path).split('/')
    return parts[0] if len(parts) > 1 else ''


def _package_dependencies(files: Mapping[str, str], key: str) -> dict:
    try:
        pkg = json.loads(files[key])
    except (ValueError, TypeError, AttributeError):
        return {}
    if not isinstance(pkg, dict):
        return {}
    dependencies = pkg.get('dependencies') or {}
    dev_dependencies = pkg.get('devDependencies') or {}
    if not isinstance(dependencies, dict):
        dependencies = {}
    if not isinstance(dev_dependencies, dict):
        dev_dependencies = {}
    return {**dependencies, **dev_dependencies}


def _resolve_frontend_framework(deps: dict, files: Mapping[str, str]) -> dict | None:
    """Return {"technology", "framework"} when the package.json looks like a frontend."""
    filenames = {_basename(name) for name in files}
    has_next = 'next' in deps or any(n.startswith('next.config') for n in filenames)
    has_react = 'react' in deps or 'react-dom' in deps or '@types/react' in deps
    has_vue = 'vue' in deps
    has_angular = '@angular/core' in deps
    has_vite = (
        'vite' in deps
        or '@vitejs/plugin-react' in deps
        or '@vitejs/plugin-vue' in deps
        or any(n.startswith('vite.config') for n in filenames)
    )
    has_cra = 'react-scripts' in deps

    if has_next:
        return {'technology': 'React', 'framework': 'Next.js'}
    if has_react and has_vite:
        return {'technology': 'React', 'framework': 'Vite'}
    if has_cra:
        return {'technology': 'React', 'framework': 'CRA'}
    if has_react:
        return {'technology': 'React', 'framework': None}
    if has_vue and has_vite:
        return {'technology': 'Vue', 'framework': 'Vite'}
    if has_vue:
        return {'technology': 'Vue', 'framework': None}
    if has_angular:
        return {'technology': 'Angular', 'framework': None}
    if has_vite:
        return {'technology': 'JavaScript', 'framework': 'Vite'}
    return None


def detect_frontend(files: Mapping[str, str], *, tree: list[dict] | None = None) -> dict:
    """
    Detect the frontend application.

    Returns {} when no frontend is detected, otherwise:
        {"technology": "React", "framework": "Vite"}  (framework may be null)
    """
    files = files or {}
    package_keys = sorted(
        (key for key in files if _basename(key) == 'package.json'),
        key=_normalize_path,
    )
    if not package_keys:
        return {}

    candidates = []
    for key in package_keys:
        deps = _package_dependencies(files, key)
        in_frontend_dir = _first_segment(key) in FRONTEND_DIRECTORIES
        resolved = _resolve_frontend_framework(deps, files)
        if resolved is None and not in_frontend_dir:
            continue
        candidates.append({
            'key': key,
            'in_frontend_dir': in_frontend_dir,
            'has_signals': resolved is not None,
            'resolved': resolved,
        })

    if not candidates:
        return {}

    # Prefer package.json files with frontend signals, then frontend directories.
    candidates.sort(key=lambda c: (c['has_signals'], c['in_frontend_dir']), reverse=True)
    chosen = candidates[0]
    if chosen['resolved'] is not None:
        return dict(chosen['resolved'])
    # Inside a frontend directory but without a known framework.
    return {'technology': 'JavaScript', 'framework': None}


def _node_backend_framework(deps: dict) -> str | None:
    for dependency, name in (
        ('express', 'Express'),
        ('fastify', 'Fastify'),
        ('koa', 'Koa'),
        ('@nestjs/core', 'NestJS'),
        ('@hapi/hapi', 'Hapi'),
    ):
        if dependency in deps:
            return name
    return None


def detect_backend(files: Mapping[str, str], *, tree: list[dict] | None = None) -> dict:
    """
    Detect the backend application.

    Returns {} when no backend is detected, otherwise:
        {"technology": "Java", "framework": "Spring Boot"}  (framework may be null)
    """
    files = files or {}

    # ── Java (Maven / Gradle) ─────────────────────────────────────────
    java_key = next(
        (key for key in sorted(files) if _basename(key) in (
            'pom.xml', 'build.gradle', 'build.gradle.kts',
        )),
        None,
    )
    if java_key is not None:
        content = (files[java_key] or '').lower()
        is_spring = 'spring-boot' in content or 'springframework' in content
        return {'technology': 'Java', 'framework': 'Spring Boot' if is_spring else None}

    # ── Node.js (Express / Fastify / Koa / NestJS) ────────────────────
    node_candidates = []
    for key in sorted(k for k in files if _basename(k) == 'package.json'):
        segment = _first_segment(key)
        in_backend_dir = segment in BACKEND_DIRECTORIES
        deps = _package_dependencies(files, key)
        framework = _node_backend_framework(deps)
        if framework is not None:
            priority = 2 if in_backend_dir else 1
            node_candidates.append((priority, key, framework))
        elif in_backend_dir and not _resolve_frontend_framework(deps, files):
            node_candidates.append((0, key, None))
    if node_candidates:
        node_candidates.sort(reverse=True)
        _, _, framework = node_candidates[0]
        return {'technology': 'Node.js', 'framework': framework}

    # ── Python (Django / Flask / other) ───────────────────────────────
    python_keys = [
        key for key in sorted(files)
        if _basename(key) in ('manage.py', 'requirements.txt', 'pyproject.toml')
    ]
    if python_keys:
        filenames = {_basename(key) for key in python_keys}
        corpus = '\n'.join((files[key] or '') for key in python_keys).lower()
        if 'manage.py' in filenames or re.search(r'\bdjango\b', corpus):
            framework = 'Django'
        elif re.search(r'\bflask\b', corpus):
            framework = 'Flask'
        else:
            framework = None
        return {'technology': 'Python', 'framework': framework}

    return {}


def detect_package_managers(
    files: Mapping[str, str],
    *,
    tree: list[dict] | None = None,
) -> list[str]:
    """Detect package managers from manifests and lockfiles. Never guessed beyond npm default for package.json."""
    files = files or {}
    basenames = {_basename(key) for key in files}
    for node in tree or []:
        if isinstance(node, dict) and node.get('path'):
            basenames.add(_basename(node['path']))

    found = set()

    if 'package.json' in basenames:
        js_managers = set()
        if 'package-lock.json' in basenames:
            js_managers.add('npm')
        if 'pnpm-lock.yaml' in basenames:
            js_managers.add('pnpm')
        if 'yarn.lock' in basenames:
            js_managers.add('yarn')
        if 'bun.lock' in basenames or 'bun.lockb' in basenames:
            js_managers.add('bun')
        if not js_managers:
            js_managers.add('npm')
        found.update(js_managers)

    if 'pom.xml' in basenames:
        found.add('maven')
    if 'build.gradle' in basenames or 'build.gradle.kts' in basenames:
        found.add('gradle')
    if 'requirements.txt' in basenames or 'pyproject.toml' in basenames:
        found.add('pip')

    return [manager for manager in PACKAGE_MANAGER_ORDER if manager in found]


def _parse_env_variable_names(content: str) -> list[str]:
    names = []
    for raw_line in (content or '').splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):].lstrip()
        if '=' not in line:
            continue
        name = line.split('=', 1)[0].strip()
        if _ENV_NAME_PATTERN.match(name):
            names.append(name)
    return names


def detect_environment_variables(files: Mapping[str, str]) -> list[str]:
    """
    Extract environment variable NAMES from .env.example / .env.sample /
    .env.template files. Values are never returned, and sensitive .env files
    are never parsed.
    """
    files = files or {}
    names: list[str] = []
    seen = set()
    for key in sorted(files, key=_normalize_path):
        filename = _basename(key)
        if filename not in ENV_TEMPLATE_FILENAMES:
            continue
        for name in _parse_env_variable_names(files[key]):
            if name not in seen:
                seen.add(name)
                names.append(name)
    return names


def _collect_prisma_providers(files: Mapping[str, str]) -> set[str]:
    providers = set()
    for key, content in files.items():
        if _basename(key) != 'schema.prisma':
            continue
        for match in re.finditer(
            r'provider\s*=\s*["\']?([a-zA-Z0-9_-]+)', content or '',
        ):
            providers.add(match.group(1).lower())
    return providers


def detect_database(files: Mapping[str, str], *, tree: list[dict] | None = None) -> dict:
    """
    Detect the database technology used by the repository.

    CloudWise never provisions databases — the user supplies an external
    database (Neon / Supabase / AWS RDS / PlanetScale / MongoDB Atlas / ...).

    Returns {"type": "PostgreSQL"|"MySQL"|"MongoDB", "detected": True}
    or     {"type": None, "detected": False}.
    """
    files = files or {}

    package_deps: set[str] = set()
    python_corpus_parts: list[str] = []
    jvm_corpus_parts: list[str] = []
    drizzle_corpus_parts: list[str] = []
    connection_corpus_parts: list[str] = []

    for key, content in files.items():
        content = content or ''
        filename = _basename(key)

        if filename == 'package.json':
            package_deps.update(k.lower() for k in _package_dependencies(files, key))
        if filename in ('requirements.txt', 'pyproject.toml', 'Pipfile'):
            python_corpus_parts.append(content.lower())
        if filename in ('pom.xml', 'build.gradle', 'build.gradle.kts'):
            jvm_corpus_parts.append(content.lower())
        if filename.startswith('drizzle.config'):
            drizzle_corpus_parts.append(content.lower())
        if filename in ENV_TEMPLATE_FILENAMES or filename.startswith('docker-compose'):
            connection_corpus_parts.append(content.lower())
        # Connection strings in any scanned manifest (e.g. compose files, configs).
        if '://' in content:
            connection_corpus_parts.append(content.lower())

    python_corpus = '\n'.join(python_corpus_parts)
    jvm_corpus = '\n'.join(jvm_corpus_parts)
    drizzle_corpus = '\n'.join(drizzle_corpus_parts)
    connection_corpus = '\n'.join(connection_corpus_parts)
    prisma_providers = _collect_prisma_providers(files)
    env_names = set(detect_environment_variables(files))

    # PostgreSQL
    if (
        'pg' in package_deps
        or 'postgres' in package_deps
        or 'psycopg2' in python_corpus
        or 'asyncpg' in python_corpus
        or 'org.postgresql' in jvm_corpus
        or 'postgresql' in prisma_providers
        or 'postgres' in prisma_providers
        or 'postgres' in drizzle_corpus
        or 'postgres://' in connection_corpus
        or 'postgresql://' in connection_corpus
        or re.search(r'database_url\s*=\s*postgres', connection_corpus)
    ):
        return {'type': 'PostgreSQL', 'detected': True}

    # MySQL
    if (
        'mysql' in package_deps
        or 'mysql2' in package_deps
        or 'mysqlclient' in python_corpus
        or 'pymysql' in python_corpus
        or 'mysql-connector' in jvm_corpus
        or 'com.mysql' in jvm_corpus
        or 'mysql' in prisma_providers
        or 'mysql' in drizzle_corpus
        or 'mysql://' in connection_corpus
        or re.search(r'database_url\s*=\s*mysql', connection_corpus)
    ):
        return {'type': 'MySQL', 'detected': True}

    # MongoDB
    if (
        'mongodb' in package_deps
        or 'mongoose' in package_deps
        or 'pymongo' in python_corpus
        or re.search(r'\bmotor\b', python_corpus)
        or 'mongodb' in prisma_providers
        or 'mongodb://' in connection_corpus
        or 'mongodb+srv://' in connection_corpus
        or 'MONGO_URI' in env_names
        or 'MONGODB_URI' in env_names
    ):
        return {'type': 'MongoDB', 'detected': True}

    return {'type': None, 'detected': False}


def detect_application_type(
    files: Mapping[str, str],
    *,
    tree: list[dict] | None = None,
    frontend: dict | None = None,
    backend: dict | None = None,
) -> str:
    """
    Classify the repository as "full-stack", "frontend-only", "backend-only",
    or "" when it cannot be determined.
    """
    files = files or {}
    frontend = frontend or {}
    backend = backend or {}

    paths = [key for key in files]
    for node in tree or []:
        if isinstance(node, dict) and node.get('path'):
            paths.append(node['path'])

    structural_frontend = any(
        _first_segment(path) in FRONTEND_DIRECTORIES and _basename(path) == 'package.json'
        for path in paths
    )
    structural_backend = any(
        _first_segment(path) in BACKEND_DIRECTORIES
        and (
            _basename(path) == 'package.json'
            or _basename(path) in BACKEND_MARKER_FILENAMES
        )
        for path in paths
    )
    root_backend_marker = any(
        '/' not in _normalize_path(path) and _basename(path) in BACKEND_MARKER_FILENAMES
        for path in paths
    )

    has_frontend = bool(frontend) or structural_frontend
    has_backend = bool(backend) or structural_backend or root_backend_marker

    if has_frontend and has_backend:
        return 'full-stack'
    if has_frontend:
        return 'frontend-only'
    if has_backend:
        return 'backend-only'
    return ''


def _backend_default_port(backend: dict) -> int | None:
    technology = backend.get('technology')
    if technology == 'Java':
        return 8080
    if technology == 'Node.js':
        return 3000
    if technology == 'Python':
        return 5000 if backend.get('framework') == 'Flask' else 8000
    return None


def build_deployment_requirements(
    files: Mapping[str, str],
    *,
    tree: list[dict] | None = None,
    frontend: dict | None = None,
    backend: dict | None = None,
    package_managers: list[str] | None = None,
    environment_variables: list[str] | None = None,
    database: dict | None = None,
    application_type: str | None = None,
) -> dict:
    """Build the deployment plan inputs derived from repository analysis."""
    files = files or {}
    frontend = frontend or {}
    backend = backend or {}
    database = database if database is not None else {'type': None, 'detected': False}

    requirements = {
        'applicationType': application_type or '',
        'packageManagers': list(package_managers or []),
        'environmentVariables': list(environment_variables or []),
        'database': dict(database),
        'frontend': {},
        'backend': {},
        'port': None,
    }

    frontend_port = None
    if frontend:
        frontend_stack = detect_frontend_stack(files, tree=tree)
        frontend_port = frontend_stack.get('port')
        requirements['frontend'] = {
            'technology': frontend.get('technology'),
            'framework': frontend.get('framework'),
            'buildCommand': frontend_stack.get('build_command'),
            'installCommand': frontend_stack.get('install_command'),
            'outputDirectory': frontend_stack.get('output_directory'),
            'rootDirectory': frontend_stack.get('root_directory'),
            'port': frontend_port,
        }

    backend_port = None
    if backend:
        backend_port = _backend_default_port(backend)
        requirements['backend'] = {
            'technology': backend.get('technology'),
            'framework': backend.get('framework'),
            'port': backend_port,
        }

    requirements['port'] = backend_port or frontend_port
    return requirements


def analyze_repository(
    files: Mapping[str, str],
    *,
    tree: list[dict] | None = None,
    repository_size: dict | None = None,
) -> dict:
    """
    Run the full CloudWise repository analysis and return the structured
    payload merged into the repository inspection API response.
    """
    files = files or {}
    tree = tree or []

    frontend = detect_frontend(files, tree=tree)
    backend = detect_backend(files, tree=tree)
    package_managers = detect_package_managers(files, tree=tree)
    database = detect_database(files, tree=tree)
    environment_variables = detect_environment_variables(files)
    application_type = detect_application_type(
        files, tree=tree, frontend=frontend, backend=backend,
    )
    deployment_requirements = build_deployment_requirements(
        files,
        tree=tree,
        frontend=frontend,
        backend=backend,
        package_managers=package_managers,
        environment_variables=environment_variables,
        database=database,
        application_type=application_type,
    )

    return {
        'frontend': frontend,
        'backend': backend,
        'database': database,
        'packageManagers': package_managers,
        'environmentVariables': environment_variables,
        'applicationType': application_type,
        'repositorySize': dict(repository_size) if repository_size else {},
        'deploymentRequirements': deployment_requirements,
    }
