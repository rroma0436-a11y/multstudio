"""Вікно вибору (фон, герой, предмет, емоція): вкладки-«чипи» зверху й сітка мініатюр."""
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.recycleview import RecycleView
from kivy.uix.scrollview import ScrollView

import theme

Builder.load_string("""
<ThumbCell>:
    orientation: 'vertical'
    padding: dp(5)
    spacing: dp(3)
    canvas.before:
        Color:
            rgba: (0.36, 0.27, 0.62, 1) if (self.state == 'down' or self.current) else (0.17, 0.13, 0.3, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(12)]
        Color:
            rgba: (0.72, 0.56, 1, 1) if self.current else (0, 0, 0, 0)
        Line:
            rounded_rectangle: (self.x, self.y, self.width, self.height, dp(12))
            width: dp(1.6)
    Image:
        source: root.src
        fit_mode: root.fit
        nocache: True
    Label:
        text: root.text
        size_hint_y: None
        height: dp(34)
        font_size: sp(13)
        color: 0.96, 0.95, 1, 1
        halign: 'center'
        valign: 'middle'
        text_size: self.width, None
        shorten: True
        max_lines: 2

<ThumbGrid>:
    viewclass: 'ThumbCell'
    bar_width: dp(5)
    RecycleGridLayout:
        cols: root.cols
        default_size: None, root.cell_h
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        spacing: dp(8)
        padding: dp(6)
""")


class ThumbCell(ButtonBehavior, BoxLayout):
    src = StringProperty("")
    text = StringProperty("")
    fit = StringProperty("contain")
    index = NumericProperty(0)
    current = BooleanProperty(False)
    grid = ObjectProperty(None, allownone=True)

    def on_release(self):
        if self.grid is not None:
            self.grid.picked(self.index)


class ThumbGrid(RecycleView):
    cols = NumericProperty(3)
    cell_h = NumericProperty(dp(150))
    min_cell = NumericProperty(dp(110))
    ratio = NumericProperty(1.0)       # висота картинки до ширини клітинки
    on_pick = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(width=self._cols, min_cell=self._cols, ratio=self._cols)

    def _cols(self, *_):
        self.cols = max(2, int(self.width / self.min_cell))
        cw = (self.width - dp(8) * (self.cols + 1)) / self.cols
        self.cell_h = cw * self.ratio + dp(44)

    def set_items(self, items, fit="contain", current=None):
        """items: [(мініатюра, підпис)]; current — індекс вибраного."""
        self.data = [{"src": s, "text": t, "index": i, "grid": self, "fit": fit, "current": i == current}
                     for i, (s, t) in enumerate(items)]
        self.scroll_y = 1

    def picked(self, index):
        if self.on_pick:
            self.on_pick(index)


class ChipRow(ScrollView):
    """Горизонтальний ряд вкладок-«чипів»."""

    def __init__(self, names, on_select, start=0, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(46))
        super().__init__(do_scroll_y=False, bar_width=0, **kw)
        self.row = BoxLayout(size_hint_x=None, spacing=dp(6), padding=[dp(2), dp(4)])
        self.row.bind(minimum_width=self.row.setter("width"))
        self.chips = []
        self.on_select = on_select
        for i, name in enumerate(names):
            c = theme.chip(name, selected=(i == start))
            c.bind(on_release=lambda b, i=i: self.select(i))
            self.row.add_widget(c)
            self.chips.append(c)
        self.add_widget(self.row)
        self.current = start

    def select(self, i, notify=True):
        self.current = i
        for k, c in enumerate(self.chips):
            theme.set_chip(c, k == i)
        if notify:
            self.on_select(i)


class Picker(ModalView):
    """tabs: [(назва вкладки, [(мініатюра, підпис, значення)])]; callback(значення)."""

    def __init__(self, title, tabs, callback, start_tab=0, current_value=None, ratio=1.0,
                 fit="contain", min_cell=dp(110), **kw):
        kw.setdefault("size_hint", (1, 1))
        super().__init__(**kw)
        self.background_color = (0, 0, 0, 0)
        self.overlay_color = (0, 0, 0, 0.6)
        self.tabs = tabs
        self.callback = callback
        self.current_value = current_value
        self.current = []
        self.fit = fit

        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=[dp(10), dp(10)])
        theme.paint(root, theme.BG)
        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        back = theme.button("←", theme.CARD, size_hint_x=None, width=dp(48), font_size=sp(22))
        back.bind(on_release=lambda *_: self.dismiss())
        top.add_widget(back)
        top.add_widget(theme.label(title, 19, True, halign="left", valign="middle", shorten=True))
        root.add_widget(top)
        if len(tabs) > 1:
            root.add_widget(ChipRow([n for n, _ in tabs], self.show_tab, start=start_tab))
        self.grid = ThumbGrid(ratio=ratio, min_cell=min_cell)
        self.grid.on_pick = self._picked
        root.add_widget(self.grid)
        self.add_widget(root)
        self.show_tab(start_tab)

    def show_tab(self, i):
        self.current = self.tabs[i][1]
        cur = next((k for k, it in enumerate(self.current) if it[2] == self.current_value), None)
        self.grid.set_items([(src, lab) for src, lab, _ in self.current], fit=self.fit, current=cur)

    def _picked(self, index):
        value = self.current[index][2]
        self.dismiss()
        self.callback(value)
