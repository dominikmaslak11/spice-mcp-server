#!/usr/bin/env python3
"""MCP server for quick SPICE circuit simulation via ngspice."""

import re
import subprocess
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from mcp.server.mcpserver import MCPServer  # noqa: E402

BASE_DIR = Path(__file__).parent.resolve()
CIRCUITS_DIR = BASE_DIR / "circuits"
CIRCUITS_DIR.mkdir(exist_ok=True)

mcp = MCPServer("spice-sim", version="0.1.0")


def _circuit_dir(name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("name must match [A-Za-z0-9_-]+")
    d = CIRCUITS_DIR / name
    (d / "data").mkdir(parents=True, exist_ok=True)
    (d / "plots").mkdir(parents=True, exist_ok=True)
    return d


def _parse_numeric_table(path: Path, max_rows: int = 500) -> dict:
    rows = []
    with open(path) as f:
        for line in f:
            parts = line.split()
            try:
                rows.append([float(p) for p in parts])
            except ValueError:
                continue
    truncated = len(rows) > max_rows
    if truncated:
        step = max(1, len(rows) // max_rows)
        rows = rows[::step]
    cols = list(zip(*rows)) if rows else []
    return {
        "n_rows": len(rows),
        "n_cols": len(cols),
        "columns": [list(c) for c in cols],
        "truncated_for_display": truncated,
    }


@mcp.tool()
def list_circuits() -> list[str]:
    """List saved circuit names."""
    return sorted(p.name for p in CIRCUITS_DIR.iterdir() if p.is_dir())


@mcp.tool()
def save_circuit(name: str, netlist: str) -> str:
    """Save (or overwrite) a SPICE netlist under the given circuit name.

    The netlist should be a full ngspice deck: title line, component
    lines, a .control block with the analysis + wrdata commands to
    write results into ./data/<file>, and .endc / .end.
    """
    d = _circuit_dir(name)
    path = d / "circuit.cir"
    path.write_text(netlist)
    return str(path)


@mcp.tool()
def get_circuit(name: str) -> str:
    """Return the saved netlist text for a circuit."""
    path = _circuit_dir(name) / "circuit.cir"
    if not path.exists():
        raise FileNotFoundError(f"No saved circuit named {name!r}")
    return path.read_text()


@mcp.tool()
def run_simulation(name: str, netlist: str | None = None, timeout_s: int = 60) -> dict:
    """Run ngspice in batch mode on a circuit and return the log plus any
    data files the netlist's .control block wrote into ./data/.

    If `netlist` is given it is saved first (overwriting any previous
    version). The netlist's .control block should end with one or more
    `wrdata data/<file>.txt <vectors>` commands -- those files are what
    this tool parses and returns as numeric columns.
    """
    d = _circuit_dir(name)
    circuit_path = d / "circuit.cir"
    if netlist is not None:
        circuit_path.write_text(netlist)
    if not circuit_path.exists():
        raise FileNotFoundError(f"No saved circuit named {name!r}; pass netlist=")

    data_dir = d / "data"
    before = {p: p.stat().st_mtime for p in data_dir.glob("*")}
    start = time.time()

    try:
        proc = subprocess.run(
            ["ngspice", "-b", str(circuit_path)],
            cwd=d,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        log = proc.stdout + proc.stderr
        success = proc.returncode == 0 and "error" not in log.lower()
    except subprocess.TimeoutExpired as e:
        log = (e.stdout or "") + (e.stderr or "") + f"\n[timed out after {timeout_s}s]"
        success = False

    new_files = [
        p for p in data_dir.glob("*") if p.stat().st_mtime >= start - 0.01 and (p not in before or p.stat().st_mtime > before.get(p, 0))
    ]

    data = {}
    for p in new_files:
        try:
            data[p.name] = _parse_numeric_table(p)
        except Exception as e:
            data[p.name] = {"error": str(e)}

    return {
        "success": success,
        "log": log[-8000:],
        "data_files": data,
        "circuit_dir": str(d),
    }


@mcp.tool()
def plot_result(
    name: str,
    data_file: str,
    x_col: int = 0,
    y_cols: list[int] | None = None,
    labels: list[str] | None = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    logx: bool = False,
    logy: bool = False,
) -> str:
    """Render a quick PNG plot from a data file produced by run_simulation
    (e.g. data/tran.txt) and return the PNG path.
    """
    d = _circuit_dir(name)
    path = d / "data" / data_file
    if not path.exists():
        raise FileNotFoundError(str(path))
    table = _parse_numeric_table(path, max_rows=100000)
    cols = table["columns"]
    if not cols:
        raise ValueError("no numeric data parsed from file")
    y_cols = y_cols or [c for c in range(len(cols)) if c != x_col]

    fig, ax = plt.subplots(figsize=(8, 5))
    x = cols[x_col]
    for i, yc in enumerate(y_cols):
        label = labels[i] if labels and i < len(labels) else f"col{yc}"
        ax.plot(x, cols[yc], label=label)
    if logx:
        ax.set_xscale("log")
    if logy:
        ax.set_yscale("log")
    ax.set_title(title or name)
    ax.set_xlabel(xlabel or f"col{x_col}")
    ax.set_ylabel(ylabel or "value")
    ax.grid(True, alpha=0.3)
    ax.legend()

    out_path = d / "plots" / (Path(data_file).stem + ".png")
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return str(out_path)


@mcp.tool()
def spice_cheatsheet() -> str:
    """Quick ngspice netlist syntax reference: components, analyses, and
    the wrdata pattern this server expects for extracting results."""
    return """\
NGSPICE NETLIST QUICK REFERENCE
================================
Line 1 of a deck is always a title/comment (ignored) -- never a component.

Components:
  R1 n1 n2 1k                  resistor
  C1 n1 n2 100n                capacitor
  L1 n1 n2 10m                 inductor
  V1 n+ n- DC 5                DC voltage source
  V1 n+ n- DC 0 AC 1           AC source (for .ac analysis)
  V1 n+ n- PULSE(0 5 0 1n 1n 1m 2m)   pulse source
  V1 n+ n- SIN(0 1 1k)         sine source
  I1 n+ n- DC 1m               current source
  D1 anode cathode DMOD        diode (needs .model)
  Q1 c b e QMOD                BJT (needs .model)
  M1 d g s b MMOD              MOSFET (needs .model)
  X1 n1 n2 out SUBCKT_NAME     subcircuit instance
  Node 0 is always ground.

Analyses:
  .op                          DC operating point
  .dc V1 0 5 0.1               DC sweep
  .ac dec 20 1 1meg            AC sweep (decade, points/dec, fstart, fstop)
  .tran 1u 2m                  transient (step, stop time)

Standard control block (put this in every netlist, run_simulation reads
only files written under ./data/ via wrdata):

.control
run
wrdata data/result.txt v(out) v(in)
.endc
.end

For multiple analyses in one deck, repeat run + wrdata with different
filenames, e.g. data/dc.txt, data/ac.txt, data/tran.txt.

Common op-amp macro (ideal, for quick filter/amp sketches):
.subckt OPAMP in+ in- out
Egain out 0 in+ in- 1e6
.ends

Workflow: save_circuit or run_simulation(netlist=...) -> run_simulation
-> plot_result(data_file="result.txt", x_col=0, y_cols=[1,2])
"""


if __name__ == "__main__":
    mcp.run()
