import asyncio
import os


async def _run_command(*args: str, timeout: float | None = None) -> tuple[int | None, str, str]:
    """Run a shell command and return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise

    return proc.returncode, stdout.decode().strip(), stderr.decode().strip()


async def check_x_server_available():
    """Ensure DISPLAY is set and the X server responds. Raises on failure."""
    if not (display := os.environ.get("DISPLAY")):
        raise RuntimeError("DISPLAY environment variable is not set")

    async def _gather_diagnostics(display: str, xdpyinfo_error: str) -> str:
        """Gather diagnostic info when X server check fails."""
        info = [f"xdpyinfo error: {xdpyinfo_error[:200]}"]

        try:
            rc, stdout, _ = await _run_command("pgrep", "-a", "Xvnc")
            if rc == 0 and stdout:
                info.append(f"GOOD Xvnc: {stdout}")
            else:
                info.append("ERROR Xvnc process not found")
        except Exception as exc:
            info.append(f"ERROR Xvnc check failed: {exc}")

        try:
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
                info.append(f"Uptime: {uptime:.0f}s")
        except Exception:
            info.append("Uptime: unknown")

        try:
            rc, stdout, _ = await _run_command("pgrep", "-c", "chromium")
            if rc == 0 and stdout:
                info.append(f"Chrome processes: {stdout}")
            else:
                info.append("Chrome processes: 0")
        except Exception:
            info.append("Chrome processes: unknown")

        return "\n".join(info)

    try:
        rc, _, stderr = await _run_command("xdpyinfo", "-display", display, timeout=5)
    except FileNotFoundError:
        # xdpyinfo not installed - skip X server check (common in CI/test environments)
        return
    except asyncio.TimeoutError:
        diagnostics = await _gather_diagnostics(display, "xdpyinfo timed out")
        raise RuntimeError(f"X server check timed out:\n{diagnostics}")

    if rc == 0:
        return

    diagnostics = await _gather_diagnostics(display, stderr)
    raise RuntimeError(f"X server check failed:\n{diagnostics}")
