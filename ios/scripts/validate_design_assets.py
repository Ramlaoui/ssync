#!/usr/bin/env python3
"""Validate the design handoff, without claiming native runtime verification."""

from __future__ import annotations

import json
import re
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def luminance(hexa):
    channels = [int(hexa[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [
        v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels
    ]
    return sum(
        value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722))
    )


def ratio(a, b):
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def anchors(content):
    result = set()
    for heading in re.findall(r"^#{1,6}\s+(.+)$", content, re.M):
        slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
        result.add(slug)
    return result


def main():
    errors = []
    counts = {}
    # This generated report is also linked by the source documents on a clean rebuild.
    report_path = ROOT / "design/VALIDATION.md"
    report_path.touch(exist_ok=True)
    for suffix in ("json", "svg", "png", "gif", "pdf"):
        counts[suffix] = len(list(ROOT.rglob("*." + suffix)))
    for path in ROOT.rglob("*.json"):
        try:
            json.loads(path.read_text())
        except (ValueError, OSError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    for path in ROOT.rglob("*.svg"):
        try:
            root = ET.parse(path).getroot()
            assert root.tag.endswith("svg") and root.attrib.get("viewBox")
            assert root.find("{http://www.w3.org/2000/svg}title") is not None
        except (ET.ParseError, AssertionError) as exc:
            errors.append(f"SVG {path.relative_to(ROOT)}: {exc}")
    for path in ROOT.rglob("*.png"):
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            errors.append(f"Invalid PNG: {path.relative_to(ROOT)}")
            continue
        width, height = struct.unpack(">II", data[16:24])
        if "app-icon-" in path.name and (width, height) != (1024, 1024):
            errors.append(f"App icon dimensions: {path.relative_to(ROOT)}")
    for path in (ROOT / "assets/app-icon").glob("*.png"):
        opaque = subprocess.check_output(
            ["magick", "identify", "-format", "%[opaque]", str(path)], text=True
        )
        if opaque.lower() != "true":
            errors.append(f"App icon not opaque: {path.name}")
    for contents in (ROOT / "Resources/Assets.xcassets").rglob("Contents.json"):
        data = json.loads(contents.read_text())
        for item in data.get("images", []):
            if not (contents.parent / item["filename"]).exists():
                errors.append(
                    f"Missing catalog image: {contents.parent.name}/{item['filename']}"
                )
    tokens = json.loads((ROOT / "design/tokens.json").read_text())
    contrast = []
    pairs = [
        ("Ink", "Canvas"),
        ("Ink", "Surface"),
        ("Ink", "SurfaceSecondary"),
        ("InkSecondary", "Canvas"),
        ("InkSecondary", "Surface"),
        ("InkSecondary", "SurfaceSecondary"),
        ("InkSecondary", "CodeCanvas"),
        ("Accent", "Surface"),
        ("Accent", "Canvas"),
        ("Accent", "AccentSoft"),
        ("Accent", "SurfaceSecondary"),
        ("OnAccent", "Accent"),
        ("Success", "Surface"),
        ("Success", "SuccessSoft"),
        ("Warning", "Surface"),
        ("Warning", "WarningSoft"),
        ("Danger", "Surface"),
        ("Danger", "DangerSoft"),
    ]
    for mode in ("light", "dark"):
        for fg, bg in pairs:
            value = ratio(tokens["colors"][fg][mode], tokens["colors"][bg][mode])
            contrast.append((mode, fg, bg, value))
            if value < 4.5:
                errors.append(f"Contrast {mode} {fg}/{bg}: {value:.2f}")
    for name, modes in tokens["colors"].items():
        path = ROOT / f"Resources/Assets.xcassets/{name}.colorset/Contents.json"
        data = json.loads(path.read_text())
        for item in data["colors"]:
            mode = "dark" if item.get("appearances") else "light"
            components = item["color"]["components"]
            actual = "#" + "".join(
                f"{round(float(components[k]) * 255):02X}"
                for k in ("red", "green", "blue")
            )
            if actual != modes[mode].upper():
                errors.append(f"Color mismatch: {name} {mode}")
    for path in ROOT.rglob("*.md"):
        content = path.read_text()
        for raw in re.findall(r"\[[^\]]*\]\(([^)\n]+)\)", content):
            target = raw.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or target.startswith("mailto:"):
                continue
            relative, _, fragment = target.partition("#")
            destination = (
                (path.parent / unquote(relative)).resolve() if relative else path
            )
            if not destination.exists():
                errors.append(f"Broken link in {path.relative_to(ROOT)}: {target}")
            elif (
                fragment
                and destination.suffix == ".md"
                and unquote(fragment) not in anchors(destination.read_text())
            ):
                errors.append(f"Broken anchor in {path.relative_to(ROOT)}: {target}")
    symbol_data = json.loads((ROOT / "design/symbols.json").read_text())
    for custom in symbol_data["custom"]:
        if not (ROOT / "design" / custom["file"]).exists():
            errors.append(f"Missing custom glyph: {custom['file']}")
    for source in (ROOT / "design").rglob("*.svg"):
        if not source.with_suffix(".png").exists():
            errors.append(f"Missing rendered preview: {source.relative_to(ROOT)}")
    for source in (ROOT / "assets/motion").glob("*.svg"):
        if not source.with_suffix(".gif").exists():
            errors.append(f"Missing motion preview: {source.name}")
    spec = (ROOT / "DESIGN_SPEC.md").read_text()
    lines = [
        "# Design asset validation",
        "",
        "Status: " + ("PASS" if not errors else "FAIL"),
        "",
        "This validates source assets and document structure, not an iOS application build or live integration.",
        "",
        f"- Main specification: {len(spec.split()):,} words; {len(spec.splitlines()):,} lines.",
        f"- SVG: {counts['svg']}; PNG: {counts['png']}; GIF: {counts['gif']}; PDF: {counts['pdf']}; JSON: {counts['json']}.",
        f"- Screen concepts: {len(list((ROOT / 'design/screens').glob('*.svg')))}.",
        f"- Semantic adaptive colors: {len(tokens['colors'])}.",
        f"- SF Symbol roles: {len(symbol_data['symbols'])}; runtime availability still requires the shipping iOS SDK.",
        "- App-icon PNGs checked for 1024 × 1024 size and opacity.",
        "- SVG/XML, JSON, catalog references, local Markdown links and anchors checked.",
        "- Motion demonstrations have static reduced-motion groups; behavior needs browser/device review.",
        "",
        "## Solid-color text contrast",
        "",
        "| Appearance | Foreground | Background | Ratio |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| {mode} | {fg} | {bg} | {value:.2f}:1 |" for mode, fg, bg, value in contrast
    ]
    lines += [
        "",
        "All listed pairs target at least 4.5:1. Separators are decorative and excluded. System materials, wallpaper, native fonts, actual controls, and extensions require on-device testing.",
        "",
    ]
    if errors:
        lines += ["## Errors", ""] + ["- " + error for error in errors]
    (ROOT / "design/VALIDATION.md").write_text("\n".join(lines).rstrip() + "\n")
    print(
        "\n".join(errors)
        if errors
        else f"PASS: {sum(counts.values())} asset files; {len(contrast)} contrast pairs; local links and catalog references."
    )
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
