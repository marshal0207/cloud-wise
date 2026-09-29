"""
In-instance database connectivity probe (pure standard library).

This module is executed **on the deployment instance** (uploaded base64
encoded through SSM and run with ``python3``) and is also imported by the
CloudWise test suite, so its logic is unit-testable without an EC2 box.

It answers three questions for a deployment whose repository declares an
external database (MongoDB Atlas / Neon / RDS / ...):

* ``env``  — is the declared environment variable present **and** non-empty
  in the ``.env`` file CloudWise uploaded?
* ``dns``  — can this machine resolve the database host?
* ``tcp``  — can this machine open a TCP connection to ``host:port``?

For ``mongodb+srv://`` connection strings the host has no A record (only
``_mongodb._tcp.<host>`` SRV + TXT records), so the SRV record is resolved
first and the concrete seed-list node is probed instead.

A fourth marker (``CLOUDWISE_PROXY``) records what answered on the public
HTTP entry point so a nginx ``502`` can be told apart from a dead backend.

Only marker lines are printed — never a connection string, host+credential
pair, password or any other secret. The script always exits 0 so a missing
runtime can never be mistaken for an SSM command failure.
"""

from __future__ import annotations

import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from typing import Callable, Sequence

DNS_TIMEOUT_SECONDS = 4
TCP_TIMEOUT_SECONDS = 6
HTTP_TIMEOUT_SECONDS = 6

# DNS-over-HTTPS resolvers used only to discover the SRV seed list. They are
# public, read-only endpoints; nothing about the deployment is sent to them
# apart from the SRV record name (the cluster hostname, no credentials).
DOH_ENDPOINTS: tuple[str, ...] = (
    "https://cloudflare-dns.com/dns-query?name={name}&type=SRV",
    "https://dns.google/resolve?name={name}&type=SRV",
)

DB_PROBE_MARKER = "CLOUDWISE_DB_PROBE"
PROXY_MARKER = "CLOUDWISE_PROXY"

_SAFE_HOST_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,251})$")
# The default nginx error page carries the version, e.g.
# ``<center>nginx/1.31.6</center>``; only matching ``<center>nginx</center>``
# made every 502 look like the *application* answered, which silently turned
# "backend down" into "no specific diagnosis".
_NGINX_SIGNATURE = re.compile(
    r"<center>\s*nginx(?:/[\w.-]+)?\s*</center>", re.IGNORECASE
)

NOT_APPLICABLE = "not_applicable"
VERDICT_NOT_APPLICABLE = NOT_APPLICABLE
VERDICT_REACHABLE = "reachable"
VERDICT_UNREACHABLE = "unreachable"
VERDICT_ENV_MISSING = "env_missing"
VERDICT_UNKNOWN = "unknown"


def safe_host(value: object) -> str:
    """Return a host that is safe to hand to the OS resolver, else ''."""
    text = str(value or "").strip().rstrip(".")
    if not text or len(text) > 253 or not _SAFE_HOST_RE.match(text):
        return ""
    return text


# ---------------------------------------------------------------------------
# environment variable check
# ---------------------------------------------------------------------------

def check_env(env_file: str, var: str) -> str:
    """
    ``ok``     — ``VAR=value`` with a non-empty value
    ``missing``— the file or the variable is absent / empty
    ``unknown``— nothing to check (no file, no variable name)
    """
    if not var:
        return "unknown"
    if not env_file:
        return "missing"
    try:
        with open(env_file, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                name, _, value = stripped.partition("=")
                if name.strip() == var:
                    return "ok" if value.strip() else "missing"
        return "missing"
    except OSError:
        return "missing"


# ---------------------------------------------------------------------------
# DNS (SRV discovery + host resolution)
# ---------------------------------------------------------------------------

def parse_srv_payload(payload: object) -> tuple[list[tuple[str, int]], bool]:
    """
    Parse a DNS-over-HTTPS JSON answer.

    Returns ``(records, definitive)`` — ``definitive`` is True when the
    resolver actually answered (so a second resolver does not have to be
    tried), False when the payload was unusable.
    """
    try:
        data = json.loads(str(payload))
    except (TypeError, ValueError):
        return [], False
    if not isinstance(data, dict):
        return [], False

    status = data.get("Status")
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = None
    if status not in (0, 3):  # NOERROR / NXDOMAIN — anything else is retryable
        return [], False

    records: list[tuple[str, int]] = []
    answers = data.get("Answer")
    if isinstance(answers, list):
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            if answer.get("type") not in (33, "33"):
                continue
            parts = str(answer.get("data") or "").split()
            if len(parts) != 4:
                continue
            try:
                port = int(parts[2])
            except ValueError:
                continue
            target = safe_host(parts[3])
            if target and 0 < port < 65536:
                records.append((target, port))
    return records, True


def _urllib_fetch(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "accept": "application/dns-json",
            "user-agent": "CloudWise-Deploy/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(65536).decode("utf-8", "replace")


def resolve_srv(
    host: str,
    *,
    fetch: Callable[[str, float], str] | None = None,
    endpoints: Sequence[str] = DOH_ENDPOINTS,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> list[tuple[str, int]]:
    """Resolve ``_mongodb._tcp.<host>`` → [(target, port), ...]."""
    host = safe_host(host)
    if not host:
        return []
    do_fetch = fetch or _urllib_fetch
    for template in endpoints:
        try:
            payload = do_fetch(template.format(name=host), timeout)
        except Exception:  # noqa: BLE001 — network/HTTPS simply unavailable
            continue
        records, definitive = parse_srv_payload(payload)
        if records:
            return records
        if definitive:
            return []
    return []


def resolve_target(
    host: str,
    port: int,
    srv: bool,
    *,
    resolver: Callable[[str], list[tuple[str, int]]] | None = None,
) -> tuple[str, int, str]:
    """
    Return ``(target_host, target_port, source)``.

    ``source`` is ``direct`` (host from the connection string), ``srv``
    (seed-list node discovered through SRV) or ``unresolved`` (nothing
    probeable — the caller must report ``unknown``, never a failure).
    """
    host = safe_host(host)
    if not host:
        return "", int(port or 0), "unresolved"
    if not srv:
        return host, int(port), "direct"
    resolve = resolver or resolve_srv
    try:
        records = resolve(host)
    except Exception:  # noqa: BLE001 — an exotic resolver must not break us
        records = []
    if records:
        target, srv_port = records[0]
        return target, int(srv_port or port), "srv"
    return "", int(port), "unresolved"


def check_dns(host: str) -> str:
    """``ok`` / ``fail`` through the machine's own resolver, else ``unknown``."""
    if not host:
        return "unknown"
    for _ in range(2):
        try:
            socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            return "ok"
        except OSError:
            continue
    return "fail"


# ---------------------------------------------------------------------------
# TCP connectivity
# ---------------------------------------------------------------------------

def check_tcp(host: str, port: int) -> str:
    """``ok`` / ``fail`` / ``unknown`` (nothing to probe)."""
    if not host or not port:
        return "unknown"
    try:
        with socket.create_connection((host, int(port)), timeout=TCP_TIMEOUT_SECONDS):
            return "ok"
    except OSError:
        return "fail"


# ---------------------------------------------------------------------------
# HTTP entry-point probe (nginx vs application origin)
# ---------------------------------------------------------------------------

def _urllib_http(url: str, timeout: float) -> tuple[int, str]:
    request = urllib.request.Request(
        url, headers={"user-agent": "CloudWise-Deploy/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.getcode() or 0), response.read(8192).decode(
                "utf-8", "replace"
            )
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read(8192).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            body = ""
        return int(exc.code or 0), body
    except Exception:  # noqa: BLE001 — refused / timed out / unreachable
        return 0, ""


def check_proxy(
    url: str,
    *,
    fetch: Callable[[str, float], tuple[int, str]] | None = None,
    timeout: float = HTTP_TIMEOUT_SECONDS,
) -> dict:
    """
    Probe the public HTTP entry point.

    Returns ``{"api": <http code, 0 when nothing answered>,
    "proxy": none|nginx|app|unknown}``.
    """
    if not url:
        return {"api": 0, "proxy": "unknown"}
    do_fetch = fetch or _urllib_http
    try:
        code, body = do_fetch(url, timeout)
    except Exception:  # noqa: BLE001
        return {"api": 0, "proxy": "unknown"}
    try:
        code = int(code)
    except (TypeError, ValueError):
        code = 0
    if code <= 0:
        return {"api": 0, "proxy": "none"}
    origin = "nginx" if _NGINX_SIGNATURE.search(body or "") else "app"
    return {"api": code, "proxy": origin}


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def verdict_for(kind: str, env: str, dns: str, tcp: str) -> str:
    if not kind or kind == "none":
        return NOT_APPLICABLE
    if env == "missing":
        return VERDICT_ENV_MISSING
    if dns == "fail" or tcp == "fail":
        return VERDICT_UNREACHABLE
    if dns == "ok" and tcp == "ok":
        return VERDICT_REACHABLE
    return VERDICT_UNKNOWN


def build_report(
    *,
    kind: str = "",
    env: str = "unknown",
    dns: str = "unknown",
    tcp: str = "unknown",
    proxy: dict | None = None,
) -> dict:
    return {
        "kind": kind or "none",
        "env": env,
        "dns": dns,
        "tcp": tcp,
        "verdict": verdict_for(kind or "", env, dns, tcp),
        "proxy": dict(proxy or {"api": 0, "proxy": "unknown"}),
    }


def format_markers(report: dict) -> str:
    proxy = report.get("proxy") or {}
    return "\n".join(
        [
            (
                f"{DB_PROBE_MARKER} kind={report.get('kind') or 'none'} "
                f"env={report.get('env')} dns={report.get('dns')} "
                f"tcp={report.get('tcp')} verdict={report.get('verdict')}"
            ),
            (
                f"{PROXY_MARKER} api={int(proxy.get('api') or 0)} "
                f"proxy={proxy.get('proxy') or 'unknown'}"
            ),
        ]
    )


def run_probe(
    *,
    kind: str = "",
    env_file: str = "",
    var: str = "",
    host: str = "",
    port: int = 0,
    srv: bool = False,
    proxy_url: str = "",
    env_check: Callable[[str, str], str] = check_env,
    target_resolver: Callable[..., tuple[str, int, str]] = resolve_target,
    dns_check: Callable[[str], str] = check_dns,
    tcp_check: Callable[[str, int], str] = check_tcp,
    proxy_check: Callable[[str], dict] = check_proxy,
) -> dict:
    """Run every check and return the structured report (seams injectable)."""
    if kind:
        env = env_check(env_file, var)
        target, target_port, source = target_resolver(host, port, srv)
        dns = dns_check(target)
        # A TCP probe is only meaningful once the name resolves.
        tcp = tcp_check(target, target_port) if dns == "ok" else "unknown"
    else:
        env, target, target_port, source = "unknown", "", 0, "none"
        dns = tcp = "unknown"
    proxy = proxy_check(proxy_url) if proxy_url else {"api": 0, "proxy": "unknown"}
    report = build_report(kind=kind, env=env, dns=dns, tcp=tcp, proxy=proxy)
    report["targetSource"] = source if kind else "none"
    report["targetPort"] = int(target_port or 0) if kind else 0
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cloudwise-db-probe", add_help=False
    )
    parser.add_argument("--kind", default="")
    parser.add_argument("--env-file", default="")
    parser.add_argument("--var", default="")
    parser.add_argument("--host", default="")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--srv", type=int, default=0)
    parser.add_argument("--proxy-url", default="")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        report = run_probe(
            kind=str(args.kind or ""),
            env_file=str(args.env_file or ""),
            var=str(args.var or ""),
            host=str(args.host or ""),
            port=int(args.port or 0),
            srv=bool(int(args.srv or 0)),
            proxy_url=str(args.proxy_url or ""),
        )
        print(format_markers(report))
    except Exception:  # noqa: BLE001 — markers only, never a traceback
        print(f"{DB_PROBE_MARKER} status=unavailable")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":  # pragma: no cover — executed on the instance
    raise SystemExit(main())
