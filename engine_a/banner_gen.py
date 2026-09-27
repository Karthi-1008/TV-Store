"""Banner generator for Android TV (320x180 px Leanback banner).
Generates tv_banner.png from app icon or fallback branded card.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import shutil

def find_best_icon_file(decompiled_dir: Path, icon_ref: str) -> Path | None:
    """Find the best resolution raster icon (PNG/WEBP) in decompiled res/."""
    decompiled_dir = Path(decompiled_dir)
    res_dir = decompiled_dir / "res"
    if not res_dir.exists():
        return None

    # Strip @drawable/, @mipmap/, res/
    icon_name = icon_ref
    if icon_name.startswith("@"):
        icon_name = icon_name.split("/")[-1]
    elif icon_name.startswith("res/"):
        icon_name = Path(icon_name).stem
    else:
        icon_name = Path(icon_name).stem

    # Search in all mipmap and drawable folders for png or webp
    candidates = []
    for ext in ("png", "webp", "jpg"):
        for p in res_dir.glob(f"**/{icon_name}.{ext}"):
            candidates.append(p)
        for p in res_dir.glob(f"**/*ic_launcher*.{ext}"):
            candidates.append(p)

    if not candidates:
        return None

    # Sort by file size as a proxy for highest resolution
    candidates.sort(key=lambda p: p.stat().st_size, reverse=True)
    return candidates[0]

def generate_tv_banner(
    decompiled_dir: Path,
    app_label: str,
    icon_ref: str = "",
    width: int = 320,
    height: int = 180
) -> Path:
    """Generate a 320x180 Android TV banner and save to res/drawable/tv_banner.png."""
    decompiled_dir = Path(decompiled_dir)
    drawable_dir = decompiled_dir / "res" / "drawable"
    drawable_dir.mkdir(parents=True, exist_ok=True)
    target_banner = drawable_dir / "tv_banner.png"

    # Background canvas: dark TV theme (#1a1c23 with a subtle gradient)
    banner = Image.new("RGBA", (width, height), (26, 28, 35, 255))
    draw = ImageDraw.Draw(banner)

    # Draw gradient or subtle accent bar at bottom
    for y in range(height):
        # subtle vertical gradient
        alpha = int(25 + (y / height) * 35)
        draw.line([(0, y), (width, y)], fill=(alpha, alpha + 10, alpha + 20, 255))

    # Bottom accent line
    draw.rectangle([0, height - 4, width, height], fill=(79, 134, 247, 255))

    # Try to load icon
    icon_path = find_best_icon_file(decompiled_dir, icon_ref)
    icon_img = None
    if icon_path and icon_path.exists():
        try:
            icon_img = Image.open(icon_path).convert("RGBA")
        except Exception:
            icon_img = None

    if icon_img:
        # Resize icon to fit nicely (e.g. 100x100 max)
        icon_size = 96
        icon_img.thumbnail((icon_size, icon_size), Image.Resampling.LANCZOS)
        # Position icon on the left or center
        if app_label:
            # Icon on left, text on right
            icon_x = 24
            icon_y = (height - icon_img.height) // 2
            banner.paste(icon_img, (icon_x, icon_y), icon_img)

            # Draw text
            text_x = icon_x + icon_img.width + 16
            # Use basic default font
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None

            # Wrap or truncate text if needed
            display_title = app_label[:20] + "..." if len(app_label) > 22 else app_label
            draw.text((text_x, height // 2 - 10), display_title, fill=(255, 255, 255, 255), font=font)
        else:
            # Centered icon
            icon_x = (width - icon_img.width) // 2
            icon_y = (height - icon_img.height) // 2
            banner.paste(icon_img, (icon_x, icon_y), icon_img)
    else:
        # No icon available, draw stylish text card
        display_title = app_label or "TV App"
        draw.text((width // 4, height // 2 - 10), display_title, fill=(255, 255, 255, 255))

    banner.save(target_banner, "PNG")
    return target_banner
