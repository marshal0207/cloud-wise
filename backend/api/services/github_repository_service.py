import base64
import time
import urllib.parse
from datetime import datetime

from .github_service import GitHubApiError, _request_json, normalize_github_repo_url
from .tech_stack_detector import ENV_TEMPLATE_FILENAMES


SUPPORTED_REPOSITORY_FILES = (
    'pom.xml',
    'build.gradle',
    'build.gradle.kts',
    'package.json',
    'requirements.txt',
    'pyproject.toml',
    'Dockerfile',
    'docker-compose.yml',
    'docker-compose.yaml',
    'go.mod',
    'Cargo.toml',
    'vercel.json',
)

_SUPPORTED_REPOSITORY_FILENAMES = {name.lower() for name in SUPPORTED_REPOSITORY_FILES}


# ---------------------------------------------------------------------------
# CloudWise platform repository analysis limits
# ---------------------------------------------------------------------------

class RepositoryLimitError(ValueError):
    """Raised when a repository exceeds CloudWise platform analysis limits."""


DEFAULT_REPOSITORY_LIMITS = {
    'max_repository_size_mb': 500,
    'max_files': 10000,
    'max_single_file_mb': 10,
    'max_analysis_time_minutes': 5,
}

_LIMIT_SETTINGS = {
    'max_repository_size_mb': 'MAX_REPOSITORY_SIZE_MB',
    'max_files': 'MAX_FILES',
    'max_single_file_mb': 'MAX_SINGLE_FILE_MB',
    'max_analysis_time_minutes': 'MAX_ANALYSIS_TIME_MINUTES',
}


def get_repository_limits() -> dict:
    """Resolve repository analysis limits from Django settings (env-configurable)."""
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
        node for node in (full_tree or [])
        if isinstance(node, dict) and node.get('type') == 'file'
    ]


def compute_repository_size(full_tree) -> dict:
    """Summarise repository size from the scanned tree."""
    nodes = _file_nodes(full_tree)
    total_bytes = 0
    largest_bytes = 0
    for node in nodes:
        size = int(node.get('size') or 0)
        total_bytes += size
        if size > largest_bytes:
            largest_bytes = size
    return {
        'totalBytes': total_bytes,
        'totalMegabytes': round(total_bytes / (1024 ** 2), 2),
        'fileCount': len(nodes),
        'largestFileBytes': largest_bytes,
    }


def check_repository_limits(full_tree, *, elapsed_seconds: float = 0.0, limits: dict | None = None) -> None:
    """
    Raise RepositoryLimitError when the repository exceeds CloudWise
    platform analysis limits (size, file count, single file, analysis time).
    """
    limits = limits if limits is not None else get_repository_limits()
    nodes = _file_nodes(full_tree)

    total_bytes = 0
    largest_bytes = 0
    largest_path = ''
    for node in nodes:
        size = int(node.get('size') or 0)
        total_bytes += size
        if size > largest_bytes:
            largest_bytes = size
            largest_path = node.get('path', '')

    max_bytes = int(limits['max_repository_size_mb']) * 1024 * 1024
    if total_bytes > max_bytes:
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"Repository size: {_format_size(total_bytes)}\n"
            f"Maximum supported size: {_format_mb_limit(int(limits['max_repository_size_mb']))}"
        )

    if len(nodes) > int(limits['max_files']):
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"Repository files: {len(nodes)}\n"
            f"Maximum supported files: {int(limits['max_files'])}"
        )

    max_single_bytes = int(limits['max_single_file_mb']) * 1024 * 1024
    if largest_bytes > max_single_bytes:
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"File size: {_format_size(largest_bytes)} ({largest_path})\n"
            f"Maximum supported single file size: {_format_mb_limit(int(limits['max_single_file_mb']))}"
        )

    max_seconds = int(limits['max_analysis_time_minutes']) * 60
    if elapsed_seconds > max_seconds:
        raise RepositoryLimitError(
            "Repository analysis limit reached.\n\n"
            f"Analysis time: {elapsed_seconds / 60:.1f} minutes\n"
            f"Maximum analysis time: {int(limits['max_analysis_time_minutes'])} minutes"
        )


def _is_sensitive_env_filename(filename: str) -> bool:
    """True for real secret files (.env, .env.local, ...) — never downloaded."""
    return filename == '.env' or filename.startswith('.env.')


def _is_analysis_file(path: str) -> bool:
    """Whether a repository file should be downloaded for CloudWise analysis.

    Environment templates (.env.example / .env.sample / .env.template) are
    downloaded for variable-name detection. Sensitive .env files are never
    downloaded.
    """
    normalized = path.replace('\\', '/')
    filename = normalized.split('/')[-1].lower()

    if filename in ENV_TEMPLATE_FILENAMES:
        return True
    if _is_sensitive_env_filename(filename):
        return False
    if filename in _SUPPORTED_REPOSITORY_FILENAMES:
        return True
    if filename.startswith('dockerfile') or filename.startswith('docker-compose'):
        return True
    if filename == 'manage.py':
        return True
    if filename.startswith('vite.config') or filename.startswith('next.config'):
        return True
    if filename.startswith('drizzle.config'):
        return True
    if filename == 'schema.prisma':
        return True
    if normalized.startswith('.github/workflows/'):
        return True
    return False


def _repository_parts(repository):
    return normalize_github_repo_url(repository)


def _walk_directory_contents(owner, repo, path, branch, token):
    """
    Fallback recursive directory walker using GitHub Contents API
    when Git Trees API returns truncated = true.
    """
    nodes = []
    encoded_path = urllib.parse.quote(path, safe='/')
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded_path}?ref={urllib.parse.quote(branch)}"
    contents = _request_json(url, token, allow_404=True)
    if not isinstance(contents, list):
        return nodes

    for item in contents:
        item_path = item.get('path', '')
        item_type = item.get('type')
        if item_type == 'file':
            nodes.append({
                'path': item_path,
                'type': 'file',
                'size': item.get('size', 0),
                'sha': item.get('sha', ''),
            })
        elif item_type == 'dir':
            nodes.append({
                'path': item_path,
                'type': 'directory',
                'size': 0,
                'sha': item.get('sha', ''),
            })
            # Recurse subfolder
            sub_nodes = _walk_directory_contents(owner, repo, item_path, branch, token)
            nodes.extend(sub_nodes)
    return nodes


def inspect_repository(token, repository):
    """
    Fetch comprehensive recursive repository structure through GitHub's Git Trees API.
    Handles truncated responses, access verification, and metadata calculation.
    Enforces CloudWise platform repository analysis limits.
    """
    started_at = time.monotonic()
    owner, repo_name, full_name = normalize_github_repo_url(repository)
    encoded_full_name = urllib.parse.quote(full_name, safe='/')

    # 1. Verify GitHub repository access & obtain metadata
    repo_url = f"https://api.github.com/repos/{encoded_full_name}"
    repo_meta = _request_json(repo_url, token, allow_404=False)
    if not repo_meta or not isinstance(repo_meta, dict):
        raise GitHubApiError(f"Unable to access repository '{full_name}'.", status_code=404)

    default_branch = (
        (repository.get('default_branch') if isinstance(repository, dict) else None)
        or repo_meta.get('default_branch')
        or 'main'
    )

    # 2. Get latest commit SHA for the branch
    commit_sha = ''
    commit_url = f"https://api.github.com/repos/{encoded_full_name}/commits/{urllib.parse.quote(default_branch)}"
    commit_info = _request_json(commit_url, token, allow_404=True)
    if isinstance(commit_info, dict):
        commit_sha = commit_info.get('sha', '')

    # 3. Fetch full recursive tree
    tree_url = (
        f'https://api.github.com/repos/{encoded_full_name}/git/trees/'
        f'{urllib.parse.quote(default_branch)}?recursive=1'
    )

    tree_data = _request_json(tree_url, token, allow_404=True)
    raw_tree = tree_data.get('tree', []) if isinstance(tree_data, dict) else []
    truncated = bool(tree_data.get('truncated')) if isinstance(tree_data, dict) else False

    full_tree = []
    target_paths_to_fetch = set()

    if raw_tree:
        for node in raw_tree:
            path = node.get('path', '')
            node_type = node.get('type', 'blob')  # 'blob' or 'tree'
            size = node.get('size', 0)
            sha = node.get('sha', '')

            is_dir = node_type in ('tree', 'dir', 'directory')
            full_tree.append({
                'path': path,
                'type': 'directory' if is_dir else 'file',
                'size': size if not is_dir else 0,
                'sha': sha,
            })

            if not is_dir and _is_analysis_file(path):
                target_paths_to_fetch.add(path)

    # Fallback to Contents API if tree was truncated or empty
    if truncated or not full_tree:
        walked_nodes = _walk_directory_contents(owner, repo_name, "", default_branch, token)
        if walked_nodes:
            full_tree = walked_nodes
            for node in full_tree:
                if node['type'] == 'file' and _is_analysis_file(node['path']):
                    target_paths_to_fetch.add(node['path'])

    total_files = len([node for node in full_tree if node.get('type') == 'file'])
    total_directories = len([node for node in full_tree if node.get('type') in ('directory', 'folder')])

    # Enforce CloudWise platform analysis limits before downloading file contents
    check_repository_limits(full_tree, elapsed_seconds=time.monotonic() - started_at)
    repository_size = compute_repository_size(full_tree)

    # Standard fallbacks if target_paths_to_fetch is empty
    if not target_paths_to_fetch:
        for fname in SUPPORTED_REPOSITORY_FILES:
            target_paths_to_fetch.add(fname)

    # 4. Fetch contents of discovered target files for tech stack analysis
    found_files = {}
    for path in target_paths_to_fetch:
        filename = path.replace('\\', '/').split('/')[-1].lower()
        if filename not in ENV_TEMPLATE_FILENAMES and _is_sensitive_env_filename(filename):
            continue
        check_repository_limits(
            full_tree,
            elapsed_seconds=time.monotonic() - started_at,
        )
        encoded_path = urllib.parse.quote(path, safe='/')
        url = (
            f'https://api.github.com/repos/{encoded_full_name}/contents/'
            f'{encoded_path}?ref={urllib.parse.quote(default_branch)}'
        )
        item = _request_json(url, token, allow_404=True)
        if item is None or not isinstance(item, dict) or item.get('type') != 'file':
            continue

        encoded_content = item.get('content')
        if not encoded_content:
            continue

        try:
            content = base64.b64decode(
                encoded_content.replace('\n', '').encode(),
                validate=True,
            ).decode('utf-8')
            found_files[path] = content
        except (ValueError, UnicodeDecodeError):
            pass

    has_dockerfile = any(p.lower().endswith('dockerfile') for p in found_files.keys())
    has_compose = any('docker-compose' in p.lower() for p in found_files.keys())
    has_cicd = any('.github/workflows' in p.lower() for p in found_files.keys())

    return {
        'repository': {
            'owner': owner,
            'name': repo_name,
            'full_name': full_name,
            'defaultBranch': default_branch,
        },
        'branch': default_branch,
        'commitSha': commit_sha,
        'tree': full_tree,
        'files': found_files,
        'totalFiles': total_files,
        'totalDirectories': total_directories,
        'truncated': truncated,
        'scannedAt': datetime.now().isoformat(),
        'repositorySize': repository_size,
        'has_dockerfile': has_dockerfile,
        'has_compose': has_compose,
        'has_cicd': has_cicd,
    }

