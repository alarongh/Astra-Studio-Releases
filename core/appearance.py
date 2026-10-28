"""Validated appearance settings and contrast helpers, independent of Qt."""
from __future__ import annotations

import re
from collections.abc import Mapping


DEFAULT_BACKGROUND_COLOR = "#1E1E1E"
SOLID_COLOR_PALETTE = {
    "Графит": DEFAULT_BACKGROUND_COLOR,
    "Ночной синий": "#17233A",
    "Сланец": "#293241",
    "Лесной": "#17312B",
    "Баклажан": "#2D1F35",
    "Светлый": "#F4F6F8",
}
COLOR_ROLES = {
    "background": "Фон рабочей области",
    "panels": "Плашки и боковые панели",
    "editor": "Редактор",
    "console": "Консоль",
    "project": "Дерево проекта",
    "settings": "Настройки",
}
LEGACY_WALLPAPER_COLORS = {
    "Astra Neon Core": "#17233A",
    "Astra Deep Space": "#111827",
    "Astra Classic": "#17233A",
    "Astra Eclipse": "#1E1E1E",
    "Astra Crown Night": "#211B2D",
    "Astra Sakura Dusk": "#352535",
    "Astra Cyber Ritual": "#15182D",
    "Astra Crimson Prayer": "#301C29",
    "Angel 404": "#23182F",
}
_HEX = re.compile(r"^#?(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def normalize_hex_color(value: object) -> str:
    """Accept only solid RGB HEX colors; never permit arbitrary stylesheet text."""
    if not isinstance(value, str) or not _HEX.fullmatch(value.strip()):
        raise ValueError("Введите HEX-цвет: #RGB или #RRGGBB")
    digits = value.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.upper()


def load_appearance_colors(settings: Mapping[str, object]) -> tuple[str, dict[str, str]]:
    """Migrate built-in photos to colors without touching any user image file."""
    fallback = LEGACY_WALLPAPER_COLORS.get(str(settings.get("preset_wallpaper", "")), DEFAULT_BACKGROUND_COLOR)
    try:
        background = normalize_hex_color(settings.get("background_color", fallback))
    except ValueError:
        background = fallback
    overrides: dict[str, str] = {}
    raw = settings.get("panel_colors")
    if isinstance(raw, Mapping):
        for role, value in raw.items():
            if role not in COLOR_ROLES or role == "background":
                continue
            try:
                overrides[role] = normalize_hex_color(value)
            except ValueError:
                continue
    return background, overrides


def restore_splitter_sizes(value: object, count: int) -> list[int]:
    """Reject malformed layout settings before passing them to Qt/C++ ints."""
    if not isinstance(value, list) or len(value) != count:
        return []
    if any(type(size) is not int or not 0 <= size <= 1_000_000 for size in value) or not any(value):
        return []
    return list(value)


def _rgb(value: str) -> tuple[int, int, int]:
    color = normalize_hex_color(value)[1:]
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(value: str) -> float:
    channels = [v / 255 for v in _rgb(value)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast_ratio(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def readable_text_color(background: str) -> str:
    return max(("#FFFFFF", "#000000"), key=lambda c: contrast_ratio(c, background))


def blend_colors(first: str, second: str, amount: float) -> str:
    amount = max(0.0, min(1.0, amount))
    values = [round(a * (1 - amount) + b * amount) for a, b in zip(_rgb(first), _rgb(second))]
    return "#" + "".join(f"{v:02X}" for v in values)


def ensure_contrast(foreground: str, background: str, minimum: float = 4.5) -> str:
    """Keep the theme hue where possible, moving toward readable black/white."""
    foreground = normalize_hex_color(foreground)
    if contrast_ratio(foreground, background) >= minimum:
        return foreground
    target = readable_text_color(background)
    for step in range(1, 101):
        candidate = blend_colors(foreground, target, step / 100)
        if contrast_ratio(candidate, background) >= minimum:
            return candidate
    return target


def editor_theme_with_background(theme: Mapping[str, str], background: str) -> dict[str, str]:
    result = dict(theme)
    result["editor"] = normalize_hex_color(background)
    for key in ("text", "muted", "keyword", "string", "comment", "number", "function", "class"):
        result[key] = ensure_contrast(result[key], result["editor"])
    result["line"] = blend_colors(result["editor"], result["text"], 0.07)
    result["selection"] = blend_colors(result["editor"], result["text"], 0.18)
    # The gutter and completion popup follow the editor surface.
    result["panel"] = result["editor"]
    result["panel2"] = result["editor"]
    return result
