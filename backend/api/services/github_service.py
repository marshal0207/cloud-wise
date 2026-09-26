import base64
import json
import time
import urllib.error
import urllib.parse
import urllib.request


class GitHubApiError(RuntimeError):
    def __init__(self, message, status_code=500, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.details = details or message


_RATE_LIMIT_STATUS_CODES = {403, 429}
_MAX_RETRIES = 3
_INITIAL_RETRY_DELAY = 1.0


def _is_rate_limit_response(exc):
    """Return True when GitHub indicates the API rate limit is exhausted."""
    if exc.code not in _RATE_LIMIT_STATUS_CODES:
        return False
    remaining = exc.headers.get('X-RateLimit-Remaining')
    if remaining is not None and remaining == '0':
        return True
    try:
        body = json.loads(exc.read().decode(errors='replace') or '{}')
        return body.get('message', '').lower().startswith('api rate limit')
    except (ValueError, AttributeError):
        return False


def _read_details(exc):
    try:
        return exc.read().decode(errors='replace')
    except Exception:
        return str(exc)


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


def _request_json(url, token=None, method='GET', payload=None, allow_404=True, max_retries=3):
    """
    Perform a GitHub API request with exponential-backoff retries for
    rate-limit (403/429) and transient network errors.

    Never falls back to an unauthenticated request: a private repository
    must only be reachable with the caller's own token, so silently
    falling through would leak data or give the wrong result.
    """
    last_exc = None
    delay = _INITIAL_RETRY_DELAY

    for attempt in range(max_retries + 1):
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {
            'Accept': 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': 'CloudWise',
        }
        if token:
            headers['Authorization'] = f'Bearer {token}'

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode()
                return json.loads(raw) if raw else {}

        except urllib.error.HTTPError as exc:
            details = _read_details(exc)

            if exc.code in _RATE_LIMIT_STATUS_CODES and _is_rate_limit_response(exc):
                if attempt < max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise GitHubApiError(
                    'GitHub API rate limit exceeded. Please wait a few minutes before retrying.',
                    status_code=429, details=details
                )

            if exc.code == 401:
                raise GitHubApiError(
                    'GitHub authentication failed or token expired. Re-authorize your GitHub account.',
                    status_code=401, details=details
                )

            if exc.code == 403 and not _is_rate_limit_response(exc):
                raise GitHubApiError(
                    'GitHub permission denied — the connected account does not have access to this repository.',
                    status_code=403, details=details
                )

            if exc.code == 404:
                if allow_404:
                    return None
                raise GitHubApiError(
                    'GitHub repository or resource not found.',
                    status_code=404, details=details
                )

            if exc.code == 422:
                raise GitHubApiError(
                    'Invalid repository data. Confirm the repository exists and is accessible.',
                    status_code=422, details=details
                )

            raise GitHubApiError(
                f'GitHub API returned HTTP {exc.code}: {details}',
                status_code=exc.code, details=details
            )

        except urllib.error.URLError as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise GitHubApiError(
                f'GitHub API request failed (network error): {exc}',
                status_code=502, details=str(exc)
            )
        except json.JSONDecodeError as exc:
            last_exc = exc
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
                continue
            raise GitHubApiError(
                'Failed to parse GitHub API response.',
                status_code=502, details=str(exc)
            )

    raise GitHubApiError(
        'GitHub API request failed after retries.',
        status_code=502, details=str(last_exc) if last_exc else 'Unknown error'
    )


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
