"""ARCANA ATELIER — main application (pygame)."""
import math
import queue
import random
import threading
import time
import traceback

import numpy as np
import pygame

from .config import SR, W, H, FPS, COL
from . import glyphs, synth, world, ui
from .canvas import Canvas, CW, CH, PALETTES, BGS, BRUSHES
from .render3d import Sanctuary, MAXP

VIEW = pygame.Rect(320, 100, 760, 560)
KEYS = [pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_f, pygame.K_g, pygame.K_h, pygame.K_j, pygame.K_k]
KEY_LABELS = 'ASDFGHJK'
SWATCHES = [(157, 123, 255), (79, 227, 255), (245, 194, 107), (255, 111, 168), (255, 122, 69), (125, 255, 203), (70, 184, 255), (255, 255, 255), (30, 24, 50), (201, 164, 107)]


def wrap(a):
    return (a + 180) % 360 - 180


# ======================================================================= audio
class Audio:
    """Synthesis runs on a worker thread; finished buffers are played on the main thread."""

    def __init__(self):
        self.ok = False
        try:
            pygame.mixer.pre_init(SR, -16, 2, 512)
            pygame.mixer.init(SR, -16, 2, 512)
            pygame.mixer.set_num_channels(48)
            self.ok = pygame.mixer.get_init() is not None
            self.channels = pygame.mixer.get_init()[2] if self.ok else 2
        except pygame.error as e:
            print('audio disabled:', e)
        self.jobs, self.done = queue.Queue(), queue.Queue()
        self.gen = 0
        self.last = None
        self.master = 0.8
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self):
        while True:
            g, fn, tag = self.jobs.get()
            if g != self.gen:
                continue
            try:
                self.done.put((g, fn(), tag))
            except Exception:
                traceback.print_exc()

    def submit(self, fn, tag=None):
        self.jobs.put((self.gen, fn, tag))

    def pump(self):
        while not self.done.empty():
            g, st, tag = self.done.get()
            if g != self.gen or st is None:
                continue
            if tag == 'note':
                self.last = st
            self.play(st)

    def play(self, st):
        if not self.ok or st is None or len(st) == 0:
            return
        a = np.clip(st * self.master, -1, 1)
        if self.channels == 1:
            a = a.mean(1)
        snd = pygame.sndarray.make_sound(np.ascontiguousarray((a * 32767).astype(np.int16)))
        snd.play()

    def stop(self):
        self.gen += 1
        while not self.jobs.empty():
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                break
        if self.ok:
            pygame.mixer.stop()


def render_note(tx, txm, tym, f, dur, az, el, dist, E, mode):
    n = int(dur * SR)
    env = synth.adsr(n, 0.012, 0.25, 0.6, min(0.18, dur * 0.4))
    if mode == 'mirror':
        L = synth.wavetable_osc(txm, f / 2, dur) * env
        R = synth.wavetable_osc(tym, f / 2, dur) * env
        return synth.reverb(np.stack([L, R], 1) * 0.6, 1.2, 0.2)
    mono = synth.wavetable_osc(tx, f, dur, vib_cents=E.get('vib', 0)) * env
    if E.get('layer'):
        mono = mono + 0.4 * synth.wavetable_osc(tx, f * E['layer'], dur) * env
    if E['lp'] < 14000:
        mono = synth.lowpass(mono, E['lp'])
    st = synth.spatialize(mono, az, el, dist)
    if E.get('comb'):
        st = synth.comb(st)
    if E.get('echo'):
        d = int(0.38 * SR)
        out = np.zeros((len(st) + d * 4, 2))
        for k in range(5):
            out[k * d:k * d + len(st)] += st * (0.45 ** k)
        st = out
    return synth.reverb(st, E['ir'], E['wet']) * 0.6


# ======================================================================= app
class App:
    def __init__(self, headless_frames=None):
        pygame.init()
        self.screen = pygame.display.set_mode((W, H))
        pygame.display.set_caption('ARCANA ATELIER')
        self.fonts = ui.Fonts()
        self.audio = Audio()
        self.clock = pygame.time.Clock()
        self.t0 = time.time()
        self.headless_frames = headless_frames
        # state
        self.glyph_idx = 3
        self.glyph = glyphs.make_preset(3)
        self.element, self.scale_key, self.mode, self.view = 'wind', 'penta', 'cast', 'circle'
        self.scale = world.scale_midis(self.scale_key)
        self.orb = (0.0, 0.0, 2.0)
        self.cast_until = 0.0
        self.glow = 0.4
        self.queue = []                 # (time, callable)
        self.creatures = {}
        self.pause_at = None
        self.beast_paint = True
        self.auto, self.auto_next, self.auto_deg = False, 0.0, 3
        self.tool2, self.tool3 = 'brush', 'orbit'
        self.size, self.alpha, self.depth = 16, 0.7, 6.0
        self.color, self.autocolor, self.drawsound = SWATCHES[0], True, True
        self.canvas = Canvas()
        self.sanct = Sanctuary()
        self.view3 = pygame.Surface(VIEW.size)
        self.stroke = None
        self.drag = None
        self.flash = ('', 0.0)
        self.toast = ('', 0.0)
        self.trail_t = 0.0
        self.prev2d = None
        self.epi_t = 0.0
        self.last_note_t = 0.0
        self.paused_frames = 0
        self._build_ui()

    # ------------------------------------------------------------- helpers
    @property
    def now(self):
        return time.time() - self.t0

    def say(self, s, sec=2.2):
        self.flash = (s, self.now + sec)

    def notify(self, s):
        self.toast = (s, self.now + 3)

    def later(self, dt, fn):
        self.queue.append((self.now + dt, fn))

    def yaw(self):
        return math.degrees(self.sanct.cam.theta) if self.view == '3d' else 0.0

    def orb_world(self):
        az, el, d = self.orb
        d *= 1.4
        hr = d * math.cos(math.radians(el))
        return (hr * math.sin(math.radians(az)), 1.6 + d * math.sin(math.radians(el)), -hr * math.cos(math.radians(az)))

    def orb_canvas(self):
        az, el, d = self.orb
        s = min(CW, CH) / 2 / 4.4
        hr = d * math.cos(math.radians(el))
        return (CW / 2 + hr * math.sin(math.radians(az)) * s, CH / 2 - hr * math.cos(math.radians(az)) * s)

    def spell_name(self):
        g = self.glyph
        if g is None:
            return '—'
        b = g.centroid
        adj = '静寂の' if b < 1.4 else '澄みわたる' if b < 2.6 else '煌めく' if b < 5 else '荒ぶる'
        size = '環' if g.count <= 3 else '陣' if g.count <= 12 else '大陣'
        return f'{adj}{g.name}{size}・{world.ELEMENTS[self.element]["noun"]}'

    def tool_color(self, deg):
        return self.canvas.note_color(self.scale[deg]) if self.autocolor else self.color

    # ------------------------------------------------------------- sound actions
    def play_note(self, deg, dur=0.45, paint=True, quiet=False):
        if self.glyph is None:
            return
        midi = self.scale[deg]
        f = synth.mtof(midi)
        E = world.ELEMENTS[self.element]
        if E.get('jump'):
            self.orb = (random.uniform(-180, 180), random.uniform(-10, 40), random.uniform(1.5, 4.5))
        az, el, d = self.orb
        if E.get('doppler'):
            a2 = world.orb_position(self.element, self.now + 0.05, self.orb)
            vr = (a2[2] - d) / 0.05
            f *= 343 / (343 + vr * 6)
        g = self.glyph
        tx, txm, tym = g.table('x'), g.table('xm'), g.table('ym')
        args = (tx, txm, tym, f, dur, wrap(az + self.yaw()), el, d, E, self.mode)
        self.audio.submit(lambda: render_note(*args), 'note')
        self.cast_until = max(self.cast_until, self.now + 0.6)
        self.glow = min(1.6, self.glow + 0.5)
        if paint and not quiet:
            x, y = self.orb_canvas() if self.mode == 'cast' else (CW / 2 + random.uniform(-60, 60), CH / 2 + random.uniform(-40, 40))
            self.canvas.paint_note(g, self.element, x, y, midi, self.prev2d)
            self.prev2d = (x, y)
            col = self.canvas.note_color(midi)
            self.sanct.sculpt(self.orb_world(), col, 24, 0.35)
            self.sanct.burst(self.orb_world(), col, 40)

    def cast(self):
        if self.glyph is None:
            self.set_glyph(3)
        amps = self.glyph.amps
        top = [int(n) % 8 for n in np.argsort(-amps)[:6]]
        phrase = ([0] + top + [7])[:8]
        for k, deg in enumerate(phrase):
            self.later(k * 0.24, lambda d=deg: self.play_note(d, 0.42))
        self.glow = 1.8
        self.sanct.burst(self.orb_world(), world.ELEMENTS[self.element]['col'], 120)

    def set_glyph(self, i=None, raw=None):
        if raw is not None:
            self.glyph = glyphs.Glyph(raw, '自作の'); self.glyph_idx = -1
        else:
            self.glyph_idx = i; self.glyph = glyphs.make_preset(i)
        self.glyph.set_spirits(int(self.spirits.value) if hasattr(self, 'spirits') else 24)
        self.glow = 1.2

    def set_element(self, el):
        self.element = el

    # ------------------------------------------------------------- spells & creatures
    def cast_spell(self, text):
        text = text.strip()
        if not text:
            return
        n = world.norm(text)
        beast = next((c for c in world.CREATURES if world.norm(c['name']) in n and (n.startswith(world.norm('アドヴォカ')) or n == world.norm(c['name']))), None)
        spell = next((s for s in world.SPELLS if world.norm(s[0]) == n), None)
        syl = world.syllables(text)
        self.say(text)
        if syl:
            scale = list(self.scale)
            seed = world.text_hash(text)
            self.audio.submit(lambda: synth.reverb(synth.spatialize(synth.chant(syl, scale, seed), 0, 0, 1.0), 2.5, 0.45) * 0.9)
        dur = sum(s.get('pause', 0) + 0.24 * s.get('len', 0) for s in syl) + 0.4

        def fire():
            if beast:
                self.summon(beast['id']); return
            if spell and spell[1].startswith('fx:'):
                fx = spell[1][3:]
                if fx == 'paint':
                    self.beast_paint = not self.beast_paint
                    self.say('魔法動物が描き始めた' if self.beast_paint else '魔法動物が筆を置いた')
                elif fx == 'chorus':
                    for cid in self.creatures:
                        self.creature_call(cid, loud=True)
                    self.sanct.burst((0, 1.5, 0), COL['gold'], 120)
                elif fx == 'rest':
                    self.creatures.clear(); self.say('静けさが戻った')
                return
            el = spell[1] if spell else list(world.ELEMENTS)[world.text_hash(n) % 8]
            self.set_element(el)
            if not spell:
                self.say(f'{text} ― {world.ELEMENTS[el]["sym"]}の呪文')
            self.cast()
        self.later(max(0.3, dur * 0.85), fire)

    def summon(self, cid):
        if cid in self.creatures:
            return
        if self.pause_at is not None:
            self.set_pause(False)
        self.creatures[cid] = dict(t0=self.now + random.uniform(0, 20), next=self.now + 0.6, last_paint=0.0, hist=[])
        info = world.CREATURE_BY_ID[cid]
        self.sanct.burst((0, 0.2, 0), info['col'], 150)
        self.say(f'{info["name"]}が現れた')

    def dismiss(self, cid):
        self.creatures.pop(cid, None)

    def set_pause(self, on):
        if on and self.pause_at is None:
            self.pause_at = self.now
        elif not on and self.pause_at is not None:
            d = self.now - self.pause_at
            for st in self.creatures.values():
                st['t0'] += d; st['next'] = self.now + 0.5
            self.pause_at = None

    def creature_call(self, cid, loud=False):
        st = self.creatures.get(cid)
        if not st or 'pos' not in st:
            return
        x, y, z = st['pos']
        dx, dy, dz = x, y - 1.6, z
        az = wrap(math.degrees(math.atan2(dx, -dz)) + self.yaw())
        el = math.degrees(math.atan2(dy, math.hypot(dx, dz)))
        dist = max(1.0, math.sqrt(dx * dx + dy * dy + dz * dz) * 0.6)
        scale = list(self.scale)
        self.audio.submit(lambda: synth.reverb(synth.spatialize(synth.creature_call(cid, scale, loud), az, el, dist), 1.5, 0.3) * 0.8)

    def step_creatures(self, dt):
        if self.pause_at is not None:
            return
        now = self.now
        for cid, st in list(self.creatures.items()):
            tt = now - st['t0'] + 100
            p = world.creature_pos(cid, tt)
            st['prev'] = st.get('pos', p); st['pos'] = p
            if cid == 'ryu':
                st['hist'].insert(0, p); del st['hist'][60:]
            if cid == 'drako':
                beat = int(tt * 2)
                if beat != st.get('beat'):
                    st['beat'] = beat
                    if self.view == '3d':
                        self.sanct.shake = 0.06
            if cid == 'hare':
                hop = int(tt * 3.1 / math.pi)
                if hop != st.get('hop'):
                    st['hop'] = hop
                    if random.random() < 0.45:
                        self.creature_call(cid)
            if cid == 'phoenix':
                ph = (tt % 11) / 11
                if ph > 0.96 and not st.get('burst'):
                    st['burst'] = True
                    self.sanct.burst(p, (255, 90, 58), 180)
                    self.audio.submit(lambda: synth.spatialize(synth.crackle(), 0, 30, 2.0) * 0.6)
                if ph < 0.5:
                    st['burst'] = False
            info = world.CREATURE_BY_ID[cid]
            if now > st['next']:
                self.creature_call(cid)
                st['next'] = now + info['every'] * random.uniform(0.7, 1.3)
            if self.beast_paint and now - st['last_paint'] > 0.09:
                st['last_paint'] = now
                self.sanct.sculpt(p, info['col'], 3 if cid == 'whale' else 1, 0.6 if cid == 'whale' else 0.08)
                s2 = min(CW, CH) / 2 / 14
                pr = st['prev']
                self.canvas.trail(CW / 2 + p[0] * s2, CH / 2 + p[2] * s2, CW / 2 + pr[0] * s2, CH / 2 + pr[2] * s2, info['col'])
                if random.random() < 0.2:
                    self.canvas.element_brush(info['el'], CW / 2 + p[0] * s2, CH / 2 + p[2] * s2, info['col'], 40 if cid == 'whale' else 16)

    def stop_everything(self):
        self.audio.stop()
        self.queue.clear()
        self.auto = False
        self.creatures.clear()
        self.pause_at = None
        self.cast_until = 0.0
        self.say('静寂')

    # ------------------------------------------------------------- UI
    def _build_ui(self):
        B, S = ui.Button, ui.Slider
        self.widgets = []
        add = self.widgets.append
        # header
        add(B((1222, 12, 206, 34), '■ ぜんぶ止める  Esc', self.stop_everything, color=COL['stop']))
        # left: glyph presets
        for i, (sym, name, _) in enumerate(glyphs.PRESETS):
            r, c = divmod(i, 4)
            add(B((24 + c * 70, 92 + r * 34, 66, 30), f'{sym} {name}', lambda i=i: self.set_glyph(i), selected=lambda i=i: self.glyph_idx == i))
        for i, (k, e) in enumerate(world.ELEMENTS.items()):
            r, c = divmod(i, 4)
            add(B((24 + c * 70, 292 + r * 44, 66, 40), e['sym'], lambda k=k: self.set_element(k), sub=e['name'], selected=lambda k=k: self.element == k, color=e['col']))
        for i, (k, (nm, sub, _)) in enumerate(world.SCALES.items()):
            r, c = divmod(i, 3)
            add(B((24 + c * 92, 406 + r * 44, 88, 40), nm, lambda k=k: self.set_scale(k), sub=sub[:7], selected=lambda k=k: self.scale_key == k))
        add(B((24, 516, 134, 30), '詠唱 CAST', lambda: setattr(self, 'mode', 'cast'), selected=lambda: self.mode == 'cast'))
        add(B((162, 516, 134, 30), '鏡写し MIRROR', lambda: setattr(self, 'mode', 'mirror'), selected=lambda: self.mode == 'mirror'))
        self.spirits = S((24, 556, 272, 34), '精霊の数（フーリエ近似の項数）', 1, 64, 24, lambda v: self.glyph and self.glyph.set_spirits(int(v)), step=1, fmt=lambda v: f'{int(v)} 体')
        add(self.spirits)
        # center: tabs, keys, cast, bottom row
        for i, (k, lab) in enumerate((('circle', 'MAGIC CIRCLE  1'), ('3d', 'SANCTUARY 3D  2'), ('2d', 'CANVAS 2D  3'))):
            add(B((320 + i * 168, 64, 162, 30), lab, lambda k=k: setattr(self, 'view', k), selected=lambda k=k: self.view == k))
        for i in range(8):
            add(B((320 + i * 68, 716, 64, 52), lambda i=i: world.NOTE_JP[(self.scale[i] - 57) % 12], lambda i=i: self.play_note(i), sub=KEY_LABELS[i]))
        add(B((870, 716, 210, 52), '✦ CAST ✦', self.cast, big=True))
        add(B((320, 778, 184, 32), lambda: '✒ 自動筆記 ON' if self.auto else '✒ 自動筆記', self.toggle_auto, selected=lambda: self.auto))
        add(B((512, 778, 184, 32), '🖼 額装して保存', self.save))
        b = B((704, 778, 184, 32), '↶ 元に戻す', self.canvas.pop_undo); b.visible = lambda: self.view == '2d'; add(b)
        b = B((896, 778, 184, 32), '新しい画布', self.canvas.paint_bg); b.visible = lambda: self.view == '2d'; add(b)
        b = B((704, 778, 184, 32), '光の彫刻を消す', self.sanct.clear); b.visible = lambda: self.view == '3d'; add(b)
        b = B((896, 778, 184, 32), '視点を戻す', self.reset_cam); b.visible = lambda: self.view == '3d'; add(b)
        b = B((704, 778, 184, 32), '魔法陣を消す', lambda: setattr(self, 'glyph', None)); b.visible = lambda: self.view == 'circle'; add(b)
        # right: spellbook
        self.textbox = ui.TextBox((1104, 94, 236, 32), '呪文を唱える…', self.submit_spell)
        add(self.textbox)
        add(B((1346, 94, 70, 32), '唱える', lambda: self.submit_spell(self.textbox.text)))
        for i, (w_, el, d) in enumerate(world.SPELLS):
            r, c = divmod(i, 2)
            add(B((1104 + c * 158, 134 + r * 32, 154, 28), w_, lambda w_=w_: self.cast_spell(w_), color=COL['cyan'] if el.startswith('fx') else None))
        for i, cr in enumerate(world.CREATURES):
            r, c = divmod(i, 2)
            add(B((1104 + c * 158, 350 + r * 32, 154, 28), lambda cr=cr: ('● ' if cr['id'] in self.creatures else '') + cr['name'],
                  lambda cr=cr: self.toggle_creature(cr['id']), selected=lambda cr=cr: cr['id'] in self.creatures, color=cr['col']))
        add(B((1104, 548, 102, 28), lambda: '▶ 起こす' if self.pause_at is not None else '⏸ 休ませる', lambda: self.set_pause(self.pause_at is None), selected=lambda: self.pause_at is not None))
        add(B((1210, 548, 102, 28), 'すべて召喚', self.summon_all))
        add(B((1316, 548, 100, 28), 'すべて帰す', self.creatures.clear))
        add(B((1104, 582, 312, 26), lambda: ('☑' if self.beast_paint else '☐') + ' 魔法動物も絵を描く', lambda: setattr(self, 'beast_paint', not self.beast_paint)))
        # right: tools (contextual)
        v2, v3, v23 = (lambda: self.view == '2d'), (lambda: self.view == '3d'), (lambda: self.view in ('2d', '3d'))
        for i, (k, nm) in enumerate(BRUSHES):
            r, c = divmod(i, 3)
            b = B((1104 + c * 105, 664 + r * 30, 101, 26), nm, lambda k=k: setattr(self, 'tool2', k), selected=lambda k=k: self.tool2 == k); b.visible = v2; add(b)
        for i, (k, nm) in enumerate((('orbit', '⟳ 見回す'), ('air', '✎ 空中に描く'))):
            b = B((1104 + i * 158, 664, 154, 26), nm, lambda k=k: setattr(self, 'tool3', k), selected=lambda k=k: self.tool3 == k); b.visible = v3; add(b)
        for i, c in enumerate(SWATCHES):
            b = B((1104 + i * 26, 726, 22, 22), '', lambda c=c: self.pick_color(c), selected=lambda c=c: (not self.autocolor) and self.color == c, color=c); b.visible = v23; add(b)
            b.draw_swatch = c
        b = B((1366, 724, 50, 26), lambda: '音色' if self.autocolor else '自由', lambda: setattr(self, 'autocolor', not self.autocolor), selected=lambda: self.autocolor); b.visible = v23; add(b)
        s = S((1104, 754, 312, 30), '太さ', 2, 80, 16, lambda v: setattr(self, 'size', v), step=1, fmt=lambda v: f'{int(v)} px'); s.visible = v23; add(s)
        s = S((1104, 788, 312, 30), '濃さ', 0.05, 1, 0.7, lambda v: setattr(self, 'alpha', v), fmt=lambda v: f'{int(v * 100)} %'); s.visible = v2; add(s)
        s = S((1104, 788, 312, 30), '空中に描く奥行き', 2, 14, 6, lambda v: setattr(self, 'depth', v), fmt=lambda v: f'{v:.1f} m'); s.visible = v3; add(s)
        for i, n in enumerate((1, 4, 6, 8)):
            b = B((1104 + i * 79, 826, 75, 24), f'対称 {n}', lambda n=n: setattr(self.canvas, 'sym', n), selected=lambda n=n: self.canvas.sym == n); b.visible = v2; add(b)
        for i, (k, nm) in enumerate(BGS.items()):
            b = B((1104 + i * 52, 856, 49, 24), nm, lambda k=k: self.set_bg(k), selected=lambda k=k: self.canvas.bg == k); b.visible = v2; add(b)
        for i, (k, (nm, _)) in enumerate(PALETTES.items()):
            b = B((1262 + i * 52, 856, 49, 24), nm[:3], lambda k=k: setattr(self.canvas, 'palette', k), selected=lambda k=k: self.canvas.palette == k); b.visible = v2; add(b)
        b = B((1104, 826, 312, 24), lambda: ('☑' if self.sanct.spin else '☐') + ' ゆっくり自動で回る', lambda: setattr(self.sanct, 'spin', not self.sanct.spin)); b.visible = v3; add(b)
        b = B((1104, 856, 312, 24), lambda: ('☑' if self.drawsound else '☐') + ' 描くと音が鳴る', lambda: setattr(self, 'drawsound', not self.drawsound)); b.visible = v3; add(b)

    def set_scale(self, k):
        self.scale_key = k; self.scale = world.scale_midis(k)

    def set_bg(self, k):
        self.canvas.bg = k; self.canvas.paint_bg()

    def pick_color(self, c):
        self.color = c; self.autocolor = False

    def reset_cam(self):
        self.sanct.cam.theta, self.sanct.cam.phi, self.sanct.cam.r = 0.7, 1.12, 14.0

    def toggle_auto(self):
        self.auto = not self.auto; self.auto_next = self.now

    def toggle_creature(self, cid):
        if cid in self.creatures:
            self.dismiss(cid)
        else:
            self.cast_spell('アドヴォカ・' + world.CREATURE_BY_ID[cid]['name'])

    def summon_all(self):
        for k, c in enumerate(world.CREATURES):
            self.later(k * 0.25, lambda cid=c['id']: self.summon(cid))
        self.say('コルス・オムニア ― すべての魔法動物')

    def submit_spell(self, text):
        self.cast_spell(text)

    def save(self):
        title = self.spell_name()
        meta = f'{self.glyph.name if self.glyph else ""}の陣 × {world.ELEMENTS[self.element]["sym"]}属性 × {world.SCALES[self.scale_key][0]}音階 ／ {time.strftime("%Y.%m.%d")}'
        art = self.view3 if self.view == '3d' else self.canvas.surf if self.view == '2d' else self.screen.subsurface(VIEW).copy()
        path = self.canvas.save_framed(title, meta, art, self.fonts.title, self.fonts.m)
        self.notify(f'保存しました: {path}')

    # ------------------------------------------------------------- input
    def view_to_canvas(self, pos):
        cw = VIEW.w - 16; ch = cw * CH / CW
        ox, oy = VIEW.x + 8, VIEW.y + (VIEW.h - ch) / 2
        return ((pos[0] - ox) / cw * CW, (pos[1] - oy) / ch * CH), pygame.Rect(ox, oy, cw, ch)

    def handle(self, ev):
        if ev.type == pygame.QUIT:
            return False
        if self.textbox.handle(ev):
            return True
        for w_ in self.widgets:
            if w_ is not self.textbox and w_.handle(ev):
                return True
        if ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                self.stop_everything()
            elif ev.key in KEYS:
                self.play_note(KEYS.index(ev.key), 0.6)
            elif ev.key == pygame.K_SPACE:
                self.cast()
            elif ev.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                self.view = ('circle', '3d', '2d')[ev.key - pygame.K_1]
            elif ev.key == pygame.K_z and (ev.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)):
                self.canvas.pop_undo()
        if ev.type == pygame.MOUSEWHEEL and self.view == '3d' and VIEW.collidepoint(pygame.mouse.get_pos()):
            self.sanct.cam.r = min(40, max(5, self.sanct.cam.r * (1 - ev.y * 0.08)))
        if ev.type == pygame.MOUSEBUTTONDOWN and VIEW.collidepoint(ev.pos):
            self.mouse_down(ev)
        elif ev.type == pygame.MOUSEMOTION and self.drag:
            self.mouse_move(ev)
        elif ev.type == pygame.MOUSEBUTTONUP and self.drag:
            self.mouse_up(ev)
        return True

    def mouse_down(self, ev):
        if ev.button not in (1, 3):
            return
        if self.view == 'circle' and ev.button == 1:
            self.drag = {'kind': 'glyph', 'pts': [self.circle_coord(ev.pos)]}
        elif self.view == '3d':
            if ev.button == 1 and self.tool3 == 'air':
                self.drag = {'kind': 'air', 'last': None, 'note': 0.0}; self.air_paint(ev.pos)
            else:
                self.drag = {'kind': 'orbit'}
        elif self.view == '2d' and ev.button == 1:
            (x, y), _ = self.view_to_canvas(ev.pos)
            self.canvas.push_undo()
            self.drag = {'kind': 'paint', 'x': x, 'y': y, 'note': 0.0, 'stamp': (x, y)}
            self.canvas.tool_stroke(self.tool2, x, y, x, y, self.size, self.alpha, self.tool_color(self.deg_from_y(y / CH)), self.glyph)
            if self.drawsound:
                self.play_at(x, y)

    def mouse_move(self, ev):
        d = self.drag
        if d['kind'] == 'glyph':
            p = self.circle_coord(ev.pos)
            if math.hypot(p[0] - d['pts'][-1][0], p[1] - d['pts'][-1][1]) > 0.012:
                d['pts'].append(p)
        elif d['kind'] == 'orbit':
            c = self.sanct.cam
            c.theta -= ev.rel[0] * 0.008
            c.phi = min(1.5, max(0.25, c.phi - ev.rel[1] * 0.006))
        elif d['kind'] == 'air':
            self.air_paint(ev.pos)
        elif d['kind'] == 'paint':
            (x, y), _ = self.view_to_canvas(ev.pos)
            if self.tool2 == 'glyph':
                if math.hypot(x - d['stamp'][0], y - d['stamp'][1]) < self.size * 3:
                    return
                d['stamp'] = (x, y)
            self.canvas.tool_stroke(self.tool2, x, y, d['x'], d['y'], self.size, self.alpha, self.tool_color(self.deg_from_y(y / CH)), self.glyph)
            d['x'], d['y'] = x, y
            if self.drawsound and self.tool2 != 'erase' and self.now - d['note'] > 0.16:
                d['note'] = self.now; self.play_at(x, y)

    def mouse_up(self, ev):
        d = self.drag; self.drag = None
        if d['kind'] == 'glyph' and len(d['pts']) >= 12:
            self.set_glyph(raw=d['pts'])

    def circle_coord(self, pos):
        R = min(VIEW.w, VIEW.h) * 0.43 * 0.72
        return ((pos[0] - VIEW.centerx) / R, (pos[1] - VIEW.centery) / R)

    def deg_from_y(self, k):
        return int(min(7, max(0, round((1 - k) * 7))))

    def play_at(self, x, y):
        s = min(CW, CH) / 2 / 4.4
        dx, dy = (x - CW / 2) / s, (y - CH / 2) / s
        self.orb = (math.degrees(math.atan2(dx, -dy)), 0.0, max(0.6, math.hypot(dx, dy)))
        self.hold_orb = self.now + 0.5
        self.play_note(self.deg_from_y(y / CH), 0.25, quiet=True)

    def air_paint(self, pos):
        c = self.sanct.cam
        o, dirv = c.ray(pos[0] - VIEW.x, pos[1] - VIEW.y, VIEW.w, VIEW.h)
        p = o + dirv * self.depth
        deg = self.deg_from_y((pos[1] - VIEW.y) / VIEW.h)
        col = self.tool_color(deg)
        d = self.drag
        last = d['last']
        steps = max(1, int(np.linalg.norm(p - last) / 0.05)) if last is not None else 1
        for k in range(1, steps + 1):
            q = last + (p - last) * k / steps if last is not None else p
            self.sanct.sculpt(q, col, max(1, int(self.size / 8)), self.size * 0.006)
        d['last'] = p
        if self.drawsound and self.now - d['note'] > 0.14:
            d['note'] = self.now
            rel = p
            self.orb = (math.degrees(math.atan2(rel[0], -rel[2])), max(-80, min(80, math.degrees(math.atan2(rel[1] - 1.6, math.hypot(rel[0], rel[2]))))), max(0.6, math.hypot(rel[0], rel[2]) / 1.4))
            self.hold_orb = self.now + 0.4
            self.play_note(deg, 0.22, quiet=True)

    # ------------------------------------------------------------- update
    def update(self, dt):
        now = self.now
        due = [q for q in self.queue if q[0] <= now]
        self.queue = [q for q in self.queue if q[0] > now]
        for _, fn in sorted(due, key=lambda q: q[0]):
            fn()
        if now > getattr(self, 'hold_orb', 0) and self.element != 'bolt':
            self.orb = world.orb_position(self.element, now, self.orb)
        self.step_creatures(dt)
        active = now < self.cast_until or self.auto
        if active and self.mode == 'cast' and now - self.trail_t > 0.07 and self.glyph is not None:
            self.trail_t = now
            x, y = self.orb_canvas()
            col = world.ELEMENTS[self.element]['col']
            if self.prev2d:
                self.canvas.trail(x, y, self.prev2d[0], self.prev2d[1], self.canvas.note_color(self.scale[self.auto_deg]))
            self.prev2d = (x, y)
            self.sanct.sculpt(self.orb_world(), col, 3, 0.12)
        if self.auto and now > self.auto_next:
            self.auto_deg = int(min(7, max(0, self.auto_deg + random.choice([-2, -1, -1, 1, 1, 2, 0, 3, -3]))))
            d = random.choice([0.25, 0.35, 0.5, 0.8])
            self.play_note(self.auto_deg, d * 0.9)
            self.auto_next = now + d
        self.glow = max(0.15, self.glow - dt * 0.6)
        self.audio.pump()

    # ------------------------------------------------------------- drawing
    def draw(self, dt):
        s, f = self.screen, self.fonts
        s.fill(COL['bg'])
        ui.text(s, f.title, 'ARCANA ATELIER', (24, 12), COL['gold'])
        ui.text(s, f.s, '呪文を唱え、魔法動物を呼び、音で空間に絵を描く ― 音響魔術と共感覚のアトリエ（Python版）', (300, 22), COL['muted'])
        ui.panel(s, pygame.Rect(12, 64, 296, 824), 'GRIMOIRE', f, '20 glyphs')
        ui.text(s, f.s, 'ELEMENT', (24, 274), COL['gold']); ui.text(s, f.s, 'SCALE', (24, 388), COL['gold'])
        ui.text(s, f.s, 'RITUAL', (24, 498), COL['gold'])
        ui.panel(s, pygame.Rect(1092, 64, 336, 824), 'SPELLBOOK', f, 'formant chant')
        ui.text(s, f.s, 'BESTIARY', (1104, 332), COL['gold']); ui.text(s, f.s, f'{len(self.creatures)}/12', (1416, 332), COL['dim'], right=True)
        ui.text(s, f.s, 'TOOLS', (1104, 644), COL['gold'])
        if self.view == 'circle':
            ui.text(s, f.s, '魔法陣を描くと、その形が音色になります。', (1104, 666), COL['muted'])
            ui.text(s, f.s, '中央の円をドラッグして一筆書きで描く。', (1104, 686), COL['muted'])
            ui.text(s, f.s, '精霊の数を減らすと形も音も丸くなる。', (1104, 706), COL['muted'])
        # view
        pygame.draw.rect(s, (5, 4, 11), VIEW, border_radius=10)
        if self.view == 'circle':
            self.draw_circle(s, dt)
        elif self.view == '3d':
            E = world.ELEMENTS[self.element]
            self.sanct.draw(self.view3, self.now, dt, self.glyph, self.orb_world() if self.mode == 'cast' else None, E['col'],
                            self.now < self.cast_until or self.auto, self.creatures)
            sh = self.sanct.shake; self.sanct.shake *= 0.85
            s.blit(self.view3, (VIEW.x + random.uniform(-1, 1) * sh * 60, VIEW.y + random.uniform(-1, 1) * sh * 60))
            ui.text(s, f.s, f'{"空中に描く（右ドラッグで視点）" if self.tool3 == "air" else "ドラッグで回す・ホイールで寄る"}   魔法動物 {len(self.creatures)}/12   光 {min(self.sanct.n, MAXP)} 粒', (VIEW.x + 12, VIEW.y + 10), COL['muted'])
        else:
            _, r = self.view_to_canvas((0, 0))
            for i, c in enumerate([(58, 42, 18), (233, 199, 122), (122, 90, 34)]):
                pygame.draw.rect(s, c, r.inflate(16 - i * 4, 16 - i * 4), 3)
            s.blit(pygame.transform.smoothscale(self.canvas.surf, r.size), r.topleft)
        pygame.draw.rect(s, COL['line'], VIEW, 1, border_radius=10)
        if self.flash[1] > self.now:
            img = f.xl.render(self.flash[0], True, COL['gold'])
            s.blit(img, (VIEW.centerx - img.get_width() / 2, VIEW.y + VIEW.h * 0.4))
        # plate
        ui.text(s, f.l, self.spell_name(), (VIEW.centerx, 668), COL['gold'], center=True)
        E = world.ELEMENTS[self.element]
        ui.text(s, f.s, f'{E["sym"]}属性：{E["note"]}', (VIEW.centerx, 694), COL['muted'], center=True)
        ui.text(s, f.s, f'{world.SCALES[self.scale_key][0]}音階（{world.SCALES[self.scale_key][1]}） ・ 画布 {self.canvas.strokes} 筆 ・ 光 {min(self.sanct.n, MAXP)} 粒', (320, 822), COL['dim'])
        ui.text(s, f.s, 'キー A〜K で演奏 ・ Space で詠唱 ・ 1/2/3 で表示切替 ・ Esc でぜんぶ止める', (320, 842), COL['dim'])
        if self.toast[1] > self.now:
            ui.text(s, f.s, self.toast[0], (320, 862), COL['cyan'])
        # harmonics + scope
        self.draw_harmonics(s, pygame.Rect(24, 604, 272, 90))
        self.draw_scope(s, pygame.Rect(24, 772, 110, 110))
        if self.glyph:
            g = self.glyph
            ui.text(s, f.s, f'有効な倍音  {g.count} 本', (146, 772), COL['muted'])
            ui.text(s, f.s, f'基音の純度  {g.purity * 100:.0f} %', (146, 792), COL['muted'])
            ui.text(s, f.s, f'明るさ  {g.centroid * 440:.0f} Hz', (146, 812), COL['muted'])
            if g.purity < 0.05:
                ui.text(s, f.s, '基音なしでも高さが聞こえる', (146, 840), COL['gold'])
                ui.text(s, f.s, '＝ミッシング・ファンダメンタル', (146, 858), COL['gold'])
        # widgets
        mp = pygame.mouse.get_pos()
        for w_ in self.widgets:
            if hasattr(w_, 'draw_swatch') and w_.visible():
                pygame.draw.rect(s, w_.draw_swatch, w_.rect, border_radius=4)
                if w_.selected():
                    pygame.draw.rect(s, COL['fg'], w_.rect, 2, border_radius=4)
                continue
            w_.draw(s, f, hasattr(w_, 'rect') and w_.rect.collidepoint(mp))
        pygame.display.flip()

    def draw_circle(self, s, dt):
        cx, cy = VIEW.center
        R = min(VIEW.w, VIEW.h) * 0.43
        sc = R * 0.72
        rot = self.now / 24
        glow = min(1.0, self.glow)
        gold = tuple(int(c * (0.45 + 0.4 * glow)) for c in COL['gold'])
        pygame.draw.circle(s, gold, (cx, cy), int(R), 1)
        pygame.draw.circle(s, tuple(int(c * 0.5) for c in gold), (cx, cy), int(R * 0.9), 1)
        runes = 'ARCANA · ACOUSTICA · FOURIER · HRTF · HARMONIA · '
        for i, ch in enumerate(runes * 2):
            a = i / (len(runes) * 2) * 2 * math.pi + rot
            img = self.fonts.s.render(ch, True, gold)
            s.blit(img, (cx + math.sin(a) * R * 0.95 - img.get_width() / 2, cy - math.cos(a) * R * 0.95 - img.get_height() / 2))
        for i in range(48):
            a = i / 48 * 2 * math.pi + rot
            l = 9 if i % 4 == 0 else 4
            pygame.draw.line(s, gold, (cx + math.sin(a) * R * 0.9, cy - math.cos(a) * R * 0.9), (cx + math.sin(a) * (R * 0.9 - l), cy - math.cos(a) * (R * 0.9 - l)))
        hexa = [(cx + math.cos(-rot * 1.6 + k / 6 * 2 * math.pi) * R * 0.86, cy + math.sin(-rot * 1.6 + k / 6 * 2 * math.pi) * R * 0.86) for k in range(6)]
        pygame.draw.polygon(s, (60, 48, 110), hexa, 1)
        if self.drag and self.drag['kind'] == 'glyph' and len(self.drag['pts']) > 1:
            pygame.draw.lines(s, COL['gold'], False, [(cx + x * sc, cy + y * sc) for x, y in self.drag['pts']], 3)
        g = self.glyph
        if g is None:
            ui.text(s, self.fonts.m, '円の中をなぞって、魔法陣を描こう', (cx, VIEW.bottom - 30), COL['muted'], center=True)
            return
        pygame.draw.aalines(s, (60, 50, 30), True, [(cx + x * sc, cy + y * sc) for x, y in g.pts])
        pygame.draw.aalines(s, tuple(int(c * (0.4 + 0.3 * glow)) for c in COL['cyan']), True, [(cx + x * sc, cy + y * sc) for x, y in g.recon])
        speed = 1 / (2.2 if self.now < self.cast_until + 2 or self.auto else 7)
        self.epi_t = (self.epi_t + dt * speed) % 1
        pts = g.epicycles(self.epi_t)
        for k, ((x0, y0), (x1, y1)) in enumerate(zip(pts[:-1], pts[1:])):
            r = math.hypot(x1 - x0, y1 - y0) * sc
            if r > 1:
                pygame.draw.circle(s, (100, 78, 170) if k < 3 else (55, 45, 100), (int(cx + x0 * sc), int(cy + y0 * sc)), int(r), 1)
            pygame.draw.aaline(s, (150, 145, 180), (cx + x0 * sc, cy + y0 * sc), (cx + x1 * sc, cy + y1 * sc))
        M = len(g.recon)
        i0 = int(self.epi_t * M)
        tl = int(M * 0.85)
        for j in range(1, tl):
            a, b = g.recon[(i0 - j) % M], g.recon[(i0 - j + 1) % M]
            k = (1 - j / tl) * (0.6 + 0.4 * glow)
            col = tuple(int(c * k + 5 * (1 - k)) for c in COL['gold'])
            pygame.draw.line(s, col, (cx + a[0] * sc, cy + a[1] * sc), (cx + b[0] * sc, cy + b[1] * sc), max(1, int(3 * (1 - j / tl)) + 1))
        tip = pts[-1]
        pygame.draw.circle(s, COL['gold'], (int(cx + tip[0] * sc), int(cy + tip[1] * sc)), int(4 + 2 * glow))

    def draw_harmonics(self, s, r):
        ui.text(s, self.fonts.s, 'HARMONICS', (r.x, r.y - 18), COL['gold'])
        pygame.draw.rect(s, (8, 7, 22), r)
        if not self.glyph:
            return
        a = self.glyph.amps[:32]
        mx = a.max() or 1
        bw = r.w / 32
        for n, v in enumerate(a):
            db = max(0, 1 + 20 * math.log10(v / mx) / 48) if v > 0 else 0
            h = db * (r.h - 6)
            col = (int(157 + (245 - 157) * db), int(123 + (194 - 123) * db), int(255 + (107 - 255) * db))
            pygame.draw.rect(s, col, (r.x + n * bw + 1, r.bottom - h, max(1, bw - 2), h))

    def draw_scope(self, s, r):
        pygame.draw.rect(s, (8, 7, 22), r)
        pygame.draw.rect(s, COL['line'], r, 1)
        st = self.audio.last
        if st is None or len(st) < 4000:
            ui.text(s, self.fonts.s, 'SCOPE', (r.centerx, r.centery - 6), COL['dim'], center=True)
            return
        seg = st[2000:2000 + 2048]
        pk = np.abs(seg).max() or 1
        k = r.w * 0.45 / pk
        pts = [(r.centerx + L * k, r.centery + (R if self.mode == 'mirror' else -R) * k) for L, R in seg[::2]]
        pygame.draw.aalines(s, COL['gold'] if self.mode == 'mirror' else COL['cyan'], False, pts)

    # ------------------------------------------------------------- loop
    def run(self):
        running = True
        frames = 0
        while running:
            dt = min(0.1, self.clock.tick(FPS) / 1000)
            for ev in pygame.event.get():
                if not self.handle(ev):
                    running = False
            self.update(dt)
            self.draw(dt)
            frames += 1
            if self.headless_frames and frames >= self.headless_frames:
                running = False
        pygame.quit()


def main():
    App().run()
