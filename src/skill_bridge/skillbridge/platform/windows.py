import subprocess
import os


def _run_powershell(script: str) -> tuple[str, str, int]:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def batch_check_paths(paths: list[str]) -> list[dict]:
    """Check multiple paths in a single PowerShell call for performance."""
    import json as _json
    paths_json = _json.dumps(paths)
    script = f"""
    $paths = '{paths_json}' | ConvertFrom-Json
    $result = @()
    foreach ($p in $paths) {{
        $item = Get-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue
        $isJunction = $false
        $isDir = $false
        $resolved = ''
        if ($item) {{
            $attrs = $item.Attributes
            $isJunction = ($attrs -band [System.IO.FileAttributes]::ReparsePoint) -ne 0
            if (-not $isJunction) {{
                $isDir = ($attrs -band [System.IO.FileAttributes]::Directory) -ne 0
            }}
        }}
        if ($isJunction) {{
            $targetVal = $item.Target
            if ($targetVal) {{
                if ($targetVal -is [string]) {{
                    $resolvedTarget = $targetVal
                }} else {{
                    $resolvedTarget = $targetVal[0]
                }}
                if (Test-Path -LiteralPath $resolvedTarget) {{
                    $resolved = $resolvedTarget
                }} else {{
                    $resolved = 'BROKEN'
                }}
            }}
        }}
        $result += @{{'path'=$p; 'is_junction'=$isJunction; 'is_real_dir'=$isDir; 'resolved'=[string]$resolved}}
    }}
    Write-Output ($result | ConvertTo-Json -Compress)
    """
    out, err, code = _run_powershell(script)
    if code != 0 or not out:
        return []
    try:
        data = _json.loads(out)
        # PowerShell ConvertTo-Json returns a single dict (not array) for 1 element
        if isinstance(data, dict):
            return [data]
        return data
    except Exception:
        return []


def is_junction(path: str) -> bool:
    res = batch_check_paths([path])
    return res[0]["is_junction"] if res else False


def is_real_directory(path: str) -> bool:
    res = batch_check_paths([path])
    return res[0]["is_real_dir"] if res else False


def resolve_junction_target(path: str) -> str:
    res = batch_check_paths([path])
    return res[0]["resolved"] if res else ""


def create_junction(target_path: str, source_path: str) -> tuple[bool, str]:
    try:
        # Remove existing junction via cmd if present (avoids PowerShell confirm prompts)
        if os.path.exists(target_path):
            import subprocess as _sp
            _sp.run(["cmd", "/c", "rmdir", target_path], capture_output=True, timeout=15)
        script = f"""
        New-Item -ItemType Junction -Path '{target_path}' -Target '{source_path}' -Force | Out-Null
        if (-not (Test-Path -LiteralPath '{target_path}')) {{ exit 1 }}
        Write-Output 'ok'
        """
        out, err, code = _run_powershell(script)
        if out != "ok":
            return False, err or out or "junction creation failed"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "PowerShell operation timed out"
    except Exception as e:
        return False, str(e)


def remove_junction(path: str) -> tuple[bool, str]:
    try:
        if not os.path.exists(path):
            return True, ""
        # Verify it's a junction before removing
        if not is_junction(path):
            return False, "Path is a real directory, not a junction"
        import subprocess as _sp
        result = _sp.run(["cmd", "/c", "rmdir", path], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return False, result.stderr.strip() or result.stdout.strip() or f"rmdir failed (code {result.returncode})"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "rmdir operation timed out"
    except Exception as e:
        return False, str(e)


def resolve_junction_target(path: str) -> str:
    script = f"""
    $item = Get-Item -LiteralPath '{path}' -Force -ErrorAction SilentlyContinue
    if ($item -and ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {{
        $target = $item.Target
        if ($target -and (Test-Path -LiteralPath $target)) {{
            Write-Output $target
        }} else {{
            Write-Output 'BROKEN'
        }}
    }} else {{
        Write-Output ''
    }}
    """
    out, _, _ = _run_powershell(script)
    return out


def backup_real_directory(path: str, backup_dir: str) -> tuple[bool, str]:
    try:
        script = f"""
        $ConfirmPreference = 'None'
        if (-not (Test-Path -LiteralPath '{path}')) {{
            Write-Output 'skipped'
            exit 0
        }}
        $item = Get-Item -LiteralPath '{path}' -Force
        if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {{
            Write-Error "Path is a junction, not a real directory"
            exit 1
        }}
        $backupParent = Split-Path -Parent '{backup_dir}'
        if (-not (Test-Path $backupParent)) {{
            New-Item -ItemType Directory -Path $backupParent -Force | Out-Null
        }}
        Move-Item -LiteralPath '{path}' -Destination '{backup_dir}' -Force
        if ($LASTEXITCODE -ne 0) {{ exit 1 }}
        Write-Output 'ok'
        """
        out, err, code = _run_powershell(script)
        if code != 0 or out != "ok":
            return False, err or out
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "PowerShell operation timed out"
    except Exception as e:
        return False, str(e)


def move_directory(src: str, dst: str) -> tuple[bool, str]:
    try:
        script = f"""
        $ConfirmPreference = 'None'
        if (-not (Test-Path -LiteralPath '{src}')) {{
            Write-Error "Source does not exist"
            exit 1
        }}
        $dstParent = Split-Path -Parent '{dst}'
        if (-not (Test-Path $dstParent)) {{
            New-Item -ItemType Directory -Path $dstParent -Force | Out-Null
        }}
        Move-Item -LiteralPath '{src}' -Destination '{dst}' -Force
        if ($LASTEXITCODE -ne 0) {{ exit 1 }}
        Write-Output 'ok'
        """
        out, err, code = _run_powershell(script)
        if code != 0 or out != "ok":
            return False, err or out
        return True, ""
    except Exception as e:
        return False, str(e)
