"""Вікно вибору (фон, герой, предмет, емоція): вкладки зверху й сітка мініатюр."""
from kivy.lang import Builder
from kivy.metrics import dp, sp
from kivy.properties import ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.recycleview import RecycleView
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton

import theme

Builder.load_string("""
<ThumbCell>:
    orientation: 'vertical'
    padding: dp(4)
    spacing: dp(2)
    canvas.before:
        Color:
            rgba: (1, 0.86, 0.7, 1) if self.state == 'down' else (1, 1, 1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [dp(10)]
    Image:
        source: root.src
        fit_mode: 'contain'
        nocache: True
    Label:
        text: root.text
        size_hint_y: None
        height: dp(34)
        font_size: sp(13)
        color: 0.18, 0.16, 0.15, 1
        halign: 'center'
        valign: 'middle'
        text_size: self.width, None
        shorten: True
        max_lines: 2

<ThumbGrid>:
    viewclass: 'ThumbCell'
    bar_width: dp(6)
    RecycleGridLayout:
        cols: root.cols
        default_size: None, root.cell_h
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        spacing: dp(8)
        padding: dp(8)
""")


class ThumbCell(ButtonBehavior, BoxLayout):
    src = StringProperty("")
    text = StringProperty("")
    index = NumericProperty(0)
    grid = ObjectProperty(None, allownone=True)

    def on_release(self):
        if self.grid is not None:
            self.grid.picked(self.index)


class ThumbGrid(RecycleView):
    cols = NumericProperty(4)
    cell_h = NumericProperty(dp(150))
    on_pick = ObjectProperty(None, allownone=True)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.bind(width=self._cols)

    def _cols(self, *_):
        target = dp(130)
        self.cols = max(3, int(self.width / target))
        cw = (self.width - dp(8) * (self.cols + 1)) / self.cols
        self.cell_h = cw + dp(40)

    def set_items(self, items):
        """items: [(мініатюра, підпис)]"""
        self.data = [{"src": s, "text": t, "index": i, "grid": self} for i, (s, t) in enumerate(items)]
        self.scroll_y = 1

    def picked(self, index):
        if self.on_pick:
            self.on_pick(index)


class Picker(ModalView):
    """tabs: [(назва вкладки, [(мініатюра, підпис, значення)])]; callback(значення)."""

    def __init__(self, title, tabs, callback, start_tab=0, **kw):
        kw.setdefault("size_hint", (0.96, 0.94))
        kw.setdefault("auto_dismiss", True)
        super().__init__(**kw)
        self.background_color = (0, 0, 0, 0.55)
        self.tabs = tabs
        self.callback = callback
        self.current = []

        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        with root.canvas.before:
            from kivy.graphics import Color, RoundedRectangle
            Color(*theme.BG)
            self._bg = RoundedRectangle(radius=[dp(16)])
        root.bind(pos=lambda w, v: setattr(self._bg, "pos", v), size=lambda w, v: setattr(self._bg, "size", v))

        top = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        top.add_widget(Label(text=title, font_size=sp(20), bold=True, color=theme.TEXT,
                             halign="left", valign="middle", text_size=(None, None)))
        close = theme.button("Закрити", size_hint_x=None, width=dp(120), bg=theme.GREY)
        close.bind(on_release=lambda *_: self.dismiss())
        top.add_widget(close)
        root.add_widget(top)

        if len(tabs) > 1:
            sv = ScrollView(size_hint_y=None, height=dp(48), do_scroll_y=False, bar_width=0)
            row = BoxLayout(size_hint_x=None, spacing=dp(6))
            row.bind(minimum_width=row.setter("width"))
            group = f"tabs{id(self)}"
            for i, (name, _) in enumerate(tabs):
                tb = ToggleButton(text=name, group=group, size_hint_x=None, font_size=sp(15),
                                  background_normal="", background_down="",
                                  background_color=theme.ACCENT if i == start_tab else theme.CARD,
                                  color=(1, 1, 1, 1) if i == start_tab else theme.TEXT,
                                  allow_no_selection=False, state="down" if i == start_tab else "normal")
                tb.texture_update()
                tb.width = max(dp(90), tb.texture_size[0] + dp(28))
                tb.bind(on_release=lambda b, i=i: self.show_tab(i))
                tb.bind(state=self._tab_color)
                row.add_widget(tb)
            sv.add_widget(row)
            root.add_widget(sv)

        self.grid = ThumbGrid()
        self.grid.on_pick = self._picked
        root.add_widget(self.grid)
        self.add_widget(root)
        self.show_tab(start_tab)

    @staticmethod
    def _tab_color(btn, state):
        on = state == "down"
        btn.background_color = theme.ACCENT if on else theme.CARD
        btn.color = (1, 1, 1, 1) if on else theme.TEXT

    def show_tab(self, i):
        self.current = self.tabs[i][1]
        self.grid.set_items([(src, label) for src, label, _ in self.current])

    def _picked(self, index):
        value = self.current[index][2]
        self.dismiss()
        self.callback(value)
