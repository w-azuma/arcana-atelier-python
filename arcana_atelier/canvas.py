"""The 2D painting canvas: synaesthetic colours, element brushes, free brushes,
mandala symmetry, undo, and a framed PNG export."""
import math
import os
import time
import numpy as np
import pygame
from .config import COL, hexrgb

CW, CH = 1200, 675

SCRIABIN = [hexrgb(h) for h in ['#ff2a2a', '#a33cff', '#ffe83a', '#9fb3d6', '#cfe9ff', '#9b1b30', '#3d6bff', '#ff8a1f', '#c08cff', '#2fd16a', '#c48a9a', '#5aa8ff']]
GOLD = [hexrgb(h) for h in ['#1f3a93', '#2a4fb0', '#3c66c9', '#c8a03c', '#e0b84a', '#f5c26b', '#b8322a', '#d4483c', '#f5d58a', '#e9c77a', '#284a9e', '#ffe6b0']]


def hsl(h, s, l):
    s /= 100; l /= 100
    k = lambda n: (n + h / 30) % 12
    a = s * min(l, 1 - l)
    f = lambda n: l - a * max(-1, min(k(n) - 3, min(9 - k(n), 1)))
    return tuple(int(f(n) * 255) for n in (0, 8, 4))


PALETTES = {
    'scriabin': ('スクリャービン', lambda pc: SCRIABIN[pc]),
    'fifths': ('五度圏の虹', lambda pc: hsl(((pc * 7) % 12) * 30, 88, 62)),
    'gold': ('金箔と群青', lambda pc: GOLD[pc]),
}
BGS = {'night': '夜空', 'paper': '和紙', 'sumi': '墨'}
BG_COL = {'night': (10, 8, 24), 'paper': (239, 230, 210), 'sumi': (11, 11, 14)}
BRUSHES = [('brush', '筆'), ('mist', '霧'), ('stars', '星屑'), ('ink', '墨'), ('glyph', '魔法陣'), ('erase', '消す')]


class Canvas:
    def __init__(self):
        self.surf = pygame.Surface((CW, CH))
        self.bg = 'night'
        self.sym = 6
        self.palette = 'scriabin'
        self.strokes = 0
        self.undo = []
        self._sprites = {}
        self.paint_bg()

    def note_color(self, midi):
        return PALETTES[self.palette][1](midi % 12)

    # ------------------------------------------------ background
    def paint_bg(self):
        s = self.surf
        rng = np.random.default_rng()
        if self.bg == 'paper':
            s.fill(BG_COL['paper'])
            for _ in range(2200):
                x, y = rng.uniform(0, CW), rng.uniform(0, CH)
                a = rng.uniform(0, math.pi); l = rng.uniform(4, 22)
                c = tuple(int(v) for v in (rng.integers(205, 230), rng.integers(190, 215), rng.integers(160, 190)))
                pygame.draw.line(s, c, (x, y), (x + math.cos(a) * l, y + math.sin(a) * l))
        else:
            s.fill(BG_COL[self.bg])
            if self.bg == 'night':
                g = self._sprite(int(CW * 0.55), (26, 19, 64), 1.0)
                s.blit(g, (CW / 2 - g.get_width() / 2, CH * 0.45 - g.get_height() / 2), special_flags=pygame.BLEND_RGB_ADD)
                for _ in range(420):
                    v = int(rng.integers(90, 240))
                    s.set_at((int(rng.uniform(0, CW)), int(rng.uniform(0, CH))), (v, v, min(255, v + 20)))
        self.strokes = 0

    # ------------------------------------------------ sprites (soft radial dabs)
    def _sprite(self, r, col, alpha):
        key = (r, col, round(alpha, 2), self.bg == 'paper')
        if key in self._sprites:
            return self._sprites[key]
        r = max(1, int(r))
        y, x = np.mgrid[-r:r + 1, -r:r + 1]
        fall = np.clip(1 - np.sqrt(x * x + y * y) / r, 0, 1) ** 1.6 * alpha
        if self.bg == 'paper':     # multiply sprite: white -> colour
            arr = 255 - (255 - np.array(col, float))[None, None, :] * fall[..., None]
        else:                      # additive sprite
            arr = np.array(col, float)[None, None, :] * fall[..., None]
        surf = pygame.surfarray.make_surface(np.clip(arr, 0, 255).astype(np.uint8).transpose(1, 0, 2))
        if len(self._sprites) > 400:
            self._sprites.clear()
        self._sprites[key] = surf
        return surf

    def _blend_flag(self):
        return pygame.BLEND_RGB_MULT if self.bg == 'paper' else pygame.BLEND_RGB_ADD

    def dab(self, x, y, r, col, alpha):
        sp = self._sprite(int(r), col, alpha)
        self.surf.blit(sp, (x - sp.get_width() / 2, y - sp.get_height() / 2), special_flags=self._blend_flag())

    # ------------------------------------------------ symmetry
    def sym_points(self, x, y):
        cx, cy = CW / 2, CH / 2
        out = []
        for k in range(self.sym):
            a = k * 2 * math.pi / self.sym
            dx, dy = x - cx, y - cy
            if self.sym > 1 and k % 2 == 1:
                dy = -dy
            out.append((cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a), a, k % 2 == 1))
        return out

    # ------------------------------------------------ free tools
    def push_undo(self):
        self.undo.append(self.surf.copy())
        if len(self.undo) > 8:
            self.undo.pop(0)

    def pop_undo(self):
        if self.undo:
            self.surf.blit(self.undo.pop(), (0, 0))

    def tool_stroke(self, tool, x, y, px, py, size, alpha, col, glyph=None):
        for (sx, sy, a, mir), (qx, qy, _, _) in zip(self.sym_points(x, y), self.sym_points(px, py)):
            if tool == 'brush':
                d = math.hypot(sx - qx, sy - qy); n = max(1, int(d / max(1, size * 0.3)))
                for k in range(n + 1):
                    self.dab(qx + (sx - qx) * k / n, qy + (sy - qy) * k / n, size * 0.6, col, alpha * 0.9)
            elif tool == 'mist':
                self.dab(sx, sy, size * 2, col, alpha * 0.25)
            elif tool == 'stars':
                for _ in range(4):
                    ox, oy = np.random.uniform(-1.5, 1.5, 2) * size
                    c = (255, 255, 255) if np.random.random() < 0.3 else col
                    self.dab(sx + ox, sy + oy, np.random.uniform(1.5, 0.25 * size + 2), c, alpha)
            elif tool == 'ink':
                ink = (21, 16, 31) if self.bg == 'paper' else col
                for _ in range(3):
                    ox, oy = np.random.uniform(-0.5, 0.5, 2) * size
                    sp = self._sprite(int(size * np.random.uniform(0.5, 1.3)), ink, alpha * 0.4)
                    self.surf.blit(sp, (sx + ox - sp.get_width() / 2, sy + oy - sp.get_height() / 2), special_flags=self._blend_flag())
            elif tool == 'glyph' and glyph is not None:
                self.stamp(glyph, sx, sy, size * 2.2, np.random.uniform(0, 6.28), col)
            elif tool == 'erase':
                pygame.draw.line(self.surf, BG_COL[self.bg], (qx, qy), (sx, sy), int(size * 1.5))
                pygame.draw.circle(self.surf, BG_COL[self.bg], (int(sx), int(sy)), int(size * 0.75))
        self.strokes += 1

    def stamp(self, glyph, x, y, R, rot, col):
        g = glyph.recon
        c, s = math.cos(rot), math.sin(rot)
        pts = [(x + (a * c - b * s) * R, y + (a * s + b * c) * R) for a, b in g]
        if self.bg == 'paper':
            col = tuple(int(v * 0.7) for v in col)
        pygame.draw.aalines(self.surf, col, True, pts)

    # ------------------------------------------------ musical painting
    def paint_note(self, glyph, element, x, y, midi, prev=None):
        col = self.note_color(midi)
        size = 50 + (1 - (midi - 57) / 20) * 70
        for sx, sy, a, mir in self.sym_points(x, y):
            self.element_brush(element, sx, sy, col, size, prev)
            if glyph is not None:
                self.stamp(glyph, sx, sy, size * 0.55, a + np.random.uniform(0, 0.3), col)
        self.strokes += 1

    def element_brush(self, el, x, y, col, size, prev=None):
        r = np.random
        if el == 'fire':
            for _ in range(8):
                self.dab(x + r.uniform(-.3, .3) * size, y - r.uniform(0, .9) * size, size * r.uniform(.05, .14), col, 0.8)
        elif el == 'water':
            for _ in range(3):
                self.dab(x + r.uniform(-.2, .2) * size, y + r.uniform(-.2, .2) * size, size * r.uniform(.35, .7), col, 0.18)
        elif el == 'wind':
            ang = math.atan2(y - prev[1], x - prev[0]) if prev else r.uniform(0, 6.28)
            for _ in range(3):
                L = size * r.uniform(1, 2.4)
                a = ang + r.uniform(-.3, .3)
                p0 = (x - math.cos(a) * L, y - math.sin(a) * L)
                pygame.draw.aaline(self.surf, col, p0, (x + math.cos(a) * L * 0.3, y + math.sin(a) * L * 0.3))
        elif el == 'bolt':
            bx, by = CW / 2 + r.uniform(-30, 30), CH / 2 + r.uniform(-30, 30)
            pts = [(bx + (x - bx) * k / 10 + r.uniform(-1, 1) * 30 * (1 - k / 10), by + (y - by) * k / 10 + r.uniform(-1, 1) * 30 * (1 - k / 10)) for k in range(11)]
            pygame.draw.lines(self.surf, (255, 240, 150) if self.bg != 'paper' else (120, 100, 20), False, pts, 2)
            self.dab(x, y, size * 0.4, col, 0.5)
        elif el == 'ice':
            for k in range(6):
                a = k * math.pi / 3
                L = size * 0.8
                pygame.draw.aaline(self.surf, col, (x, y), (x + math.cos(a) * L, y + math.sin(a) * L))
                for b in (1, 2, 3):
                    bx, by = x + math.cos(a) * L * b / 4, y + math.sin(a) * L * b / 4
                    for s_ in (0.8, -0.8):
                        pygame.draw.aaline(self.surf, col, (bx, by), (bx + math.cos(a + s_) * L * .18, by + math.sin(a + s_) * L * .18))
        elif el == 'light':
            self.dab(x, y, size * 0.9, col, 0.45)
            for k in range(12):
                a = k * math.pi / 6
                pygame.draw.aaline(self.surf, col, (x, y), (x + math.cos(a) * size * 1.4, y + math.sin(a) * size * 1.4))
        elif el == 'dark':
            ink = (27, 18, 48) if self.bg == 'paper' else (70, 30, 120)
            for _ in range(4):
                self.dab(x + r.uniform(-.4, .4) * size, y + r.uniform(-.4, .4) * size, size * r.uniform(.3, .8), ink, 0.35)
        elif el == 'earth':
            for _ in range(60):
                a = r.uniform(0, 6.28); d = r.random() ** 0.6 * size * 0.7
                c = col if r.random() < 0.6 else (201, 164, 107)
                if self.bg == 'paper':
                    c = tuple(int(v * 0.6) for v in c)
                self.surf.fill(c, (int(x + math.cos(a) * d), int(y + math.sin(a) * d), 2, 2))

    def trail(self, x, y, px, py, col):
        for (sx, sy, _, _), (qx, qy, _, _) in zip(self.sym_points(x, y), self.sym_points(px, py)):
            pygame.draw.aaline(self.surf, col if self.bg != 'paper' else tuple(int(v * 0.6) for v in col), (qx, qy), (sx, sy))

    # ------------------------------------------------ export
    def save_framed(self, title, meta, art_surface=None, font_title=None, font_meta=None, folder='gallery'):
        art = art_surface or self.surf
        W, H = 1500, 1040
        out = pygame.Surface((W, H))
        out.fill((13, 11, 22))
        for i, c in enumerate([(58, 42, 18), (138, 106, 46), (233, 199, 122), (122, 90, 34), (216, 180, 106)]):
            pygame.draw.rect(out, c, (50 + i * 4, 40 + i * 4, W - 100 - i * 8, 790 - i * 8), 4)
        pygame.draw.rect(out, (26, 19, 8), (74, 64, W - 148, 742))
        out.blit(pygame.transform.smoothscale(art, (W - 160, 730)), (80, 70))
        pygame.draw.rect(out, (21, 18, 48), (W / 2 - 380, 860, 760, 110))
        pygame.draw.rect(out, (54, 46, 102), (W / 2 - 380, 860, 760, 110), 1)
        if font_title:
            t = font_title.render(title, True, COL['gold']); out.blit(t, (W / 2 - t.get_width() / 2, 880))
        if font_meta:
            m = font_meta.render(meta[:60], True, COL['muted']); out.blit(m, (W / 2 - m.get_width() / 2, 930))
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, time.strftime('arcana-%Y%m%d-%H%M%S') + f'-{int(time.time() * 1000) % 1000:03d}.png')
        pygame.image.save(out, path)
        return path
