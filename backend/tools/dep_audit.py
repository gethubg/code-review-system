import json
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger()


def run_pip_audit(repo_path: str) -> dict:
    """Run pip-audit against the repo and return structured results.

    Returns:
        {
            "vulnerabilities": list[dict],
            "total": int,
            "error": str | None,
        }
    """
    path = Path(repo_path)
    if not path.exists():
        msg = f"repo_path does not exist: {repo_path}"
        log.error(msg)
        return {"vulnerabilities": [], "total": 0, "error": msg}

    try:
        result = subprocess.run(
            ["pip-audit", "--json", "--progress-spinner", "off"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = result.stdout.strip()
        if not raw:
            # pip-audit exits non-zero when vulns found, check stderr
            error = result.stderr.strip() or None
            if result.returncode not in (0, 1):
                log.error("pip-audit error", stderr=error, repo_path=repo_path)
                return {"vulnerabilities": [], "total": 0, "error": error}
            return {"vulnerabilities": [], "total": 0, "error": error}

        data = json.loads(raw)
        # pip-audit JSON output: list of {name, version, vulns: [...]}
        vulns = []
        for pkg in data:
            for v in pkg.get("vulns", []):
                vulns.append(
                    {
                        "package": pkg.get("name"),
                        "version": pkg.get("version"),
                        "id": v.get("id"),
                        "description": v.get("description", ""),
                        "fix_versions": v.get("fix_versions", []),
                        "aliases": v.get("aliases", []),
                    }
                )

        log.info("pip-audit complete", repo_path=repo_path, total=len(vulns))
        return {"vulnerabilities": vulns, "total": len(vulns), "error": None}

    except FileNotFoundError:
        msg = "pip-audit not found; install with: pip install pip-audit"
        log.warning(msg)
        return {"vulnerabilities": [], "total": 0, "error": msg}
    except subprocess.TimeoutExpired:
        msg = "pip-audit timed out"
        log.error(msg, repo_path=repo_path)
        return {"vulnerabilities": [], "total": 0, "error": msg}
    except json.JSONDecodeError as exc:
        msg = f"pip-audit JSON parse error: {exc}"
        log.error(msg, repo_path=repo_path)
        return {"vulnerabilities": [], "total": 0, "error": msg}
    except Exception as exc:
        msg = str(exc)
        log.exception("pip-audit unexpected error", repo_path=repo_path, error=msg)
        return {"vulnerabilities": [], "total": 0, "error": msg}


def run_npm_audit(repo_path: str) -> dict:
    """Run npm audit against the repo and return structured results.

    Returns:
        {
            "vulnerabilities": list[dict],
            "total": int,
            "error": str | None,
        }
    """
    path = Path(repo_path)
    if not path.exists():
        msg = f"repo_path does not exist: {repo_path}"
        log.error(msg)
        return {"vulnerabilities": [], "total": 0, "error": msg}

    package_json = path / "package.json"
    if not package_json.exists():
        msg = "No package.json found; skipping npm audit"
        log.info(msg, repo_path=repo_path)
        return {"vulnerabilities": [], "total": 0, "error": msg}

    try:
        result = subprocess.run(
            ["npm", "audit", "--json"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = result.stdout.strip()
        if not raw:
            error = result.stderr.strip() or None
            log.error("npm audit produced no output", stderr=error, repo_path=repo_path)
            return {"vulnerabilities": [], "total": 0, "error": error}

        data = json.loads(raw)

        # npm audit JSON v2 format
        vulns = []
        raw_vulns = data.get("vulnerabilities", {})
        for pkg_name, info in raw_vulns.items():
            severity = info.get("severity", "unknown")
            via = info.get("via", [])
            advisories = [v for v in via if isinstance(v, dict)]
            if advisories:
                for adv in advisories:
                    vulns.append(
                        {
                            "package": pkg_name,
                            "severity": severity,
                            "title": adv.get("title", ""),
                            "url": adv.get("url", ""),
                            "range": adv.get("range", ""),
                            "cwe": adv.get("cwe", []),
                            "cvss": adv.get("cvss", {}),
                        }
                    )
            else:
                vulns.append(
                    {
                        "package": pkg_name,
                        "severity": severity,
                        "title": "",
                        "url": "",
                        "range": info.get("range", ""),
                        "cwe": [],
                        "cvss": {},
                    }
                )

        metadata = data.get("metadata", {})
        total = metadata.get("vulnerabilities", {})
        if isinstance(total, dict):
            total_count = sum(total.values())
        else:
            total_count = len(vulns)

        log.info("npm audit complete", repo_path=repo_path, total=total_count)
        return {"vulnerabilities": vulns, "total": total_count, "error": None}

    except FileNotFoundError:
        msg = "npm not found in PATH"
        log.warning(msg)
        return {"vulnerabilities": [], "total": 0, "error": msg}
    except subprocess.TimeoutExpired:
        msg = "npm audit timed out"
        log.error(msg, repo_path=repo_path)
        return {"vulnerabilities": [], "total": 0, "error": msg}
    except json.JSONDecodeError as exc:
        msg = f"npm audit JSON parse error: {exc}"
        log.error(msg, repo_path=repo_path)
        return {"vulnerabilities": [], "total": 0, "error": msg}
    except Exception as exc:
        msg = str(exc)
        log.exception("npm audit unexpected error", repo_path=repo_path, error=msg)
        return {"vulnerabilities": [], "total": 0, "error": msg}
