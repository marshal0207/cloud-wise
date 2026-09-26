import base64
import re
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

_SENSITIVE_FILENAMES = {'.env', '.env.local', '.env.production', '.env.staging', '.env.development'}

_SECRETS_PATTERN = re.compile(
    r'(?i)(secret|password|passwd|pass|token|api[_-]?key|access[_-]?key|private[_-]?key|credential|auth|bearer|client_secret|db_url|database_url|connection_string|aws_secret|stripe|sk_live|ghp_|gho_|github_pat_)',
)


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


def _is_analysis_file(path: str) -> bool:
    normalized = path.replace('\\', '/')
    filename = normalized.split('/')[-1].lower()
    if filename in ENV_TEMPLATE_FILENAMES:
        return True
    if filename in _SENSITIVE_FILENAMES:
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


def _redact_secrets(content: str) -> str:
    """Return a redacted copy — secret VALUES are replaced with [REDACTED]."""
    return re.sub(
        r'(?i)(secret|password|passwd|pass|token|api[_-]?key|access[_-]?key|private[_-]?key|credential|auth|bearer|client_secret|db_url|database_url|connection_string|aws_secret|stripe|sk_live|ghp_|gho_|github_pat_)\s*[=:]\s*["\']?[^\s"\',;}\]]+["\']?',
        r'\1=[REDACTED]',
        content,
    )


def _looks_like_secret_path(path: str) -> bool:
    filename = path.strip('/').split('/')[-1].lower()
    return filename in _SENSITIVE_FILENAMES


def _walk_directory_contents(owner, repo, path, branch, token):
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
            sub_nodes = _walk_directory_contents(owner, repo, item_path, branch, token)
            nodes.extend(sub_nodes)
    return nodes


def _extract_commit_info(commit_info):
    if not isinstance(commit_info, dict):
        return '', '', '', ''
    commit = commit_info.get('commit', {})
    return (
        commit_info.get('sha', ''),
        commit.get('message', '')[:200] if commit.get('message') else '',
        commit.get('author', {}).get('date', '') if isinstance(commit.get('author'), dict) else '',
        commit_info.get('commit', {}).get('committer', {}).get('date', '') if isinstance(commit_info.get('commit', {}).get('committer'), dict) else '',
    )


def inspect_repository(token, repository, progress_callback=None):
    """
    Inspect a real GitHub repository using the caller's own token.

    Steps:
      1. Validate repo format (owner/repo)
      2. Fetch repository metadata
      3. Verify access (private repos require the connected account)
      4. Get latest commit
      5. Fetch recursive tree
      6. Download relevant file contents (with secrets redaction)
      7. Return full analysis object
    """
    started_at = time.monotonic()

    def _progress(stage: str, message: str, pct: int):
        if progress_callback is not None:
            progress_callback(stage, message, pct)

    _progress('validating', 'Validating repository format...', 0)
    try:
        owner, repo_name, full_name = normalize_github_repo_url(repository)
    except ValueError as exc:
        raise ValueError(str(exc)) from exc

    encoded_full_name = urllib.parse.quote(full_name, safe='/')

    _progress('fetching_repo', 'Fetching repository metadata...', 10)
    repo_url = f"https://api.github.com/repos/{encoded_full_name}"
    repo_meta = _request_json(repo_url, token, allow_404=False)
    if not repo_meta or not isinstance(repo_meta, dict):
        raise GitHubApiError(
            f"Unable to access repository '{full_name}'.", status_code=404
        )

    if repo_meta.get('private') and not repo_meta.get('permissions', {}).get('pull', False):
        try:
            permissions_url = f"https://api.github.com/repos/{encoded_full_name}/collaborators/{owner}/permission"
            perm = _request_json(permissions_url, token, allow_404=True)
            if perm and perm.get('permission') in ('pull', 'triage', 'push', 'maintain', 'admin'):
                pass
            else:
                raise GitHubApiError(
                    f"Account does not have access to private repository '{full_name}'.",
                    status_code=403, details='access_denied'
                )
        except GitHubApiError:
            raise
        except Exception as exc:
            raise GitHubApiError(
                f"Unable to verify access to private repository '{full_name}'.",
                status_code=403, details=str(exc)
            )

    default_branch = repo_meta.get('default_branch') or 'main'
    visibility = repo_meta.get('visibility', 'private' if repo_meta.get('private') else 'public')
    language = repo_meta.get('language') or ''
    size = repo_meta.get('size', 0)
    description = repo_meta.get('description', '')
    stargazers = repo_meta.get('stargazers_count', 0)
    forks = repo_meta.get('forks_count', 0)
    open_issues = repo_meta.get('open_issues_count', 0)

    _progress('fetching_commit', 'Reading latest commit...', 25)
    commit_sha = ''
    commit_message = ''
    commit_date = ''
    commit_url = f"https://api.github.com/repos/{encoded_full_name}/commits/{urllib.parse.quote(default_branch)}"
    commit_info = _request_json(commit_url, token, allow_404=True)
    if isinstance(commit_info, dict):
        commit_sha, commit_message, commit_date, _ = _extract_commit_info(commit_info)

    _progress('fetching_tree', 'Reading repository tree...', 40)
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
            node_type = node.get('type', 'blob')
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

    if truncated or not full_tree:
        walked_nodes = _walk_directory_contents(owner, repo_name, "", default_branch, token)
        if walked_nodes:
            full_tree = walked_nodes
            for node in full_tree:
                if node['type'] == 'file' and _is_analysis_file(node['path']):
                    target_paths_to_fetch.add(node['path'])

    total_files = len([n for n in full_tree if n.get('type') == 'file'])
    total_directories = len([n for n in full_tree if n.get('type') in ('directory', 'folder')])

    check_repository_limits(full_tree, elapsed_seconds=time.monotonic() - started_at)
    repository_size = compute_repository_size(full_tree)

    if not target_paths_to_fetch:
        for fname in SUPPORTED_REPOSITORY_FILES:
            target_paths_to_fetch.add(fname)

    _progress('detecting_files', 'Detecting project files...', 55)
    found_files = {}
    for path in sorted(target_paths_to_fetch):
        if _looks_like_secret_path(path):
            continue
        filename = path.replace('\\', '/').split('/')[-1].lower()
        is_target = (
            filename in ENV_TEMPLATE_FILENAMES
            or filename in _SUPPORTED_REPOSITORY_FILENAMES
            or filename.startswith('dockerfile')
            or filename.startswith('docker-compose')
            or filename == 'manage.py'
            or filename.startswith('vite.config')
            or filename.startswith('next.config')
            or filename.startswith('drizzle.config')
            or filename == 'schema.prisma'
            or path.startswith('.github/workflows/')
        )
        if not is_target:
            continue
        check_repository_limits(full_tree, elapsed_seconds=time.monotonic() - started_at)
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
                encoded_content.replace('\n', '').encode(), validate=True
            ).decode('utf-8')
            redacted = _redact_secrets(content)
            found_files[path] = redacted
        except (ValueError, UnicodeDecodeError):
            pass

    _progress('analyzing', 'Analyzing project structure...', 75)
    has_dockerfile = any(p.lower().endswith('dockerfile') for p in found_files.keys())
    has_compose = any('docker-compose' in p.lower() for p in found_files.keys())
    has_cicd = any('.github/workflows' in p.lower() for p in found_files.keys())
    has_readme = any(p.lower() == 'readme.md' for p in found_files.keys())
    has_env_example = any(p.lower().startswith('.env.') or p.lower() == '.env.example' for p in found_files.keys())

    env_files = sorted(
        p for p in found_files.keys()
        if p.lower().endswith(('.env', '.env.example', '.env.sample', '.env.template', '.env.local'))
    )

    _progress('scanning_complete', 'Scan completed.', 100)

    return {
        'repository': {
            'owner': owner,
            'name': repo_name,
            'full_name': full_name,
            'defaultBranch': default_branch,
            'visibility': visibility,
            'language': language,
            'description': description,
            'sizeMb': size,
            'stargazersCount': stargazers,
            'forksCount': forks,
            'openIssuesCount': open_issues,
        },
        'branch': default_branch,
        'commitSha': commit_sha,
        'commitMessage': commit_message,
        'commitDate': commit_date,
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
        'has_readme': has_readme,
        'env_files_detected': env_files,
    }
