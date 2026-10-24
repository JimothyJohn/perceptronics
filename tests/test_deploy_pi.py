"""The pick PC deployment's contract, checked without a Pi (deploy/pi/, scripts/deploy-pi.sh).

The scripts must parse (and pass shellcheck where it is installed), the systemd unit must
run the cockpit as an unprivileged user with a restart policy and a command line the real
CLI accepts, the installer must pin librealsense to the release the ctypes binding was
written against and never pipe a download into a shell, every variable the cell.env
template sets must be one the code reads, the cell.env the installer writes must parse
the same under perceptronics's own parser, and the firewall must drop by default.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from perceptronics import webapp
from perceptronics.cell import list_cells, parse_env_text
from perceptronics.picknode import DEFAULT_PICK_PORT

ROOT = Path(__file__).resolve().parents[1]
PI = ROOT / "deploy" / "pi"
INSTALL = PI / "install.sh"
UNIT = PI / "perceptronics-cockpit.service"
NFT = PI / "nftables.conf"
TEMPLATE = PI / "cell.env.template"
DOCTOR = PI / "perceptronics-doctor"
CELL_DHCP_CONF = PI / "cell-dhcp.conf"
CELL_DHCP_UNIT = PI / "perceptronics-cell-dhcp.service"
NM_HOOK = PI / "50-perceptronics-cell"
DEPLOY = ROOT / "scripts" / "deploy-pi.sh"
BASH_SCRIPTS = [INSTALL, DEPLOY]


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _code(text: str) -> str:
    """The script without its comment lines (so documentation can name what code must not do)."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


# ----- shell scripts ------------------------------------------------------------------------


def _real_bash() -> str | None:
    """A bash that runs (on a Windows runner ``bash`` is WSL's launcher with no distribution)."""
    bash = shutil.which("bash")
    if bash is None:
        return None
    try:
        ran = subprocess.run([bash, "-c", "echo ok"], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return bash if ran.stdout.strip() == b"ok" else None


@pytest.mark.parametrize("script", BASH_SCRIPTS, ids=lambda p: p.name)
def test_bash_scripts_parse(script):
    bash = _real_bash()
    if bash is None:
        pytest.skip("no working bash on this machine")
    subprocess.run([bash, "-n", str(script)], check=True)


def test_doctor_wrapper_parses_as_posix_sh():
    subprocess.run(["sh", "-n", str(DOCTOR)], check=True)


@pytest.mark.parametrize("script", [*BASH_SCRIPTS, DOCTOR], ids=lambda p: p.name)
def test_shellcheck_clean(script):
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed (CI's lint job installs it)")
    result = subprocess.run(["shellcheck", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("script", BASH_SCRIPTS, ids=lambda p: p.name)
def test_strict_mode(script):
    assert re.search(r"^set -euo pipefail$", _text(script), re.M)


@pytest.mark.parametrize("script", [*BASH_SCRIPTS, DOCTOR], ids=lambda p: p.name)
def test_no_password_plumbing(script):
    code = _code(_text(script))
    assert "sshpass" not in code
    assert "SSHPASS" not in code
    assert not re.search(r"\bsudo\s+-S\b", code), "sudo -S reads a password from stdin"


@pytest.mark.parametrize("script", [*BASH_SCRIPTS, DOCTOR], ids=lambda p: p.name)
def test_never_pipes_a_download_into_a_shell(script):
    code = _code(_text(script))
    assert not re.search(r"\b(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b", code)
    assert not re.search(r"\b(ba)?sh\s+<\(\s*(curl|wget)", code)


def test_deploy_script_is_executable():
    # the mode git records is what a Linux checkout (the PC, CI) gets; Windows has no exec bit
    for path in (INSTALL, DEPLOY, DOCTOR):
        rel = path.relative_to(ROOT).as_posix()
        try:
            staged = subprocess.run(
                ["git", "ls-files", "-s", "--", rel], cwd=ROOT, capture_output=True, text=True, timeout=30
            ).stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            staged = []
        if staged:
            assert staged[0] == "100755", f"{rel} is committed without its executable bit"
        elif sys.platform != "win32":
            assert path.stat().st_mode & 0o111, f"{path} is not executable"


# ----- librealsense pin -------------------------------------------------------------------


def _assignment(name: str, text: str) -> str:
    m = re.search(rf'^readonly {name}="([^"]+)"$', text, re.M)
    assert m, f"no readonly {name}=... in install.sh"
    return m.group(1)


def test_librealsense_is_pinned_to_the_binding_release():
    text = _text(INSTALL)
    tag = _assignment("LIBREALSENSE_TAG", text)
    commit = _assignment("LIBREALSENSE_COMMIT", text)
    assert re.fullmatch(r"v\d+\.\d+\.\d+", tag), f"not a release tag: {tag}"
    assert re.fullmatch(r"[0-9a-f]{40}", commit), "the tag's commit must be pinned too"
    # the ctypes binding checks enum ordinals written against this minor
    binding = _text(ROOT / "perceptronics" / "realsense.py")
    minor = re.search(r"written against librealsense (\d+\.\d+)", binding).group(1)
    assert tag.lstrip("v").startswith(minor + "."), f"{tag} is not librealsense {minor}.x"
    assert 'rev-parse HEAD)"' in text and "$LIBREALSENSE_COMMIT" in text, "the clone's commit is checked"


@pytest.mark.parametrize(
    "option",
    [
        "-DFORCE_RSUSB_BACKEND=ON",
        "-DBUILD_EXAMPLES=OFF",
        "-DBUILD_GRAPHICAL_EXAMPLES=OFF",
        "-DBUILD_PYTHON_BINDINGS=OFF",
        "-DCHECK_FOR_UPDATES=OFF",
    ],
)
def test_librealsense_build_options(option):
    block = re.search(r"LIBREALSENSE_CMAKE_OPTS=\((.*?)\)", _text(INSTALL), re.S).group(1)
    assert option in block.split()


def test_installed_library_is_what_the_template_points_at():
    text = _text(INSTALL)
    link = _assignment("LIBREALSENSE_LINK", text)
    assert parse_env_text(_text(TEMPLATE))["REALSENSE_LIB"] == f"{link}/lib/librealsense2.so"


def test_installer_copies_only_files_that_exist():
    # the loop inside copy_deploy_files (install_vision_wheels has a `for f in` of its own, before it)
    body = _text(INSTALL).split("copy_deploy_files() {", 1)[1]
    m = re.search(r"for f in ([^;]+); do", body)
    names = [n for n in m.group(1).split() if n != "\\"]
    assert names, "copy_deploy_files names no files"
    for name in names:
        assert (PI / name).is_file(), f"install.sh copies {name}, which is not in deploy/pi/"


# ----- systemd unit -----------------------------------------------------------------------


def _unit(path: Path) -> dict[str, dict[str, list[str]]]:
    """systemd's INI dialect: repeated keys accumulate, ``#``/``;`` lines are comments."""
    sections: dict[str, dict[str, list[str]]] = {}
    current = None
    for raw in _text(path).splitlines():
        line = raw.strip()
        if not line or line[0] in "#;":
            continue
        m = re.fullmatch(r"\[([A-Za-z]+)\]", line)
        if m:
            current = sections.setdefault(m.group(1), {})
            continue
        assert current is not None, f"{path.name}: {raw!r} is outside a section"
        assert "=" in line, f"{path.name}: {raw!r} is not KEY=VALUE"
        key, value = line.split("=", 1)
        assert re.fullmatch(r"[A-Za-z]+", key.strip()), f"{path.name}: bad key {key!r}"
        current.setdefault(key.strip(), []).append(value.strip())
    return sections


def _one(section: dict[str, list[str]], key: str) -> str:
    assert key in section, f"missing {key}="
    return section[key][-1]


def test_unit_has_the_three_sections():
    assert set(_unit(UNIT)) == {"Unit", "Service", "Install"}
    assert _one(_unit(UNIT)["Install"], "WantedBy") == "multi-user.target"


def test_unit_runs_unprivileged_and_restarts():
    svc = _unit(UNIT)["Service"]
    user = _one(svc, "User")
    assert user and user not in ("root", "0")
    assert _one(svc, "Restart") in ("on-failure", "always")
    assert _one(svc, "RestartSec")
    assert _one(svc, "NoNewPrivileges") == "yes"
    assert _one(svc, "ProtectSystem") == "strict"
    assert _one(svc, "PrivateTmp") == "yes"
    assert _one(svc, "CapabilityBoundingSet") == ""
    assert "PrivateDevices" not in svc, "PrivateDevices hides /dev/bus/usb from librealsense"
    assert "char-usb_device rw" in svc["DeviceAllow"]


def test_unit_state_is_writable_where_the_cockpit_writes():
    svc = _unit(UNIT)["Service"]
    workdir = _one(svc, "WorkingDirectory")
    writable = " ".join(svc.get("ReadWritePaths", [])).split()
    assert workdir in writable, "captures/ (relative to the working directory) must be writable"
    template = parse_env_text(_text(TEMPLATE))
    for key in ("PERCEPTRONICS_HANDEYE_FILE", "UR_AUDIT_LOG"):
        assert Path(template[key]).is_relative_to(workdir), f"{key} is outside ReadWritePaths"


def test_unit_reads_the_cell_file_the_installer_writes():
    svc = _unit(UNIT)["Service"]
    cell_env = _assignment("CELL_ENV", _text(INSTALL).replace("${ETC_DIR}", "/etc/perceptronics"))
    assert _one(svc, "EnvironmentFile") == cell_env
    assert f"--cell {cell_env}" in _text(DOCTOR).replace('"$CELL"', cell_env)


def test_unit_execstart_parses_under_the_real_cli(monkeypatch):
    argv = _one(_unit(UNIT)["Service"], "ExecStart").split()
    assert argv[0] == "/opt/perceptronics/current/bin/perceptronics"
    monkeypatch.delenv("UR_CELL", raising=False)
    served = {}
    monkeypatch.setattr(webapp, "camera_from_args", lambda args, config: None)
    monkeypatch.setattr(webapp, "robot_from_args", lambda args: None)
    monkeypatch.setattr(webapp, "serve", lambda *a, **kw: served.update(kw))
    from perceptronics import cli

    assert cli.main(argv[1:]) == 0  # argparse exits 2 on an unknown flag
    assert served["bind"] == "0.0.0.0"
    assert served["port"] == webapp.DEFAULT_PORT
    assert served["pick_port"] == DEFAULT_PICK_PORT
    assert served["open_browser"] is False


def test_unit_documents_ports_and_stop_command():
    text = _text(UNIT)
    assert str(webapp.DEFAULT_PORT) in text and str(DEFAULT_PICK_PORT) in text
    assert "systemctl stop perceptronics-cockpit" in text
    assert "/api/pick/log" in text, "where the pick trace is read is written where the next person looks"


# ----- cell.env ---------------------------------------------------------------------------


def _env_names_read_by_code() -> set[str]:
    names: set[str] = set()
    for pkg in ("perceptronics", "urctl"):
        for path in (ROOT / pkg).rglob("*.py"):
            names.update(re.findall(r"[\"']((?:UR|PERCEPTRONICS|REALSENSE)_[A-Z0-9_]+)[\"']", _text(path)))
    return names


def test_template_keys_are_read_by_the_code():
    keys = set(parse_env_text(_text(TEMPLATE)))
    assert keys, "empty template"
    unknown = keys - _env_names_read_by_code()
    assert not unknown, f"cell.env.template sets variables no code reads: {sorted(unknown)}"


def test_template_is_plain_for_both_parsers():
    for raw in _text(TEMPLATE).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        assert not set(value) & set("\"'\\$`#"), (
            f"{key}: systemd and the cell parser read {value!r} differently"
        )


def _cell_writer() -> str:
    m = re.search(r"<<'PY'\n(.*?)\nPY\n", _text(INSTALL), re.S)
    assert m, "install.sh has no cell.env writer heredoc"
    return m.group(1)


def _write_cell(tmp_path: Path, cell: str, robot_host: str) -> subprocess.CompletedProcess:
    out = tmp_path / "cell.env"
    return subprocess.run(
        [sys.executable, "-c", _cell_writer(), cell, robot_host, str(TEMPLATE), str(out)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.parametrize("cell", list_cells())
def test_written_cell_env_parses_and_is_self_contained(tmp_path, cell):
    result = _write_cell(tmp_path, cell, "192.168.3.3")
    assert result.returncode == 0, result.stderr
    values = parse_env_text((tmp_path / "cell.env").read_text(encoding="utf-8"))
    assert values["UR_HOST"] == "192.168.3.3"
    assert values["REALSENSE_LIB"] == parse_env_text(_text(TEMPLATE))["REALSENSE_LIB"]
    assert set(values) <= _env_names_read_by_code()


def test_cell_env_needs_a_robot_host(tmp_path):
    empty = [
        c
        for c in list_cells()
        if not parse_env_text(_text(ROOT / "perceptronics" / "cells" / f"{c}.env")).get("UR_HOST")
    ]
    if not empty:
        pytest.skip("every shipped cell has a UR_HOST")
    result = _write_cell(tmp_path, empty[0], "")
    assert result.returncode != 0
    assert "--robot-host" in result.stderr
    assert not (tmp_path / "cell.env").exists()


def test_cell_env_refuses_unknown_cell(tmp_path):
    result = _write_cell(tmp_path, "no-such-cell", "10.0.0.2")
    assert result.returncode != 0 and "--cell" in result.stderr


# ----- firewall ---------------------------------------------------------------------------


def _chain(name: str) -> str:
    m = re.search(rf"chain {name} \{{(.*?)\n    \}}", _text(NFT), re.S)
    assert m, f"no chain {name}"
    return m.group(1)


def test_firewall_drops_by_default():
    assert re.search(r"type filter hook input priority filter; policy drop;", _chain("input"))
    assert re.search(r"hook forward .*policy drop;", _chain("forward"))


def test_firewall_opens_only_ssh_and_the_cockpit_to_the_cell():
    rules = [
        ln.strip() for ln in _chain("input").splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    accepts = [r for r in rules if r.endswith("accept")]
    port_rules = [r for r in accepts if "dport" in r and "udp sport 67" not in r]
    assert "tcp dport 22 accept" in port_rules
    cockpit = [r for r in port_rules if r != "tcp dport 22 accept"]
    assert cockpit == [
        "iifname $CELL_IF udp dport 67 accept",  # the robot's DHCP request, on the cell port only
        "ip saddr $CELL_NET tcp dport $COCKPIT_PORTS accept",
    ]
    assert re.search(
        rf"define COCKPIT_PORTS = \{{ {webapp.DEFAULT_PORT}, {DEFAULT_PICK_PORT} \}}", _text(NFT)
    )
    assert 'iif "lo" accept' in rules


def test_firewall_subnet_is_substituted_by_the_installer():
    assert "define CELL_NET = @CELL_NET@" in _text(NFT)
    assert "s#@CELL_NET@#" in _text(INSTALL)
    marker = re.search(r'NFT_MARKER="([^"]+)"', _text(INSTALL)).group(1)
    assert marker in _text(NFT), "install.sh recognises its own /etc/nftables.conf by this marker"
    assert "flush ruleset" not in _code(_text(NFT)), "only our own table is replaced"


# ----- the cell port: fixed address + one-lease DHCP for a robot nobody configured ----------


def _render(path: Path) -> str:
    """The file as install.sh writes it for the defaults (eth0, the ur3 cell's UR_HOST)."""
    from perceptronics import cellnet

    return (
        _text(path)
        .replace("@CELL_IF@", "eth0")
        .replace("@ROBOT_ADDRESS@", cellnet.ROBOT_ADDRESS)
        .replace("@CELL_MASK@", "255.255.255.0")
    )


def test_every_placeholder_in_the_cell_files_is_one_the_installer_fills():
    filled = set(re.findall(r'-e "s#(@[A-Z_]+@)#', _text(INSTALL)))
    for path in (CELL_DHCP_CONF, CELL_DHCP_UNIT, NM_HOOK, NFT):
        used = set(re.findall(r"@[A-Z_]+@", _text(path)))
        assert used <= filled | {"@CELL_NET@"}, f"{path.name}: {used - filled} never substituted"
        assert not re.findall(r"@[A-Z_]+@", _render(path).replace("@CELL_NET@", "x"))


def test_cell_dhcp_serves_one_address_and_nothing_else():
    from perceptronics import cellnet

    lines = [ln for ln in _render(CELL_DHCP_CONF).splitlines() if ln and not ln.startswith("#")]
    assert "port=0" in lines, "no DNS server"
    assert "interface=eth0" in lines and "except-interface=lo" in lines
    ranges = [ln for ln in lines if ln.startswith("dhcp-range=")]
    a = cellnet.ROBOT_ADDRESS
    assert ranges == [f"dhcp-range={a},{a},255.255.255.0,12h"], "one lease: the robot's address never moves"
    # an empty option is sent as "none": no default route and no DNS offered, the cell stays offline
    assert "dhcp-option=option:router" in lines and "dhcp-option=option:dns-server" in lines
    banned = ("dhcp-authoritative", "server=", "address=", "enable-tftp")
    assert not any(ln.startswith(banned) for ln in lines)


def test_cell_dhcp_only_starts_after_the_probe_heard_no_other_server():
    unit = _unit(CELL_DHCP_UNIT)
    assert set(unit) == {"Unit", "Service", "Install"}
    cond = _one(unit["Service"], "ExecCondition")
    assert cond == "/opt/perceptronics/current/bin/python -m perceptronics.cellnet probe @CELL_IF@"
    start = _one(unit["Service"], "ExecStart")
    assert start == "/usr/sbin/dnsmasq --keep-in-foreground --conf-file=/etc/perceptronics/cell-dhcp.conf"
    doc = _text(CELL_DHCP_UNIT)
    assert "stop:" in doc and "journalctl -u perceptronics-cell-dhcp" in doc


def test_link_up_re_probes(tmp_path):
    hook = _render(NM_HOOK)
    assert hook.startswith("#!/bin/sh")
    assert "systemctl restart --no-block perceptronics-cell-dhcp.service" in hook
    # NetworkManager only runs an executable hook: what ships is git's mode, not the checkout's
    # (a Windows checkout has no exec bit at all)
    staged = subprocess.run(
        ["git", "ls-files", "--stage", str(NM_HOOK.relative_to(ROOT))],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if staged.returncode == 0 and staged.stdout:
        assert staged.stdout.startswith("100755 "), staged.stdout
    else:
        assert NM_HOOK.stat().st_mode & 0o111
    script = tmp_path / "hook"
    script.write_text(hook, encoding="utf-8")
    subprocess.run(["sh", "-n", str(script)], check=True)
    if shutil.which("shellcheck"):
        r = subprocess.run(["shellcheck", "-s", "sh", str(script)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout


def test_installer_defaults_and_its_guards():
    code = _code(_text(INSTALL))
    assert 'cell_if="eth0" cell_address="192.168.3.20/24"' in code
    assert "--cell-if)" in code and "--cell-address)" in code
    # a port already on another network (the bench's office LAN) is never re-addressed
    assert re.search(r'if \[ -n "\$have" \]; then\n\s+log "cell port: .* is on another network', code)
    # the lease must be on the pick PC's network, or nothing is served
    assert "is not on ${cidr} — not serving" in code
    assert "/usr/sbin/dnsmasq --test" in code
    # Raspberry Pi OS's own eth0 profile names no interface (netplan `match: {}`) and still
    # owns the port: one that already carries the address is kept, not duplicated
    assert '" 802-3-ethernet "*' in code
    assert "dnsmasq-base" in code


# ----- the hand-eye lives in the calibration file, not cell.env ---------------------------------


def _handeye_snippet() -> str:
    """The Python install.sh's handeye_out_of_env runs, exactly as written there."""
    body = _text(INSTALL).split("handeye_out_of_env() {", 1)[1]
    return body.split("<<'PY'\n", 1)[1].split("\nPY\n", 1)[0]


def _run_handeye(tmp_path, cell_text: str, existing: str | None = None):
    cell_env, file, out = tmp_path / "cell.env", tmp_path / "cal" / "handeye.json", tmp_path / "cell.env.new"
    cell_env.write_text(cell_text, encoding="utf-8")
    if existing is not None:
        file.parent.mkdir()
        file.write_text(existing, encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, "-", str(cell_env), str(file), str(out)],
        input=_handeye_snippet(),
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=True,
    )
    return ran.stdout.strip(), file, out


def test_the_profiles_hand_eye_seeds_the_file_and_leaves_the_environment(tmp_path):
    from perceptronics.cell import load_cell
    from perceptronics.handeye import ENV_HANDEYE_FILE, ENV_T_FLANGE_CAMERA, HandEye

    pose = load_cell("ur3")[ENV_T_FLANGE_CAMERA]
    said, file, out = _run_handeye(tmp_path, f"UR_HOST=192.168.3.3\n{ENV_T_FLANGE_CAMERA}={pose}\n")
    assert said == "seeded"
    assert ENV_T_FLANGE_CAMERA not in parse_env_text(out.read_text(encoding="utf-8"))
    he = HandEye.from_env({ENV_HANDEYE_FILE: str(file)})
    assert he.source == f"file:{file}"
    assert he.as_dict()["flange_to_depth_pose"] == pytest.approx(json.loads(pose))


def test_a_calibration_made_on_the_pc_survives_a_redeploy(tmp_path):
    saved = '{"flange_to_depth_pose": [0.02, 0.05, 0.01, 0.1, -0.16, 3.1], "source": "touch-and-click"}'
    said, file, out = _run_handeye(
        tmp_path, "UR_HOST=192.168.3.3\nPERCEPTRONICS_T_FLANGE_CAMERA=[0,0,0,0,0,0]\n", existing=saved
    )
    assert said == "kept" and file.read_text(encoding="utf-8") == saved
    assert "PERCEPTRONICS_T_FLANGE_CAMERA" not in out.read_text(encoding="utf-8")


def test_a_cell_env_without_a_hand_eye_is_left_alone(tmp_path):
    said, file, out = _run_handeye(tmp_path, "UR_HOST=192.168.3.3\n")
    assert said == "none" and not file.exists() and not out.exists()


def test_the_installer_runs_the_move_on_every_install():
    code = _code(_text(INSTALL))
    main = code.split("main() {", 1)[1]
    assert main.index("write_cell_env") < main.index("handeye_out_of_env") < main.index("install_units")
    # and the cell.env it writes no longer tells anyone to delete the line by hand
    assert "delete the PERCEPTRONICS_T_FLANGE_CAMERA" not in _text(INSTALL)


# ----- deploy-pi.sh: the Python that builds the wheel ---------------------------------------


def _python_with_pip() -> str | None:
    for cand in (sys.executable, shutil.which("python3"), "/opt/homebrew/bin/python3", "/usr/bin/python3"):
        if cand and subprocess.run([cand, "-m", "pip", "--version"], capture_output=True).returncode == 0:
            return cand
    return None


def test_deploy_skips_a_python_without_pip(tmp_path):
    # Regression (2026-10-02): the repo's .venv (no pip) was first on PATH and the deploy died
    # with "python3 with pip not found" although Homebrew's python3 had pip.
    bash, good = _real_bash(), _python_with_pip()
    if bash is None or good is None or sys.platform == "win32":
        pytest.skip("needs bash and some python3 with pip")
    code = _text(DEPLOY)
    loop = code[code.index('py=""\n') : code.index('[ -n "$py" ]')]
    fake = tmp_path / "bin"
    fake.mkdir()
    nopip = fake / "python3"
    nopip.write_text('#!/bin/sh\n[ "$2" = pip ] && exit 1\nexit 0\n', encoding="utf-8")
    nopip.chmod(0o755)
    script = f'{loop}\nprintf "%s" "$py"\n'
    env = {"PATH": f"{fake}:/usr/bin:/bin", "PYTHON": str(nopip)}
    picked = subprocess.run([bash, "-c", script], env=env, capture_output=True, text=True).stdout
    assert picked not in (str(nopip), "python3")  # never the pip-less one (a later install, or none)
    env["PYTHON"] = good
    assert subprocess.run([bash, "-c", script], env=env, capture_output=True, text=True).stdout == good


def test_deploy_copies_the_files_of_deploy_pi_not_its_directories():
    # Regression (2026-10-06): the first deploy after #49 died at the copy with
    # `scp: local ".../deploy/pi/image" is not a regular file` — deploy/pi/ grew a
    # subdirectory (image/, the card-image tooling, not for the PC). The fix that held at the
    # cell (2026-10-08) copies deploy/pi's regular files only, never a bare `deploy/pi/*`.
    assert any(p.is_dir() for p in PI.iterdir()), "deploy/pi has no subdirectory any more"
    text = _text(DEPLOY)
    assert 'for f in "$repo"/deploy/pi/*; do [ -f "$f" ] && pi_files+=("$f"); done' in text
    copies = [line for line in text.splitlines() if line.lstrip().startswith("scp ")]
    assert not [c for c in copies if "deploy/pi/*" in c], copies
    assert any('"${pi_files[@]}"' in c for c in copies), copies


def test_removing_the_cell_dhcp_clears_its_failed_state():
    # Regression (2026-10-06, old card): switching the robot DHCP off through the portal left
    # `perceptronics-cell-dhcp.service: failed (Result: signal)` in `systemctl --failed` — the
    # NetworkManager hook had restarted the unit on the address change and remove_cell_dhcp
    # stopped and deleted it mid-start. A deleted unit's failed entry stays until reset-failed.
    code = _text(INSTALL)
    body = code[code.index("remove_cell_dhcp() {") :]
    body = body[: body.index("\n}\n")]
    assert "reset-failed" in body, body
    assert body.index("daemon-reload") < body.index("reset-failed"), body


# ----- port 80: the portal without a port number (Nick, 2026-10-06) -----------------------


def test_firewall_serves_the_cockpit_on_port_80_too():
    # "Users won't be familiar with ports": http://<pick PC>/setup must work. The cockpit stays
    # unprivileged on :7621; nftables rewrites :80 before the input chain sees it, from the
    # same subnets that may reach :7621 (the input chain then admits it as :7621).
    chain = _chain("prerouting")
    assert re.search(r"type nat hook prerouting priority dstnat; policy accept;", chain)
    rules = [ln.strip() for ln in chain.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    assert rules[1:] == [f"ip saddr $CELL_NET tcp dport 80 redirect to :{webapp.DEFAULT_PORT}"], rules
    # and the input chain is unchanged: no separate accept for :80 (it never reaches input as :80)
    assert "dport 80" not in _chain("input")


def _installer_functions(tmp_path: Path, **paths: Path) -> Path:
    """A copy of install.sh to `source`: its functions, without the trailing `main "$@"`, with the
    named readonly paths (NETWORK_ENV, APP_ROOT, DEPLOY_COPY, ...) pointed into tmp_path."""
    code = _text(INSTALL).replace('\nmain "$@"\n', "\n")
    for name, value in paths.items():
        if name == "HERE":  # the bundle's deploy dir: set from BASH_SOURCE, then made readonly
            code, n = re.subn(r"^HERE=.*$", f'HERE="{value}"', code, flags=re.M)
        else:
            code, n = re.subn(rf"^readonly {name}=.*$", f'readonly {name}="{value}"', code, flags=re.M)
        assert n == 1, f"install.sh has no `{name}=` line to point at {value}"
    copy = tmp_path / "install.sh"
    copy.write_text(code)
    return copy


def test_a_network_change_recomputes_the_allowed_subnets(tmp_path):
    # Regression (2026-10-06, old card): after the portal moved the PC to 192.168.50.20 and back,
    # the firewall still admitted 192.168.50.0/24 — the saved ALLOW_FROM is the default of every
    # later run (right for an update), and --network reused it instead of computing the list for
    # the network it was moving to. A network change starts from the new address; only an explicit
    # --allow-from on that command line is kept.
    bash = _real_bash()
    if bash is None or sys.platform == "win32":
        pytest.skip("needs bash")
    saved = tmp_path / "network.env"
    saved.write_text(
        "CELL_IF=eth0\nCELL_ADDRESS=192.168.50.20/24\nALLOW_FROM=192.168.50.0/24,192.168.3.0/24\n"
    )
    copy = _installer_functions(tmp_path, NETWORK_ENV=saved)
    script = f"""
        source {copy}
        id() {{ echo 0; }}
        apply_network() {{ printf '%s|' "$@"; echo; }}
        main --network --cell-address 192.168.3.20/24 --gateway none --dns none
        main --network --cell-address 192.168.3.20/24 --allow-from 10.9.0.0/16
        main --wheel /nowhere.whl 2>/dev/null || true
    """
    out = subprocess.run([bash, "-c", script], capture_output=True, text=True)
    lines = out.stdout.strip().splitlines()
    assert len(lines) >= 2, (out.stdout, out.stderr)
    assert lines[0] == "eth0|192.168.3.20/24||||auto||", out  # recomputed by apply_network
    assert lines[1] == "eth0|192.168.3.20/24||||auto|10.9.0.0/16|", out  # the explicit one wins


# ----- rollback brings back the previous release's deploy files (2026-10-06) ---------------


def _fake_app_root(tmp_path: Path) -> Path:
    """releases/good (with its deploy files and wheel name kept) and releases/bad; current -> bad."""
    root = tmp_path / "opt"
    for name in ("good", "bad"):
        rel = root / "releases" / name
        (rel / "bin").mkdir(parents=True)
        (rel / "bin" / "perceptronics").write_text("#!/bin/sh\n")
        (rel / "bin" / "perceptronics").chmod(0o755)
        (rel / ".complete").touch()
    good = root / "releases" / "good"
    # every wheel has this name, so the release keeps its own copy (wheels/ holds only the newest)
    (good / "perceptronics-0.1.0-py3-none-any.whl").write_bytes(b"not really")
    (good / ".wheel").write_text("perceptronics-0.1.0-py3-none-any.whl\n")
    (good / "deploy").mkdir()
    stub = good / "deploy" / "install.sh"
    stub.write_text(f'#!/bin/bash\nprintf "%s\\n" "$@" > {tmp_path}/good-installer-argv\n')
    stub.chmod(0o755)
    (root / "current").symlink_to(root / "releases" / "bad")
    (root / "previous").symlink_to(good)
    return root


def _run_installer_function(bash: str, copy: Path, body: str) -> subprocess.CompletedProcess:
    script = f"""
        source {copy}
        systemctl() {{ echo "systemctl $*"; }}
        {body}
    """
    return subprocess.run([bash, "-c", script], capture_output=True, text=True)


def test_rollback_reinstalls_the_previous_release_with_its_own_installer(tmp_path):
    # Regression (2026-10-06, old card): a broken bundle's install.sh rewrote the firewall, the
    # units and /opt/perceptronics/deploy before its cockpit failed; --rollback swapped `current`
    # back and left all of that in place (port 80 gone, an older install.sh for the next job).
    bash = _real_bash()
    if bash is None or sys.platform == "win32":
        pytest.skip("needs bash")
    root = _fake_app_root(tmp_path)
    good = root / "releases" / "good"
    copy = _installer_functions(tmp_path, APP_ROOT=root)
    out = _run_installer_function(bash, copy, "rollback")
    assert out.returncode == 0, (out.stdout, out.stderr)
    argv = (tmp_path / "good-installer-argv").read_text().split()
    assert argv == ["--wheel", str(good / "perceptronics-0.1.0-py3-none-any.whl")], out.stdout
    assert "systemctl" not in out.stdout, "the previous installer restarts the service itself"


def test_rollback_to_a_release_without_kept_deploy_files_swaps_and_says_so(tmp_path):
    bash = _real_bash()
    if bash is None or sys.platform == "win32":
        pytest.skip("needs bash")
    root = _fake_app_root(tmp_path)
    shutil.rmtree(root / "releases" / "good" / "deploy")  # installed before the files were kept
    copy = _installer_functions(tmp_path, APP_ROOT=root)
    out = _run_installer_function(bash, copy, "rollback")
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert (root / "current").resolve() == root / "releases" / "good"
    assert (root / "previous").resolve() == root / "releases" / "bad"
    assert "systemctl restart perceptronics-cockpit.service" in out.stdout
    assert "not kept" in out.stdout, out.stdout


def test_the_installer_keeps_its_deploy_files_and_wheel_name_in_the_release(tmp_path):
    bash = _real_bash()
    if bash is None or sys.platform == "win32":
        pytest.skip("needs bash")
    root = _fake_app_root(tmp_path)
    copy = _installer_functions(tmp_path, APP_ROOT=root, HERE=PI)
    out = _run_installer_function(bash, copy, "copy_deploy_files")
    assert out.returncode == 0, (out.stdout, out.stderr)
    for where in (root / "deploy", root / "releases" / "bad" / "deploy"):  # current -> bad
        assert (where / "install.sh").is_file() and (where / "nftables.conf").is_file(), where
        assert (where / "install.sh").stat().st_mode & 0o111, where
        assert (where / "perceptronics-admin").stat().st_mode & 0o111, where
    # and install_app keeps the release's own wheel + its name, for rollback to re-run its installer
    app = _text(INSTALL)
    # (--rollback passes the release's own copy as --wheel: on the old card the first rollback died
    # on `cp: ... are the same file` and left the broken release running, 2026-10-06)
    into_release = r'"\$\{dest\}/\$\(basename "\$wheel"\)"'
    assert re.search(rf'\[ "\$wheel" -ef {into_release} \] \|\| cp -f "\$wheel" {into_release}', app), (
        "the wheel goes into the release, unless it is that copy already"
    )
    assert re.search(r'basename "\$wheel" *>"\$\{dest\}/\.wheel"', app), "install_app writes .wheel"
