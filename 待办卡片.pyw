# -*- coding: utf-8 -*-
"""todo —— 桌面待办小卡片（Windows 单文件版 / macOS 配色）

双击本文件即可运行（.pyw 关联 pythonw，不会出现黑色控制台窗口）。
只依赖 Python 标准库；如果装了 Pillow，界面会自动使用抗锯齿圆角。

功能
  · 待办：回车或 ＋ 新增，点圆圈切换完成，双击文字编辑（点别处即保存）
  · 右键任意一条：复制 / 编辑 / 标记 / 删除；行尾 ✕ 删除，误删可按 Ctrl+Z 撤销
  · 列表一页装得下时固定不滚动，超出才可滚动
  · 按住某一项上下拖动可调整顺序（拿起跟随指针、松手落位）
  · 底部状态栏统计，可一键清空已完成
  · 右上角：置顶开关、设置、关闭
  · 设置：自定义背景色 / 按钮色（取色器 + 预设色，即时生效），窗口不透明度滑块，开关开机自启
  · 无边框卡片，拖动标题栏移动，拖边框/四角缩放，位置会记住
  · 数据实时保存

数据与日志：%APPDATA%\\TodoCard\\
自检：命令行运行  python 待办卡片.pyw --selftest
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import time
import traceback
import uuid
import tkinter as tk
from tkinter import colorchooser
from tkinter import font as tkfont

try:  # 开机自启写注册表（仅 Windows 需要）
    import winreg
except Exception:
    winreg = None

try:  # 有 Pillow 就用抗锯齿圆角，没有也能跑
    from PIL import Image, ImageDraw, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #

APP_NAME = "todo"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WIN_W, WIN_H = 362, 444
MIN_W, MIN_H = 300, 240
MIN_OPACITY = 40             # 最淡只能到 40%，再低就看不见了
GRIP = 5                     # 边缘缩放热区厚度
CORNER = 14                  # 四角缩放热区边长
FAMILY = "Microsoft YaHei UI"          # main() 里按可用字体修正
PLACEHOLDER = "写点要做的，回车添加"

MDL2 = "Segoe MDL2 Assets"             # Windows 自带图标字体
ICON_PIN = "\ue718"                    # Pin
ICON_CLOSE = "\ue8bb"                  # ChromeClose
ICON_GEAR = "\ue713"                   # Setting

# --------------------------------------------------------------------------- #
# 配色：用户只挑「背景色 + 按钮色」，其余深浅全部推导出来
# --------------------------------------------------------------------------- #

DEFAULT_THEME = {"bg": "#FFFFFF", "accent": "#3A3A3C"}

PRESET_BG = ["#FFFFFF", "#F7F4EF", "#F1F6F3", "#EDF1FA", "#2A2A2E", "#16181D"]
PRESET_ACCENT = ["#007AFF", "#5E5CE6", "#FF2D55", "#FF9500", "#34C759", "#3A3A3C"]


def _is_hex(s) -> bool:
    if not isinstance(s, str) or len(s) != 7 or not s.startswith("#"):
        return False
    return all(ch in "0123456789abcdefABCDEF" for ch in s[1:])


def _hex_rgb(h):
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _rgb_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(round(c)))) for c in rgb)


def mix(c1: str, c2: str, t: float) -> str:
    """按比例混合两色（t=0 全 c1，t=1 全 c2）。"""
    a, b = _hex_rgb(c1), _hex_rgb(c2)
    return _rgb_hex([a[i] + (b[i] - a[i]) * t for i in range(3)])


def luminance(h: str) -> float:
    """相对亮度：用来判断底色是深是浅。"""
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _hex_rgb(h)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def build_palette(bg_hex: str = "#FFFFFF", accent_hex: str = "#3A3A3C") -> dict:
    """把「背景色 + 按钮色」展开成整套界面配色；深色底自动换成浅色文字。"""
    bg_hex = bg_hex.lower() if _is_hex(bg_hex) else DEFAULT_THEME["bg"]
    accent_hex = (accent_hex.lower() if _is_hex(accent_hex)
                  else DEFAULT_THEME["accent"])
    dark = luminance(bg_hex) < 0.45
    if dark:
        panel = mix(bg_hex, "#FFFFFF", 0.08)
        line = mix(bg_hex, "#FFFFFF", 0.14)
        border = mix(bg_hex, "#FFFFFF", 0.22)
        text = "#F5F5F7"
        muted = mix(text, bg_hex, 0.38)
        faint = mix(text, bg_hex, 0.58)
        done = mix(text, bg_hex, 0.52)
        hover = mix(bg_hex, "#FFFFFF", 0.10)
        track = mix(bg_hex, "#FFFFFF", 0.18)
        soft_t = 0.30
        raised, shadow, raised_line = (mix(bg_hex, "#FFFFFF", 0.12),
                                       mix(bg_hex, "#000000", 0.45),
                                       mix(bg_hex, "#FFFFFF", 0.26))
    else:
        panel = mix(bg_hex, "#000000", 0.04)
        line = mix(bg_hex, "#000000", 0.07)
        border = mix(bg_hex, "#000000", 0.12)
        text = "#1D1D1F"
        muted = mix(text, bg_hex, 0.50)
        faint = mix(text, bg_hex, 0.74)
        done = mix(text, bg_hex, 0.64)
        hover = mix(bg_hex, "#000000", 0.05)
        track = mix(bg_hex, "#000000", 0.09)
        soft_t = 0.10
        raised, shadow, raised_line = "#FFFFFF", "#D9DCE4", "#C9CEDA"
    accent_soft = mix(bg_hex, accent_hex, soft_t)
    return {
        "bg": bg_hex, "panel": panel, "line": line, "border": border,
        "text": text, "muted": muted, "faint": faint, "done": done,
        "hover": hover, "track": track,
        "accent": accent_hex,
        "accent_dark": mix(accent_hex, "#000000", 0.20),
        "accent_soft": accent_soft,
        "accent_soft_dark": mix(accent_soft, accent_hex, 0.22),
        "on_accent": "#1D1D1F" if luminance(accent_hex) > 0.60 else "#FFFFFF",
        "raised": raised, "raise_line": raised_line, "shadow": shadow,
        "danger": "#FF3B30",                       # systemRed
        "danger_soft": mix(bg_hex, "#FF3B30", 0.14),
        "green": "#34C759",                        # systemGreen
    }


# 当前生效的配色（换肤时原地更新，所有绘制都实时读它）
C = build_palette(DEFAULT_THEME["bg"], DEFAULT_THEME["accent"])


def _init_data_dir() -> str:
    base = os.environ.get("APPDATA") or BASE_DIR
    path = os.path.join(base, "TodoCard")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        path = BASE_DIR
    return path


DATA_DIR = _init_data_dir()
STATE = {"data_path": os.path.join(DATA_DIR, "todo_data.json")}
LOG_FILE = os.path.join(DATA_DIR, "todo_card.log")
LOG_MAX = 256 * 1024          # 日志超过 256KB 就只保留尾部，避免无限增长


def _log(msg: str) -> None:
    """pythonw 没有控制台，出问题就写日志（带简单轮转）。"""
    try:
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > LOG_MAX:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-200:]
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("".join(tail))
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 圆角绘制
# --------------------------------------------------------------------------- #

_IMG_CACHE: dict = {}
IMG_CACHE_MAX = 1200          # 超量时逐出最旧的（别整体清空，可能清掉正在显示的图）


def _cache_put(key, photo):
    _IMG_CACHE[key] = photo
    while len(_IMG_CACHE) > IMG_CACHE_MAX:
        _IMG_CACHE.pop(next(iter(_IMG_CACHE)))


def round_image(w, h, r, fill, outline=None, width=1, scale=4):
    """生成抗锯齿圆角矩形（Pillow 缺失时返回 None）。"""
    if not HAS_PIL or w <= 0 or h <= 0:
        return None
    key = (w, h, r, fill, outline, width)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    try:
        img = Image.new("RGBA", (int(w * scale), int(h * scale)), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            [0, 0, int(w * scale) - 1, int(h * scale) - 1],
            radius=max(0, int(r * scale)), fill=fill,
            outline=outline, width=max(1, int(width * scale)) if outline else 0)
        img = img.resize((int(w), int(h)), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _cache_put(key, photo)
        return photo
    except Exception:
        return None


def draw_round_rect(cv, x1, y1, x2, y2, r, fill, tags=None):
    """Pillow 不可用时的圆角兜底（无抗锯齿）。"""
    tags = tags or ()
    for shape in (
            (lambda: cv.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline="", tags=tags)),
            (lambda: cv.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline="", tags=tags)),
            (lambda: cv.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=fill, outline="", tags=tags)),
            (lambda: cv.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=fill, outline="", tags=tags)),
            (lambda: cv.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=fill, outline="", tags=tags)),
            (lambda: cv.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=fill, outline="", tags=tags))):
        shape()


def paint_round(cv, w, h, x, y, r, fill, outline=None, width=1, tags=None):
    """在画布上画一个圆角块，优先用抗锯齿图片。"""
    img = round_image(w, h, r, fill, outline, width)
    if img is not None:
        cv.create_image(x, y, anchor="nw", image=img, tags=tags)
    else:
        draw_round_rect(cv, x, y, x + w - 1, y + h - 1, r, fill, tags=tags)


def circle_image(size, fill=None, outline=None, width=1, check=None, scale=6):
    """抗锯齿圆形（可带对勾），用于完成状态圆圈。Tk 的 create_oval 无抗锯齿。"""
    if not HAS_PIL or size <= 0:
        return None
    key = ("circ", size, fill, outline, width, check)
    if key in _IMG_CACHE:
        return _IMG_CACHE[key]
    try:
        s = int(size * scale)
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([0, 0, s - 1, s - 1], fill=fill, outline=outline,
                  width=max(1, int(round(width * scale))) if outline else 0)
        if check:                                  # 对勾随图一起超采样，整图清晰
            pts = [(5, 9.6), (8.1, 12.6), (13, 6.8)]
            lw = max(scale, int(round(0.13 * s)))
            d.line([(x * scale, y * scale) for x, y in pts],
                   fill=check, width=lw, joint="curve")
            for px, py in pts:                     # 端点补圆头
                rr = lw / 2
                d.ellipse([px * scale - rr, py * scale - rr,
                           px * scale + rr, py * scale + rr], fill=check)
        img = img.resize((int(size), int(size)), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        _cache_put(key, photo)
        return photo
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 圆角按钮
# --------------------------------------------------------------------------- #

class Pill(tk.Canvas):
    def __init__(self, master, text="", command=None, font=None, bg=None,
                 fill="#FFFFFF", hover_fill=None, fg=None, hover_fg=None,
                 pad_x=12, width=None, height=28, radius=None, tooltip=None):
        bg = bg or master.cget("bg")
        self._font = font or (FAMILY, 9)
        f = tkfont.Font(font=self._font)
        w = width if width is not None else max(24, f.measure(text) + pad_x * 2)
        super().__init__(master, width=w, height=height, bg=bg,
                         highlightthickness=0, bd=0,
                         cursor="hand2" if command else "arrow")
        self._text = text
        self._command = command
        self._tip = tooltip
        self._pw, self._ph = w, height          # 注意：不能用 _w，tkinter 内部占用了
        self._r = radius if radius is not None else height // 2
        fg = C["text"] if fg is None else fg    # 主题会变，默认值不能写死在签名里
        self._fill, self._hover_fill = fill, hover_fill or fill
        self._fg, self._hover_fg = fg, hover_fg or fg
        self._on = False
        self._draw()
        if command:
            self.bind("<Button-1>", self._click)
            self.bind("<Enter>", self._enter)
            self.bind("<Leave>", self._leave)
        if tooltip:
            self.bind("<Enter>", lambda e: self._show_tip(), add="+")
            self.bind("<Leave>", lambda e: self._hide_tip(), add="+")

    def _draw(self):
        self.delete("all")
        fill = self._hover_fill if self._on else self._fill
        fg = self._hover_fg if self._on else self._fg
        paint_round(self, self._pw, self._ph, 0, 0, self._r, fill)
        cid = self.create_text(self._pw / 2, self._ph / 2 + 0.5, text=self._text,
                               fill=fg, font=self._font, anchor="center")
        bb = self.bbox(cid)          # 全角「＋」等字形自带偏移，按实际包围盒再居中
        if bb:
            dx = self._pw / 2 - (bb[0] + bb[2]) / 2
            dy = self._ph / 2 + 0.5 - (bb[1] + bb[3]) / 2
            if abs(dx) > 0.3 or abs(dy) > 0.3:
                self.move(cid, dx, dy)

    def _click(self, _e=None):
        if self._command:
            self._command()

    def _enter(self, _e=None):
        self._on = True
        self._draw()

    def _leave(self, _e=None):
        self._on = False
        self._draw()

    def _show_tip(self):
        try:
            self._tipwin = tk.Toplevel(self)
            self._tipwin.overrideredirect(True)
            self._tipwin.attributes("-topmost", True)
            x = self.winfo_rootx() + self.winfo_width() // 2 - 24
            y = self.winfo_rooty() + self.winfo_height() + 6
            self._tipwin.geometry(f"+{x}+{y}")
            tk.Label(self._tipwin, text=self._tip, font=(FAMILY, 8),
                     bg="#3A3A3C", fg="#FFFFFF", padx=8, pady=2).pack()
        except Exception:
            pass

    def _hide_tip(self):
        try:
            self._tipwin.destroy()
        except Exception:
            pass

    def restyle(self, fill=None, hover_fill=None, fg=None, hover_fg=None):
        if fill is not None:
            self._fill = fill
        if hover_fill is not None:
            self._hover_fill = hover_fill
        if fg is not None:
            self._fg = fg
        if hover_fg is not None:
            self._hover_fg = hover_fg
        self._draw()


class Swatch(tk.Canvas):
    """设置面板里的圆形色块，点一下即采用该颜色。"""

    def __init__(self, master, color, size=22, selected=False, command=None,
                 bg=None):
        bg = bg or master.cget("bg")
        super().__init__(master, width=size, height=size, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._size = size
        self._color = color
        self._sel = bool(selected)
        self._command = command
        self._draw()
        if command:
            self.bind("<Button-1>", lambda e: self._command(self._color))

    def _draw(self):
        self.delete("all")
        s = self._size
        if self._sel:
            ring = circle_image(s, outline=C["accent"], width=2)
            inner = circle_image(s - 10, fill=self._color, outline=C["border"])
            if ring is not None and inner is not None:
                self.create_image(0, 0, anchor="nw", image=ring)
                self.create_image(5, 5, anchor="nw", image=inner)
                return
            self.create_oval(0.5, 0.5, s - 0.5, s - 0.5,
                             outline=C["accent"], width=2)
            self.create_oval(5, 5, s - 5, s - 5, fill=self._color,
                             outline=C["border"])
        else:
            img = circle_image(s - 4, fill=self._color, outline=C["border"])
            if img is not None:
                self.create_image(2, 2, anchor="nw", image=img)
            else:
                self.create_oval(2, 2, s - 2, s - 2, fill=self._color,
                                 outline=C["border"])


class Switch(tk.Canvas):
    """小开关（用于开机自启）。"""

    def __init__(self, master, value=False, command=None, bg=None,
                 width=46, height=26):
        bg = bg or master.cget("bg")
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._sw, self._sh = width, height
        self._value = bool(value)
        self._command = command
        self._draw()
        self.bind("<Button-1>", self._click)

    def _draw(self):
        self.delete("all")
        w, h = self._sw, self._sh
        paint_round(self, w, h, 0, 0, h // 2,
                    C["accent"] if self._value else C["track"],
                    None if self._value else C["border"], 1)
        d = h - 6
        x = (w - d - 3) if self._value else 3
        img = circle_image(d, fill="#FFFFFF")
        if img is not None:
            self.create_image(x, 3, anchor="nw", image=img)
        else:
            self.create_oval(x, 3, x + d, 3 + d, fill="#FFFFFF", outline="")

    def set(self, value):
        self._value = bool(value)
        self._draw()

    def _click(self, _e=None):
        self._value = not self._value
        self._draw()
        if self._command:
            self._command(self._value)


class Slider(tk.Canvas):
    """扁平滑块：拖动手柄或点轨道都能调，值域 [minimum, maximum]。"""

    def __init__(self, master, value=1.0, minimum=0.0, maximum=1.0,
                 command=None, bg=None, width=196, height=26):
        bg = bg or master.cget("bg")
        super().__init__(master, width=width, height=height, bg=bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._cw, self._ch = width, height     # 注意别用 _w（tkinter 内部占用了）
        self._min, self._max = float(minimum), float(maximum)
        self._value = min(max(float(value), self._min), self._max)
        self._command = command
        self._pad = 9
        self._dragging = False
        self._draw()
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", self._release)

    def value(self):
        return self._value

    def set(self, value, notify=False, done=False):
        self._value = min(max(float(value), self._min), self._max)
        self._draw()
        if notify and self._command:
            self._command(self._value, done)
        return self._value

    def _on_configure(self, event):
        if event.width != self._cw:
            self._cw = event.width
            self._draw()

    def _t(self):
        span = (self._max - self._min) or 1.0
        return (self._value - self._min) / span

    def _from_x(self, x):
        x0, x1 = self._pad, self._cw - self._pad
        t = (x - x0) / ((x1 - x0) or 1)
        return self._min + max(0.0, min(1.0, t)) * (self._max - self._min)

    def _draw(self):
        self.delete("all")
        w, h, pad = self._cw, self._ch, self._pad
        cy = h / 2
        x0, x1 = pad, w - pad
        kx = x0 + (x1 - x0) * self._t()
        paint_round(self, x1 - x0 + 6, 6, x0 - 3, cy - 3, 3, C["track"])
        if kx > x0 + 1:
            paint_round(self, kx - x0 + 6, 6, x0 - 3, cy - 3, 3, C["accent"])
        img = circle_image(18, fill="#FFFFFF", outline=C["border"], width=1)
        if img is not None:
            self.create_image(kx - 9, cy - 9, anchor="nw", image=img)
        else:
            self.create_oval(kx - 9, cy - 9, kx + 9, cy + 9, fill="#FFFFFF",
                             outline=C["border"], width=1)

    def _press(self, e):
        self._dragging = True
        self._move(e)

    def _move(self, e):
        if self._dragging:
            self.set(self._from_x(e.x), notify=True)

    def _release(self, _e=None):
        if self._dragging:
            self._dragging = False
            if self._command:
                self._command(self._value, True)


# --------------------------------------------------------------------------- #
# 数据
# --------------------------------------------------------------------------- #

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _clean_items(raw) -> list:
    items, seen = [], set()
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        iid = str(it.get("id") or "") or _uid()
        while iid in seen:                     # 手工编辑数据可能撞 id，撞了就重发
            iid = _uid()
        seen.add(iid)
        items.append({"id": iid, "text": str(it.get("text", "")),
                      "done": bool(it.get("done"))})
    return items


def _clean_theme(raw) -> dict:
    t = dict(DEFAULT_THEME)
    if isinstance(raw, dict):
        for k in ("bg", "accent"):
            if _is_hex(raw.get(k)):
                t[k] = str(raw[k]).lower()
    return t


def _clean_opacity(raw) -> int:
    try:
        return max(MIN_OPACITY, min(100, int(raw)))
    except Exception:
        return 100


def fresh_state() -> dict:
    return {"items": [{"id": _uid(), "done": False,
                       "text": "点圆圈标记完成 · 双击文字可编辑 · ✕ 删除"}],
            "pos": None, "size": None, "topmost": True,
            "theme": dict(DEFAULT_THEME), "opacity": 100}


def load_state() -> dict:
    path = STATE["data_path"]
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                theme = _clean_theme(data.get("theme"))
                opacity = _clean_opacity(data.get("opacity", 100))
                if "items" in data:
                    return {"items": _clean_items(data["items"]),
                            "pos": data.get("pos"),
                            "size": data.get("size"),
                            "topmost": data.get("topmost", True),
                            "theme": theme, "opacity": opacity}
                if data.get("cards"):            # 兼容早期「多卡片」格式
                    cards = data["cards"]
                    card = next((c for c in cards if c.get("id") == data.get("active")),
                                cards[0])
                    return {"items": _clean_items(card.get("items")),
                            "pos": data.get("pos"),
                            "size": data.get("size"),
                            "topmost": data.get("topmost", True),
                            "theme": theme, "opacity": opacity}
        except Exception:
            _log("读取数据失败\n" + traceback.format_exc())
    return fresh_state()


def save_state(data: dict) -> None:
    try:
        tmp = STATE["data_path"] + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE["data_path"])
    except Exception:
        _log("保存数据失败\n" + traceback.format_exc())


# --------------------------------------------------------------------------- #
# 主界面
# --------------------------------------------------------------------------- #

class TodoApp:

    def __init__(self, root: tk.Tk, silent: bool = False):
        self.root = root
        self.silent = silent
        self.data = load_state()
        self._theme = _clean_theme(self.data.get("theme"))
        self.data["theme"] = dict(self._theme)
        C.clear()
        C.update(build_palette(self._theme["bg"], self._theme["accent"]))
        self.settings_win = None
        self._drag_offset = None
        self._resize = None
        self._editing = False
        self._rows = {}
        self._row_ws = {}          # iid -> 行画布
        self._hover_iid = None     # 当前 hover 的行（由 Enter/Leave 事件维护）
        self._press = None         # 行内按下状态
        self._drag_id = None       # 正在拖动的行
        self._ghost = None         # 拖动状态（抓取高度等）
        self._slot = None          # 被拖行留下的灰色槽位
        self._float_cv = None      # 悬浮中的行画布（place 置顶跟随指针）
        self._edit_entry = None    # 当前编辑框及其提交函数（点别处即保存）
        self._edit_commit = None
        self._last_list_w = 0
        self._resize_after = None  # 缩放时的重建去抖
        self._render_depth = 0     # 防止重建过程中递归重建
        self._pre_toggle = None    # 上一次单击切换完成前的状态（供双击还原）
        self._last_deleted = None  # 最近一次删除，供 Ctrl+Z 撤销
        self._status_flash = None  # 状态栏临时提示

        root.title(APP_NAME)
        root.overrideredirect(True)
        root.configure(bg=C["border"])
        root.resizable(False, False)

        size = self._initial_size()
        pos = self._initial_pos(size)
        self._row_w = max(180, size[0] - 24)
        root.geometry(f"{int(size[0])}x{int(size[1])}+{int(pos[0])}+{int(pos[1])}")

        self._init_fonts()
        self._build()
        self._build_grips()
        self._apply_topmost(self.data.get("topmost", True))
        self._apply_opacity()
        root.update_idletasks()
        _round_corners(root)
        self.render_all()
        # 窗口映射后再重申一次置顶（映射前设置偶尔会被 Windows 忽略）
        root.after(80, lambda: self._apply_topmost(self.data.get("topmost", True)))

    def _init_fonts(self):
        self.f_title = tkfont.Font(family=FAMILY, size=12, weight="bold")
        self.f_item = tkfont.Font(family=FAMILY, size=10)
        self.f_item_done = tkfont.Font(family=FAMILY, size=10, overstrike=1)
        self.f_small = tkfont.Font(family=FAMILY, size=8)
        self.f_menu = tkfont.Font(family=FAMILY, size=9)
        self.f_check = tkfont.Font(family=FAMILY, size=8, weight="bold")
        self.f_icon, self.g_pin, self.g_close, self.g_gear = None, "置顶", "✕", "⚙"
        try:
            if MDL2 in set(tkfont.families(self.root)):
                self.f_icon = tkfont.Font(family=MDL2, size=10)
                self.g_pin, self.g_close, self.g_gear = (ICON_PIN, ICON_CLOSE,
                                                         ICON_GEAR)
        except Exception:
            pass

    def _initial_size(self):
        size = self.data.get("size")
        if isinstance(size, (list, tuple)) and len(size) == 2:
            try:
                w = max(MIN_W, min(2000, int(size[0])))
                h = max(MIN_H, min(2000, int(size[1])))
                return (w, h)
            except Exception:
                pass
        return (WIN_W, WIN_H)

    def _default_pos(self, size):
        return (max(0, self.root.winfo_screenwidth() - size[0] - 60), 90)

    def _initial_pos(self, size):
        """记忆的位置若已不在任何屏幕上（如拔掉外接显示器），退回默认位置。"""
        pos = self.data.get("pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            try:
                x, y = int(pos[0]), int(pos[1])
                if self._pos_visible(x, y, size):
                    return (x, y)
            except Exception:
                pass
        return self._default_pos(size)

    def _pos_visible(self, x, y, size) -> bool:
        """标题栏区域是否与虚拟桌面（所有显示器）有足够重叠。"""
        try:
            u = ctypes.windll.user32
            vx = u.GetSystemMetrics(76)        # SM_XVIRTUALSCREEN
            vy = u.GetSystemMetrics(77)        # SM_YVIRTUALSCREEN
            vw = u.GetSystemMetrics(78)        # SM_CXVIRTUALSCREEN
            vh = u.GetSystemMetrics(79)        # SM_CYVIRTUALSCREEN
        except Exception:
            vx, vy = 0, 0
            vw, vh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        if vw <= 0 or vh <= 0:
            return True
        return (x + size[0] > vx + 40 and x < vx + vw - 40
                and y + 40 > vy and y < vy + vh - 20)

    # ------------------------------------------------------------- 界面搭建 --
    def _build(self):
        self.root.unbind_all("<MouseWheel>")     # 换肤会整块重建，先清掉全局绑定
        self.root.unbind_all("<ButtonRelease-1>")
        self.root.unbind_all("<Button-1>")
        shell = tk.Frame(self.root, bg=C["bg"])
        shell.pack(fill="both", expand=True, padx=1, pady=1)

        # 标题栏
        head = tk.Frame(shell, bg=C["bg"], height=48)
        head.pack(fill="x")
        head.pack_propagate(False)
        icon_font = self.f_icon or (FAMILY, 8)
        self.close_btn = Pill(head, self.g_close, self.quit_app, font=icon_font,
                              fill=C["bg"], hover_fill=C["panel"], fg=C["text"],
                              hover_fg=C["text"], width=28, height=28, radius=8,
                              bg=C["bg"], tooltip="关闭")
        self.close_btn.pack(side="right", padx=(0, 10))
        self.pin_btn = Pill(head, self.g_pin, self.toggle_topmost, font=icon_font,
                            fill=C["bg"], hover_fill=C["panel"], fg=C["faint"],
                            hover_fg=C["accent"], width=28, height=28, radius=8,
                            bg=C["bg"], tooltip="置顶")
        self.pin_btn.pack(side="right", padx=(0, 2))
        self.gear_btn = Pill(head, self.g_gear, self.open_settings, font=icon_font,
                             fill=C["bg"], hover_fill=C["panel"], fg=C["muted"],
                             hover_fg=C["text"], width=28, height=28, radius=8,
                             bg=C["bg"], tooltip="设置")
        self.gear_btn.pack(side="right", padx=(0, 2))
        title = tk.Label(head, text=APP_NAME, font=self.f_title, bg=C["bg"], fg=C["text"])
        title.pack(side="left", padx=(16, 0))
        for w in (head, title):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)
            w.bind("<ButtonRelease-1>", self._drag_end)

        # 主体
        self.body = tk.Frame(shell, bg=C["bg"])

        # 状态栏（先 pack 到底部）
        bottom = tk.Frame(self.body, bg=C["bg"])
        bottom.pack(fill="x", side="bottom")
        tk.Frame(bottom, bg=C["line"], height=1).pack(fill="x")
        status = tk.Frame(bottom, bg=C["bg"], height=34)
        status.pack(fill="x")
        status.pack_propagate(False)
        self.status_label = tk.Label(status, text="", font=self.f_small,
                                     bg=C["bg"], fg=C["muted"])
        self.status_label.pack(side="left", padx=16)
        self.clear_btn = Pill(status, "清空已完成", self.clear_done, font=self.f_small,
                              fill=C["bg"], hover_fill=C["panel"], fg=C["muted"],
                              hover_fg=C["danger"], pad_x=10, height=24, bg=C["bg"])

        # 输入区
        inp = tk.Frame(self.body, bg=C["bg"])
        inp.pack(fill="x", padx=16, pady=(2, 8))
        Pill(inp, "＋", self.add_item, font=(FAMILY, 12), fill=C["accent"],
             hover_fill=C["accent_dark"], fg=C["on_accent"], width=36, height=36,
             radius=18, bg=C["bg"]).pack(side="right", padx=(10, 0))
        self.input_canvas = tk.Canvas(inp, height=36, bg=C["bg"],
                                      highlightthickness=0, bd=0)
        self.input_canvas.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(self.input_canvas, font=self.f_item, bg=C["panel"],
                              fg=C["muted"], relief="flat", bd=0,
                              insertbackground=C["accent"])
        self._entry_win = self.input_canvas.create_window(
            14, 18, anchor="w", window=self.entry,
            width=max(60, self.root.winfo_width() - 120), height=22)
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", self._entry_in)
        self.entry.bind("<FocusOut>", self._entry_out)
        self.entry.bind("<Return>", lambda e: self.add_item())
        self.input_canvas.bind("<Configure>", self._on_input_resize)

        # 列表
        area = tk.Frame(self.body, bg=C["bg"])
        self.canvas = tk.Canvas(area, bg=C["bg"], highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.list_inner = tk.Frame(self.canvas, bg=C["bg"])
        self._listwin = self.canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_list_resize)
        self.root.bind_all("<MouseWheel>", self._on_wheel)
        self.root.bind_all("<ButtonRelease-1>", self._global_release, add="+")
        self.root.bind_all("<Button-1>", self._edit_click_guard, add="+")
        self.root.bind("<Deactivate>", lambda e: self._edit_click_guard())
        for seq in ("<Control-z>", "<Control-Z>"):
            self.root.bind(seq, self.undo_delete)

        area.pack(fill="both", expand=True)
        self.body.pack(fill="both", expand=True)
        self.canvas.yview_moveto(0)

    # ------------------------------------------------------- 缩放热区（手柄）--
    def _build_grips(self):
        G, K = GRIP, CORNER
        specs = (
            # (方向, place 参数, 光标)
            ("n",  dict(x=K, y=1, relwidth=1, width=-2 * K, height=G, anchor="nw"), "size_ns"),
            ("s",  dict(x=K, rely=1, y=-1, relwidth=1, width=-2 * K, height=G, anchor="sw"), "size_ns"),
            ("w",  dict(x=1, y=K, relheight=1, height=-2 * K, width=G, anchor="nw"), "size_we"),
            ("e",  dict(relx=1, x=-1, y=K, relheight=1, height=-2 * K, width=G, anchor="ne"), "size_we"),
            ("nw", dict(x=1, y=1, width=K, height=K, anchor="nw"), "size_nw_se"),
            ("ne", dict(relx=1, x=-1, y=1, width=K, height=K, anchor="ne"), "size_ne_sw"),
            ("sw", dict(x=1, rely=1, y=-1, width=K, height=K, anchor="sw"), "size_ne_sw"),
            ("se", dict(relx=1, x=-1, rely=1, y=-1, width=K, height=K, anchor="se"), "size_nw_se"),
        )
        self._grips = []
        for direction, place_kw, cursor in specs:
            g = tk.Frame(self.root, bg=C["bg"], cursor=cursor,
                         highlightthickness=0, bd=0)
            g.place(**place_kw)
            g.bind("<Button-1>", lambda e, d=direction: self._resize_start(d, e))
            g.bind("<B1-Motion>", self._resize_move)
            g.bind("<ButtonRelease-1>", self._resize_end)
            self._grips.append(g)

    def _resize_start(self, direction, event):
        self._resize = {"dir": direction, "x": event.x_root, "y": event.y_root,
                        "w": self.root.winfo_width(), "h": self.root.winfo_height(),
                        "wx": self.root.winfo_x(), "wy": self.root.winfo_y()}
        return "break"

    def _resize_move(self, event):
        st = self._resize
        if not st:
            return "break"
        dx, dy = event.x_root - st["x"], event.y_root - st["y"]
        w, h, x, y = st["w"], st["h"], st["wx"], st["wy"]
        if "e" in st["dir"]:
            w = st["w"] + dx
        if "s" in st["dir"]:
            h = st["h"] + dy
        if "w" in st["dir"]:
            w = st["w"] - dx
            x = st["wx"] + dx
            if w < MIN_W:
                x, w = st["wx"] + (st["w"] - MIN_W), MIN_W
        if "n" in st["dir"]:
            h = st["h"] - dy
            y = st["wy"] + dy
            if h < MIN_H:
                y, h = st["wy"] + (st["h"] - MIN_H), MIN_H
        w, h = max(MIN_W, w), max(MIN_H, h)
        self.root.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
        return "break"

    def _resize_end(self, _e=None):
        if self._resize:
            self._resize = None
            self.data["pos"] = [self.root.winfo_x(), self.root.winfo_y()]
            self.data["size"] = [self.root.winfo_width(), self.root.winfo_height()]
            self.save()
        return "break"

    # ------------------------------------------------------------ 尺寸回调 --
    def _on_input_resize(self, e):
        self.input_canvas.delete("bg")
        paint_round(self.input_canvas, e.width, 36, 0, 0, 18, C["panel"], tags=("bg",))
        self.input_canvas.tag_lower("bg")
        self.input_canvas.itemconfigure(self._entry_win, width=max(60, e.width - 28))

    def _on_list_resize(self, e):
        self.canvas.itemconfigure(self._listwin, width=e.width)
        if abs(e.width - self._last_list_w) > 2:
            self._last_list_w = e.width
            self._row_w = max(180, e.width - 16)
            if self._resize_after is not None:     # 拖边框时每像素都重建会卡，去抖
                try:
                    self.root.after_cancel(self._resize_after)
                except Exception:
                    pass
            self._resize_after = self.root.after(120, self._flush_resize)

    def _flush_resize(self):
        self._resize_after = None
        if not self._drag_id:
            self.render_items()

    def _within_host(self, widget) -> bool:
        """控件是否属于主卡片（排除设置面板等其它 Toplevel）。"""
        w = widget
        while w is not None:
            if w is self.root:
                return True
            if isinstance(w, tk.Toplevel):
                return False
            w = getattr(w, "master", None)
        return False

    def _on_wheel(self, e):
        if not self._within_host(self.root.winfo_containing(e.x_root, e.y_root)):
            return
        if not self._list_overflows():        # 一页装得下就固定，不允许滑动
            return
        try:
            steps = int(-e.delta / 120)
            if steps == 0:                    # 高精度触控板 delta 可能是 ±1
                steps = -1 if e.delta > 0 else 1
            self.canvas.yview_scroll(steps, "units")
        except Exception:
            pass

    def _list_overflows(self):
        """列表内容是否超出一页（超出才允许滚动）。"""
        try:
            return self.list_inner.winfo_height() > self.canvas.winfo_height() + 2
        except Exception:
            return False

    # --------------------------------------------------------------- 拖动 --
    def _drag_start(self, e):
        self._drag_offset = (e.x_root - self.root.winfo_x(),
                             e.y_root - self.root.winfo_y())

    def _drag_move(self, e):
        if self._drag_offset:
            self.root.geometry(f"+{e.x_root - self._drag_offset[0]}"
                               f"+{e.y_root - self._drag_offset[1]}")

    def _drag_end(self, _e):
        self._drag_offset = None
        self.data["pos"] = [self.root.winfo_x(), self.root.winfo_y()]
        self.save()

    # ---------------------------------------------------------- 输入框提示 --
    def _entry_in(self, _e=None):
        if self.entry.get() == PLACEHOLDER:
            self.entry.delete(0, "end")
            self.entry.configure(fg=C["text"])

    def _entry_out(self, _e=None):
        if not self.entry.get().strip():
            self.entry.delete(0, "end")
            self.entry.insert(0, PLACEHOLDER)
            self.entry.configure(fg=C["muted"])

    def _entry_value(self):
        v = self.entry.get().strip()
        return "" if v == PLACEHOLDER else v

    # ------------------------------------------------------------ 数据操作 --
    def items(self) -> list:
        return self.data["items"]

    def save(self):
        save_state(self.data)

    def add_item(self, text=None):
        if text is None:
            text = self._entry_value()
        text = (text or "").strip()
        if not text:
            self.entry.focus_set()
            return
        self.items().append({"id": _uid(), "text": text, "done": False})
        self.save()
        if text == self._entry_value():
            self.entry.delete(0, "end")
        self.entry.focus_set()
        self.render_items()
        self.canvas.yview_moveto(1.0)

    def toggle_item(self, iid):
        for it in self.items():
            if it["id"] == iid:
                it["done"] = not it["done"]
                break
        self.save()
        row = self._rows.get(iid)
        if row:
            row()
        self.render_status()

    def delete_item(self, iid):
        idx = next((i for i, it in enumerate(self.items()) if it["id"] == iid), None)
        if idx is None:
            return
        it = self.items().pop(idx)
        self._last_deleted = [(idx, it)]      # 记住原位置，撤销时插回原处
        self.save()
        self.render_items()
        self._flash_status("已删除 · Ctrl+Z 撤销")

    def clear_done(self):
        removed = [(i, it) for i, it in enumerate(self.items()) if it["done"]]
        if not removed:
            return
        for i, _it in reversed(removed):
            self.items().pop(i)
        self._last_deleted = removed
        self.save()
        self.render_items()
        self._flash_status("已清空 %d 项 · Ctrl+Z 撤销" % len(removed))

    def undo_delete(self, _e=None):
        """Ctrl+Z：恢复最近一次删除 / 清空（含原始顺序）。"""
        entries = self._last_deleted
        if not entries:
            self._flash_status("没有可撤销的操作")
            return "break"
        self._last_deleted = None
        for idx, it in sorted(entries, key=lambda x: x[0]):
            self.items().insert(max(0, min(idx, len(self.items()))), it)
        self.save()
        self.render_items()
        self._flash_status("已恢复 %d 项" % len(entries))
        return "break"

    def _flash_status(self, text, ms=2600):
        """状态栏临时提示，到点自动恢复统计文案。"""
        if self._status_flash is not None:
            try:
                self.root.after_cancel(self._status_flash)
            except Exception:
                pass
        self._status_flash = self.root.after(ms, self.render_status)
        self.status_label.configure(text=text, fg=C["accent"])

    # --------------------------------------------------------------- 渲染 --
    def render_all(self):
        self.render_items()
        self._refresh_pin()

    def render_items(self):
        """整表重建：防重入 + 先提交正在编辑的内容（重建会销毁编辑框）。"""
        if self._render_depth:
            return
        self._render_depth = 1
        try:
            self._items_inner()
        finally:
            self._render_depth = 0

    def _commit_edit(self):
        """正在编辑就强制提交，避免重建把用户输入吃掉。"""
        commit = self._edit_commit
        if self._editing and commit:
            try:
                commit()
            except Exception:
                _log("提交编辑失败\n" + traceback.format_exc())
        self._editing = False
        self._edit_entry = None
        self._edit_commit = None

    def _items_inner(self):
        self._commit_edit()
        if self._slot is not None or self._float_cv is not None:
            try:                              # 行重建后悬浮/槽位一并清理
                if self._slot is not None:
                    self._slot.destroy()
            except Exception:
                pass
            try:
                if self._float_cv is not None:
                    self._float_cv.place_forget()
            except Exception:
                pass
            self._slot = None
            self._float_cv = None
            self._drag_id = None
        for w in self.list_inner.winfo_children():
            w.destroy()
        self._rows = {}
        self._row_ws = {}
        self._press = None
        self._hover_iid = None
        items = self.items()
        if not items:
            self._empty_state()
        else:
            for it in items:
                self._build_row(it)
        self.list_inner.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        if not self._list_overflows():
            self.canvas.yview_moveto(0)       # 装得下就回到顶部，固定不动
        self.render_status()

    def _empty_state(self):
        box = tk.Frame(self.list_inner, bg=C["bg"])
        box.pack(pady=40)
        tk.Label(box, text="✓", font=(FAMILY, 22, "bold"), bg=C["bg"],
                 fg=C["track"]).pack()
        tk.Label(box, text="还没有待办", font=self.f_item, bg=C["bg"],
                 fg=C["muted"]).pack(pady=(8, 2))
        tk.Label(box, text="在上面输入框写一条，回车即可", font=self.f_small,
                 bg=C["bg"], fg=C["faint"]).pack()

    def _row_height(self, text, font):
        wrap = max(80, self._row_w - 104)
        try:
            width = font.measure(text)
        except Exception:
            width = len(text) * 12
        lines = max(1, int(math.ceil(width / float(wrap))))
        return max(36, lines * 21 + 12)

    def _build_row(self, item):
        h = self._row_height(item["text"], self.f_item)
        cv = tk.Canvas(self.list_inner, width=self._row_w, height=h, bg=C["bg"],
                       highlightthickness=0, bd=0, cursor="hand2")
        cv.pack(pady=2)
        iid = item["id"]

        def redraw():
            if self._editing:
                return
            cv.delete("all")
            dragging = self._drag_id == iid
            inside = self._hover_iid == iid and not dragging
            w = self._row_w
            if dragging:                      # 悬浮卡样式（"拿起"效果）
                paint_round(cv, w - 8, h - 2, 5, 4, 12, C["shadow"])
                paint_round(cv, w - 8, h - 4, 1, 0, 12, C["raised"],
                            C["raise_line"], 1)
                ty = (h - 4) / 2 + 1
            elif inside:
                paint_round(cv, w - 4, h - 2, 2, 1, 10, C["hover"])
                ty = h / 2
            else:
                ty = h / 2
            if item["done"]:                  # 抗锯齿圆圈 + 整图对勾
                img = circle_image(18, fill=C["accent"], check=C["on_accent"])
                if img is not None:
                    cv.create_image(12, ty - 9, anchor="nw", image=img)
                else:
                    cv.create_oval(12, ty - 9, 30, ty + 9, fill=C["accent"],
                                   outline="")
                    cv.create_text(21, ty + 1, text="✓", fill=C["on_accent"],
                                   font=self.f_check)
            else:
                img = circle_image(18, outline=C["muted"], width=2)
                if img is not None:
                    cv.create_image(12, ty - 9, anchor="nw", image=img)
                else:
                    cv.create_oval(12.5, ty - 8.5, 29.5, ty + 8.5,
                                   outline=C["muted"], width=2)
            cv.create_text(40, ty, text=item["text"], anchor="w",
                           width=max(60, w - 104),
                           font=self.f_item_done if item["done"] else self.f_item,
                           fill=C["muted"] if dragging else
                           (C["done"] if item["done"] else C["text"]))
            if not dragging:                  # 悬浮时不画 ✕ 和分隔线
                cv.create_text(w - 20, ty, text="✕", font=self.f_small,
                               fill=C["text"] if inside else C["muted"], tags=("del",))
                items = self.items()          # 行分隔线（最后一行不画）
                if items and items[-1]["id"] != iid:
                    cv.create_line(40, h - 1, w - 36, h - 1, fill=C["line"])

        self._rows[iid] = redraw
        self._row_ws[iid] = cv
        redraw()

        cv.bind("<Enter>", lambda e: self._set_hover(iid))
        cv.bind("<Leave>", lambda e: self._clear_hover(iid))
        cv.bind("<Button-1>", lambda e: self._row_press(cv, iid, e))
        cv.bind("<B1-Motion>", lambda e: self._row_motion(cv, iid, e))
        cv.bind("<ButtonRelease-1>", lambda e: self._row_release(cv, iid, e))
        cv.bind("<Double-Button-1>", lambda e: self._start_edit(cv, item))
        cv.bind("<Button-3>", lambda e: self._item_menu(e, item))

    def _set_hover(self, iid):
        """hover 状态只信 Enter/Leave 事件，不做坐标反推。"""
        if self._drag_id or self._editing:
            return
        prev = self._hover_iid
        self._hover_iid = iid
        if prev != iid:
            for r in (prev, iid):
                row = self._rows.get(r)
                if row:
                    row()

    def _clear_hover(self, iid):
        if self._hover_iid == iid:
            self._hover_iid = None
            row = self._rows.get(iid)
            if row:
                row()

    # ------------------------------------------------------- 行的点击/拖动 --
    def _row_press(self, cv, iid, event):
        cur = cv.find_withtag("current")
        try:
            off = max(6, min(cv.winfo_height() - 6, event.y_root - cv.winfo_rooty()))
        except Exception:
            off = cv.winfo_height() // 2
        self._press = {"iid": iid, "y": event.y_root, "off": off,
                       "del": bool(cur and "del" in cv.gettags(cur[0])),
                       "dragging": False}

    def _row_motion(self, cv, iid, event):
        p = self._press
        if not p or p["iid"] != iid:
            return
        if not p["dragging"]:
            if abs(event.y_root - p["y"]) < 4:
                return
            p["dragging"] = True
            self._begin_drag(iid, cv)
        self._drag_update(event)

    def _begin_drag(self, iid, cv):
        self._drag_id = iid
        prev = self._hover_iid
        self._hover_iid = None
        for r in {prev, iid}:
            row = self._rows.get(r)
            if row:
                row()
        self._ghost = {"h": cv.winfo_height(),
                       "off": self._press["off"] if self._press else 18}
        try:
            cv.configure(cursor="fleur")
        except Exception:
            pass
        # 行本体变成悬浮卡（place 永远盖在其它行之上），原位置留灰色槽位
        self._slot = tk.Canvas(self.list_inner, width=self._row_w,
                               height=self._ghost["h"], bg=C["bg"],
                               highlightthickness=0, bd=0)
        self._slot.pack(before=cv, pady=2)
        self._slot.bind("<Configure>", lambda e: (
            self._slot.delete("all"),
            paint_round(self._slot, e.width - 4, e.height - 4, 2, 2, 10,
                        C["panel"])))
        self._slot.update_idletasks()
        self._float_cv = cv
        cv.pack_forget()
        self.list_inner.update_idletasks()   # 让后续几何判断拿到新坐标
        try:
            py = self._press["y"] - self.list_inner.winfo_rooty()
            cv.place(in_=self.list_inner, x=12,
                     y=int(py - self._ghost["off"]))
        except Exception:
            pass
        try:
            cv.tk.call("raise", cv._w)        # Canvas.lift 是 tag_raise，不能用
        except Exception:
            pass
        row = self._rows.get(iid)
        if row:
            row()

    def _drag_update(self, event):
        """把被拖动的行按指针位置插入到新的下标。"""
        if not self._drag_id:
            return
        if self._list_overflows():             # 只有一页装不下时才自动滚动
            try:
                top = self.canvas.winfo_rooty()
                if event.y_root < top + 24:
                    self.canvas.yview_scroll(-1, "units")
                elif event.y_root > top + self.canvas.winfo_height() - 24:
                    self.canvas.yview_scroll(1, "units")
            except Exception:
                pass
        order = [it["id"] for it in self.items()]
        others = [i for i in order if i != self._drag_id]
        py = event.y_root - self.list_inner.winfo_rooty()
        target = len(others)
        for k, oid in enumerate(others):
            w = self._row_ws.get(oid)
            if w is None:
                continue
            if py < w.winfo_y() + w.winfo_height() / 2.0:
                target = k
                break
        new_order = others[:target] + [self._drag_id] + others[target:]
        if new_order != order:
            self._apply_order(new_order)
        self._move_floating(event)

    def _move_floating(self, event):
        """悬浮的行跟随指针（坐标相对列表，向上也一路可见）。"""
        cv = self._float_cv
        if cv is None or self._ghost is None:
            return
        try:
            py = event.y_root - self.list_inner.winfo_rooty()
            cv.place_configure(x=12, y=int(py - self._ghost["off"]))
        except Exception:
            pass

    def _apply_order(self, order):
        """按新顺序重排：悬浮行不参与流式布局，灰色槽位顶替它。"""
        by_id = {it["id"]: it for it in self.items()}
        self.data["items"] = [by_id[i] for i in order]
        flow = []
        for i in order:
            if i == self._drag_id:
                if self._slot is not None:
                    flow.append(self._slot)
            else:
                w = self._row_ws.get(i)
                if w is not None:
                    flow.append(w)
        prev = None                           # 链式 after 重排，避免全量 pack_forget 造成闪烁
        for w in flow:
            try:
                w.pack_configure(pady=2)
                if prev is not None:
                    w.pack_configure(after=prev)
            except Exception:
                pass
            prev = w
        self.list_inner.update_idletasks()

    def _end_drag(self):
        self._drag_id = None
        self._ghost = None
        try:
            if self._slot is not None:
                self._slot.destroy()
        except Exception:
            pass
        self._slot = None
        cv = self._float_cv
        self._float_cv = None
        try:
            if cv is not None:
                cv.place_forget()
                cv.configure(cursor="hand2")
        except Exception:
            pass
        self.save()
        self.render_items()

    def _global_release(self, _e=None):
        """兜底：不管松手事件发生在哪，都不能把拖拽状态卡住。"""
        self._press = None
        if self._drag_id:
            self._end_drag()

    def _row_release(self, cv, iid, event):
        p = self._press
        self._press = None
        if self._editing:                     # 双击进入编辑后，松手不能算单击
            return
        if p and p["dragging"]:
            self._end_drag()
            return
        if p and p["del"]:
            if self._over_delete(cv, event):  # 按下 ✕ 却拖开再松手 = 取消删除
                self.delete_item(iid)
            return
        before = next((it["done"] for it in self.items() if it["id"] == iid), None)
        self.toggle_item(iid)
        self._pre_toggle = (iid, before, time.time())

    def _over_delete(self, cv, event) -> bool:
        """松手位置是否还在行尾的 ✕ 上。"""
        x = getattr(event, "x", None)
        if x is None:
            return True                       # 无坐标信息（自检）沿用原行为
        try:
            return x >= cv.winfo_width() - 36
        except Exception:
            return True

    def _edit_click_guard(self, event=None):
        """编辑期间点了编辑框以外的任何地方（含窗口失活），立即保存退出。"""
        if not self._editing:
            return
        # 双击的第二次按下会先开编辑、再落到这里，同一事件不能立刻关掉
        if time.time() - getattr(self, "_edit_started", 0) < 0.25:
            return
        if event is not None and event.widget is self._edit_entry:
            return                        # 点在编辑框内部（挪光标），不算离开
        if self._edit_commit:
            self._edit_commit()

    def _start_edit(self, cv, item):
        if self._editing or self._drag_id:    # 拖动中不允许进入编辑
            return
        # 双击的第一下已经切换过完成状态：按快照还原（比再 toggle 一次可靠，
        # 双击间隔较长时也不会误改状态），并让第二下的松手不再算点击
        self._press = None
        snap = self._pre_toggle
        if snap and snap[0] == item["id"] and time.time() - snap[2] < 1.0:
            self._pre_toggle = None
            if item["done"] != snap[1]:
                item["done"] = snap[1]
                self.save()
        self._editing = True
        self._edit_started = time.time()
        cv.delete("all")
        h = cv.winfo_height()
        cy = h / 2
        paint_round(cv, self._row_w - 4, h - 2, 2, 1, 10, C["panel"])
        entry = tk.Entry(cv, font=self.f_item, bg=C["panel"], fg=C["text"],
                         relief="flat", bd=0, insertbackground=C["accent"])
        cv.create_window(40, cy, anchor="w", window=entry,
                         width=max(60, self._row_w - 104), height=22)
        entry.insert(0, item["text"])
        entry.focus_set()
        entry.select_range(0, "end")
        state = {"done": False}

        def commit(_e=None):
            if state["done"]:
                return
            state["done"] = True
            self._editing = False
            self._edit_entry = None
            self._edit_commit = None
            text = entry.get().strip()
            if text and text != item["text"]:
                item["text"] = text
                self.save()
            self.render_items()

        def cancel(_e=None):
            if state["done"]:
                return
            state["done"] = True
            self._editing = False
            self._edit_entry = None
            self._edit_commit = None
            self.render_items()

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)
        self._edit_entry = entry
        self._edit_commit = commit

    def _item_menu(self, event, item):
        m = tk.Menu(self.root, tearoff=0, font=self.f_menu,
                    bg=C["bg"], fg=C["text"], activebackground=C["accent"],
                    activeforeground=C["on_accent"], relief="flat", bd=0)
        m.add_command(label="复制", command=lambda: self._copy_item(item))
        m.add_command(label="编辑", command=lambda: self._start_edit_by_item(item))
        m.add_command(label="标记为" + ("未完成" if item["done"] else "已完成"),
                      command=lambda: self.toggle_item(item["id"]))
        m.add_separator()
        m.add_command(label="删除", command=lambda: self.delete_item(item["id"]))
        _popup(m, event)

    def _copy_item(self, item):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(item["text"])
        except Exception:
            _log("复制失败\n" + traceback.format_exc())

    def _start_edit_by_item(self, item):
        cv = self._row_ws.get(item["id"])     # 按 id 直查；按控件顺序找会在拖动排序后错位
        if cv is not None:
            self._start_edit(cv, item)

    def render_status(self):
        if self._status_flash is not None:     # 统计文案刷新时，作废未到期的临时提示
            try:
                self.root.after_cancel(self._status_flash)
            except Exception:
                pass
            self._status_flash = None
        items = self.items()
        total = len(items)
        done = sum(1 for it in items if it["done"])
        if total == 0:
            text = "空空如也"
        elif done == total:
            text = f"全部完成 · 共 {total} 项 ✓"
        else:
            text = f"未完成 {total - done} · 已完成 {done}"
        all_done = bool(done) and done == total
        self.status_label.configure(text=text, fg=C["green"] if all_done else C["muted"])
        if done > 0 and not self.clear_btn.winfo_ismapped():
            self.clear_btn.pack(side="right", padx=8)
        elif done == 0:
            self.clear_btn.pack_forget()

    # --------------------------------------------------------------- 主题 --
    def _retheme(self, bg=None, accent=None, rebuild=True):
        """换肤：只认背景色 + 按钮色，其余深浅由 build_palette 推导。"""
        if _is_hex(bg):
            self._theme["bg"] = str(bg).lower()
        if _is_hex(accent):
            self._theme["accent"] = str(accent).lower()
        self.data["theme"] = dict(self._theme)
        C.clear()
        C.update(build_palette(self._theme["bg"], self._theme["accent"]))
        if rebuild:
            self._rebuild_ui()
        self.save()

    def _rebuild_ui(self):
        """颜色在创建时就写死了，换肤直接整块重建，最省事也最可靠。"""
        self._commit_edit()                   # 重建前先保存编辑中的文字
        for w in self.root.winfo_children():
            if isinstance(w, tk.Toplevel):        # 别把设置窗口一起销毁
                continue
            w.destroy()
        self._grips = []
        self._float_cv = None
        self._slot = None
        self._drag_id = None
        self._editing = False
        self.root.configure(bg=C["border"])
        self._row_w = max(180, self.root.winfo_width() - 24)
        self._last_list_w = 0
        self._build()
        self._build_grips()
        self._apply_topmost(self.data.get("topmost", True))
        self._apply_opacity()
        self.render_all()
        if self.settings_win is not None:         # 设置面板自己也要重新着色
            try:
                if self.settings_win.winfo_exists():
                    self.settings_win.after(1, self.settings_win.rebuild)
            except Exception:
                pass

    def open_settings(self):
        if self.settings_win is not None:
            try:
                if self.settings_win.winfo_exists():
                    self.settings_win.deiconify()
                    self.settings_win.lift()
                    self.settings_win.focus_force()
                    return
            except Exception:
                pass
        self.settings_win = SettingsWindow(self)

    # ----------------------------------------------------------- 不透明度 --
    def _apply_opacity(self, pct=None):
        """整窗透明度（Windows 的 -alpha）。40%–100%。"""
        pct = _clean_opacity(self.data.get("opacity", 100) if pct is None else pct)
        self.data["opacity"] = pct
        try:
            self.root.attributes("-alpha", pct / 100.0)
        except Exception:
            pass
        return pct

    def _opacity_changed(self, value, done=False):
        """滑块回调：拖动时实时预览，松手才写盘。"""
        self._apply_opacity(int(round(float(value) * 100)))
        if done:
            self.save()

    # ------------------------------------------------------------- 置顶 --
    def _apply_topmost(self, on):
        on = bool(on)
        self.data["topmost"] = on
        try:
            self.root.attributes("-topmost", on)
        except Exception:
            pass
        try:                        # Win32 兜底：Tk 的 -topmost 偶尔不生效
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            user32.SetWindowPos(hwnd, -1 if on else -2, 0, 0, 0, 0,
                                0x0001 | 0x0002 | 0x0010)   # NOSIZE|NOMOVE|NOACTIVATE
        except Exception:
            pass
        if on:
            try:
                self.root.lift()
            except Exception:
                pass

    def toggle_topmost(self):
        self._apply_topmost(not self.data.get("topmost", True))
        self.save()
        self._refresh_pin()

    def _refresh_pin(self):
        pinned = self.data.get("topmost", True)
        if pinned:
            self.pin_btn.restyle(fill=C["accent_soft"],
                                 hover_fill=C["accent_soft_dark"],
                                 fg=C["accent"], hover_fg=C["accent_dark"])
        else:
            self.pin_btn.restyle(fill=C["bg"], hover_fill=C["panel"],
                                 fg=C["faint"], hover_fg=C["muted"])
        self.pin_btn._tip = "取消置顶" if pinned else "置顶"

    def quit_app(self):
        self.data["pos"] = [self.root.winfo_x(), self.root.winfo_y()]
        self.data["size"] = [self.root.winfo_width(), self.root.winfo_height()]
        self.save()
        self.root.destroy()


class SettingsWindow(tk.Toplevel):
    """设置面板：背景色 / 按钮色 / 开机自启（改动即时生效）。"""

    W, H = 348, 542

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.overrideredirect(True)
        self.resizable(False, False)
        try:
            self.attributes("-topmost", bool(app.data.get("topmost", True)))
        except Exception:
            pass
        self._drag = None
        self._build()
        self._place()
        self.bind("<Escape>", lambda e: self.close())
        self.after(60, self._activate)

    def _activate(self):
        try:
            self.focus_force()
        except Exception:
            pass

    def _place(self):
        """贴着主卡片放：左边优先，放不下就放右边。"""
        r = self.app.root
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = r.winfo_x() - self.W - 12
        if x < 8:
            x = r.winfo_x() + r.winfo_width() + 12
        x = max(8, min(x, sw - self.W - 8))
        y = max(8, min(r.winfo_y(), sh - self.H - 48))
        self.geometry("%dx%d+%d+%d" % (self.W, self.H, int(x), int(y)))

    # ---------------------------------------------------------------- 界面 --
    def _build(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(bg=C["border"])
        shell = tk.Frame(self, bg=C["bg"])
        shell.pack(fill="both", expand=True, padx=1, pady=1)

        head = tk.Frame(shell, bg=C["bg"], height=44)
        head.pack(fill="x")
        head.pack_propagate(False)
        icon_font = self.app.f_icon or (FAMILY, 8)
        Pill(head, self.app.g_close, self.close, font=icon_font,
             fill=C["bg"], hover_fill=C["panel"], fg=C["text"],
             hover_fg=C["text"], width=26, height=26, radius=8,
             bg=C["bg"], tooltip="关闭").pack(side="right", padx=(0, 10))
        title = tk.Label(head, text="设置", font=self.app.f_title,
                         bg=C["bg"], fg=C["text"])
        title.pack(side="left", padx=(16, 0))
        for w in (head, title):
            w.bind("<Button-1>", self._drag_start)
            w.bind("<B1-Motion>", self._drag_move)

        # 底部（先占位，剩下的都给主体）
        foot = tk.Frame(shell, bg=C["bg"], height=52)
        foot.pack(fill="x", side="bottom")
        foot.pack_propagate(False)
        tk.Frame(shell, bg=C["line"], height=1).pack(fill="x", side="bottom")
        Pill(foot, "恢复默认配色", self.reset_theme, font=self.app.f_small,
             fill=C["panel"], hover_fill=C["hover"], fg=C["muted"],
             hover_fg=C["text"], pad_x=12, height=28, radius=8,
             bg=C["bg"]).pack(side="left", padx=16, pady=12)

        body = tk.Frame(shell, bg=C["bg"])
        body.pack(fill="both", expand=True)
        self._section(body, "背景色", self.app._theme["bg"], PRESET_BG, "bg")
        tk.Frame(body, bg=C["line"], height=1).pack(fill="x", padx=16, pady=(12, 0))
        self._section(body, "按钮色", self.app._theme["accent"],
                      PRESET_ACCENT, "accent")
        tk.Frame(body, bg=C["line"], height=1).pack(fill="x", padx=16, pady=(12, 0))
        self._opacity_row(body)
        tk.Frame(body, bg=C["line"], height=1).pack(fill="x", padx=16, pady=(14, 0))
        self._autostart_row(body)

    def _section(self, parent, title, current, presets, key):
        box = tk.Frame(parent, bg=C["bg"])
        box.pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(box, text=title, font=self.app.f_small, bg=C["bg"],
                 fg=C["muted"]).pack(anchor="w")
        row = tk.Frame(box, bg=C["bg"])
        row.pack(fill="x", pady=(6, 0))
        sw = tk.Canvas(row, width=26, height=26, bg=C["bg"],
                       highlightthickness=0, bd=0)
        sw.pack(side="left")
        paint_round(sw, 26, 26, 0, 0, 8, current, C["border"], 1)
        tk.Label(row, text=str(current).upper(), font=self.app.f_small,
                 bg=C["bg"], fg=C["text"]).pack(side="left", padx=8)
        Pill(row, "取色…", lambda k=key: self._pick(k), font=self.app.f_small,
             fill=C["panel"], hover_fill=C["hover"], fg=C["text"],
             hover_fg=C["text"], pad_x=10, height=26, radius=8,
             bg=C["bg"]).pack(side="right")
        picks = tk.Frame(box, bg=C["bg"])
        picks.pack(fill="x", pady=(10, 0))
        for col in presets:
            Swatch(picks, col, 22, col.lower() == str(current).lower(),
                   lambda c, k=key: self._set(k, c), bg=C["bg"]).pack(
                       side="left", padx=(0, 10))

    def _opacity_row(self, parent):
        box = tk.Frame(parent, bg=C["bg"])
        box.pack(fill="x", padx=16, pady=(14, 0))
        row = tk.Frame(box, bg=C["bg"])
        row.pack(fill="x")
        tk.Label(row, text="不透明度", font=self.app.f_item, bg=C["bg"],
                 fg=C["text"]).pack(side="left")
        self.op_label = tk.Label(row, text="", font=self.app.f_small,
                                 bg=C["bg"], fg=C["muted"])
        self.op_label.pack(side="right")
        self.opacity = Slider(box, value=self.app.data.get("opacity", 100) / 100.0,
                              minimum=MIN_OPACITY / 100.0, maximum=1.0,
                              command=self._opacity_moved, bg=C["bg"], height=26)
        self.opacity.pack(fill="x", pady=(8, 0))
        self._refresh_opacity_label()

    def _opacity_moved(self, value, done=False):
        self.app._opacity_changed(value, done)
        self._refresh_opacity_label()

    def _refresh_opacity_label(self):
        self.op_label.configure(text="%d%%" % int(self.app.data.get("opacity", 100)))

    def _autostart_row(self, parent):
        box = tk.Frame(parent, bg=C["bg"])
        box.pack(fill="x", padx=16, pady=(14, 0))
        row = tk.Frame(box, bg=C["bg"])
        row.pack(fill="x")
        tk.Label(row, text="开机自启动", font=self.app.f_item, bg=C["bg"],
                 fg=C["text"]).pack(side="left")
        self.auto_sw = Switch(row, value=autostart_enabled(),
                              command=self._toggle_auto, bg=C["bg"])
        self.auto_sw.pack(side="right")
        self.auto_hint = tk.Label(box, text="", font=self.app.f_small,
                                  bg=C["bg"], fg=C["muted"], anchor="w",
                                  justify="left", wraplength=self.W - 64)
        self.auto_hint.pack(fill="x", pady=(6, 0))
        self._refresh_auto_hint()

    # ---------------------------------------------------------------- 交互 --
    def _set(self, key, color):
        """即时换肤：背景色 / 按钮色。"""
        self.app._retheme(**{key: color})

    def _pick(self, key):
        try:
            _rgb, val = colorchooser.askcolor(color=self.app._theme[key],
                                              parent=self, title="选择颜色")
        except Exception:
            _log("取色器异常\n" + traceback.format_exc())
            return
        if val:
            self._set(key, str(val).lower())

    def reset_theme(self):
        self.app._retheme(bg=DEFAULT_THEME["bg"], accent=DEFAULT_THEME["accent"])

    def _toggle_auto(self, value):
        ok = set_autostart(value)
        real = autostart_enabled()
        self.auto_sw.set(real)
        self._refresh_auto_hint(real, ok)

    def _refresh_auto_hint(self, value=None, ok=True):
        if value is None:
            value = autostart_enabled()
        if not autostart_supported():
            text = "当前环境不支持（仅 Windows 可用）"
        elif not ok:
            text = "设置失败，可稍后重试；详情见日志 %s" % LOG_FILE
        elif value:
            text = "已开启：开机后自动打开这张卡片"
        else:
            text = "已关闭：开机不会自动启动"
        self.auto_hint.configure(text=text)

    def _drag_start(self, e):
        self._drag = (e.x_root - self.winfo_x(), e.y_root - self.winfo_y())

    def _drag_move(self, e):
        if self._drag:
            self.geometry("+%d+%d" % (e.x_root - self._drag[0],
                                      e.y_root - self._drag[1]))

    def rebuild(self):
        if self.winfo_exists():
            self._build()

    def close(self):
        try:
            self.app.settings_win = None
        except Exception:
            pass
        self.destroy()


def _popup(menu, event=None):
    try:
        if event is not None and hasattr(event, "x_root"):
            x, y = event.x_root, event.y_root
        else:
            x, y = 0, 0
        menu.tk_popup(x, y)
    finally:
        menu.grab_release()


# --------------------------------------------------------------------------- #
# Windows 细节
# --------------------------------------------------------------------------- #

def _round_corners(window):
    """Win11 圆角窗口（失败无影响）。"""
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4)
    except Exception:
        pass


def acquire_single_instance() -> bool:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.CreateMutexW(None, False, "WorkBuddyTodoCardMutex")
        if handle and ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            hwnd = ctypes.windll.user32.FindWindowW(None, APP_NAME)
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            return False
        globals()["_MUTEX"] = handle
    except Exception:
        _log("单实例检查异常\n" + traceback.format_exc())
    return True


def pick_family(root) -> str:
    try:
        fams = set(tkfont.families(root))
    except Exception:
        return FAMILY
    for f in ("Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "SimHei"):
        if f in fams:
            return f
    return FAMILY


# --------------------------------------------------------------------------- #
# 开机自启（HKCU\...\Run）
# --------------------------------------------------------------------------- #

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "TodoCard"


def _autostart_command() -> str:
    """用 pythonw 启动本脚本（无控制台窗口）。"""
    script = os.path.abspath(__file__)
    exe = sys.executable or ""
    if os.name == "nt" and exe.lower().endswith("python.exe"):
        cand = exe[: -len("python.exe")] + "pythonw.exe"   # 换成无窗口解释器
        if os.path.exists(cand):
            exe = cand
    if os.name == "nt" and exe:
        return '"%s" "%s"' % (exe, script)
    return '"%s"' % script


def autostart_supported() -> bool:
    return winreg is not None and os.name == "nt"


def autostart_enabled() -> bool:
    if not autostart_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _t = winreg.QueryValueEx(k, RUN_NAME)
            return bool(str(val).strip())
    except FileNotFoundError:
        return False
    except Exception:
        _log("读取开机自启失败\n" + traceback.format_exc())
        return False


def set_autostart(on: bool) -> bool:
    if not autostart_supported():
        return False
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            if on:
                winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ,
                                  _autostart_command())
            else:
                try:
                    winreg.DeleteValue(k, RUN_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        _log("设置开机自启失败\n" + traceback.format_exc())
        return False


# --------------------------------------------------------------------------- #
# 自检 / 入口
# --------------------------------------------------------------------------- #

def run_selftest(app):
    def step():
        try:
            app.data["items"] = []
            app.add_item("测试待办 A")
            assert app.items() and app.items()[-1]["text"] == "测试待办 A", "新增待办失败"
            iid = app.items()[-1]["id"]
            app.toggle_item(iid)
            assert app.items()[-1]["done"] is True, "切换完成失败"
            app.add_item("测试待办 B")
            app.add_item("测试待办 C")
            app.delete_item(app.items()[0]["id"])
            assert len(app.items()) == 2, "删除待办失败"
            app.clear_done()
            assert len(app.items()) == 2, "清空已完成失败"
            app.render_all()
            # 拖动排序：把第一项拖到第二项下面
            app.add_item("测试待办 D")
            app.root.update_idletasks()
            ids = [it["id"] for it in app.items()]
            li = app.list_inner.winfo_rooty()
            cv0, cv1 = app._row_ws[ids[0]], app._row_ws[ids[1]]
            y0 = li + cv0.winfo_y() + 5
            y1 = li + cv1.winfo_y() + cv1.winfo_height() - 1
            app._row_press(cv0, ids[0], _FakeEvent(y0, y0))
            app._row_motion(cv0, ids[0], _FakeEvent(y1, y1))
            app._row_release(cv0, ids[0], _FakeEvent(y1, y1))
            order = [it["text"] for it in app.items()]
            assert order == ["测试待办 C", "测试待办 B", "测试待办 D"], \
                "拖动排序失败: %r" % (order,)
            # 单击仍然能切换完成
            cv1b = app._row_ws[ids[1]]
            y2 = app.list_inner.winfo_rooty() + cv1b.winfo_y() + 5
            was = next(i for i in app.items() if i["id"] == ids[1])["done"]
            app._row_press(cv1b, ids[1], _FakeEvent(y2, y2))
            app._row_release(cv1b, ids[1], _FakeEvent(y2, y2))
            now = next(i for i in app.items() if i["id"] == ids[1])["done"]
            assert now != was, "单击切换完成失败"
            assert app._slot is None and app._float_cv is None, "拖动状态未清理"
            # 双击编辑：第二下松手不应再切换完成状态
            ids2 = [it["id"] for it in app.items()]
            it2 = next(i for i in app.items() if i["id"] == ids2[1])
            cv2 = app._row_ws[ids2[1]]
            y3 = app.list_inner.winfo_rooty() + cv2.winfo_y() + 5
            done_before = it2["done"]             # 双击之前的状态
            app._row_press(cv2, ids2[1], _FakeEvent(y3, y3))
            app._row_release(cv2, ids2[1], _FakeEvent(y3, y3))
            app._row_press(cv2, ids2[1], _FakeEvent(y3, y3))
            app._start_edit(cv2, it2)
            app._row_release(cv2, ids2[1], _FakeEvent(y3, y3))
            assert app._editing, "双击未进入编辑"
            assert it2["done"] == done_before, "双击编辑误改了完成状态"
            entries = [w for w in cv2.winfo_children() if isinstance(w, tk.Entry)]
            assert entries, "编辑框未创建"
            assert entries[0].bind("<FocusOut>") and entries[0].bind("<Return>"), \
                "编辑框未绑定失焦/回车保存"
            # 双击第二次按下的同一事件不能立刻触发"点别处保存"（v13 回归）
            fake_press2 = type("E", (), {"widget": cv2})()
            app._edit_click_guard(fake_press2)
            assert app._editing, "双击第二次按下误触发保存退出"
            # 改文字后点别处 → 立即保存退出
            entries[0].delete(0, "end")
            entries[0].insert(0, "编辑后文本")
            app._edit_started = time.time() - 1
            app._edit_click_guard(type("E", (), {"widget": None})())
            assert not app._editing, "点别处未退出编辑"
            assert it2["text"] == "编辑后文本", "点别处未保存文字"
            # 编辑中途该行被删除/重建，编辑状态必须被清理（否则行重绘被冻结）
            app.delete_item(ids2[1])
            assert not app._editing, "删除后编辑状态未清理"
            # Ctrl+Z：撤销删除并恢复原位置
            app.undo_delete()
            order_u = [it["text"] for it in app.items()]
            assert order_u == ["测试待办 C", "编辑后文本", "测试待办 D"], \
                "撤销删除未恢复原顺序: %r" % (order_u,)
            # 编辑中整表重建（缩放/换肤触发）不能吃掉已输入的文字
            tgt = app.items()[0]
            cv_edit = app._row_ws[tgt["id"]]
            app._start_edit(cv_edit, tgt)
            assert app._editing, "未能进入编辑"
            e_in = [w for w in cv_edit.winfo_children() if isinstance(w, tk.Entry)][0]
            e_in.delete(0, "end")
            e_in.insert(0, "重建前输入")
            app.render_items()
            assert tgt["text"] == "重建前输入", "重建时编辑内容丢失"
            assert not app._editing, "重建后未退出编辑态"
            # 双击按快照还原完成状态（间隔较长也不该多切一次）
            item_x = app.items()[-1]
            cvx = app._row_ws[item_x["id"]]
            item_x["done"] = True
            app._pre_toggle = (item_x["id"], False, time.time() - 0.8)
            app._start_edit(cvx, item_x)
            assert item_x["done"] is False, "双击未按快照还原完成状态"
            app._commit_edit()
            cvx = app._row_ws[item_x["id"]]    # commit 会整表重建，行控件要重新取
            item_x["done"] = True
            app._pre_toggle = (item_x["id"], False, time.time() - 5)   # 过期快照
            app._start_edit(cvx, item_x)
            assert item_x["done"] is True, "过期快照被误用"
            app._commit_edit()
            # ✕：按下后拖开再松手不能删；在 ✕ 上松手才删
            victim = app.items()[0]["id"]
            cvd = app._row_ws[victim]
            yd = app.list_inner.winfo_rooty() + cvd.winfo_y() + 5
            n0 = len(app.items())
            app._press = {"iid": victim, "y": yd, "off": 10, "del": True,
                          "dragging": False}
            app._row_release(cvd, victim, _FakeEvent(yd, yd, x=10))
            assert len(app.items()) == n0, "✕ 按下后拖开仍被删除"
            app._press = {"iid": victim, "y": yd, "off": 10, "del": True,
                          "dragging": False}
            app._row_release(cvd, victim, _FakeEvent(yd, yd, x=cvd.winfo_width() - 8))
            assert len(app.items()) == n0 - 1, "✕ 上松手未删除"
            app.undo_delete()
            assert len(app.items()) == n0, "撤销 ✕ 删除失败"
            # 右键「编辑」按 id 找行：拖动排序后也不能编辑错行
            tail_item = app.items()[-1]
            cv_tail = app._row_ws[tail_item["id"]]
            app._start_edit_by_item(tail_item)
            assert [w for w in cv_tail.winfo_children() if isinstance(w, tk.Entry)], \
                "右键编辑定位到了错误的行"
            app._commit_edit()
            # 窗口位置记忆：屏外位置要被纠正
            assert app._pos_visible(120, 120, (360, 440)), "正常位置被判为屏幕外"
            assert not app._pos_visible(-6000, -6000, (360, 440)), "屏外位置未纠正"
            # 图片缓存是逐出最旧的，不能整体清空（清空会让正在显示的图失效）
            probe = _IMG_CACHE.get(("circ", 18, C["accent"], None, 1, C["on_accent"]))
            for k in range(IMG_CACHE_MAX + 25):
                _cache_put(("probe", k), probe)
            assert len(_IMG_CACHE) <= IMG_CACHE_MAX, "图片缓存未设上限"
            assert ("circ", 18, C["accent"], None, 1, C["on_accent"]) not in _IMG_CACHE \
                or len(_IMG_CACHE) <= IMG_CACHE_MAX, "缓存逐出异常"
            _IMG_CACHE.clear()
            # ---- 换肤 / 设置面板 / 开机自启 ----
            assert build_palette("#FFFFFF")["text"] == "#1D1D1F", "浅色底文字色错误"
            assert build_palette("#1E1F22")["text"] == "#F5F5F7", "深色底文字色错误"
            assert build_palette("#FFFFFF", "#007AFF")["on_accent"] != \
                build_palette("#FFFFFF", "#FFD60A")["on_accent"], "按钮色明暗判断失效"
            app._retheme(bg="#1E1F22", accent="#FF9500")
            app.root.update_idletasks()
            assert C["bg"] == "#1e1f22" and C["accent"] == "#ff9500", "换肤未生效"
            assert app.data["theme"]["bg"] == "#1e1f22", "主题未写入数据"
            assert app._row_ws, "换肤后列表未重建"
            app._retheme(bg=DEFAULT_THEME["bg"], accent=DEFAULT_THEME["accent"])
            app.root.update_idletasks()
            assert C["bg"] == DEFAULT_THEME["bg"].lower(), "恢复默认配色失败"
            app.open_settings()
            app.root.update()
            assert app.settings_win is not None and app.settings_win.winfo_exists(), \
                "设置面板未打开"
            assert isinstance(app.settings_win.auto_sw, Switch), "自启开关未创建"
            prior_auto = autostart_enabled()
            set_autostart(False)
            app.settings_win.rebuild()
            sw = app.settings_win.auto_sw
            sw._click()
            assert autostart_enabled(), "开启开机自启失败"
            sw._click()
            assert not autostart_enabled(), "关闭开机自启失败"
            if prior_auto:
                set_autostart(True)
            cmd = _autostart_command()
            assert ".pyw" in cmd, "自启命令异常: %s" % cmd
            # 不透明度：滑块 ↔ 窗口 alpha ↔ 数据
            app._opacity_changed(0.7, True)
            assert app.data["opacity"] == 70, "不透明度未写入数据"
            assert abs(float(app.root.attributes("-alpha")) - 0.7) < 0.02, \
                "窗口透明度未生效"
            sl = app.settings_win.opacity
            sl.set(0.5, notify=True, done=True)
            assert app.data["opacity"] == 50, "滑块未联动透明度"
            sl.set(0.1, notify=True, done=True)          # 不能低于下限
            assert app.data["opacity"] == MIN_OPACITY, "不透明度下限失效"
            sl.set(1.0, notify=True, done=True)
            assert app.data["opacity"] == 100, "恢复不透明度失败"
            assert abs(float(app.root.attributes("-alpha")) - 1.0) < 0.02, \
                "恢复后窗口仍透明"
            app.settings_win.close()
            app.root.update_idletasks()
            assert app.settings_win is None, "设置面板未关闭"
            # 缩放：模拟拖右下角手柄
            app.root.update_idletasks()
            root = app.root
            start = {"x": root.winfo_x() + root.winfo_width(),
                     "y": root.winfo_y() + root.winfo_height()}
            app._resize_start("se", _FakeEvent(start["x"], start["y"]))
            app._resize_move(_FakeEvent(start["x"] + 60, start["y"] + 80))
            app._resize_end()
            root.update_idletasks()
            assert root.winfo_width() > WIN_W, "放大窗口失败"
            assert app.data.get("size") is not None, "缩放后未记录尺寸"
            # 再缩小回去并验证最小值约束
            sx, sy = root.winfo_x() + root.winfo_width(), root.winfo_y() + root.winfo_height()
            app._resize_start("se", _FakeEvent(sx, sy))
            app._resize_move(_FakeEvent(sx - 5000, sy - 5000))
            app._resize_end()
            root.update_idletasks()
            assert root.winfo_width() == MIN_W and root.winfo_height() == MIN_H, "最小值约束失败"
            app.data["topmost"] = True
            app.toggle_topmost()
            app.save()
            print("SELFTEST OK  PIL=%s  icon=%s  数据目录=%s"
                  % (HAS_PIL, bool(app.f_icon), DATA_DIR))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            print("SELFTEST FAILED:", exc)
        finally:
            app.root.destroy()

    app.root.after(220, step)
    app.root.mainloop()


class _FakeEvent:
    def __init__(self, x_root, y_root, x=None, y=None):
        self.x_root = x_root
        self.y_root = y_root
        self.x = x
        self.y = y


def main():
    global FAMILY
    silent = "--selftest" in sys.argv
    if silent:
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "todo_selftest.json")
        if os.path.exists(path):
            os.remove(path)
        STATE["data_path"] = path
    elif not acquire_single_instance():
        return

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    FAMILY = pick_family(root)
    root.report_callback_exception = lambda *a: _log(
        "回调异常\n" + "".join(traceback.format_exception(*a)))
    app = TodoApp(root, silent=silent)
    if silent:
        run_selftest(app)
    else:
        _log(f"启动成功 PIL={HAS_PIL}")
        if autostart_enabled():
            set_autostart(True)       # 脚本挪过位置就顺手修正自启命令
        root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log("启动失败\n" + traceback.format_exc())
        if sys.stderr is not None:
            raise
