#!/usr/bin/env python3
"""Render the existing title-header SVG into every app/plugin icon representation."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

MACOS = Path(__file__).resolve().parent
ROOT = MACOS.parent
SOURCE = MACOS / 'Sources/CodexDuoMenu/Resources/Brand/AppIcon.svg'
ASSETS = MACOS / 'Assets'
SIZES = {f'icon_{points}x{points}{suffix}.png': points * scale
         for points in (16, 32, 128, 256, 512) for suffix, scale in (('', 1), ('@2x', 2))}


def generate():
    renderer = shutil.which('rsvg-convert')
    if not renderer:
        raise SystemExit('rsvg-convert is required; existing artwork is not replaced.')
    iconset = ASSETS / 'AppIcon.iconset'; iconset.mkdir(parents=True, exist_ok=True)
    for name, pixels in SIZES.items():
        subprocess.run([renderer, '--width', str(pixels), '--height', str(pixels),
            '--output', str(iconset / name), str(SOURCE)], check=True)
        raw = (iconset / name).read_bytes()
        if raw[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', raw[16:24]) != (pixels, pixels):
            raise SystemExit('Invalid rendered icon size: ' + name)
    subprocess.run(['/usr/bin/iconutil', '--convert', 'icns', '--output',
        str(ASSETS / 'AppIcon.icns'), str(iconset)], check=True)
    shutil.copyfile(iconset / 'icon_512x512.png', ASSETS / 'AppIcon-preview.png')
    plugin = ROOT / 'plugins/codex-duo/assets'
    shutil.copyfile(SOURCE, plugin / 'tandem.svg')
    shutil.copyfile(iconset / 'icon_512x512@2x.png', plugin / 'tandem.png')
    return {'source': str(SOURCE.relative_to(ROOT)),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(), 'sizes': SIZES,
        'icns_sha256': hashlib.sha256((ASSETS / 'AppIcon.icns').read_bytes()).hexdigest(),
        'plugin_png_sha256': hashlib.sha256((plugin / 'tandem.png').read_bytes()).hexdigest()}


if __name__ == '__main__': print(json.dumps(generate(), indent=2))
