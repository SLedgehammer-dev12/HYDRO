#!/usr/bin/env python3
"""Generate docs/codebase_map.md from the Graphify knowledge graph.

Usage:
    python3 skills/graphify/scripts/graphify.py build
    python3 tools/generate_codebase_map.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GRAPH_PATH = ROOT / ".graphify" / "graph.json"
OUTPUT_PATH = ROOT / "docs" / "codebase_map.md"

CRITICAL_FILES = (
    "hidrostatik_test/domain/hydrotest_core.py",
    "hidrostatik_test/domain/water_properties.py",
    "hidrostatik_test/domain/time_series.py",
    "hidrostatik_test/services/updater.py",
    "hidrostatik_test/services/download_manager.py",
    "hidrostatik_test/services/database.py",
    "hidrostatik_test/services/report_export.py",
    "hidrostatik_test/ui/app.py",
    "webapp/backend/app/main.py",
    "webapp/backend/app/api/calculations.py",
    "webapp/backend/app/services/calculations.py",
    "webapp/backend/app/services/sessions.py",
)


def package_of(path: str) -> str:
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] == "hidrostatik_test":
        return ".".join(parts[:2])
    if len(parts) >= 4 and parts[0] == "webapp" and parts[1] == "backend":
        return ".".join(parts[:4])
    return parts[0] if parts else "."


def load_graph() -> dict:
    if not GRAPH_PATH.exists():
        raise SystemExit("Graph yok. Once: python3 skills/graphify/scripts/graphify.py build")
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def importers_of(graph: dict, target_file: str) -> list[str]:
    """Resolve exact import edges (including ``from pkg import module``) to files."""
    module_to_file: dict[str, str] = {}
    for node in graph["nodes"].values():
        if node["type"] != "file" or not node["path"].startswith(
            ("hidrostatik_test/", "webapp/backend/app/")
        ):
            continue
        path = node["path"]
        parts = list(Path(path).with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        module_to_file[".".join(parts)] = path

    target_parts = list(Path(target_file).with_suffix("").parts)
    if target_parts[-1] == "__init__":
        target_parts = target_parts[:-1]
    target_module = ".".join(target_parts)

    result: set[str] = set()
    for edge in graph["edges"]:
        if edge["relation"] not in ("imports", "imports_from"):
            continue
        source = edge["source"].replace("file:", "")
        module = edge["target"].replace("module:", "")
        matched = module == target_module
        if not matched and edge["relation"] == "imports_from":
            names = edge.get("names", [])
            matched = any(f"{module}.{name}" == target_module for name in names)
        if matched and source != target_file:
            result.add(source)
    return sorted(result)


def main() -> None:
    graph = load_graph()
    nodes = graph["nodes"]
    edges = graph["edges"]
    summary = graph["summary"]

    files = sorted(n["path"] for n in nodes.values() if n["type"] == "file")
    symbols_by_file: Counter[str] = Counter()
    classes_by_file: Counter[str] = Counter()
    functions_by_file: Counter[str] = Counter()
    for node in nodes.values():
        if node["type"] == "class":
            symbols_by_file[node["path"]] += 1
            classes_by_file[node["path"]] += 1
        elif node["type"] == "function":
            symbols_by_file[node["path"]] += 1
            functions_by_file[node["path"]] += 1

    package_edges: Counter[tuple[str, str]] = Counter()
    for edge in edges:
        if edge["relation"] not in ("imports", "imports_from"):
            continue
        source = edge["source"].replace("file:", "")
        target = edge["target"].replace("module:", "")
        if not target.startswith("hidrostatik_test"):
            continue
        package_edges[(package_of(source), ".".join(target.split(".")[:2]))] += 1

    test_mappings = graph.get("test_mappings", {})
    source_files = [
        f
        for f in files
        if f.startswith(("hidrostatik_test/", "webapp/backend/app/"))
        and not f.endswith("__init__.py")
    ]
    tested_sources = {f for f in test_mappings if f in source_files}
    untested = [f for f in source_files if f not in tested_sources]

    call_graph = graph.get("call_graph", {})
    hotspots = sorted(call_graph.items(), key=lambda item: len(item[1]), reverse=True)[:30]

    lines: list[str] = []
    add = lines.append

    add("# HYDRO Codebase Map")
    add("")
    add("Bu dosya `skills/graphify` tarafindan uretilmistir. Elle duzenlemeyin;")
    add("`python3 skills/graphify/scripts/graphify.py build` ve")
    add("`python3 tools/generate_codebase_map.py` komutlarini calistirin.")
    add("")
    add("## Ozet")
    add("")
    add("| Metrik | Deger |")
    add("| --- | ---: |")
    add(f"| Dosya | {summary['total_files']} |")
    add(f"| Sembol (sinif + fonksiyon) | {summary['total_symbols']} |")
    add(f"| Dugum | {summary['total_nodes']} |")
    add(f"| Kenar | {summary['total_edges']} |")
    add(f"| SQLite tablosu | {summary['total_tables']} |")
    add(f"| Test edilen kaynak dosya | {len(tested_sources)} / {len(source_files)} |")
    add("")

    add("## Paket Bagimliliklari")
    add("")
    add("| Kaynak paket | Hedef paket | Import sayisi |")
    add("| --- | --- | ---: |")
    for (src, dst), count in sorted(package_edges.items(), key=lambda item: (-item[1], item[0])):
        if src == dst:
            continue
        add(f"| `{src}` | `{dst}` | {count} |")
    add("")

    add("## En Buyuk Dosyalar (sembol sayisina gore)")
    add("")
    add("| Dosya | Sinif | Fonksiyon | Toplam |")
    add("| --- | ---: | ---: | ---: |")
    for path, count in symbols_by_file.most_common(20):
        add(f"| `{path}` | {classes_by_file[path]} | {functions_by_file[path]} | {count} |")
    add("")

    add("## Test Haritasi")
    add("")
    add("| Kaynak dosya | Bagli test dosyalari |")
    add("| --- | --- |")
    for source in sorted(test_mappings):
        tests = ", ".join(f"`{t}`" for t in test_mappings[source])
        add(f"| `{source}` | {tests} |")
    add("")
    if untested:
        add("### Dogrudan test eslesmesi olmayan kaynak dosyalar")
        add("")
        for path in untested:
            add(f"- `{path}`")
        add("")

    add("## Cagri Grafigi Odaklari")
    add("")
    add("| Sembol | Cagri noktasi | Ornek cagiranlar |")
    add("| --- | ---: | --- |")
    for symbol, callers in hotspots:
        sample = ", ".join(f"`{c}`" for c in callers[:3])
        if len(callers) > 3:
            sample += f" (+{len(callers) - 3})"
        add(f"| `{symbol}` | {len(callers)} | {sample} |")
    add("")

    add("## Kritik Dosyalarin Etki Alani")
    add("")
    for target in CRITICAL_FILES:
        add(f"### `{target}`")
        add("")
        tests = test_mappings.get(target, [])
        importers = importers_of(graph, target)
        add(f"- Bagli testler: {', '.join(f'`{t}`' for t in tests) if tests else 'YOK'}")
        add(
            f"- Etkilenen dosyalar ({len(importers)}): {', '.join(f'`{i}`' for i in importers) if importers else 'YOK'}"
        )
        add("")

    add("## Veritabani Tablolari")
    add("")
    add("| Tablo | Kullanan moduller |")
    add("| --- | --- |")
    for table, usages in sorted(graph.get("table_usages", {}).items()):
        add(f"| `{table}` | {', '.join(f'`{u}`' for u in usages)} |")
    add("")

    add("## Mermaid: Paket Bagimliligi")
    add("")
    add("```mermaid")
    add("graph LR")
    packages = sorted({src for src, _ in package_edges} | {dst for _, dst in package_edges})
    safe = {p: f"P{index}" for index, p in enumerate(packages)}
    for pkg, alias in safe.items():
        add(f'    {alias}["{pkg}"]')
    for (src, dst), count in sorted(package_edges.items()):
        if src == dst:
            continue
        add(f"    {safe[src]} -->|{count}| {safe[dst]}")
    add("```")
    add("")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[map] {OUTPUT_PATH} yazildi ({len(lines)} satir)")


if __name__ == "__main__":
    main()
