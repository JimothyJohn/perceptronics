"""``perceptronics init`` (a cell file from a few answers) and ``up``'s defaults (2026-10-06)."""

from __future__ import annotations

import io

import pytest

from perceptronics.cell import load_cell
from perceptronics.wizard import cell_text, run_init, up_bind


def _init(tmp_path, answers: str = "", **kw) -> tuple[int, str, str]:
    out = io.StringIO()
    rc = run_init("demo", out_dir=str(tmp_path), inp=io.StringIO(answers), out=out, **kw)
    text = (tmp_path / "demo.env").read_text(encoding="utf-8") if (tmp_path / "demo.env").exists() else ""
    return rc, out.getvalue(), text


def test_the_defaults_are_the_ur3e_test_cell(tmp_path):
    rc, shown, text = _init(tmp_path, yes=True)
    assert rc == 0
    cell = load_cell(str(tmp_path / "demo.env"))  # the loader accepts it: every key in its namespace
    assert cell["UR_HOST"] == "192.168.3.3" and cell["UR_PLATFORM"] == "e-series"
    assert cell["UR_ROBOT_MODEL"] == "UR3e" and cell["PERCEPTRONICS_TIP_M"] == "0.163"
    assert cell["PERCEPTRONICS_STANDOFF_M"] == "0.075" and cell["PERCEPTRONICS_BRACKET"] == "eseries"
    assert cell["PERCEPTRONICS_RS_PRESET"] == "high_density" and "PERCEPTRONICS_FAKE" not in cell
    assert "doctor" in shown and "up" in shown and "demo.env" in shown
    assert text.startswith("# Cell profile 'demo'")


def test_answers_from_a_pipe_make_a_polyscope_x_cell_with_no_camera(tmp_path):
    answers = "ur-polyscopex\n10.0.0.44\nUR10e\n120\n60\nur20\nnone\n"
    rc, shown, _ = _init(tmp_path, answers)
    assert rc == 0, shown
    cell = load_cell(str(tmp_path / "demo.env"))
    assert cell["UR_PLATFORM"] == "polyscopex" and cell["UR_ROBOT_API_PORT"] == "80"
    assert cell["UR_HOST"] == "10.0.0.44" and cell["UR_ROBOT_MODEL"] == "UR10e"
    assert cell["PERCEPTRONICS_TIP_M"] == "0.120" and cell["PERCEPTRONICS_STANDOFF_M"] == "0.060"
    assert cell["PERCEPTRONICS_BRACKET"] == "ur20" and cell["PERCEPTRONICS_FAKE"] == "1"


def test_a_wrong_answer_falls_back_to_the_default_and_says_so(tmp_path):
    answers = "fanuc\n\nur99\nlots\n\n\n\n"
    rc, shown, _ = _init(tmp_path, answers)
    assert rc == 0, shown
    cell = load_cell(str(tmp_path / "demo.env"))
    assert cell["UR_PLATFORM"] == "e-series" and cell["UR_ROBOT_MODEL"] == "UR3e"
    assert cell["PERCEPTRONICS_TIP_M"] == "0.163"
    assert "not one of" in shown and "is not a number" in shown


def test_sim_and_no_robot_cells(tmp_path):
    rc, _, _ = _init(tmp_path, "sim\n\n\n\n\n\n")
    assert rc == 0
    cell = load_cell(str(tmp_path / "demo.env"))
    assert cell["UR_HOST"] == "localhost" and cell["UR_ROBOT_API_PORT"] == "8000"
    assert cell["UR_PRIMARY_PORT"] == "31001"
    rc, _, text = _init(tmp_path, "none\n\n\n\n\n", force=True)
    assert rc == 0 and "UR_HOST=\n" in text and "UR_PLATFORM" not in text


def test_an_existing_file_is_kept_unless_forced(tmp_path):
    assert _init(tmp_path, yes=True)[0] == 0
    (tmp_path / "demo.env").write_text("UR_HOST=1.2.3.4\n")
    rc, shown, text = _init(tmp_path, yes=True)
    assert rc == 2 and "exists" in shown and text == "UR_HOST=1.2.3.4\n"
    assert _init(tmp_path, yes=True, force=True)[0] == 0


@pytest.mark.parametrize("name", ["bad name", "a/b", ""])
def test_a_bad_name_is_refused(tmp_path, name):
    out = io.StringIO()
    rc = run_init(name, out_dir=str(tmp_path), yes=True, inp=io.StringIO(), out=out)
    assert (rc, name == "") in ((2, False), (0, True))  # '' means the default name


def test_the_file_only_holds_keys_the_loader_takes():
    for a in (
        {
            "robot": "ur-eseries",
            "host": "1.1.1.1",
            "model": "UR5e",
            "tip_mm": "163",
            "standoff_mm": "75",
            "bracket": "eseries",
            "camera": "realsense",
        },
        {
            "robot": "none",
            "host": "",
            "model": "UR3e",
            "tip_mm": "0",
            "standoff_mm": "10",
            "bracket": "none",
            "camera": "none",
        },
    ):
        for key in (
            ln.split("=", 1)[0]
            for ln in cell_text("x", a).splitlines()
            if "=" in ln and not ln.startswith("#")
        ):
            assert key.startswith(("UR_", "PERCEPTRONICS_", "REALSENSE_")), key


def test_up_listens_to_the_cell_when_there_is_a_robot():
    assert up_bind({"UR_HOST": "192.168.3.3"}) == "0.0.0.0"
    assert up_bind({"UR_HOST": "localhost"}) == "127.0.0.1"
    assert up_bind({}) == "127.0.0.1"
    assert up_bind({"UR_HOST": ""}) == "127.0.0.1"
