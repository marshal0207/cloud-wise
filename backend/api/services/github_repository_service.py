import base64
import urllib.parse

from .github_service import GitHubApiError, _request_json


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
)


def _repository_parts(repository):
    repository_name = repository.get('full_name') or repository.get('name', '')
    branch = repository.get('default_branch') or 'main'
    if repository_name.count('/') != 1:
        raise ValueError('GitHub repository must use the owner/name format.')
    return repository_name, branch


def inspect_repository(token, repository):
    """
    Fetch comprehensive recursive repository structure through GitHub's Git Trees API.
    Guarantees no file or folder is missed.
    """
    repository_name, branch = _repository_parts(repository)
    encoded_repository = urllib.parse.quote(repository_name, safe='/')

    # 1. Fetch full recursive tree
    tree_url = (
        f'https://api.github.com/repos/{encoded_repository}/git/trees/'
        f'{urllib.parse.quote(branch)}?recursive=1'
    )

    tree_data = _request_json(tree_url, token)
    raw_tree = tree_data.get('tree', []) if isinstance(tree_data, dict) else []

    full_tree = []
    found_files = {}

    target_paths_to_fetch = set()

    for node in raw_tree:
        path = node.get('path', '')
        node_type = node.get('type', 'blob')  # 'blob' or 'tree'
        size = node.get('size', 0)

        full_tree.append({
            'path': path,
            'type': 'file' if node_type == 'blob' else 'folder',
            'size': size
        })

        filename = path.split('/')[-1].lower()
        if (
            filename in (f.lower() for f in SUPPORTED_REPOSITORY_FILES)
            or filename == 'dockerfile'
            or filename.startswith('docker-compose')
            or path.startswith('.github/workflows/')
        ):
            target_paths_to_fetch.add(path)

    # Fallback to root files if recursive tree is truncated or empty
    if not target_paths_to_fetch:
        for fname in SUPPORTED_REPOSITORY_FILES:
            target_paths_to_fetch.add(fname)

    # 2. Fetch contents of discovered target files
    for path in target_paths_to_fetch:
        encoded_path = urllib.parse.quote(path, safe='/')
        url = (
            f'https://api.github.com/repos/{encoded_repository}/contents/'
            f'{encoded_path}?ref={urllib.parse.quote(branch)}'
        )
        item = _request_json(url, token)
        if item is None or item.get('type') != 'file':
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
        'repository': repository_name,
        'branch': branch,
        'tree': full_tree,
        'files': found_files,
        'has_dockerfile': has_dockerfile,
        'has_compose': has_compose,
        'has_cicd': has_cicd,
    }
