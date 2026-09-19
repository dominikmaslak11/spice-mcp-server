# spice-mcp-server

Lekki serwer MCP do szybkiej symulacji obwodów SPICE przez [ngspice](https://ngspice.sourceforge.io/),
pomyślany do sterowania przez LLM (Claude/inne) na podstawie opisu słownego.

## Narzędzia

- `save_circuit(name, netlist)` / `get_circuit(name)` / `list_circuits()`
- `run_simulation(name, netlist=None, timeout_s=60)` — zapisuje (opcjonalnie) i uruchamia netlistę
  w ngspice (`-b`), parsuje pliki wynikowe zapisane przez `wrdata` w `.control` jako kolumny liczb.
- `plot_result(name, data_file, x_col, y_cols, ...)` — generuje szybki wykres PNG z danych wynikowych.
- `spice_cheatsheet()` — ściągawka ze składnią netlist ngspice i wzorcem `.control`/`wrdata`.

## Instalacja

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install mcp numpy matplotlib
```

Wymaga zainstalowanego `ngspice` w systemie (`apt install ngspice`).

## Rejestracja w Claude Code

```bash
claude mcp add --scope user spice -- "$(pwd)/.venv/bin/python" "$(pwd)/server.py"
```

## Struktura wyników

```
circuits/<nazwa>/
├── circuit.cir     # netlista SPICE
├── data/*.txt      # wyniki (wrdata)
└── plots/*.png     # wykresy
```
