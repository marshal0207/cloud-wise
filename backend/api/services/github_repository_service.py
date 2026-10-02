import base64
import re
import time
import urllib.parse
from datetime import datetime

from .github_service import (
    GitHubApiError,
    _request_json,
    normalize_github_repo_url,
)
from .tech_stack_detector import ENV_TEMPLATE_FILENAMES


SUPPORTED_REPOSITORY_FILES = (
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "package.json",
    "requirements.txt",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "go.mod",
    "Cargo.toml",
    "vercel.json",
)

_SUPPORTED_REPOSITORY_FILENAMES = {
    name.lower() for name in SUPPORTED_REPOSITORY_FILES
}

_SENSITIVE_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.staging",
    ".env.development",
}

_SECRETS_PATTERN = re.compile(
    r"(?i)(secret|password|passwd|pass|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|credential|auth|bearer|client_secret|db_url|"
    r"database_url|connection_string|aws_secret|stripe|sk_live|ghp_|"
    r"gho_|github_pat_)"
)


class RepositoryLimitError(ValueError):
    """Raised when a repository exceeds CloudWise platform analysis limits."""


DEFAULT_REPOSITORY_LIMITS = {
    "max_repository_size_mb": 500,
    "max_files": 10000,
    "max_single_file_mb": 10,
    "max_analysis_time_minutes": 5,
}


_LIMIT_SETTINGS = {
    "max_repository_size_mb": "MAX_REPOSITORY_SIZE_MB",
    "max_files": "MAX_FILES",
    "max_single_file_mb": "MAX_SINGLE_FILE_MB",
    "max_analysis_time_minutes": "MAX_ANALYSIS_TIME_MINUTES",
}


# Directories that should never be copied to the deployment machine.
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".github",
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "coverage",
    ".cache",
    ".parcel-cache",
    ".turbo",
    "target",
}


# Binary/generated files that are generally not required for source deployment.
_EXCLUDED_EXTENSIONS = {
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".war",
    ".pyc",
    ".pyo",
    ".o",
    ".a",
    ".obj",
    ".iso",
    ".bin",
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".mp3",
    ".wav",
    ".flac",
    ".psd",
    ".ai",
    ".sketch",
}


def get_repository_limits() -> dict:
    limits = dict(DEFAULT_REPOSITORY_LIMITS)

    try:
        from django.conf import settings

        for key, setting_name in _LIMIT_SETTINGS.items():
            value = getattr(settings, setting_name, None)
            if value is not None:
                limits[key] = int(value)

    except Exception:
        pass

    return limits


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 ** 3:
        return f"{num_bytes / (1024 ** 3):.1f} GB"

    if num_bytes >= 1024 ** 2:
        return f"{num_bytes / (1024 ** 2):.1f} MB"

    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"

    return f"{num_bytes} B"


def _format_mb_limit(megabytes: int) -> str:
    if megabytes >= 1024:
        return f"{megabytes / 1024:g} GB"

    return f"{megabytes:g} MB"


def _file_nodes(full_tree) -> list[dict]:
    return [
        node
        for node in (full_tree or [])
        if isinstance(node, dict) and node.get("type") == "file"
    ]


def compute_repository_size(full_tree) -> dict:
    nodes = _file_nodes(full_tree)

    total_bytes = 0
    largest_bytes = 0

    for node in nodes:
        size = int(node.get("size") or 0)
        total_bytes += size

        if size > largest_bytes:
            largest_bytes = size

    return {
        "totalBytes": total_bytes,
        "totalMegabytes": round(total_bytes / (1024 ** 2), 2),
        "fileCount": len(nodes),
        "largestFileBytes": largest_bytes,
    }


def check_repository_limits(
    full_tree,
    *,
    elapsed_seconds: float = 0.0,
    limits: dict | None = None,
) -> None:
    limits = limits if limits is not None else get_repository_limits()

    nodes = _file_nodes(full_tree)

    total_bytes = 0
    largest_bytes = 0
    largest_path = ""

    for node in nodes:
        size = int(node.get("size") or 0)
        total_bytes += size

        if size > largest_bytes:
            largest_bytes = size
            largest_path = node.get("path", "")

    max_bytes = int(limits["max_repository_size_mb"]) * 1024 * 1024

    if total_bytes > max_bytes:
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"Repository size: {_format_size(total_bytes)}\n"
            f"Maximum supported size: "
            f"{_format_mb_limit(int(limits['max_repository_size_mb']))}"
        )

    if len(nodes) > int(limits["max_files"]):
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"Repository files: {len(nodes)}\n"
            f"Maximum supported files: {int(limits['max_files'])}"
        )

    max_single_bytes = int(limits["max_single_file_mb"]) * 1024 * 1024

    if largest_bytes > max_single_bytes:
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"File size: {_format_size(largest_bytes)} ({largest_path})\n"
            f"Maximum supported single file size: "
            f"{_format_mb_limit(int(limits['max_single_file_mb']))}"
        )

    max_seconds = int(limits["max_analysis_time_minutes"]) * 60

    if elapsed_seconds > max_seconds:
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"Analysis time: {elapsed_seconds / 60:.1f} minutes\n"
            f"Maximum analysis time: "
            f"{int(limits['max_analysis_time_minutes'])} minutes"
        )


def _is_analysis_file(path: str) -> bool:
    """
    Files required for technology-stack detection and analysis.
    """
    normalized = path.replace("\\", "/")
    filename = normalized.split("/")[-1].lower()

    if filename in ENV_TEMPLATE_FILENAMES:
        return True

    if filename in _SENSITIVE_FILENAMES:
        return False

    if filename in _SUPPORTED_REPOSITORY_FILENAMES:
        return True

    if filename.startswith("dockerfile"):
        return True

    if filename.startswith("docker-compose"):
        return True

    if filename == "manage.py":
        return True

    if filename.startswith("vite.config"):
        return True

    if filename.startswith("next.config"):
        return True

    if filename.startswith("drizzle.config"):
        return True

    if filename == "schema.prisma":
        return True

    if normalized.startswith(".github/workflows/"):
        return True

    return False


def _is_deployment_file(path: str) -> bool:
    """
    Determine whether a repository file should be copied to EC2.

    Unlike _is_analysis_file(), this intentionally includes normal
    application source files such as:

        frontend/index.html
        frontend/src/App.jsx
        frontend/src/main.jsx
        backend/server.js
        backend/routes/*.js

    while excluding secrets, Git metadata, dependencies, build output,
    caches, and common binary artifacts.
    """

    normalized = path.replace("\\", "/").strip("/")

    if not normalized:
        return False

    parts = normalized.split("/")
    filename = parts[-1]
    filename_lower = filename.lower()

    # Never deploy secret environment files from GitHub.
    if filename_lower in _SENSITIVE_FILENAMES:
        return False

    # Skip files whose path contains excluded directories.
    for part in parts[:-1]:
        if part.lower() in _EXCLUDED_DIRECTORIES:
            return False

    # Skip common binary/generated artifacts.
    for extension in _EXCLUDED_EXTENSIONS:
        if filename_lower.endswith(extension):
            return False

    # Skip common editor/system files.
    if filename_lower in {
        ".ds_store",
        "thumbs.db",
        "desktop.ini",
    }:
        return False

    return True


def _redact_secrets(content: str) -> str:
    """
    Return a redacted copy — secret VALUES are replaced with [REDACTED].
    """
    return re.sub(
        r'(?i)(secret|password|passwd|pass|token|api[_-]?key|'
        r'access[_-]?key|private[_-]?key|credential|auth|bearer|'
        r'client_secret|db_url|database_url|connection_string|'
        r'aws_secret|stripe|sk_live|ghp_|gho_|github_pat_)'
        r'\s*[=:]\s*["\']?[^\s"\',;}\]]+["\']?',
        r"\1=[REDACTED]",
        content,
    )


def _looks_like_secret_path(path: str) -> bool:
    filename = path.strip("/").split("/")[-1].lower()
    return filename in _SENSITIVE_FILENAMES


def _walk_directory_contents(owner, repo, path, branch, token):
    nodes = []

    encoded_path = urllib.parse.quote(path, safe="/")

    url = (
        f"https://api.github.com/repos/{owner}/{repo}/contents/"
        f"{encoded_path}?ref={urllib.parse.quote(branch)}"
    )

    contents = _request_json(
        url,
        token,
        allow_404=True,
    )

    if not isinstance(contents, list):
        return nodes

    for item in contents:
        item_path = item.get("path", "")
        item_type = item.get("type")

        if item_type == "file":
            nodes.append(
                {
                    "path": item_path,
                    "type": "file",
                    "size": item.get("size", 0),
                    "sha": item.get("sha", ""),
                }
            )

        elif item_type == "dir":
            nodes.append(
                {
                    "path": item_path,
                    "type": "directory",
                    "size": 0,
                    "sha": item.get("sha", ""),
                }
            )

            sub_nodes = _walk_directory_contents(
                owner,
                repo,
                item_path,
                branch,
                token,
            )

            nodes.extend(sub_nodes)

    return nodes


def _extract_commit_info(commit_info):
    if not isinstance(commit_info, dict):
        return "", "", "", ""

    commit = commit_info.get("commit", {})

    return (
        commit_info.get("sha", ""),
        (
            commit.get("message", "")[:200]
            if commit.get("message")
            else ""
        ),
        (
            commit.get("author", {}).get("date", "")
            if isinstance(commit.get("author"), dict)
            else ""
        ),
        (
            commit_info.get("commit", {})
            .get("committer", {})
            .get("date", "")
            if isinstance(
                commit_info.get("commit", {}).get("committer"),
                dict,
            )
            else ""
        ),
    )


def _decode_github_file_content(item: dict):
    """
    Decode file content returned by GitHub Contents API.

    Returns None when content is unavailable or cannot be decoded.
    """
    if not isinstance(item, dict):
        return None

    encoded_content = item.get("content")

    if not encoded_content:
        return None

    try:
        return base64.b64decode(
            encoded_content.replace("\n", "").encode(),
            validate=True,
        ).decode("utf-8")

    except (ValueError, UnicodeDecodeError):
        return None


def _fetch_file_content(
    encoded_full_name,
    path,
    default_branch,
    token,
    sha=None,
):
    """
    Fetch a repository file.

    First uses GitHub's Contents API. If GitHub does not provide inline
    content, fall back to the Git Blobs API using the file SHA.
    """

    encoded_path = urllib.parse.quote(path, safe="/")

    url = (
        f"https://api.github.com/repos/{encoded_full_name}/contents/"
        f"{encoded_path}?ref={urllib.parse.quote(default_branch)}"
    )

    item = _request_json(
        url,
        token,
        allow_404=True,
    )

    if item is None or not isinstance(item, dict):
        return None

    content = _decode_github_file_content(item)

    if content is not None:
        return content

    blob_sha = item.get("sha") or sha

    if not blob_sha:
        return None

    blob_url = (
        f"https://api.github.com/repos/{encoded_full_name}/git/blobs/"
        f"{urllib.parse.quote(blob_sha)}"
    )

    blob = _request_json(
        blob_url,
        token,
        allow_404=True,
    )

    if not isinstance(blob, dict):
        return None

    encoded_blob = blob.get("content")

    if not encoded_blob:
        return None

    try:
        return base64.b64decode(
            encoded_blob.replace("\n", "").encode(),
            validate=True,
        ).decode("utf-8")

    except (ValueError, UnicodeDecodeError):
        return None


def inspect_repository(
    token,
    repository,
    progress_callback=None,
):
    """
    Inspect a real GitHub repository using the caller's own token.

    Steps:
      1. Validate repo format.
      2. Fetch repository metadata.
      3. Verify access.
      4. Get latest commit.
      5. Fetch recursive repository tree.
      6. Fetch analysis files.
      7. Fetch complete deployable source files.
      8. Redact sensitive values from returned source.
      9. Return the analysis/deployment object.
    """

    started_at = time.monotonic()

    def _progress(stage: str, message: str, pct: int):
        if progress_callback is not None:
            progress_callback(
                stage,
                message,
                pct,
            )

    # ---------------------------------------------------------
    # Validate repository
    # ---------------------------------------------------------

    _progress(
        "validating",
        "Validating repository format...",
        0,
    )

    try:
        owner, repo_name, full_name = normalize_github_repo_url(
            repository
        )

    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    encoded_full_name = urllib.parse.quote(
        full_name,
        safe="/",
    )

    # ---------------------------------------------------------
    # Repository metadata
    # ---------------------------------------------------------

    _progress(
        "fetching_repo",
        "Fetching repository metadata...",
        10,
    )

    repo_url = (
        f"https://api.github.com/repos/{encoded_full_name}"
    )

    repo_meta = _request_json(
        repo_url,
        token,
        allow_404=False,
    )

    if not repo_meta or not isinstance(repo_meta, dict):
        raise GitHubApiError(
            f"Unable to access repository '{full_name}'.",
            status_code=404,
        )

    # ---------------------------------------------------------
    # Private repository permission check
    # ---------------------------------------------------------

    if (
        repo_meta.get("private")
        and not repo_meta.get("permissions", {}).get("pull", False)
    ):
        try:
            permissions_url = (
                f"https://api.github.com/repos/"
                f"{encoded_full_name}/collaborators/"
                f"{owner}/permission"
            )

            perm = _request_json(
                permissions_url,
                token,
                allow_404=True,
            )

            if perm and perm.get("permission") in (
                "pull",
                "triage",
                "push",
                "maintain",
                "admin",
            ):
                pass

            else:
                raise GitHubApiError(
                    f"Account does not have access to private "
                    f"repository '{full_name}'.",
                    status_code=403,
                    details="access_denied",
                )

        except GitHubApiError:
            raise

        except Exception as exc:
            raise GitHubApiError(
                f"Unable to verify access to private "
                f"repository '{full_name}'.",
                status_code=403,
                details=str(exc),
            )

    # ---------------------------------------------------------
    # Basic repository information
    # ---------------------------------------------------------

    default_branch = (
        repo_meta.get("default_branch")
        or "main"
    )

    visibility = repo_meta.get(
        "visibility",
        "private" if repo_meta.get("private") else "public",
    )

    language = repo_meta.get("language") or ""
    size = repo_meta.get("size", 0)
    description = repo_meta.get("description", "")
    stargazers = repo_meta.get("stargazers_count", 0)
    forks = repo_meta.get("forks_count", 0)
    open_issues = repo_meta.get("open_issues_count", 0)

    # ---------------------------------------------------------
    # Latest commit
    # ---------------------------------------------------------

    _progress(
        "fetching_commit",
        "Reading latest commit...",
        25,
    )

    commit_sha = ""
    commit_message = ""
    commit_date = ""

    commit_url = (
        f"https://api.github.com/repos/"
        f"{encoded_full_name}/commits/"
        f"{urllib.parse.quote(default_branch)}"
    )

    commit_info = _request_json(
        commit_url,
        token,
        allow_404=True,
    )

    if isinstance(commit_info, dict):
        (
            commit_sha,
            commit_message,
            commit_date,
            _,
        ) = _extract_commit_info(commit_info)

    # ---------------------------------------------------------
    # Repository tree
    # ---------------------------------------------------------

    _progress(
        "fetching_tree",
        "Reading repository tree...",
        40,
    )

    tree_url = (
        f"https://api.github.com/repos/"
        f"{encoded_full_name}/git/trees/"
        f"{urllib.parse.quote(default_branch)}"
        f"?recursive=1"
    )

    tree_data = _request_json(
        tree_url,
        token,
        allow_404=True,
    )

    raw_tree = (
        tree_data.get("tree", [])
        if isinstance(tree_data, dict)
        else []
    )

    truncated = (
        bool(tree_data.get("truncated"))
        if isinstance(tree_data, dict)
        else False
    )

    full_tree = []

    # ---------------------------------------------------------
    # Build complete repository tree
    # ---------------------------------------------------------

    if raw_tree:
        for node in raw_tree:
            path = node.get("path", "")
            node_type = node.get("type", "blob")
            node_size = node.get("size", 0)
            sha = node.get("sha", "")

            is_dir = node_type in (
                "tree",
                "dir",
                "directory",
            )

            full_tree.append(
                {
                    "path": path,
                    "type": (
                        "directory"
                        if is_dir
                        else "file"
                    ),
                    "size": (
                        node_size
                        if not is_dir
                        else 0
                    ),
                    "sha": sha,
                }
            )

    # ---------------------------------------------------------
    # Fallback tree walker
    # ---------------------------------------------------------

    if truncated or not full_tree:
        walked_nodes = _walk_directory_contents(
            owner,
            repo_name,
            "",
            default_branch,
            token,
        )

        if walked_nodes:
            full_tree = walked_nodes

    total_files = len(
        [
            node
            for node in full_tree
            if node.get("type") == "file"
        ]
    )

    total_directories = len(
        [
            node
            for node in full_tree
            if node.get("type")
            in ("directory", "folder")
        ]
    )

    # ---------------------------------------------------------
    # Repository limits
    # ---------------------------------------------------------

    check_repository_limits(
        full_tree,
        elapsed_seconds=time.monotonic() - started_at,
    )

    repository_size = compute_repository_size(
        full_tree
    )

    # ---------------------------------------------------------
    # Build two file lists
    #
    # Analysis files:
    #   package.json, Dockerfile, vite.config.js, etc.
    #
    # Deployment files:
    #   index.html, src/App.jsx, backend/server.js, etc.
    # ---------------------------------------------------------

    analysis_paths = set()
    deployment_paths = set()

    for node in full_tree:
        if node.get("type") != "file":
            continue

        path = node.get("path", "")

        if _is_analysis_file(path):
            analysis_paths.add(path)

        if _is_deployment_file(path):
            deployment_paths.add(path)

    # ---------------------------------------------------------
    # If no analysis files were detected, retain old fallback.
    # ---------------------------------------------------------

    if not analysis_paths:
        for fname in SUPPORTED_REPOSITORY_FILES:
            analysis_paths.add(fname)

    # ---------------------------------------------------------
    # Fetch files
    #
    # IMPORTANT:
    # We intentionally fetch deployment source files too.
    # This is the fix for the missing frontend/src and
    # frontend/index.html problem.
    # ---------------------------------------------------------

    _progress(
        "detecting_files",
        "Detecting project and deployment files...",
        55,
    )

    found_files = {}

    # Analysis + deployment files.
    # A set prevents duplicate GitHub API requests.
    paths_to_fetch = (
        analysis_paths | deployment_paths
    )

    for path in sorted(paths_to_fetch):
        # Never download .env or other sensitive env files.
        if _looks_like_secret_path(path):
            continue

        # Never download excluded directories.
        if not _is_deployment_file(path):
            # Keep analysis-only special files such as workflows.
            if not _is_analysis_file(path):
                continue

        check_repository_limits(
            full_tree,
            elapsed_seconds=time.monotonic() - started_at,
        )

        # Locate SHA for blob fallback.
        sha = ""

        for node in full_tree:
            if node.get("path") == path:
                sha = node.get("sha", "")
                break

        content = _fetch_file_content(
            encoded_full_name,
            path,
            default_branch,
            token,
            sha=sha,
        )

        if content is None:
            continue

        # Protect secrets before storing the inspection result.
        redacted = _redact_secrets(content)

        found_files[path] = redacted

    # ---------------------------------------------------------
    # Analysis metadata
    # ---------------------------------------------------------

    _progress(
        "analyzing",
        "Analyzing project structure...",
        75,
    )

    has_dockerfile = any(
        p.lower().endswith("dockerfile")
        for p in found_files.keys()
    )

    has_compose = any(
        "docker-compose" in p.lower()
        for p in found_files.keys()
    )

    has_cicd = any(
        ".github/workflows" in p.lower()
        for p in found_files.keys()
    )

    has_readme = any(
        p.lower() == "readme.md"
        for p in found_files.keys()
    )

    has_env_example = any(
        p.lower().startswith(".env.")
        or p.lower() == ".env.example"
        for p in found_files.keys()
    )

    env_files = sorted(
        p
        for p in found_files.keys()
        if p.lower().endswith(
            (
                ".env",
                ".env.example",
                ".env.sample",
                ".env.template",
                ".env.local",
            )
        )
    )

    # ---------------------------------------------------------
    # Complete
    # ---------------------------------------------------------

    _progress(
        "scanning_complete",
        "Scan completed.",
        100,
    )

    return {
        "repository": {
            "owner": owner,
            "name": repo_name,
            "full_name": full_name,
            "defaultBranch": default_branch,
            "visibility": visibility,
            "language": language,
            "description": description,
            "sizeMb": size,
            "stargazersCount": stargazers,
            "forksCount": forks,
            "openIssuesCount": open_issues,
        },
        "branch": default_branch,
        "commitSha": commit_sha,
        "commitMessage": commit_message,
        "commitDate": commit_date,
        "tree": full_tree,
        "files": found_files,
        "totalFiles": total_files,
        "totalDirectories": total_directories,
        "truncated": truncated,
        "scannedAt": datetime.now().isoformat(),
        "repositorySize": repository_size,
        "has_dockerfile": has_dockerfile,
        "has_compose": has_compose,
        "has_cicd": has_cicd,
        "has_readme": has_readme,
        "env_files_detected": env_files,
    }