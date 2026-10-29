"""Magic circles (glyphs): presets, resampling, DFT, epicycles, and the
waveform the glyph's shape turns into.

A glyph is a closed curve z(t) = x(t) + i y(t). Its complex Fourier series
    z(t) = sum_k c_k e^{i k t}
gives epicycles (one rotating circle per term) for the drawing, and the real
Fourier series of x(t) = Re z(t) gives the harmonics of the sound.
"""
import math
import random
import numpy as np

N = 256       # resampled points per glyph
KMAX = 64     # highest Fourier index kept


def resample(raw):
    pts = np.asarray(raw, float)
    pts = np.vstack([pts, pts[:1]])                       # close the curve
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(pts, axis=0).T))]
    L = seg[-1] or 1.0
    d = np.arange(N) / N * L
    x = np.interp(d, seg, pts[:, 0])
    y = np.interp(d, seg, pts[:, 1])
    x -= x.mean(); y -= y.mean()
    R = float(np.max(np.hypot(x, y))) or 1.0
    return np.c_[x / R, y / R]


def dft(pts):
    z = pts[:, 0] + 1j * pts[:, 1]
    ks = np.arange(-KMAX, KMAX + 1)
    j = np.arange(N)
    E = np.exp(-2j * np.pi * np.outer(ks, j) / N)
    return ks, E @ z / N


class Glyph:
    def __init__(self, raw, name):
        self.name = name
        self.pts = resample(raw)
        self.ks, self.c = dft(self.pts)
        self.set_spirits(24)

    def set_spirits(self, K):
        """Keep the K strongest Fourier terms ("spirits")."""
        mag = np.abs(self.c).copy()
        mag[self.ks == 0] = 0
        order = np.argsort(-mag)[:K]
        self.terms = [(int(self.ks[i]), complex(self.c[i])) for i in order if mag[i] > 1e-9]
        self.K = K
        self._harmonics()
        self.recon = self.reconstruct(220)
        self._tables = {}

    def _harmonics(self):
        H = KMAX
        xr, xi, yr, yi = (np.zeros(H + 1) for _ in range(4))
        for k, c in self.terms:
            n, s = abs(k), (1 if k > 0 else -1)
            # c e^{ikt}:  Re -> re cos(nt) - s*im sin(nt) ;  Im -> im cos(nt) + s*re sin(nt)
            xr[n] += c.real; xi[n] += -c.imag * s
            yr[n] += c.imag; yi[n] += c.real * s
        self.xr, self.xi, self.yr, self.yi = xr, xi, yr, yi
        amps = np.hypot(xr, xi)[1:]
        mx = amps.max() if amps.size else 0
        tot = float((amps ** 2).sum())
        self.amps = amps
        self.count = int((amps >= mx * 0.02).sum()) if mx > 0 else 0
        self.purity = float(amps[0] ** 2 / tot) if tot > 0 else 0.0
        self.centroid = float((np.arange(1, H + 1) * amps).sum() / (amps.sum() or 1))

    def reconstruct(self, M):
        t = np.arange(M) / M
        z = np.zeros(M, complex)
        for k, c in self.terms:
            z += c * np.exp(2j * np.pi * k * t)
        return np.c_[z.real, z.imag]

    def epicycles(self, t):
        """Centres of each spirit's circle at time t in [0,1)."""
        pts = [(0.0, 0.0)]
        z = 0j
        for k, c in self.terms:
            z += c * np.exp(2j * np.pi * k * t)
            pts.append((z.real, z.imag))
        return pts

    def table(self, comp='x', size=2048):
        """One period of x(t) (or y(t)) as a wavetable."""
        if comp in self._tables:
            return self._tables[comp]
        n = np.arange(1, KMAX + 1)[:, None]
        ph = 2 * np.pi * n * np.arange(size)[None, :] / size
        wx = (self.xr[1:, None] * np.cos(ph) + self.xi[1:, None] * np.sin(ph)).sum(0)
        wy = (self.yr[1:, None] * np.cos(ph) + self.yi[1:, None] * np.sin(ph)).sum(0)
        k = 1.0 / (max(np.max(np.abs(wx)), np.max(np.abs(wy))) or 1)   # x and y share one scale (for MIRROR)
        self._tables['x'] = wx / (np.max(np.abs(wx)) or 1)
        self._tables['xm'] = wx * k
        self._tables['ym'] = wy * k
        return self._tables[comp]


# ---------------------------------------------------------------- presets
def _poly(vs, per=24):
    out = []
    for i, v in enumerate(vs):
        w = vs[(i + 1) % len(vs)]
        for s in range(per):
            k = s / per
            out.append((v[0] + (w[0] - v[0]) * k, v[1] + (w[1] - v[1]) * k))
    return out


def _star(n, step, rot=-90):
    return _poly([(math.cos(math.radians(rot + i * 360 * step / n)),
                   math.sin(math.radians(rot + i * 360 * step / n))) for i in range(n)])


def _param(f, M=400):
    return [f(i / M * 2 * math.pi) for i in range(M)]


def _heart(t):
    return (16 * math.sin(t) ** 3, -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)))


def _inf(t):
    d = 1 + math.sin(t) ** 2
    return (math.cos(t) / d, math.sin(t) * math.cos(t) / d)


def _spiral(t):
    r = 0.12 + 0.88 * (1 - abs(t - math.pi) / math.pi)
    return (r * math.cos(4 * t), r * math.sin(4 * t))


def _moon():
    o = [(math.cos(math.radians(-110 + i * 220 / 200)), math.sin(math.radians(-110 + i * 220 / 200))) for i in range(201)]
    o += [(0.35 + 0.75 * math.cos(math.radians(110 - i * 220 / 200)), 0.85 * math.sin(math.radians(110 - i * 220 / 200))) for i in range(201)]
    return o


def _snow():
    v = [(math.cos(math.radians(-90 + i * 120)), math.sin(math.radians(-90 + i * 120))) for i in range(3)]
    for _ in range(3):
        nv = []
        for i, p in enumerate(v):
            q = v[(i + 1) % len(v)]
            d = ((q[0] - p[0]) / 3, (q[1] - p[1]) / 3)
            a = (p[0] + d[0], p[1] + d[1]); b = (p[0] + 2 * d[0], p[1] + 2 * d[1])
            ang = -math.pi / 3
            c = (a[0] + d[0] * math.cos(ang) - d[1] * math.sin(ang), a[1] + d[0] * math.sin(ang) + d[1] * math.cos(ang))
            nv += [p, a, c, b]
        v = nv
    return v


def _butterfly(t):
    T = t * 6
    r = math.exp(math.sin(T)) - 2 * math.cos(4 * T) + math.sin((2 * T - math.pi) / 24) ** 5
    return (r * math.sin(T), -r * math.cos(T))


def _eye():
    o = []
    for i in range(151):
        a = math.radians(-60 + i * 120 / 150)
        o.append((math.sin(a) * 1.0, -0.62 * math.cos(a) + 0.31))
    for i in range(151):
        a = math.radians(60 - i * 120 / 150)
        o.append((math.sin(a) * 1.0, 0.62 * math.cos(a) - 0.31))
    return o


def _rune():
    r = random.Random()
    n = 9 + r.randrange(6)
    return _poly([(math.cos(i / n * 2 * math.pi) * (0.35 + r.random() * 0.65),
                   math.sin(i / n * 2 * math.pi) * (0.35 + r.random() * 0.65)) for i in range(n)])


PRESETS = [
    ('○', '真円', lambda: _param(lambda t: (math.cos(t), math.sin(t)))),
    ('△', '三角', lambda: _star(3, 1)),
    ('□', '方陣', lambda: _star(4, 1, -45)),
    ('☆', '五芒', lambda: _star(5, 2)),
    ('✶', '七芒', lambda: _star(7, 3)),
    ('♡', '心臓', lambda: _param(_heart)),
    ('∞', '無限', lambda: _param(_inf)),
    ('✡', '六芒', lambda: _poly([(math.cos(math.radians(-90 + i * 60)), math.sin(math.radians(-90 + i * 60))) for i in (0, 2, 5, 3, 1, 4)])),
    ('✴', '八芒', lambda: _star(8, 3)),
    ('✹', '九芒', lambda: _star(9, 4)),
    ('✿', '花弁', lambda: _param(lambda t: (math.cos(5 * t) * math.cos(t), math.cos(5 * t) * math.sin(t)))),
    ('@', '螺旋', lambda: _param(_spiral, 600)),
    ('⌘', '双律', lambda: _param(lambda t: (math.sin(3 * t), math.sin(2 * t)))),
    ('☾', '三日月', _moon),
    ('❄', '雪華', _snow),
    ('⚙', '歯車', lambda: _param(lambda t: ((1 + 0.16 * math.tanh(6 * math.sin(12 * t))) * math.cos(t), (1 + 0.16 * math.tanh(6 * math.sin(12 * t))) * math.sin(t)), 800)),
    ('❂', '波紋', lambda: _param(lambda t: ((1 + 0.22 * math.sin(9 * t)) * math.cos(t), (1 + 0.22 * math.sin(9 * t)) * math.sin(t)), 600)),
    ('ᛤ', '胡蝶', lambda: _param(_butterfly, 1600)),
    ('◉', '瞳', _eye),
    ('ᛟ', '古き', _rune),
]


def make_preset(i):
    sym, name, f = PRESETS[i]
    return Glyph(f(), name)
