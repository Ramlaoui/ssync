#!/usr/bin/env python3
"""Rebuild ssync's editable design assets. Requires rsvg-convert and ImageMagick."""

from __future__ import annotations

import html
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKENS = json.loads((ROOT / "design/tokens.json").read_text())
C = {k: v["light"] for k, v in TOKENS["colors"].items()}
D = {k: v["dark"] for k, v in TOKENS["colors"].items()}
BLUE = C["Accent"]
INK = C["Ink"]
FONT = "-apple-system, BlinkMacSystemFont, Helvetica Neue, Arial, sans-serif"


def write(path, content):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n")
    return path


def svg(w, h, content, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{html.escape(title)}">'
        f"<title>{html.escape(title)}</title>{content}</svg>"
    )


def rect(x, y, w, h, fill, r=0, stroke=None):
    edge = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{edge}/>'
    )


def text(x, y, value, size=17, fill=INK, weight=400, anchor="start", mono=False):
    family = "Menlo, monospace" if mono else FONT
    return (
        f'<text x="{x}" y="{y}" fill="{fill}" font-family="{family}" '
        f'font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">'
        f"{html.escape(str(value))}</text>"
    )


def line(x1, y1, x2, y2, color, width=1):
    return (
        f'<path d="M{x1} {y1}H{x2}" stroke="{color}" stroke-width="{width}"/>'
        if y1 == y2
        else f'<path d="M{x1} {y1}L{x2} {y2}" stroke="{color}" stroke-width="{width}"/>'
    )


def circle(x, y, r, fill):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"/>'


def mark(x=0, y=0, size=100, color=BLUE):
    # Two open opposing lanes. 6 units of negative space between the middle strokes.
    return (
        f'<g transform="translate({x} {y}) scale({size / 100})" fill="none" '
        f'stroke="{color}" stroke-width="10" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M76 22H43C30 22 22 30 22 42H55"/>'
        '<path d="M24 78H57C70 78 78 70 78 58H45"/></g>'
    )


def wordmark(x=0, y=0, scale=1, color=INK):
    # Original outlined lettering; no external font required.
    paths = [
        (0, "M25 6H11C5 6 2 9 2 14S6 21 12 21H17C23 21 26 24 26 29S22 37 16 37H2"),
        (37, "M25 6H11C5 6 2 9 2 14S6 21 12 21H17C23 21 26 24 26 29S22 37 16 37H2"),
        (74, "M2 6V21C2 29 7 33 14 33S26 29 26 21V6M26 21V36C26 44 21 49 13 49H6"),
        (111, "M2 37V6M2 19C2 10 7 6 14 6S26 10 26 19V37"),
        (148, "M26 8C23 6 20 6 15 6C6 6 2 12 2 21S6 37 15 37C20 37 23 37 26 35"),
    ]
    return (
        f'<g transform="translate({x} {y}) scale({scale})" fill="none" stroke="{color}" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round">'
        + "".join(f'<path transform="translate({dx} 0)" d="{p}"/>' for dx, p in paths)
        + "</g>"
    )


def glyph(name, x, y, color, size=22):
    shapes = {
        "jobs": '<path d="M4 5h16v12H4zM7 20h10M8 9h8M8 13h5"/>',
        "watchers": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
        "launch": '<path d="m3 10 18-7-7 18-3-8-8-3Zm8 3 10-10"/>',
        "gear": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2.5"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3"/>',
        "plus": '<path d="M12 4v16M4 12h16"/>',
        "back": '<path d="m15 5-7 7 7 7"/>',
        "next": '<path d="m9 5 7 7-7 7"/>',
        "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
        "bell": '<path d="M5 17h14l-2-4V9a5 5 0 0 0-10 0v4l-2 4Zm5 3h4"/>',
        "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
        "check": '<path d="m5 12 4 4L19 6"/>',
        "running": '<circle cx="12" cy="12" r="9"/><path d="m10 8 6 4-6 4Z"/>',
        "pending": '<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
        "failed": '<circle cx="12" cy="12" r="9"/><path d="M12 6v7m0 3v1"/>',
        "completed": '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
        "folder": '<path d="M3 6h7l2 3h9v11H3Z"/>',
        "host": '<rect x="3" y="4" width="18" height="6" rx="2"/><rect x="3" y="14" width="18" height="6" rx="2"/><path d="M7 7h1m-1 10h1"/>',
        "pin": '<path d="m8 3 8 0-1 7 4 4H5l4-4-1-7Zm4 11v7"/>',
    }
    return f'<g transform="translate({x} {y}) scale({size / 24})" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{shapes[name]}</g>'


def pill(x, y, label, fg, bg, width=None):
    width = width or len(label) * 7 + 24
    return rect(x, y, width, 28, bg, 14) + text(
        x + width / 2, y + 19, label, 13, fg, 600, "middle"
    )


def button(x, y, w, label, p=C, primary=True):
    return rect(
        x, y, w, 50, p["Accent"] if primary else p["SurfaceSecondary"], 14
    ) + text(
        x + w / 2,
        y + 31,
        label,
        17,
        p["OnAccent"] if primary else p["Accent"],
        600,
        "middle",
    )


def section(y, title, extra="", p=C):
    return text(20, y, title, 20, p["Ink"], 650) + (
        text(370, y, extra, 13, p["InkSecondary"], anchor="end") if extra else ""
    )


def field(y, label, value, p=C, disclosure=True):
    return (
        text(36, y + 23, label, 13, p["InkSecondary"])
        + text(36, y + 49, value, 17, p["Ink"], 500)
        + (glyph("next", 344, y + 26, p["InkSecondary"], 16) if disclosure else "")
    )


def shell(
    title,
    body,
    tab="jobs",
    dark=False,
    back=False,
    subtitle="",
    toolbar="gear",
    tabs=True,
    back_label="Jobs",
):
    p = D if dark else C
    out = rect(0, 0, 390, 844, p["Canvas"])
    out += text(27, 34, "9:41", 15, p["Ink"], 600)
    out += rect(145, 14, 100, 28, "#05070B", 14)
    out += text(323, 34, "•••", 14, p["Ink"], 600) + rect(352, 24, 22, 10, p["Ink"], 3)
    if back:
        out += glyph("back", 18, 61, p["Accent"]) + text(
            42, 78, back_label, 17, p["Accent"]
        )
        out += text(195, 79, title, 17, p["Ink"], 600, "middle")
        out += glyph(toolbar, 348, 60, p["Accent"])
    else:
        out += text(20, 104, title, 36, p["Ink"], 750)
        if toolbar:
            out += glyph(toolbar, 340, 76, p["Accent"], 25)
        if subtitle:
            out += text(20, 133, subtitle, 15, p["InkSecondary"])
    out += body
    if tabs:
        out += rect(12, 750, 366, 67, p["Surface"], 32, p["Separator"])
        for i, (key, label) in enumerate(
            [
                ("jobs", "Jobs"),
                ("host", "Hosts"),
                ("watchers", "Watchers"),
                ("launch", "Launch"),
            ]
        ):
            x = 20 + i * 89
            active = key == tab
            if active:
                out += rect(x, 756, 83, 55, p["AccentSoft"], 26)
            color = p["Accent"] if active else p["InkSecondary"]
            out += glyph(key, x + 30, 762, color, 23) + text(
                x + 41, 800, label, 11, color, 600, "middle"
            )
    out += rect(132, 830, 126, 5, p["Ink"], 3)
    return svg(390, 844, out, f"ssync — {title}; design concept, illustrative data")


def jobrow(y, name, jid, state, detail, p=C, pin=False):
    color = p[
        {
            "Running": "Running",
            "Pending": "Warning",
            "Failed": "Danger",
            "Completed": "Success",
        }[state]
    ]
    out = glyph(state.lower(), 32, y + 15, color, 22)
    out += text(65, y + 28, name, 17, p["Ink"], 600)
    if pin:
        out += glyph("pin", 337, y + 13, p["InkSecondary"], 17)
    out += text(65, y + 51, f"{jid} · {state}", 13, color, 500)
    out += text(65, y + 74, detail, 13, p["InkSecondary"])
    return out


def relay_row(y, name, jid, state, detail, p=C, pin=False):
    color = p[
        {
            "Running": "Running",
            "Pending": "Warning",
            "Failed": "Danger",
            "Completed": "Success",
        }[state]
    ]
    out = rect(20, y, 350, 91, p["Surface"], 12)
    out += rect(20, y + 18, 3, 54, color, 1.5)
    out += text(38, y + 29, name, 18, p["Ink"], 650)
    out += text(38, y + 53, f"{jid} · {state}", 13, color, 550)
    out += text(38, y + 76, detail, 13, p["InkSecondary"])
    out += glyph("pin" if pin else "next", 339, y + 20, p["InkSecondary"], 17)
    return out


def screens():
    result = {}
    for dark, suffix in [(False, "light"), (True, "dark")]:
        p = D if dark else C
        b = text(20, 176, "All hosts  ⌄", 16, p["Accent"], 600)
        b += text(196, 176, "Active", 15, p["Ink"], 650) + text(
            271, 176, "History", 15, p["InkSecondary"]
        )
        b += line(195, 188, 242, 188, p["Accent"], 3) + glyph(
            "search", 345, 156, p["Accent"], 22
        )
        b += rect(20, 210, 350, 146, INK, 20)
        b += text(40, 286, "3", 68, "#FFFFFF", 650)
        b += text(40, 326, "running jobs", 17, "#C3CEE5", 500)
        b += line(182, 238, 182, 328, "#465571")
        b += glyph("pending", 209, 239, "#F3CB7A", 21) + text(
            242, 256, "2 pending", 16, "#FFFFFF", 500
        )
        b += glyph("failed", 209, 282, "#FF9EA6", 21) + text(
            242, 299, "1 attention", 16, "#FFFFFF", 500
        )
        b += text(210, 329, "Last 24 hours", 12, "#C3CEE5")
        b += mark(296, 111, 35, p["Accent"])
        b += section(396, "Atlas", "Updated just now", p)
        b += relay_row(
            413,
            "protein-fold-v3",
            "48192",
            "Running",
            "2 h 18 m elapsed · 4 GPUs",
            p,
            True,
        )
        b += relay_row(
            512,
            "embedding-sweep",
            "48196 · Array",
            "Pending",
            "Waiting for resources · 64 tasks",
            p,
        )
        b += section(643, "Boreal", "Updated 12 s ago", p)
        b += relay_row(
            660, "eval-baseline", "82013", "Running", "12 m elapsed · 8 CPUs", p
        )
        result[f"01-jobs-{suffix}"] = shell(
            "Jobs", b, dark=dark, subtitle="Research workstation"
        )
    b = text(20, 132, "protein-fold-v3", 28, INK, 700)
    b += text(20, 160, "Atlas · 48192 · gpu-a100", 15, C["InkSecondary"])
    b += pill(20, 182, "Running", BLUE, C["AccentSoft"], 95)
    b += text(370, 202, "Updated just now", 13, C["InkSecondary"], anchor="end")
    b += rect(20, 230, 350, 161, BLUE, 20)
    b += text(38, 260, "ELAPSED", 12, "#FFFFFF", 600)
    b += text(38, 310, "2 h 18 m", 42, "#FFFFFF", 650)
    b += text(38, 338, "Time limit  8 h", 15, "#FFFFFF")
    b += rect(38, 355, 314, 4, "#667FE4", 2) + rect(38, 355, 90, 4, "#FFFFFF", 2)
    b += text(38, 379, "29% of time limit · not job progress", 12, "#FFFFFF")
    b += button(20, 407, 169, "View output") + button(
        201, 407, 169, "Follow live", primary=False
    )
    b += section(500, "Resources", "View all")
    b += rect(20, 517, 350, 88, "white", 20)
    for x, val, label in [
        (38, "4 × A100", "GPUs"),
        (182, "32", "CPUs"),
        (279, "128 GB", "Memory"),
    ]:
        b += text(x, 549, val, 18, INK, 600) + text(
            x, 577, label, 13, C["InkSecondary"]
        )
    b += section(648, "Watchers", "1 attached")
    b += rect(20, 665, 350, 72, "white", 20) + glyph("watchers", 35, 685, BLUE)
    b += text(73, 692, "Resume from checkpoint", 16, INK, 600) + text(
        73, 717, "Active · on time limit", 13, C["InkSecondary"]
    )
    result["02-job-detail"] = shell("Job", b, back=True, toolbar="more")
    b = rect(20, 161, 350, 105, "white", 20)
    b += text(36, 191, "CONTINUE A DRAFT", 12, C["InkSecondary"], 600)
    b += text(36, 220, "protein-fold-v4", 20, INK, 600)
    b += text(36, 247, "Atlas · edited 8 min ago", 14, C["InkSecondary"])
    b += button(20, 285, 350, "New job")
    b += section(381, "Templates", "See all")
    b += rect(20, 400, 350, 160, "white", 20)
    b += field(405, "GPU TRAINING", "A100 training · 4 GPUs")
    b += line(36, 480, 354, 480, C["Separator"])
    b += field(486, "CPU EVALUATION", "Evaluation · 8 CPUs")
    b += section(609, "Relaunch a job")
    b += rect(20, 630, 350, 91, "white", 20)
    b += jobrow(630, "protein-fold-v2", "47981", "Completed", "Atlas · yesterday")
    result["04-launch-library"] = shell(
        "Launch", b, tab="launch", subtitle="Start from what already works."
    )
    b = text(20, 130, "Ready to launch", 28, INK, 700)
    b += text(20, 157, "Review the job before submitting.", 15, C["InkSecondary"])
    b += rect(20, 182, 350, 237, "white", 20)
    b += field(189, "JOB", "protein-fold-v4", disclosure=False)
    b += line(36, 263, 354, 263, C["Separator"])
    b += field(268, "HOST & PARTITION", "Atlas · gpu-a100")
    b += line(36, 340, 354, 340, C["Separator"])
    b += field(346, "RESOURCES", "4 GPUs · 32 CPUs · 128 GB")
    b += rect(20, 437, 350, 135, "white", 20)
    b += field(443, "SOURCE ON SSYNC API SERVER", "~/research/folding")
    b += text(36, 533, "Sync enabled · respects .gitignore", 14, C["InkSecondary"])
    b += text(36, 555, "8 h time limit · 1 watcher attached", 14, C["InkSecondary"])
    b += rect(20, 593, 350, 85, C["AccentSoft"], 16)
    b += text(36, 621, "A new job will be submitted to Atlas.", 15, BLUE, 500)
    b += text(36, 647, "You can follow submission after leaving", 13, BLUE)
    b += text(36, 665, "this screen.", 13, BLUE)
    b += button(20, 730, 350, "Launch on Atlas")
    result["05-launch-review"] = shell(
        "Review", b, back=True, toolbar="more", tabs=False, back_label="Edit"
    )
    b = pill(20, 157, "Active", C["OnAccent"], BLUE, 105)
    b += pill(136, 157, "Paused", C["InkSecondary"], C["SurfaceSecondary"], 105)
    b += pill(251, 157, "All", C["InkSecondary"], C["SurfaceSecondary"], 119)
    b += section(229, "Atlas", "2 active")
    b += rect(20, 249, 350, 205, "white", 20)
    b += glyph("watchers", 36, 268, BLUE, 25)
    b += text(36, 316, "Resume from checkpoint", 20, INK, 600)
    b += text(36, 342, "protein-fold-v3 · 48192", 14, C["InkSecondary"])
    b += pill(36, 359, "On time limit", C["Warning"], C["WarningSoft"], 116)
    b += text(36, 418, "Then resubmit from captured checkpoint", 14, INK)
    b += text(36, 441, "Last checked 18 s ago · 0 triggers", 13, C["InkSecondary"])
    b += rect(20, 472, 350, 155, "white", 20)
    b += text(36, 505, "Stop on invalid loss", 20, INK, 600)
    b += text(36, 532, "embedding-sweep · 48196", 14, C["InkSecondary"])
    b += text(36, 571, "When output matches “loss: nan”", 14, INK)
    b += text(
        36, 600, "Then cancel job · applies to array tasks", 13, C["InkSecondary"]
    )
    b += button(20, 655, 350, "New watcher", primary=False)
    result["06-watchers"] = shell(
        "Watchers", b, tab="watchers", subtitle="Know what happens next."
    )
    b = text(20, 133, "Resume from checkpoint", 25, INK, 650)
    b += text(20, 159, "Atlas · protein-fold-v3 · 48192", 14, C["InkSecondary"])
    b += rect(20, 183, 350, 257, INK, 20)
    b += line(47, 221, 47, 397, "#7788AE", 2)
    for i, (y, small, big) in enumerate(
        [
            (197, "WHEN", "Job times out"),
            (273, "USING", "Captured checkpoint path"),
            (349, "THEN", "Watcher resubmission"),
        ]
    ):
        b += circle(47, y + 22, 12, "#9BADFF" if i == 0 else "#354562")
        b += text(
            47,
            y + 27,
            str(i + 1),
            12,
            "#101C45" if i == 0 else "#FFFFFF",
            650,
            "middle",
        )
        b += text(73, y + 15, small, 12, "#B7C5FF", 650) + text(
            73, y + 45, big, 17, "#FFFFFF", 500
        )
    b += button(20, 462, 350, "Pause watcher", primary=False)
    b += section(556, "Recent events", "See all")
    b += rect(20, 576, 350, 125, "white", 20)
    b += glyph("check", 35, 595, C["Success"]) + text(
        72, 613, "Checkpoint captured", 17, INK, 600
    )
    b += text(72, 640, "epoch-23.ckpt", 14, C["InkSecondary"], mono=True)
    b += text(72, 670, "09:39 · waiting for job end", 13, C["InkSecondary"])
    result["07-watcher-detail"] = shell(
        "Watcher", b, tab="watchers", back=True, toolbar="more", back_label="Watchers"
    )
    b = mark(139, 144, 112) + wordmark(121, 277, 0.85)
    b += text(195, 385, "Your cluster work.", 28, INK, 700, "middle")
    b += text(195, 421, "Within reach.", 28, INK, 700, "middle")
    b += text(
        195,
        463,
        "Connect to your ssync API server.",
        16,
        C["InkSecondary"],
        anchor="middle",
    )
    b += rect(20, 496, 350, 140, "white", 20)
    b += field(501, "SSYNC API URL", "https://ssync.example.org", disclosure=False)
    b += line(36, 574, 354, 574, C["Separator"])
    b += text(36, 606, "ssync API Key", 16, C["InkSecondary"])
    b += button(20, 665, 350, "Test connection")
    b += text(
        195,
        750,
        "Use a server reachable from this iPhone.",
        13,
        C["InkSecondary"],
        anchor="middle",
    )
    b += text(195, 778, "Explore demo", 16, BLUE, 600, "middle")
    result["08-connect"] = shell("", b, tabs=False, toolbar="")
    b = text(20, 132, "embedding-sweep", 26, INK, 700)
    b += text(20, 160, "Atlas · array 48196 · 64 tasks", 15, C["InkSecondary"])
    b += rect(20, 185, 350, 150, "white", 20)
    b += text(36, 222, "38 of 64 finished", 24, INK, 650)
    b += text(36, 250, "36 completed · 2 failed", 15, C["InkSecondary"])
    b += rect(36, 272, 318, 10, C["SurfaceSecondary"], 5)
    b += rect(36, 272, 179, 10, C["Success"], 5) + rect(215, 272, 10, 10, C["Danger"])
    b += text(36, 312, "18 running · 8 pending", 14, C["InkSecondary"])
    b += pill(20, 356, "All tasks", C["OnAccent"], BLUE, 116)
    b += pill(148, 356, "Failed · 2", C["Danger"], C["DangerSoft"], 116)
    b += section(427, "Tasks", "Task index ↑")
    b += rect(20, 446, 350, 278, "white", 20)
    b += jobrow(452, "Task 17", "48196_17", "Failed", "Exit code 1 · View stderr")
    b += line(65, 539, 354, 539, C["Separator"])
    b += jobrow(542, "Task 18", "48196_18", "Running", "42 m elapsed · 1 GPU")
    b += line(65, 631, 354, 631, C["Separator"])
    b += jobrow(634, "Task 19", "48196_19", "Completed", "Finished 09:31 · 39 m")
    result["09-job-array"] = shell("Array", b, back=True, toolbar="more")
    b = rect(20, 162, 350, 175, "white", 20)
    b += text(36, 191, "SSYNC CONNECTION", 12, C["InkSecondary"], 600)
    b += text(36, 222, "Research workstation", 20, INK, 600)
    b += text(36, 250, "ssync.example.org", 15, C["InkSecondary"])
    b += pill(36, 276, "Connected", C["Success"], C["SuccessSoft"], 117)
    b += section(382, "Preferences")
    b += rect(20, 402, 350, 264, "white", 20)
    for i, title in enumerate(
        [
            "Notifications",
            "Widgets & Live Activities",
            "Appearance",
            "Historical job window",
        ]
    ):
        y = 402 + i * 66
        b += text(36, y + 40, title, 17, INK) + glyph(
            "next", 340, y + 25, C["InkSecondary"], 18
        )
        if i < 3:
            b += line(36, y + 65, 354, y + 65, C["Separator"])
    b += text(20, 710, "Diagnostics & connection details", 15, BLUE, 500)
    result["10-settings"] = shell(
        "Settings", b, subtitle="Make ssync yours.", tabs=False, toolbar="check"
    )
    b = rect(20, 157, 350, 77, C["WarningSoft"], 16)
    b += text(36, 186, "Atlas is unavailable", 17, C["Warning"], 600)
    b += text(36, 212, "Showing saved jobs · updated 12 min ago", 13, C["Warning"])
    b += section(278, "Atlas", "Saved data")
    b += rect(20, 298, 350, 98, "white", 20)
    b += jobrow(
        302,
        "protein-fold-v3",
        "48192",
        "Running",
        "Last known state · 2 h 18 m elapsed",
    )
    b += section(442, "Boreal", "Updated just now")
    b += rect(20, 462, 350, 97, "white", 20)
    b += jobrow(467, "eval-baseline", "82013", "Running", "12 m elapsed · 8 CPUs")
    b += button(20, 604, 350, "Retry Atlas", primary=False)
    b += text(
        195,
        692,
        "Other hosts continue to update.",
        15,
        C["InkSecondary"],
        anchor="middle",
    )
    result["11-partial-offline"] = shell(
        "Jobs", b, subtitle="2 hosts · one needs a connection check"
    )
    result.update(observability_screens())
    return result


def capacity_bar(x, y, w, allocated, idle, other, total, p=C):
    out = rect(x, y, w, 8, p["SurfaceSecondary"], 4)
    if total > 0:
        a, b, c = [w * max(0, value) / total for value in [allocated, idle, other]]
        out += rect(x, y, a, 8, p["Accent"], 4)
        out += rect(x + a, y, b, 8, p["Success"], 0)
        if c:
            out += rect(x + a + b, y, c, 8, p["Warning"], 4)
    return out


def observability_screens():
    result = {}
    b = text(20, 174, "Capacity + your jobs", 17, BLUE, 600)
    b += text(370, 174, "2 hosts", 14, C["InkSecondary"], anchor="end")
    b += rect(20, 201, 350, 257, INK, 20)
    b += text(38, 239, "Atlas", 28, "white", 650) + text(
        352, 237, "Updated 40 s ago", 12, "#C3CEE5", anchor="end"
    )
    b += text(38, 275, "gpu-a100", 17, "white", 600)
    b += text(352, 275, "24 / 32 GPUs allocated", 13, "#C3CEE5", anchor="end")
    b += capacity_bar(38, 292, 314, 24, 8, 0, 32, D)
    b += text(38, 330, "compute", 17, "white", 600)
    b += text(352, 330, "192 / 256 CPUs allocated", 12, "#C3CEE5", anchor="end")
    b += capacity_bar(38, 347, 314, 192, 48, 16, 256, D)
    b += line(38, 378, 352, 378, "#465571")
    b += text(38, 411, "Your jobs", 14, "#C3CEE5") + text(
        352, 411, "2 running · 2 pending", 15, "white", 550, "end"
    )
    b += text(38, 441, "View partitions and jobs  →", 15, "#B7C5FF", 550)
    b += rect(20, 478, 350, 192, C["Surface"], 20)
    b += text(38, 516, "Boreal", 26, INK, 650) + text(
        352, 514, "Updated 1 min ago", 12, C["InkSecondary"], anchor="end"
    )
    b += text(38, 555, "cpu", 17, INK, 600) + text(
        352, 555, "64 / 128 CPUs allocated", 13, C["InkSecondary"], anchor="end"
    )
    b += capacity_bar(38, 573, 314, 64, 64, 0, 128)
    b += text(38, 614, "Your jobs", 14, C["InkSecondary"]) + text(
        352, 614, "1 running", 15, INK, 550, "end"
    )
    b += text(38, 648, "View partitions and jobs  →", 15, BLUE, 550)
    b += (
        text(20, 710, "Allocated", 12, BLUE, 550)
        + text(115, 710, "Idle", 12, C["Success"], 550)
        + text(174, 710, "Other", 12, C["Warning"], 550)
    )
    b += text(
        20,
        734,
        "Per-partition snapshots; partitions may share nodes.",
        12,
        C["InkSecondary"],
    )
    result["12-hosts"] = shell(
        "Hosts", b, tab="host", subtitle="Research workstation · user alex"
    )
    b = text(20, 132, "Atlas", 30, INK, 700) + text(
        20, 161, "2 partitions · capacity updated 40 s ago", 15, C["InkSecondary"]
    )
    b += rect(20, 186, 350, 87, C["Surface"], 16)
    b += text(38, 216, "Jobs in your scope", 13, C["InkSecondary"])
    b += text(38, 250, "2 running", 22, BLUE, 650) + text(
        220, 250, "2 pending", 22, C["Warning"], 650
    )
    b += section(315, "Partitions", "2 reported")
    for y, name, state, metric, total, alloc, idle, other, jobs in [
        (
            335,
            "gpu-a100",
            "UP · mixed",
            "GPUs",
            32,
            24,
            8,
            0,
            "1 running · 1 pending · user alex",
        ),
        (
            526,
            "compute",
            "UP · includes drained",
            "CPUs",
            256,
            192,
            48,
            16,
            "1 running · 1 pending · user alex",
        ),
    ]:
        b += rect(20, y, 350, 175, C["Surface"], 16)
        b += text(38, y + 34, name, 21, INK, 650) + glyph(
            "next", 337, y + 17, C["InkSecondary"], 18
        )
        b += text(38, y + 61, state, 13, C["InkSecondary"])
        b += text(38, y + 93, f"{alloc} / {total} {metric} allocated", 17, BLUE, 600)
        b += capacity_bar(38, y + 111, 314, alloc, idle, other, total)
        b += text(38, y + 151, jobs, 13, C["InkSecondary"])
    result["13-host-detail"] = shell(
        "Host", b, tab="host", back=True, toolbar="more", back_label="Hosts"
    )
    b = text(20, 132, "gpu-a100", 29, INK, 700)
    b += text(20, 161, "Atlas · UP · mixed · 8 nodes reported", 14, C["InkSecondary"])
    b += rect(20, 183, 350, 171, INK, 20)
    b += text(38, 214, "GPU ALLOCATION", 12, "#C3CEE5", 650)
    b += text(38, 264, "24 / 32", 42, "white", 650)
    b += text(351, 261, "8 idle", 20, "#7EDDB5", 600, "end")
    b += capacity_bar(38, 286, 314, 24, 8, 0, 32, D)
    b += text(38, 323, "A100 · scheduler allocation", 14, "#C3CEE5")
    b += text(38, 343, "Capacity observed 40 seconds ago", 12, "#C3CEE5")
    b += text(20, 389, "CPUs", 17, INK, 600) + text(
        370, 389, "192 allocated · 64 idle / 256", 13, C["InkSecondary"], anchor="end"
    )
    b += capacity_bar(20, 407, 350, 192, 64, 0, 256)
    b += section(462, "Your jobs here", "user alex")
    b += relay_row(
        480,
        "protein-fold-v3",
        "48192",
        "Running",
        "4 GPUs requested · 2 h 18 m elapsed",
    )
    b += relay_row(
        580,
        "embedding-sweep",
        "48196 · Array",
        "Pending",
        "Resources · inspect pending reason",
    )
    b += text(
        20, 705, "8 idle GPUs do not guarantee a job can start.", 13, C["InkSecondary"]
    )
    b += text(
        20,
        731,
        "Account, limits, and topology also affect scheduling.",
        12,
        C["InkSecondary"],
    )
    result["14-partition-detail"] = shell(
        "Partition", b, tab="host", back=True, toolbar="more", back_label="Atlas"
    )
    p = D
    b = text(20, 126, "protein-fold-v3", 23, p["Ink"], 650)
    b += text(20, 153, "Atlas / gpu-a100   ·   Running", 14, p["Accent"])
    b += text(20, 188, "stdout", 17, p["Ink"], 650) + text(
        110, 188, "stderr", 17, p["InkSecondary"]
    )
    b += line(20, 200, 77, 200, p["Accent"], 3)
    b += text(370, 186, "Updated 2 s ago", 12, p["InkSecondary"], anchor="end")
    b += rect(20, 220, 350, 65, p["Surface"], 12)
    b += text(34, 244, "MARKERS IN LOADED OUTPUT", 11, p["InkSecondary"], 600)
    b += text(34, 269, "3 checkpoints", 14, p["Accent"], 600) + text(
        224, 269, "2 warnings", 14, p["Warning"], 600
    )
    b += rect(12, 300, 366, 382, p["CodeCanvas"], 12)
    output = [
        ("09:39:21", "Epoch 24 / 80", "plain"),
        ("09:39:25", "step 1201  loss 0.2841", "plain"),
        ("09:39:30", "step 1202  loss 0.2816", "plain"),
        ("09:39:35", "checkpoint saved", "mark"),
        ("", "epoch-24.ckpt", "plain"),
        ("09:39:40", "step 1204  loss 0.2788", "plain"),
    ]
    for i, (stamp, value, kind) in enumerate(output):
        y = 322 + i * 52
        if kind == "mark":
            b += rect(24, y - 12, 342, 46, p["AccentSoft"], 6)
        if stamp:
            b += text(28, y, stamp, 11, p["InkSecondary"], mono=True)
        b += text(
            28,
            y + 21,
            value,
            15,
            p["Accent"] if kind == "mark" else p["Ink"],
            mono=True,
        )
    b += text(
        28, 665, "Loaded tail · 384 KB · markers are local", 12, p["InkSecondary"]
    )
    b += rect(12, 701, 366, 95, p["Surface"], 22)
    b += pill(28, 716, "24 new lines  ↓", p["Accent"], p["AccentSoft"], 172)
    b += glyph("search", 262, 719, p["Ink"], 22) + glyph("more", 324, 719, p["Ink"], 22)
    b += text(
        28, 779, "Reading earlier output · tap to follow latest", 13, p["InkSecondary"]
    )
    result["03-output-dark"] = shell(
        "Output", b, dark=True, back=True, toolbar="more", tabs=False, back_label="Job"
    )
    b = text(20, 126, "Find in output", 26, p["Ink"], 650)
    b += rect(20, 148, 350, 46, p["SurfaceSecondary"], 12)
    b += glyph("search", 32, 161, p["InkSecondary"], 19) + text(
        65, 178, "checkpoint", 17, p["Ink"]
    )
    b += text(20, 226, "3 matches in loaded stdout", 15, p["InkSecondary"])
    b += pill(20, 246, "Matches", p["OnAccent"], p["Accent"], 111)
    b += pill(143, 246, "Bookmarks", p["InkSecondary"], p["SurfaceSecondary"], 127)
    for i, (stamp, file) in enumerate(
        [
            ("09:37:12", "epoch-22.ckpt"),
            ("09:38:17", "epoch-23.ckpt"),
            ("09:39:35", "epoch-24.ckpt"),
        ]
    ):
        y = 306 + i * 112
        b += rect(20, y, 350, 96, p["Surface"], 12)
        b += text(36, y + 26, stamp, 12, p["InkSecondary"], mono=True)
        b += text(36, y + 52, "checkpoint saved", 17, p["Accent"], 600, mono=True)
        b += text(36, y + 77, file, 14, p["InkSecondary"], mono=True)
        b += glyph("next", 336, y + 40, p["InkSecondary"], 18)
    b += text(20, 683, "Tap a match to read surrounding lines.", 15, p["InkSecondary"])
    b += button(20, 717, 350, "Return to reading position", p, False)
    b += text(
        20,
        791,
        "Search covers the output loaded on this iPhone.",
        13,
        p["InkSecondary"],
    )
    result["15-output-search"] = shell(
        "Output", b, dark=True, back=True, toolbar="more", tabs=False, back_label="Read"
    )
    return result


def brand_board():
    out = rect(0, 0, 1440, 1000, C["Canvas"])
    out += text(60, 71, "ssync", 20, INK, 650) + text(
        1380, 71, "NATIVE iOS / BRAND SYSTEM 01", 12, C["InkSecondary"], 600, "end"
    )
    out += text(60, 163, "Your cluster work.", 62, INK, 700) + text(
        60, 237, "Within reach.", 62, BLUE, 700
    )
    out += text(
        60,
        285,
        "Relay — a clear connection between intention and execution.",
        20,
        C["InkSecondary"],
    )
    out += (
        rect(60, 335, 590, 365, "white", 28)
        + mark(96, 370, 224)
        + wordmark(331, 446, 1.5)
    )
    out += text(88, 662, "01  THE RELAY MARK", 12, C["InkSecondary"], 600)
    out += rect(674, 335, 326, 365, "#172137", 28) + mark(725, 385, 224, "#FFFFFF")
    out += text(702, 662, "02  ONE COLOR. ALWAYS LEGIBLE.", 12, "#AAB6CC", 600)
    out += rect(1024, 335, 356, 365, BLUE, 28) + mark(1088, 385, 224, "#FFFFFF")
    out += text(1052, 662, "03  THE APP ICON", 12, "#FFFFFF", 600)
    swatches = [
        ("Cobalt", BLUE, "white"),
        ("Ink", INK, "white"),
        ("Canvas", C["Canvas"], INK),
        ("Running", BLUE, "white"),
        ("Completed", C["Success"], "white"),
        ("Attention", C["Danger"], "white"),
    ]
    for i, (label, col, fg) in enumerate(swatches):
        x = 60 + i * 223
        out += rect(x, 737, 205, 142, col, 16, C["Separator"] if i == 2 else None)
        out += text(x + 16, 839, label, 15, fg, 600) + text(
            x + 16, 862, col, 12, fg, mono=True
        )
    out += text(60, 943, "Calm surfaces. Precise state. Native movement.", 25, INK, 600)
    out += text(
        1380,
        949,
        "Original editable vector artwork · 2026",
        13,
        C["InkSecondary"],
        anchor="end",
    )
    return svg(1440, 1000, out, "ssync Relay brand board")


def surfaces_board():
    p = D
    out = rect(0, 0, 1440, 1140, C["Canvas"])
    out += text(60, 70, "ssync beyond the app", 40, INK, 700)
    out += text(
        60,
        107,
        "Useful at a glance. Honest about freshness. Quiet until it matters.",
        20,
        C["InkSecondary"],
    )
    out += text(60, 175, "HOME SCREEN / SMALL", 12, C["InkSecondary"], 600)
    out += rect(60, 200, 230, 230, "white", 30) + mark(72, 216, 35)
    out += text(106, 241, "ssync", 16, INK, 600) + text(80, 310, "3", 54, BLUE, 650)
    out += text(80, 339, "running jobs", 18, INK, 500)
    out += text(80, 377, "2 pending · 1 needs attention", 12, C["InkSecondary"])
    out += text(80, 407, "Updated 3 min ago", 12, C["InkSecondary"])
    out += text(330, 175, "HOME SCREEN / MEDIUM", 12, C["InkSecondary"], 600)
    out += rect(330, 200, 560, 230, "white", 30)
    out += text(353, 238, "Pinned jobs", 20, INK, 650) + text(
        866, 238, "3 min ago", 12, C["InkSecondary"], anchor="end"
    )
    for i, (name, state, meta) in enumerate(
        [
            ("protein-fold-v3", "Running", "Atlas · 2 h 18 m"),
            ("eval-baseline", "Running", "Boreal · 12 m"),
            ("embedding-sweep", "Pending", "Atlas · resources"),
        ]
    ):
        y = 260 + i * 49
        out += glyph(
            state.lower(), 352, y, BLUE if state == "Running" else C["Warning"], 20
        )
        out += text(385, y + 15, name, 16, INK, 500) + text(
            866, y + 15, meta, 13, C["InkSecondary"], anchor="end"
        )
    out += text(930, 175, "LOCK SCREEN / RECTANGULAR", 12, C["InkSecondary"], 600)
    out += rect(930, 200, 450, 230, "#253044", 30)
    out += text(962, 250, "ssync", 18, "white", 650)
    out += text(962, 292, "3 running · 2 pending", 25, "white", 600)
    out += text(962, 328, "1 needs attention", 18, "white")
    out += text(962, 369, "Updated 3 min ago", 14, "#C7D0E1")
    out += text(60, 490, "LIVE ACTIVITY / LOCK SCREEN", 12, C["InkSecondary"], 600)
    out += rect(60, 515, 560, 255, p["Surface"], 30)
    out += mark(72, 530, 45, p["Accent"]) + text(
        126, 561, "ssync · Atlas", 16, p["Ink"], 600
    )
    out += pill(491, 536, "Running", p["Accent"], p["AccentSoft"], 105)
    out += text(84, 609, "protein-fold-v3", 26, p["Ink"], 650)
    out += text(84, 658, "2 h 18 m", 34, p["Ink"], 600) + text(
        594, 658, "8 h limit", 18, p["InkSecondary"], anchor="end"
    )
    out += rect(84, 682, 510, 6, p["SurfaceSecondary"], 3) + rect(
        84, 682, 147, 6, p["Accent"], 3
    )
    out += text(84, 716, "Time used · not job progress", 13, p["InkSecondary"])
    out += text(84, 746, "Open job", 16, p["Accent"], 600) + text(
        594, 746, "Updated 1 min ago", 12, p["InkSecondary"], anchor="end"
    )
    out += text(670, 490, "DYNAMIC ISLAND / EXPANDED", 12, C["InkSecondary"], 600)
    out += rect(670, 515, 430, 195, "#05070B", 38)
    out += mark(686, 532, 45, p["Accent"]) + text(748, 562, "Atlas", 15, "#CAD4E6")
    out += text(1074, 562, "Running", 14, p["Accent"], 600, "end")
    out += text(693, 606, "protein-fold-v3", 22, "white", 600)
    out += text(693, 654, "2 h 18 m", 29, "white", 600) + text(
        1075, 654, "8 h limit", 15, "#CAD4E6", anchor="end"
    )
    out += text(1140, 490, "COMPACT / MINIMAL", 12, C["InkSecondary"], 600)
    out += (
        rect(1140, 515, 240, 55, "#05070B", 28)
        + mark(1152, 524, 34, p["Accent"])
        + text(1362, 551, "2:18", 19, p["Accent"], 600, "end")
    )
    out += circle(1168, 628, 28, "#05070B") + mark(1149, 609, 38, p["Accent"])
    out += text(60, 828, "HOME SCREEN / SELECTED PARTITION", 12, C["InkSecondary"], 600)
    out += rect(60, 850, 560, 180, "white", 24)
    out += text(83, 889, "Atlas / gpu-a100", 21, INK, 650)
    out += text(597, 888, "3 min ago", 13, C["InkSecondary"], anchor="end")
    out += text(83, 933, "24 / 32 GPUs allocated", 23, BLUE, 650)
    out += capacity_bar(83, 952, 514, 24, 8, 0, 32)
    out += text(83, 1004, "Your jobs · 1 running · 1 pending", 16, C["InkSecondary"])
    out += text(678, 889, "A useful glance, wherever you are.", 25, INK, 650)
    out += text(
        678, 932, "Job and capacity snapshots show their age.", 19, C["InkSecondary"]
    )
    out += text(
        678, 969, "Live Activities follow one chosen operation.", 19, C["InkSecondary"]
    )
    out += text(
        60,
        1090,
        "Concept layouts. WidgetKit and ActivityKit own final system presentation; server integration is planned.",
        15,
        C["InkSecondary"],
    )
    return svg(1440, 1140, out, "ssync widgets and Live Activity concepts")


def component_board():
    out = rect(0, 0, 1440, 1160, C["Canvas"])
    out += text(60, 76, "Recognizably ssync.", 44, INK, 700)
    out += text(
        60,
        118,
        "Custom components shaped around hosts, jobs, rules, and output.",
        21,
        C["InkSecondary"],
    )
    out += text(60, 188, "01 / HOST OVERVIEW & STATE RAILS", 13, BLUE, 650)
    out += text(752, 188, "02 / WATCHER RULE DIAGRAM", 13, BLUE, 650)
    left = section(36, "Atlas", "Updated just now")
    left += relay_row(
        60, "protein-fold-v3", "48192", "Running", "2 h 18 m elapsed · 4 GPUs", pin=True
    )
    left += relay_row(
        162,
        "embedding-sweep",
        "48196 · Array",
        "Pending",
        "Waiting for resources · 64 tasks",
    )
    out += f'<g transform="translate(44 213) scale(1.6)">{left}</g>'
    out += rect(752, 217, 628, 402, INK, 24)
    out += line(796, 287, 796, 535, "#7788AE", 2)
    for i, (y, label, value, sub) in enumerate(
        [
            (252, "WHEN", "Job times out", "A recorded scheduler transition"),
            (376, "USING", "Captured checkpoint", "resume_run_dir from job output"),
            (500, "THEN", "Watcher resubmission", "Replay the original job context"),
        ]
    ):
        out += circle(796, y + 35, 14, "#9BADFF")
        out += text(796, y + 40, i + 1, 13, "#101C45", 650, "middle")
        out += text(833, y + 12, label, 12, "#B7C5FF", 650)
        out += text(833, y + 47, value, 24, "white", 600)
        out += text(833, y + 77, sub, 15, "#C3CEE5")
    out += text(60, 698, "03 / OUTPUT DOCK", 13, BLUE, 650)
    out += rect(60, 727, 628, 145, "#10141D", 24)
    out += text(84, 761, "step 1206  loss 0.2743", 17, "#F2F5FC", mono=True)
    out += rect(79, 790, 590, 60, "#252D3C", 16)
    out += pill(94, 805, "stdout", "#101C45", "#9BADFF", 90)
    out += pill(200, 805, "24 new lines  ↓", "#9BADFF", "#25335C", 149)
    out += glyph("search", 574, 808, "#C3CEE5", 22) + glyph(
        "more", 621, 808, "#C3CEE5", 22
    )
    out += text(752, 698, "04 / JOB SUMMARY", 13, BLUE, 650)
    out += rect(752, 727, 628, 145, BLUE, 24)
    out += text(778, 763, "PROTEIN-FOLD-V3 / RUNNING", 13, "white", 600)
    out += text(778, 823, "2 h 18 m", 46, "white", 650)
    out += text(1354, 822, "8 h limit", 22, "white", 500, "end")
    out += rect(779, 844, 575, 4, "#667FE4", 2) + rect(779, 844, 165, 4, "white", 2)
    out += line(60, 927, 1380, 927, C["Separator"])
    out += text(60, 974, "The common thread", 25, INK, 650)
    out += text(
        60,
        1013,
        "Rounded terminals. Strong hierarchy. Ink and cobalt. Movement only when something changes.",
        19,
        C["InkSecondary"],
    )
    out += text(
        60,
        1072,
        "SF system type · 4 pt spacing scale · 44 pt hit targets · accessible static states",
        16,
        BLUE,
        550,
    )
    out += text(
        60,
        1110,
        "Native navigation and input behavior underpin the custom presentation.",
        16,
        C["InkSecondary"],
    )
    return svg(1440, 1160, out, "ssync signature components")


def motion_scene(kind, progress):
    """One-shot choreography normalized to 0..1; exported demos include a pause."""
    out = rect(0, 0, 640, 320, INK, 24)
    labels = {
        "job-state-arrival": ("JOB STATE ARRIVAL", "protein-fold-v3", "Atlas · 48192"),
        "watcher-event": ("WATCHER EVENT", "Resume from checkpoint", "Atlas · 48192"),
        "launch-handoff": (
            "LAUNCH HANDOFF",
            "protein-fold-v4",
            "Atlas · new submission",
        ),
    }
    eyebrow, title, detail = labels[kind]
    out += text(28, 39, eyebrow, 12, "#B7C5FF", 650)
    out += text(28, 84, title, 27, "white", 650)
    out += text(28, 113, detail, 15, "#C3CEE5")
    positions = [58, 306, 582]
    out += line(58, 191, 582, 191, "#485773", 3)
    if kind == "job-state-arrival":
        stages = ["Pending", "Update received", "Running"]
    elif kind == "watcher-event":
        stages = ["Match", "Capture", "Action succeeded"]
    else:
        stages = ["Accepted", "Submitting", "Job 48201"]
    marker_x = 58 + 524 * progress
    out += line(58, 191, marker_x, 191, "#9BADFF", 3)
    for i, (x, label) in enumerate(zip(positions, stages)):
        complete = progress >= i / 2
        out += circle(x, 191, 10, "#9BADFF" if complete else "#485773")
        out += text(
            x,
            230,
            label,
            14,
            "white" if complete else "#C3CEE5",
            500,
            "start" if i == 0 else "end" if i == 2 else "middle",
        )
    out += circle(marker_x, 191, 5, "white")
    if kind == "job-state-arrival":
        detail = "Last known state" if progress < 1 else "Running · updated just now"
    elif kind == "watcher-event":
        detail = (
            "Inspecting the reported event"
            if progress < 1
            else "Resubmission succeeded · new job 48201"
        )
    else:
        detail = (
            "Waiting for scheduler confirmation"
            if progress < 1
            else "Job 48201 submitted · Open job"
        )
    out += text(28, 285, detail, 16, "#B7C5FF", 500)
    return out


def make_motion_assets():
    kinds = ["job-state-arrival", "watcher-event", "launch-handoff"]
    for kind in kinds:
        static = motion_scene(kind, 1)
        # SMIL supplies an editable playback study, not production timing logic.
        base = motion_scene(kind, 0)
        track = '<circle r="5" fill="white"><animateMotion dur="3s" repeatCount="indefinite" path="M58 191H582" keyPoints="0;0;1;1" keyTimes="0;0.18;0.42;1" calcMode="linear"/></circle>'
        # Replace the moving dot and add a track; final label swaps in at the endpoint.
        base = base.replace(circle(58, 191, 5, "white"), "")
        animation = "<style>.static{display:none}@media(prefers-reduced-motion:reduce){.moving{display:none}.static{display:inline}}</style>"
        animation += '<g class="moving">' + base + track
        animation += (
            '<g opacity="0">'
            + static
            + '<animate attributeName="opacity" dur="3s" repeatCount="indefinite" values="0;0;1;1" keyTimes="0;0.41;0.42;1"/></g></g>'
        )
        animation += '<g class="static">' + static + "</g>"
        write(
            f"assets/motion/{kind}.svg",
            svg(
                640, 320, animation, f"ssync {kind} motion study; looping demonstration"
            ),
        )
        # Raster previews use the same state model; generated temporary frames stay outside repo.
        import tempfile

        with tempfile.TemporaryDirectory(prefix="ssync-motion-") as tmp:
            frames = []
            for index in range(36):
                t = index / 35
                progress = min(1.0, max(0.0, (t - 0.18) / 0.24))
                # Smooth arrival, with deterministic endpoints.
                progress = progress * progress * (3 - 2 * progress)
                src = Path(tmp) / f"{index:03}.svg"
                dst = src.with_suffix(".png")
                src.write_text(svg(640, 320, motion_scene(kind, progress), kind))
                subprocess.run(["rsvg-convert", "-o", str(dst), str(src)], check=True)
                frames.append(str(dst))
            subprocess.run(
                [
                    "magick",
                    "-delay",
                    "8",
                    "-loop",
                    "0",
                    *frames,
                    "-layers",
                    "Optimize",
                    str(ROOT / f"assets/motion/{kind}.gif"),
                ],
                check=True,
            )
    board = rect(0, 0, 1440, 1180, C["Canvas"])
    board += text(60, 78, "Motion with a reason.", 44, INK, 700)
    board += text(
        60,
        121,
        "The Relay gesture: arrive, hand off, settle. Then stay quiet.",
        22,
        C["InkSecondary"],
    )
    titles = [
        "01 / Job state arrival · 480 ms",
        "02 / Watcher event · 560 ms",
        "03 / Launch handoff · 620 ms",
    ]
    for row, kind in enumerate(kinds):
        y = 182 + row * 295
        board += text(60, y, titles[row], 19, INK, 650)
        for i, progress in enumerate([0, 0.33, 0.7, 1]):
            x = 60 + i * 335
            body = motion_scene(kind, progress)
            board += f'<svg x="{x}" y="{y + 23}" width="315" height="158" viewBox="0 0 640 320">{body}</svg>'
            board += text(
                x,
                y + 207,
                ["Start", "Receive", "Resolve", "Rest"][i],
                14,
                C["InkSecondary"],
                500,
            )
    board += text(
        60,
        1093,
        "Event-triggered in the app. Reduced Motion shows the final state without a traveling trace.",
        19,
        INK,
        500,
    )
    board += text(
        60,
        1127,
        "These studies replay for review. Domain state is authoritative; animation never predicts an outcome.",
        15,
        C["InkSecondary"],
    )
    write(
        "design/boards/05-motion.svg",
        svg(1440, 1180, board, "ssync motion choreography storyboard"),
    )


def main():
    for binary in ["rsvg-convert", "magick"]:
        if not shutil.which(binary):
            raise SystemExit(f"Missing required renderer: {binary}")
    for name, color in [("cobalt", BLUE), ("ink", INK), ("white", "#FFFFFF")]:
        write(
            f"assets/brand/relay-mark-{name}.svg",
            svg(100, 100, mark(color=color), f"ssync Relay mark — {name}"),
        )
        write(
            f"assets/brand/wordmark-{name}.svg",
            svg(
                192,
                66,
                wordmark(9, 6, color=color),
                f"ssync outlined wordmark — {name}",
            ),
        )
        write(
            f"assets/brand/lockup-{name}.svg",
            svg(
                306,
                100,
                mark(size=88, y=6, color=color) + wordmark(115, 23, color=color),
                f"ssync brand lockup — {name}",
            ),
        )
    colors = [
        ("default", BLUE, "#FFFFFF"),
        ("dark", "#172137", "#B7C5FF"),
        ("tinted", "#191919", "#FFFFFF"),
    ]
    catalog = ROOT / "Resources/Assets.xcassets"
    write(
        "Resources/Assets.xcassets/Contents.json",
        json.dumps({"info": {"author": "xcode", "version": 1}}, indent=2),
    )
    images = []
    for appearance, bg, fg in colors:
        path = write(
            f"assets/app-icon/app-icon-{appearance}.svg",
            svg(
                1024,
                1024,
                rect(0, 0, 1024, 1024, bg) + mark(94, 94, 836, fg),
                f"ssync app icon — {appearance}",
            ),
        )
        dest = path.with_suffix(".png")
        subprocess.run(["rsvg-convert", "-o", str(dest), str(path)], check=True)
        subprocess.run(["magick", str(dest), "-alpha", "off", str(dest)], check=True)
        (catalog / "AppIcon.appiconset").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(dest, catalog / "AppIcon.appiconset" / dest.name)
        image = {
            "filename": dest.name,
            "idiom": "universal",
            "platform": "ios",
            "size": "1024x1024",
        }
        if appearance != "default":
            image["appearances"] = [{"appearance": "luminosity", "value": appearance}]
        images.append(image)
    write(
        "Resources/Assets.xcassets/AppIcon.appiconset/Contents.json",
        json.dumps(
            {"images": images, "info": {"author": "xcode", "version": 1}}, indent=2
        ),
    )
    write(
        "assets/app-icon/layers/background.svg",
        svg(1024, 1024, rect(0, 0, 1024, 1024, BLUE), "ssync icon background layer"),
    )
    write(
        "assets/app-icon/layers/foreground.svg",
        svg(1024, 1024, mark(94, 94, 836, "#FFFFFF"), "ssync icon foreground layer"),
    )
    for name, pair in TOKENS["colors"].items():
        entries = []
        for appearance, hexa in pair.items():
            components = {
                key: f"{int(hexa[i : i + 2], 16) / 255:.6f}"
                for key, i in [("red", 1), ("green", 3), ("blue", 5)]
            }
            entry = {
                "idiom": "universal",
                "color": {
                    "color-space": "srgb",
                    "components": {**components, "alpha": "1.000"},
                },
            }
            if appearance == "dark":
                entry["appearances"] = [{"appearance": "luminosity", "value": "dark"}]
            entries.append(entry)
        write(
            f"Resources/Assets.xcassets/{name}.colorset/Contents.json",
            json.dumps(
                {"colors": entries, "info": {"author": "xcode", "version": 1}}, indent=2
            ),
        )
    custom = {
        "job-array": '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><path d="M14 17.5h7m-3.5-3.5v7"/>',
        "watcher-rule": '<path d="M3 6h7M3 18h7m0-12 7 6-7 6"/><circle cx="19" cy="12" r="2"/>',
        "launch-recipe": '<path d="M5 3h10l4 4v14H5Z"/><path d="M14 3v5h5M8 12h8M8 16h5"/>',
    }
    for name, shape in custom.items():
        body = f'<g fill="none" stroke="#172137" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{shape}</g>'
        path = write(f"assets/icons/{name}.svg", svg(24, 24, body, f"ssync {name}"))
        aset = catalog / (name + ".imageset")
        aset.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["rsvg-convert", "-f", "pdf", "-o", str(aset / (name + ".pdf")), str(path)],
            check=True,
        )
        write(
            f"Resources/Assets.xcassets/{name}.imageset/Contents.json",
            json.dumps(
                {
                    "images": [{"filename": name + ".pdf", "idiom": "universal"}],
                    "info": {"author": "xcode", "version": 1},
                    "properties": {
                        "preserves-vector-representation": True,
                        "template-rendering-intent": "template",
                    },
                },
                indent=2,
            ),
        )
    illustrations = {
        "empty-jobs": rect(35, 35, 170, 128, "white", 20, C["Separator"])
        + glyph("jobs", 94, 66, BLUE, 50)
        + line(68, 132, 172, 132, C["Separator"], 5),
        "connection": glyph("host", 25, 69, BLUE, 60)
        + line(88, 100, 152, 100, BLUE, 3)
        + rect(159, 47, 54, 103, "white", 12, C["Separator"])
        + mark(161, 76, 50),
        "empty-watchers": circle(120, 100, 72, C["AccentSoft"])
        + glyph("watchers", 80, 60, BLUE, 80),
    }
    for name, body in illustrations.items():
        write(
            f"assets/illustrations/{name}.svg",
            svg(240, 200, body, f"ssync {name} empty state"),
        )
    write("design/boards/01-brand.svg", brand_board())
    write("design/boards/02-components.svg", component_board())
    write("design/boards/03-system-surfaces.svg", surfaces_board())
    make_motion_assets()
    rendered = screens()
    for name, source in rendered.items():
        write(f"design/screens/{name}.svg", source)
    selected = [
        "01-jobs-light",
        "12-hosts",
        "14-partition-detail",
        "03-output-dark",
        "07-watcher-detail",
        "05-launch-review",
    ]
    board = rect(0, 0, 1440, 2100, "#EAEDF5")
    board += text(60, 81, "ssync / native iOS", 42, INK, 700)
    board += text(
        60,
        125,
        "A mobile workspace for SLURM. Selected screen concepts.",
        20,
        C["InkSecondary"],
    )
    for i, name in enumerate(selected):
        x, y = 70 + (i % 3) * 451, 190 + (i // 3) * 946
        # Embed complete vector art, retaining its viewBox.
        inner = rendered[name].replace(
            'width="390" height="844"', f'x="{x}" y="{y}" width="390" height="844"', 1
        )
        board += rect(x - 2, y - 2, 394, 848, "#CCD3E1", 4) + inner
        board += text(
            x, y + 879, name.split("-", 1)[1].replace("-", " ").title(), 17, INK, 600
        )
    write(
        "design/boards/04-screen-overview.svg",
        svg(1440, 2100, board, "ssync native iOS screen concept overview"),
    )
    for path in sorted((ROOT / "design").rglob("*.svg")):
        subprocess.run(
            ["rsvg-convert", "-o", str(path.with_suffix(".png")), str(path)], check=True
        )
    print(
        f"Generated {len(rendered)} screen concepts, 5 boards, 3 motion studies, brand assets, 3 app icons, 3 custom glyphs, 3 illustrations, and {len(TOKENS['colors'])} adaptive color assets."
    )


if __name__ == "__main__":
    main()
