#!/usr/bin/env python3
"""Generate domain-specific HYDRO icons (Pipeline Cross-Section + Water + Manometer)."""

from __future__ import annotations

import json
import math
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS_ICONS = REPO_ROOT / "assets" / "icons"
FRONTEND_PUBLIC = REPO_ROOT / "webapp" / "frontend" / "public"

SVG_SOURCE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
  <defs>
    <linearGradient id="hydro-bg" x1="8" y1="6" x2="56" y2="58" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#131d33"/>
      <stop offset="100%" stop-color="#070b14"/>
    </linearGradient>
    <linearGradient id="hydro-flange" x1="12" y1="14" x2="48" y2="52" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#64748b"/>
      <stop offset="50%" stop-color="#334155"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
    <linearGradient id="hydro-water" x1="28" y1="30" x2="28" y2="49" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#22d3ee"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
    <clipPath id="hydro-bore-clip">
      <circle cx="29" cy="35" r="13.5"/>
    </clipPath>
  </defs>

  <!-- Base squircle -->
  <rect x="2" y="2" width="60" height="60" rx="14" fill="url(#hydro-bg)" stroke="#22d3ee" stroke-opacity="0.32" stroke-width="1.5"/>

  <!-- Pipeline flange + steel pipe wall -->
  <circle cx="29" cy="35" r="20.5" fill="url(#hydro-flange)" stroke="#94a3b8" stroke-width="1.4"/>
  <circle cx="29" cy="35" r="16" fill="#0f172a" stroke="#475569" stroke-width="1.2"/>
  <circle cx="29" cy="35" r="13.5" fill="#070b14"/>

  <!-- Flange bolts (6 radial bolts) -->
  <circle cx="29" cy="16.8" r="1.35" fill="#cbd5e1"/>
  <circle cx="44.8" cy="25.9" r="1.35" fill="#cbd5e1"/>
  <circle cx="44.8" cy="44.1" r="1.35" fill="#cbd5e1"/>
  <circle cx="29" cy="53.2" r="1.35" fill="#cbd5e1"/>
  <circle cx="13.2" cy="44.1" r="1.35" fill="#cbd5e1"/>
  <circle cx="13.2" cy="25.9" r="1.35" fill="#cbd5e1"/>

  <!-- Pressurized hydrostatic water fill inside pipe bore -->
  <g clip-path="url(#hydro-bore-clip)">
    <path d="M14 33.5 Q21.5 30 29 33.5 T44 33.5 V52 H14 Z" fill="url(#hydro-water)"/>
    <path d="M14 33.5 Q21.5 30 29 33.5 T44 33.5" stroke="#a5f3fc" stroke-width="1.5" stroke-linecap="round"/>
    <circle cx="24" cy="41.5" r="1.4" fill="#cffafe" fill-opacity="0.7"/>
    <circle cx="33.5" cy="39" r="1.0" fill="#cffafe" fill-opacity="0.6"/>
  </g>
  <circle cx="29" cy="35" r="13.5" stroke="#22d3ee" stroke-opacity="0.55" stroke-width="1"/>

  <!-- Integrated pressure manometer dial (top-right) -->
  <circle cx="46.5" cy="18.5" r="11.5" fill="#0f172a" stroke="#e2e8f0" stroke-width="1.8"/>
  <circle cx="46.5" cy="18.5" r="9.2" fill="#070b14"/>
  <!-- Gauge scale arc + emerald acceptance zone -->
  <path d="M39.8 22.8 A8 8 0 1 1 53.2 22.8" stroke="#475569" stroke-width="2" stroke-linecap="round"/>
  <path d="M47.8 10.6 A8 8 0 0 1 54.1 20.5" stroke="#34d399" stroke-width="2.3" stroke-linecap="round"/>
  <!-- Needle pointing cleanly into PASS zone -->
  <line x1="46.5" y1="18.5" x2="51.8" y2="14.2" stroke="#f8fafc" stroke-width="1.9" stroke-linecap="round"/>
  <circle cx="46.5" cy="18.5" r="1.9" fill="#22d3ee"/>
</svg>
"""


def _render_master_png(size: int = 1024) -> Image.Image:
    """Render high-resolution master PNG matching SVG geometry via 2x supersampling."""
    scale = 2
    w = size * scale
    img = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def px(v: float) -> float:
        return v * (w / 64.0)

    # 1) Rounded squircle background
    margin = int(round(px(2)))
    rad = int(round(px(14)))
    draw.rounded_rectangle(
        [margin, margin, w - margin, w - margin],
        radius=rad,
        fill=(11, 18, 32, 255),
        outline=(30, 92, 120, 255),
        width=max(2, int(round(px(1.5)))),
    )
    inner_margin = int(round(px(3.5)))
    draw.rounded_rectangle(
        [inner_margin, inner_margin, w - inner_margin, w - inner_margin],
        radius=max(10, rad - 16),
        fill=(14, 23, 42, 255),
    )

    # 2) Steel pipeline flange + wall cross-section (center 29, 35)
    cx, cy = px(29), px(35)
    r_flange = px(20.5)
    r_wall = px(16.0)
    r_bore = px(13.5)

    draw.ellipse(
        [cx - r_flange, cy - r_flange, cx + r_flange, cy + r_flange],
        fill=(51, 65, 85, 255),
        outline=(148, 163, 184, 255),
        width=max(2, int(round(px(1.4)))),
    )
    draw.ellipse(
        [cx - r_wall, cy - r_wall, cx + r_wall, cy + r_wall],
        fill=(15, 23, 42, 255),
        outline=(71, 85, 105, 255),
        width=max(2, int(round(px(1.2)))),
    )
    draw.ellipse(
        [cx - r_bore, cy - r_bore, cx + r_bore, cy + r_bore],
        fill=(7, 11, 20, 255),
    )

    # 6 radial bolts
    bolt_r = px(18.2)
    bolt_rad = px(1.35)
    for idx in range(6):
        ang = math.radians(-90 + idx * 60)
        bx = cx + bolt_r * math.cos(ang)
        by = cy + bolt_r * math.sin(ang)
        draw.ellipse(
            [bx - bolt_rad, by - bolt_rad, bx + bolt_rad, by + bolt_rad],
            fill=(203, 213, 225, 255),
        )

    # 3) Pressurized hydrostatic water inside bore (masked cleanly)
    water_layer = Image.new("RGBA", (w, w), (0, 0, 0, 0))
    w_draw = ImageDraw.Draw(water_layer)
    mask = Image.new("L", (w, w), 0)
    m_draw = ImageDraw.Draw(mask)
    m_draw.ellipse([cx - r_bore, cy - r_bore, cx + r_bore, cy + r_bore], fill=255)

    wave_pts: list[tuple[float, float]] = []
    steps = 64
    for i in range(steps + 1):
        t = i / steps
        x = px(15) + t * px(28)
        y = px(33.5) + math.sin(t * 2.0 * math.pi) * px(1.9)
        wave_pts.append((x, y))
    poly = wave_pts + [(px(43), px(50)), (px(15), px(50))]
    w_draw.polygon(poly, fill=(8, 145, 178, 255))
    # Brighter upper water band
    band_poly = wave_pts + [(x, y + px(5.5)) for x, y in reversed(wave_pts)]
    w_draw.polygon(band_poly, fill=(34, 211, 238, 225))
    w_draw.line(wave_pts, fill=(165, 243, 252, 255), width=max(3, int(round(px(1.5)))))

    for bx_u, by_u, br_u in ((24.0, 41.5, 1.4), (33.5, 39.0, 1.0)):
        bx, by, br = px(bx_u), px(by_u), px(br_u)
        w_draw.ellipse([bx - br, by - br, bx + br, by + br], fill=(207, 250, 254, 185))

    clipped_water = Image.composite(water_layer, Image.new("RGBA", (w, w), (0, 0, 0, 0)), mask)
    img = Image.alpha_composite(img, clipped_water)
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        [cx - r_bore, cy - r_bore, cx + r_bore, cy + r_bore],
        outline=(34, 211, 238, 150),
        width=max(2, int(round(px(1.0)))),
    )

    # 4) Precision manometer dial (top-right: center 46.5, 18.5)
    gx, gy = px(46.5), px(18.5)
    gr_outer = px(11.5)
    gr_inner = px(9.2)
    gr_arc = px(7.8)
    draw.ellipse(
        [gx - gr_outer, gy - gr_outer, gx + gr_outer, gy + gr_outer],
        fill=(15, 23, 42, 255),
        outline=(226, 232, 240, 255),
        width=max(3, int(round(px(1.8)))),
    )
    draw.ellipse(
        [gx - gr_inner, gy - gr_inner, gx + gr_inner, gy + gr_inner],
        fill=(7, 11, 20, 255),
    )
    arc_box = [gx - gr_arc, gy - gr_arc, gx + gr_arc, gy + gr_arc]
    draw.arc(
        arc_box, start=145, end=395, fill=(71, 85, 105, 255), width=max(3, int(round(px(2.0))))
    )
    draw.arc(
        arc_box, start=285, end=25, fill=(52, 211, 153, 255), width=max(4, int(round(px(2.4))))
    )

    # Gauge needle & hub
    draw.line(
        [(gx, gy), (px(51.8), px(14.2))],
        fill=(248, 250, 252, 255),
        width=max(3, int(round(px(1.9)))),
    )
    hub_r = px(1.9)
    draw.ellipse([gx - hub_r, gy - hub_r, gx + hub_r, gy + hub_r], fill=(34, 211, 238, 255))

    return img.resize((size, size), Image.Resampling.LANCZOS)


def _build_icns(master: Image.Image, target_icns: Path) -> None:
    if platform.system() != "Darwin" or not shutil.which("iconutil"):
        return
    iconset_entries = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    with tempfile.TemporaryDirectory(prefix="hydro_iconset_") as tmp:
        iconset_dir = Path(tmp) / "Hydro.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)
        for filename, dim in iconset_entries:
            resized = (
                master
                if dim == master.width
                else master.resize((dim, dim), Image.Resampling.LANCZOS)
            )
            resized.save(iconset_dir / filename, "PNG")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(target_icns)], check=True
        )


def main() -> int:
    ASSETS_ICONS.mkdir(parents=True, exist_ok=True)
    FRONTEND_PUBLIC.mkdir(parents=True, exist_ok=True)

    master = _render_master_png(1024)

    (ASSETS_ICONS / "hydro-icon.svg").write_text(SVG_SOURCE, encoding="utf-8")
    (FRONTEND_PUBLIC / "favicon.svg").write_text(SVG_SOURCE, encoding="utf-8")

    master.save(ASSETS_ICONS / "hydro-1024.png", "PNG")
    master.resize((256, 256), Image.Resampling.LANCZOS).save(ASSETS_ICONS / "hydro-256.png", "PNG")
    master.resize((64, 64), Image.Resampling.LANCZOS).save(ASSETS_ICONS / "hydro-64.png", "PNG")

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(ASSETS_ICONS / "hydro.ico", format="ICO", sizes=ico_sizes)
    master.save(FRONTEND_PUBLIC / "favicon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48)])

    master.resize((180, 180), Image.Resampling.LANCZOS).save(
        FRONTEND_PUBLIC / "apple-touch-icon.png", "PNG"
    )
    master.resize((192, 192), Image.Resampling.LANCZOS).save(
        FRONTEND_PUBLIC / "icon-192.png", "PNG"
    )
    master.resize((512, 512), Image.Resampling.LANCZOS).save(
        FRONTEND_PUBLIC / "icon-512.png", "PNG"
    )

    _build_icns(master, ASSETS_ICONS / "hydro.icns")

    manifest = {
        "name": "HYDRO | Hidrostatik Test Platformu",
        "short_name": "HYDRO",
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": "#0b1220",
        "background_color": "#070b14",
        "display": "standalone",
    }
    (FRONTEND_PUBLIC / "site.webmanifest").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Generated HYDRO domain icons in", ASSETS_ICONS, "and", FRONTEND_PUBLIC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
