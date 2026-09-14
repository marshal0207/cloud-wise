import base64
import json
import urllib.error
import urllib.parse
import urllib.request


class GitHubApiError(RuntimeError):
    pass


def _request_json(url, token, method='GET', payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'User-Agent': 'CloudWise',
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors='replace')
        if exc.code == 404:
            return None
        raise GitHubApiError(f'GitHub API returned HTTP {exc.code}: {details}') from exc
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GitHubApiError(f'GitHub API request failed: {exc}') from exc


def push_files_to_repository(token, repository, files, commit_message):
    repository_name = repository.get('full_name') or repository.get('name', '')
    branch = repository.get('default_branch') or 'main'
    if repository_name.count('/') != 1:
        raise ValueError('GitHub repository must use the owner/name format.')

    encoded_repository = urllib.parse.quote(repository_name, safe='/')
    commit_sha = None
    for path, content in files.items():
        if not isinstance(path, str) or not path.strip() or not isinstance(content, str):
            raise ValueError('Each generated file must contain a valid path and text content.')

        encoded_path = urllib.parse.quote(path, safe='/')
        file_url = f'https://api.github.com/repos/{encoded_repository}/contents/{encoded_path}'
        existing = _request_json(
            f'{file_url}?ref={urllib.parse.quote(branch)}',
            token,
        )
        payload = {
            'message': commit_message,
            'content': base64.b64encode(content.encode()).decode(),
            'branch': branch,
        }
        if existing and existing.get('sha'):
            payload['sha'] = existing['sha']

        result = _request_json(file_url, token, method='PUT', payload=payload)
        commit_sha = (result or {}).get('commit', {}).get('sha') or commit_sha

    return {
        'commit': commit_sha,
        'repository': repository_name,
        'branch': branch,
        'files': list(files.keys()),
    }