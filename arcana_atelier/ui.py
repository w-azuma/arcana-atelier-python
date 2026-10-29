"""Minimal retained-mode widgets for pygame: buttons, sliders, a text box."""
import os
import pygame
from .config import COL

JP_FONTS = ['notosanscjkjp', 'notosansjp', 'notosanscjk', 'hiraginosans', 'hiraginokakugothicpro', 'yugothic', 'yugothicui',
            'meiryo', 'msgothic', 'takaogothic', 'ipagothic', 'ipaexgothic', 'notosanscjksc', 'droidsansfallback', 'arialunicodems']


FONT_FILES = [
    '/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc', '/System/Library/Fonts/Hiragino Sans GB.ttc',
    '/Library/Fonts/Arial Unicode.ttf',
    'C:/Windows/Fonts/YuGothM.ttc', 'C:/Windows/Fonts/meiryo.ttc', 'C:/Windows/Fonts/msgothic.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', '/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/fonts-japanese-gothic.ttf',
]


def find_font(size, bold=False):
    env = os.environ.get('ARCANA_FONT')
    if env and os.path.exists(env):
        return pygame.font.Font(env, size)
    for path in FONT_FILES:
        if os.path.exists(path):
            try:
                return pygame.font.Font(path, size)
            except Exception:
                pass
    avail = set(pygame.font.get_fonts())
    for name in JP_FONTS:
        if name in avail:
            return pygame.font.SysFont(name, size, bold=bold)
    return pygame.font.Font(None, int(size * 1.3))


class Fonts:
    def __init__(self):
        self.s = find_font(12)
        self.m = find_font(14)
        self.l = find_font(18, True)
        self.xl = find_font(30, True)
        self.title = find_font(26, True)


def text(surf, font, s, pos, col=None, center=False, right=False):
    img = font.render(str(s), True, col or COL['fg'])
    x, y = pos
    if center:
        x -= img.get_width() / 2
    if right:
        x -= img.get_width()
    surf.blit(img, (x, y))
    return img.get_rect(topleft=(x, y))


def panel(surf, rect, title=None, fonts=None, sub=None):
    pygame.draw.rect(surf, COL['panel'], rect, border_radius=10)
    pygame.draw.rect(surf, COL['line'], rect, 1, border_radius=10)
    if title and fonts:
        text(surf, fonts.s, title, (rect.x + 12, rect.y + 8), COL['gold'])
        if sub:
            text(surf, fonts.s, sub, (rect.right - 12, rect.y + 8), COL['dim'], right=True)


class Button:
    def __init__(self, rect, label, on_click, sub=None, selected=None, color=None, big=False):
        self.rect = pygame.Rect(rect)
        self.label, self.sub, self.on_click = label, sub, on_click
        self.selected = selected or (lambda: False)
        self.color = color
        self.big = big
        self.visible = lambda: True

    def draw(self, surf, fonts, hover):
        if not self.visible():
            return
        sel = self.selected()
        c = self.color or COL['gold']
        bg = (34, 27, 74) if sel else COL['panel2']
        if hover:
            bg = tuple(min(255, v + 10) for v in bg)
        pygame.draw.rect(surf, bg, self.rect, border_radius=7)
        pygame.draw.rect(surf, c if sel else COL['line2'], self.rect, 2 if sel else 1, border_radius=7)
        lab = self.label() if callable(self.label) else self.label
        f = fonts.l if self.big else fonts.m
        if self.sub:
            text(surf, f, lab, (self.rect.centerx, self.rect.y + 3), COL['fg'], center=True)
            sub = self.sub() if callable(self.sub) else self.sub
            text(surf, fonts.s, sub, (self.rect.centerx, self.rect.bottom - 16), COL['muted'], center=True)
        else:
            img = f.render(lab, True, c if self.big else COL['fg'])
            surf.blit(img, (self.rect.centerx - img.get_width() / 2, self.rect.centery - img.get_height() / 2))

    def handle(self, ev):
        if self.visible() and ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and self.rect.collidepoint(ev.pos):
            self.on_click()
            return True
        return False


class Slider:
    def __init__(self, rect, label, lo, hi, value, on_change, fmt=lambda v: f'{v:.0f}', step=None):
        self.rect = pygame.Rect(rect)
        self.label, self.lo, self.hi, self.value = label, lo, hi, value
        self.on_change, self.fmt, self.step = on_change, fmt, step
        self.drag = False
        self.visible = lambda: True

    def draw(self, surf, fonts, hover):
        if not self.visible():
            return
        text(surf, fonts.s, self.label, (self.rect.x, self.rect.y), COL['muted'])
        text(surf, fonts.s, self.fmt(self.value), (self.rect.right, self.rect.y), COL['fg'], right=True)
        y = self.rect.y + 24
        pygame.draw.line(surf, COL['violet'], (self.rect.x, y), (self.rect.right, y), 3)
        k = (self.value - self.lo) / (self.hi - self.lo)
        pygame.draw.circle(surf, COL['bg'], (int(self.rect.x + k * self.rect.w), y), 7)
        pygame.draw.circle(surf, COL['gold'], (int(self.rect.x + k * self.rect.w), y), 7, 2)

    def _set(self, x):
        k = min(1, max(0, (x - self.rect.x) / self.rect.w))
        v = self.lo + k * (self.hi - self.lo)
        if self.step:
            v = round(v / self.step) * self.step
        if v != self.value:
            self.value = v
            self.on_change(v)

    def handle(self, ev):
        if not self.visible():
            return False
        hit = pygame.Rect(self.rect.x - 6, self.rect.y + 12, self.rect.w + 12, 24)
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and hit.collidepoint(ev.pos):
            self.drag = True; self._set(ev.pos[0]); return True
        if ev.type == pygame.MOUSEMOTION and self.drag:
            self._set(ev.pos[0]); return True
        if ev.type == pygame.MOUSEBUTTONUP and self.drag:
            self.drag = False; return True
        return False


class TextBox:
    def __init__(self, rect, placeholder, on_submit):
        self.rect = pygame.Rect(rect)
        self.placeholder, self.on_submit = placeholder, on_submit
        self.text, self.compose, self.focus = '', '', False
        self.visible = lambda: True

    def draw(self, surf, fonts, hover):
        pygame.draw.rect(surf, (10, 9, 25), self.rect, border_radius=7)
        pygame.draw.rect(surf, COL['gold'] if self.focus else COL['line2'], self.rect, 1, border_radius=7)
        s = self.text + self.compose
        if s:
            text(surf, fonts.m, s + ('|' if self.focus and pygame.time.get_ticks() // 500 % 2 else ''), (self.rect.x + 10, self.rect.y + 7))
        else:
            text(surf, fonts.m, self.placeholder, (self.rect.x + 10, self.rect.y + 7), COL['dim'])

    def handle(self, ev):
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            was = self.focus
            self.focus = self.rect.collidepoint(ev.pos)
            if self.focus:
                pygame.key.start_text_input(); pygame.key.set_text_input_rect(self.rect)
            elif was:
                pygame.key.stop_text_input()
            return self.focus
        if not self.focus:
            return False
        if ev.type == pygame.TEXTEDITING:
            self.compose = ev.text; return True
        if ev.type == pygame.TEXTINPUT:
            self.text += ev.text; self.compose = ''; return True
        if ev.type == pygame.KEYDOWN:
            if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and not self.compose:
                self.on_submit(self.text); return True
            if ev.key == pygame.K_BACKSPACE and not self.compose:
                self.text = self.text[:-1]; return True
            if ev.key == pygame.K_ESCAPE:
                self.focus = False; pygame.key.stop_text_input(); return False
            return True
        return False
