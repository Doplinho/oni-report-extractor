"""Junta os report_cycle_*.json exportados pelo mod em um único CSV (formato longo) para Power BI / Excel.

Uso:
    python reports_to_csv.py                      # lê a pasta export padrão, grava reports.csv nela
    python reports_to_csv.py <pasta_export> <saida.csv>
"""
import csv
import json
import sys
from pathlib import Path


def default_export_dir() -> Path:
    # Documentos pode estar redirecionado para o OneDrive.
    home = Path.home()
    for docs in (home / "OneDrive" / "Documentos", home / "OneDrive" / "Documents", home / "Documents"):
        candidate = docs / "Klei" / "OxygenNotIncluded" / "export"
        if candidate.is_dir():
            return candidate
    return home / "Documents" / "Klei" / "OxygenNotIncluded" / "export"


def main() -> None:
    export_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else default_export_dir()
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else export_dir / "reports.csv"

    files = sorted(export_dir.glob("report_cycle_*.json"), key=lambda p: int(p.stem.rsplit("_", 1)[1]))
    if not files:
        sys.exit(f"Nenhum report_cycle_*.json em {export_dir}")

    rows = 0
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:  # BOM: Excel abre acentos corretamente
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Cycle", "Timestamp", "Category", "Context", "IsDetail", "Net", "Positive", "Negative"])
        for path in files:
            report = json.loads(path.read_text(encoding="utf-8"))
            for e in report["Entries"]:
                writer.writerow([
                    report["Cycle"], report["Timestamp"], e["Category"], e.get("Context") or "",
                    int(e.get("Context") is not None), e["NetValue"], e["PositiveValue"], e["NegativeValue"],
                ])
                rows += 1

    print(f"{len(files)} ciclos, {rows} linhas -> {out_path}")


if __name__ == "__main__":
    main()
