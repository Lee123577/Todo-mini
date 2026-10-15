# -*- coding: utf-8 -*-
"""todo —— 桌面待办小卡片（Windows 单文件版 / macOS 配色）

双击本文件即可运行（.pyw 关联 pythonw，不会出现黑色控制台窗口）。
只依赖 Python 标准库；如果装了 Pillow，界面会自动使用抗锯齿圆角。

功能
  · 待办：回车或 ＋ 新增，点圆圈切换完成，双击文字编辑（失焦保存），右键可复制/编辑/删除，✕ 删除
  · 列表一页装得下时固定不滚动，超出才可滚动
  · 按住某一项上下拖动可调整顺序（拿起跟随指针、松手落位）
  · 底部状态栏统计，可一键清空已完成
  · 右上角：置顶开关、关闭
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
from tkinter import font as tkfont

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
GRIP = 5                     # 边缘缩放热区厚度
CORNER = 14                  # 四角缩放热区边长
FAMILY = "Microsoft YaHei UI"          # main() 里按可用字体修正
PLACEHOLDER = "写点要做的，回车添加"

MDL2 = "Segoe MDL2 Assets"             # Windows 自带图标字体
ICON_PIN = "\ue718"                    # Pin
ICON_CLOSE = "\ue8bb"                  # ChromeClose

# macOS 系统色（Light 模式）
C = {
    "bg": "#FFFFFF",                   # systemBackground
    "panel": "#F2F2F7",                # secondarySystemBackground
    "line": "#EFEFF4",                 # separator
    "border": "#E3E3E8",               # 窗口描边
    "text": "#1D1D1F",                 # label
    "muted": "#8E8E93",                # secondaryLabel / systemGray
    "faint": "#C7C7CC",                # tertiaryLabel / systemGray3
    "accent": "#007AFF",               # systemBlue
    "accent_dark": "#0062CC",
    "accent_soft": "#E8F1FF",
    "danger": "#FF3B30",               # systemRed
    "danger_soft": "#FFEBEA",
    "green": "#34C759",                # systemGreen
    "hover": "#F2F2F7",
    "track": "#E9E9EF",
    "done": "#AEAEB2",                 # systemGray2
}


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


def _log(msg: str) -> None:
    """pythonw 没有控制台，出问题就写日志。"""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 圆角绘制
# --------------------------------------------------------------------------- #

_IMG_CACHE: dict = {}


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
        _IMG_CACHE[key] = photo
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


# --------------------------------------------------------------------------- #
# 圆角按钮
# --------------------------------------------------------------------------- #

class Pill(tk.Canvas):
    def __init__(self, master, text="", command=None, font=None, bg=None,
                 fill="#FFFFFF", hover_fill=None, fg=C["text"], hover_fg=None,
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
        self.create_text(self._pw / 2, self._ph / 2 + 0.5, text=self._text, fill=fg,
                         font=self._font, anchor="center")

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


# --------------------------------------------------------------------------- #
# 数据
# --------------------------------------------------------------------------- #

def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _clean_items(raw) -> list:
    items = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        items.append({"id": it.get("id") or _uid(),
                      "text": str(it.get("text", "")),
                      "done": bool(it.get("done"))})
    return items


def fresh_state() -> dict:
    return {"items": [{"id": _uid(), "done": False,
                       "text": "点圆圈标记完成 · 双击文字可编辑 · ✕ 删除"}],
            "pos": None, "size": None, "topmost": True}


def load_state() -> dict:
    path = STATE["data_path"]
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                if "items" in data:
                    return {"items": _clean_items(data["items"]),
                            "pos": data.get("pos"),
                            "size": data.get("size"),
                            "topmost": data.get("topmost", True)}
                if data.get("cards"):            # 兼容早期「多卡片」格式
                    cards = data["cards"]
                    card = next((c for c in cards if c.get("id") == data.get("active")),
                                cards[0])
                    return {"items": _clean_items(card.get("items")),
                            "pos": data.get("pos"),
                            "size": data.get("size"),
                            "topmost": data.get("topmost", True)}
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
        self._drag_offset = None
        self._resize = None
        self._editing = False
        self._rows = {}
        self._row_ws = {}          # iid -> 行画布
        self._hover_iid = None     # 当前 hover 的行（由 Enter/Leave 事件维护）
        self._press = None         # 行内按下状态
        self._drag_id = None       # 正在拖动的行
        self._ghost = None         # 拖动影子的元数据
        self._last_click = None    # 用于双击时抵消单击的切换
        self._last_list_w = 0

        root.title(APP_NAME)
        root.overrideredirect(True)
        root.configure(bg=C["border"])
        root.resizable(False, False)

        size = self._initial_size()
        pos = self.data.get("pos") or self._default_pos(size)
        self._row_w = max(180, size[0] - 24)
        root.geometry(f"{int(size[0])}x{int(size[1])}+{int(pos[0])}+{int(pos[1])}")

        self._init_fonts()
        self._build()
        self._build_grips()
        self._apply_topmost(self.data.get("topmost", True))
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
        self.f_icon, self.g_pin, self.g_close = None, "置顶", "✕"
        try:
            if MDL2 in set(tkfont.families(self.root)):
                self.f_icon = tkfont.Font(family=MDL2, size=10)
                self.g_pin, self.g_close = ICON_PIN, ICON_CLOSE
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

    # ------------------------------------------------------------- 界面搭建 --
    def _build(self):
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
             hover_fill=C["accent_dark"], fg="#FFFFFF", width=36, height=36,
             radius=18, bg=C["bg"]).pack(side="right", padx=(10, 0))
        self.input_canvas = tk.Canvas(inp, height=36, bg=C["bg"],
                                      highlightthickness=0, bd=0)
        self.input_canvas.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(self.input_canvas, font=self.f_item, bg=C["panel"],
                              fg=C["muted"], relief="flat", bd=0,
                              insertbackground=C["accent"])
        self._entry_win = self.input_canvas.create_window(
            14, 18, anchor="w", window=self.entry, width=max(60, WIN_W - 120), height=22)
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
            self.render_items()

    def _on_wheel(self, e):
        if self.root.winfo_containing(e.x_root, e.y_root) is None:
            return
        if not self._list_overflows():        # 一页装得下就固定，不允许滑动
            return
        try:
            self.canvas.yview_scroll(int(-e.delta / 120), "units")
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
        self.data["items"] = [it for it in self.items() if it["id"] != iid]
        self.save()
        self.render_items()

    def clear_done(self):
        self.data["items"] = [it for it in self.items() if not it["done"]]
        self.save()
        self.render_items()

    # --------------------------------------------------------------- 渲染 --
    def render_all(self):
        self.render_items()
        self._refresh_pin()

    def render_items(self):
        self._editing = False                 # 整表重建必然退出编辑态（兜底防冻结）
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
                       highlightthickness=0, bd=0)
        cv.pack(pady=2)
        iid = item["id"]

        def redraw():
            if self._editing:
                return
            cv.delete("all")
            dragging = self._drag_id == iid
            inside = self._hover_iid == iid and not dragging
            if dragging:                      # 原位置显示为"落点槽位"
                paint_round(cv, self._row_w - 4, h - 2, 2, 1, 10, C["panel"])
            elif inside:
                paint_round(cv, self._row_w - 4, h - 2, 2, 1, 10, C["hover"])
            cy = h / 2
            if item["done"]:
                cv.create_oval(12, cy - 9, 30, cy + 9, fill=C["accent"], outline="")
                cv.create_text(21, cy + 1, text="✓", fill="#FFFFFF", font=self.f_check)
            else:
                cv.create_oval(12.5, cy - 8.5, 29.5, cy + 8.5,
                               outline=C["faint"], width=1.5)
            cv.create_text(40, cy, text=item["text"], anchor="w",
                           width=max(60, self._row_w - 104),
                           font=self.f_item_done if item["done"] else self.f_item,
                           fill=C["faint"] if dragging else
                           (C["done"] if item["done"] else C["text"]),
                           tags=("t",))
            cv.create_text(self._row_w - 20, cy, text="✕", font=self.f_small,
                           fill=C["text"] if inside else C["muted"], tags=("del",))
            items = self.items()              # 行分隔线（最后一行不画）
            if items and items[-1]["id"] != iid:
                cv.create_line(40, h - 1, self._row_w - 36, h - 1, fill=C["line"])

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
        self._ghost = {"h": cv.winfo_height(), "off": self._press["off"] if self._press else 18}
        try:
            cv.configure(cursor="fleur")
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
        self._draw_ghost(event)

    def _draw_ghost(self, event):
        """跟随指针的"拿起"影子，松手后消失。"""
        cv = self.canvas
        item = next((it for it in self.items() if it["id"] == self._drag_id), None)
        if item is None or not self._ghost:
            return
        cv.delete("ghost")
        w = max(120, cv.winfo_width() - 26)
        h = self._ghost["h"]
        cy = cv.canvasy(event.y_root - cv.winfo_rooty()) - self._ghost["off"]
        x = 12
        paint_round(cv, w + 4, h, x + 3, cy + 4, 12, "#E4E4EC", tags=("ghost",))
        paint_round(cv, w + 4, h, x, cy, 12, "#FFFFFF", "#D6DBE6", 1, tags=("ghost",))
        tcy = cy + h / 2
        if item["done"]:
            cv.create_oval(x + 12, tcy - 9, x + 30, tcy + 9,
                           fill=C["accent"], outline="", tags=("ghost",))
            cv.create_text(x + 21, tcy + 1, text="✓", fill="#FFFFFF",
                           font=self.f_check, tags=("ghost",))
        else:
            cv.create_oval(x + 12.5, tcy - 8.5, x + 29.5, tcy + 8.5,
                           outline=C["faint"], width=1.5, tags=("ghost",))
        cv.create_text(x + 40, tcy, text=item["text"], anchor="w",
                       width=max(60, w - 96),
                       font=self.f_item_done if item["done"] else self.f_item,
                       fill=C["done"] if item["done"] else C["text"],
                       tags=("ghost",))

    def _apply_order(self, order):
        """按新顺序重排（不销毁行控件，保证拖动过程不中断）。"""
        by_id = {it["id"]: it for it in self.items()}
        self.data["items"] = [by_id[i] for i in order]
        ws = [self._row_ws[i] for i in order if i in self._row_ws]
        for i in range(len(ws) - 1):
            ws[i + 1].pack_configure(after=ws[i])
        self.list_inner.update_idletasks()

    def _end_drag(self):
        cv = self._row_ws.get(self._drag_id)
        self._drag_id = None
        self._ghost = None
        try:
            self.canvas.delete("ghost")
        except Exception:
            pass
        try:
            if cv is not None:
                cv.configure(cursor="")
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
            self.delete_item(iid)
            return
        self.toggle_item(iid)
        self._last_click = (iid, time.time())

    def _start_edit(self, cv, item):
        if self._editing:
            return
        # 双击的第一下会先切换完成状态：这里还原，并让第二下的松手不再算点击
        self._press = None
        last = self._last_click
        if last and last[0] == item["id"] and time.time() - last[1] < 0.6:
            self._last_click = None
            self.toggle_item(item["id"])
        self._editing = True
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
            self.render_items()

        entry.bind("<Return>", commit)
        entry.bind("<Escape>", cancel)
        entry.bind("<FocusOut>", commit)

    def _item_menu(self, event, item):
        m = tk.Menu(self.root, tearoff=0, font=self.f_menu,
                    bg="#FFFFFF", fg=C["text"], activebackground=C["accent"],
                    activeforeground="#FFFFFF", relief="flat", bd=0)
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
        rows = self.list_inner.winfo_children()
        idx = [i for i, it in enumerate(self.items()) if it["id"] == item["id"]]
        if idx and idx[0] < len(rows):
            self._start_edit(rows[idx[0]], item)

    def render_status(self):
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
            self.pin_btn.restyle(fill=C["accent_soft"], hover_fill="#D8E7FF",
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
            assert not app.canvas.find_withtag("ghost"), "拖动影子未清理"
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
            # 编辑中途该行被删除/重建，编辑状态必须被清理（否则行重绘被冻结）
            app.delete_item(ids2[1])
            assert not app._editing, "删除后编辑状态未清理"
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
    def __init__(self, x_root, y_root):
        self.x_root = x_root
        self.y_root = y_root


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
        root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log("启动失败\n" + traceback.format_exc())
        if sys.stderr is not None:
            raise
