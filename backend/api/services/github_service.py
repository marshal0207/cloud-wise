import base64
import json
import urllib.error
import urllib.parse
import urllib.request


class GitHubApiError(RuntimeError):
    def __init__(self, message, status_code=500, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or message


def normalize_github_repo_url(repo_input):
    """
    Normalizes GitHub repository strings or dictionaries to (owner, repo, full_name).
    Supports:
    - https://github.com/Tirth-22/doctor-appointment-management-system
    - https://github.com/Tirth-22/doctor-appointment-management-system.git
    - git@github.com:Tirth-22/doctor-appointment-management-system.git
    - Tirth-22/doctor-appointment-management-system
    - Tirth-22/doctor-appointment-management-system.git
    - {'name': 'Tirth-22/doctor-appointment-management-system'}
    """
    if isinstance(repo_input, dict):
        owner = repo_input.get('owner')
        name = repo_input.get('name') or repo_input.get('repo')
        full_name = repo_input.get('full_name')
        if isinstance(owner, dict):
            owner = owner.get('login', '')
        if full_name and '/' in str(full_name):
            repo_input = full_name
        elif owner and name and '/' not in str(name):
            repo_input = f"{owner}/{name}"
        elif name:
            repo_input = name
        else:
            repo_input = ""

    if not isinstance(repo_input, str):
        raise ValueError("Invalid repository input.")

    s = repo_input.strip()
    if s.endswith('.git'):
        s = s[:-4]

    if s.startswith('git@github.com:'):
        s = s[len('git@github.com:'):]

    if s.startswith('http://') or s.startswith('https://'):
        parsed = urllib.parse.urlparse(s)
        s = parsed.path.lstrip('/')

    parts = [p for p in s.split('/') if p]
    if len(parts) >= 2:
        owner = parts[-2]
        repo = parts[-1]
        return owner, repo, f"{owner}/{repo}"
    elif len(parts) == 1:
        raise ValueError("GitHub repository must specify both owner and repository name (e.g. owner/repo).")
    else:
        raise ValueError("GitHub repository is missing or not configured.")


def _request_json(url, token=None, method='GET', payload=None, allow_404=True, try_unauthenticated_on_401=True):
    def _make_req(use_token):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': 'CloudWise',
        }
        if use_token and token:
            headers['Authorization'] = f'Bearer {token}'
        return urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        req = _make_req(use_token=True)
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        details = exc.read().decode(errors='replace')
        if exc.code == 401:
            if token and method == 'GET' and try_unauthenticated_on_401:
                # Try unauthenticated request as fallback (for public repos with expired token)
                try:
                    req = _make_req(use_token=False)
                    with urllib.request.urlopen(req, timeout=20) as response:
                        return json.loads(response.read().decode())
                except urllib.error.HTTPError as fallback_exc:
                    # If the unauthenticated fallback got a 404 and allow_404 is set, treat as not-found
                    if fallback_exc.code == 404 and allow_404:
                        return None
                    # If fallback got 404 but allow_404 is False, raise not-found error
                    if fallback_exc.code == 404:
                        raise GitHubApiError('GitHub repository or resource not found.', status_code=404, details=details)
                    # Any other fallback error (403, 500, etc) → raise 401 since auth is the root cause
                    raise GitHubApiError('GitHub authentication failed or token expired.', status_code=401, details=details)
                except (urllib.error.URLError, json.JSONDecodeError):
                    pass
            raise GitHubApiError('GitHub authentication failed or token expired.', status_code=401, details=details)
        if exc.code == 403:
            raise GitHubApiError('GitHub permission denied or API rate limit exceeded.', status_code=403, details=details)
        if exc.code == 404:
            if allow_404:
                return None
            raise GitHubApiError('GitHub repository or resource not found.', status_code=404, details=details)
        raise GitHubApiError(f'GitHub API returned HTTP {exc.code}: {details}', status_code=exc.code, details=details)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise GitHubApiError(f'GitHub API request failed: {exc}', status_code=502, details=str(exc))



def push_files_to_repository(token, repository, files, commit_message):
    owner, repo_name, full_name = normalize_github_repo_url(repository)
    branch = (repository.get('default_branch') or repository.get('branch') or 'main') if isinstance(repository, dict) else 'main'

    encoded_repository = urllib.parse.quote(full_name, safe='/')
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
        'repository': full_name,
        'branch': branch,
        'files': list(files.keys()),
    }