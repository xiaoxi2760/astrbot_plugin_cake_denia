"""主题加载与解析（预设 + 用户自定义）。

- 预设主题：resources/themes/{preset}.json（white-1 / white-2 / black-1 / black-2）
- 用户自定义：resources/theme.json（custom 或未知 preset 时读取）
- 两个渲染器（PIL / HTML）共用此模块加载主题。
"""
import json
import os

_RESOURCES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
_THEMES_DIR = os.path.join(_RESOURCES_DIR, 'themes')

# 预设主题 ID 列表（与 _conf_schema.json 的 options 保持一致）
THEME_PRESETS = ['white-1', 'white-2', 'black-1', 'black-2']


def parse_color(value, default):
    """解析主题中的颜色：#rgb/#rrggbb/rgb()/rgba()，非法时返回默认。"""
    if not isinstance(value, str):
        return default
    v = value.strip()
    if v.startswith('#'):
        h = v.lstrip('#')
        if len(h) == 3:
            h = ''.join(c * 2 for c in h)
        if len(h) == 6:
            try:
                return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            except ValueError:
                return default
    if v.startswith('rgba('):
        try:
            parts = [p.strip() for p in v[5:-1].split(',')]
            return tuple(int(float(p)) for p in parts[:4])
        except (ValueError, IndexError):
            return default
    if v.startswith('rgb('):
        try:
            parts = [p.strip() for p in v[4:-1].split(',')]
            return tuple(int(p) for p in parts[:3])
        except (ValueError, IndexError):
            return default
    return default


def _load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def load_theme(theme_preset) -> dict:
    """按预设加载主题 dict；custom 或未知值读 resources/theme.json。"""
    if theme_preset in THEME_PRESETS:
        data = _load_json(os.path.join(_THEMES_DIR, f'{theme_preset}.json'))
        if data:
            return data
    # custom / 未知 preset / 预设缺失 → 用户自定义 theme.json
    return _load_json(os.path.join(_RESOURCES_DIR, 'theme.json'))
