import base64
import urllib.parse
from datetime import datetime

from .github_service import GitHubApiError, _request_json, normalize_github_repo_url


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
    """
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

            if not is_dir:
                filename = path.split('/')[-1].lower()
                if (
                    filename in (f.lower() for f in SUPPORTED_REPOSITORY_FILES)
                    or filename == 'dockerfile'
                    or filename.startswith('docker-compose')
                    or filename == 'manage.py'
                    or filename.startswith('vite.config')
                    or filename.startswith('next.config')
                    or path.startswith('.github/workflows/')
                ):
                    target_paths_to_fetch.add(path)

    # Fallback to Contents API if tree was truncated or empty
    if truncated or not full_tree:
        walked_nodes = _walk_directory_contents(owner, repo_name, "", default_branch, token)
        if walked_nodes:
            full_tree = walked_nodes
            for node in full_tree:
                if node['type'] == 'file':
                    filename = node['path'].split('/')[-1].lower()
                    if (
                        filename in (f.lower() for f in SUPPORTED_REPOSITORY_FILES)
                        or filename == 'dockerfile'
                        or filename.startswith('docker-compose')
                        or filename == 'manage.py'
                        or node['path'].startswith('.github/workflows/')
                    ):
                        target_paths_to_fetch.add(node['path'])

    # Standard fallbacks if target_paths_to_fetch is empty
    if not target_paths_to_fetch:
        for fname in SUPPORTED_REPOSITORY_FILES:
            target_paths_to_fetch.add(fname)

    # 4. Fetch contents of discovered target files for tech stack analysis
    found_files = {}
    for path in target_paths_to_fetch:
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

    total_files = len([node for node in full_tree if node.get('type') == 'file'])
    total_directories = len([node for node in full_tree if node.get('type') in ('directory', 'folder')])

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
        'has_dockerfile': has_dockerfile,
        'has_compose': has_compose,
        'has_cicd': has_cicd,
    }

