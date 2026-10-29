"""Sound synthesis, written from scratch with numpy.

Everything here returns float arrays in [-1, 1]: mono shape (n,), stereo (n, 2).
- wavetable notes from a glyph's Fourier series
- a binaural spatializer (Woodworth ITD + Brown & Duda style head shadow + rear shading)
- a stereo reverb (exponentially decaying noise impulse response, FFT convolution)
- formant "chant" synthesis for spells (additive harmonics shaped by vowel resonances)
- the calls of the magical creatures
"""
import math
import numpy as np
from .config import SR

RNG = np.random.default_rng()


def mtof(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tsec(dur):
    return np.arange(int(dur * SR)) / SR


# ---------------------------------------------------------------- envelopes / filters
def adsr(n, a=0.012, d=0.25, s=0.6, r=0.18):
    e = np.ones(n) * s
    na, nd, nr = int(a * SR), int(d * SR), int(r * SR)
    na = min(na, n); e[:na] = np.linspace(0, 1, na, endpoint=False)
    nd = min(nd, n - na)
    if nd > 0:
        e[na:na + nd] = np.linspace(1, s, nd)
    nr = min(nr, n)
    if nr > 0:
        e[-nr:] *= np.linspace(1, 0, nr)
    return e


def perc(n, attack=0.004, decay=0.4):
    t = np.arange(n) / SR
    e = np.exp(-t / max(decay, 1e-3) * 5)
    na = max(1, int(attack * SR))
    e[:na] *= np.linspace(0, 1, na)
    return e


def fft_filter(x, H_of_f):
    n = len(x)
    if n == 0:
        return x
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    return np.fft.irfft(X * H_of_f(f), n)


def bandpass(x, fc, q=1.0):
    bw = fc / q
    return fft_filter(x, lambda f: 1 / np.sqrt(1 + ((f - fc) / bw) ** 2))


def lowpass(x, fc):
    return fft_filter(x, lambda f: 1 / np.sqrt(1 + (f / fc) ** 4))


def shelf(x, fc, g_high):
    """1 at low frequencies, g_high above fc (smooth first-order transition)."""
    return fft_filter(x, lambda f: 1 + (g_high - 1) * (f ** 2 / (f ** 2 + fc ** 2)))


# ---------------------------------------------------------------- oscillators
def wavetable_osc(table, f, dur, vib_cents=0.0, vib_rate=5.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    inst = f * 2 ** (vib_cents * np.sin(2 * np.pi * vib_rate * t) / 1200)
    ph = np.cumsum(inst) / SR % 1.0 * len(table)
    i0 = ph.astype(int)
    fr = ph - i0
    return table[i0] * (1 - fr) + table[(i0 + 1) % len(table)] * fr


def glide(f0, f1, dur, partials=((1, 1.0),), attack=0.01, decay=None):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = f0 * (f1 / f0) ** (t / max(dur, 1e-3))
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = sum(a * np.sin(r * ph) for r, a in partials)
    env = perc(n, attack, decay or dur) if decay else adsr(n, attack, dur * 0.3, 0.7, dur * 0.4)
    return y * env


def noise(n):
    return RNG.uniform(-1, 1, n)


def delayed(x, sec):
    return np.r_[np.zeros(int(sec * SR)), x]


def pad(x, n):
    return np.pad(x, (0, max(0, n - len(x))))[:n]


def mix(*parts):
    n = max(len(p) for p in parts)
    return sum(pad(p, n) for p in parts)


def normalize(x, peak=0.9):
    m = np.max(np.abs(x)) if len(x) else 0
    return x * (peak / m) if m > 1e-9 else x


# ---------------------------------------------------------------- spatial audio
HEAD_A = 0.0875   # head radius (m)
C_SND = 343.0


def spatialize(mono, az, el=0.0, dist=1.5):
    """Binaural rendering of a mono signal at azimuth az (deg, + = right),
    elevation el (deg) and distance dist (m)."""
    az_r, el_r = math.radians(az), math.radians(el)
    x = math.cos(el_r) * math.sin(az_r)          # +1 = right ear axis
    z = math.cos(el_r) * math.cos(az_r)          # +1 = in front
    lat = math.asin(max(-1, min(1, x)))
    itd = HEAD_A / C_SND * (abs(lat) + math.sin(abs(lat)))   # Woodworth
    shift = int(round(itd * SR))
    fsh = C_SND / (math.pi * HEAD_A)                         # head-shadow corner

    def ear(cos_theta):
        th = math.degrees(math.acos(max(-1, min(1, cos_theta))))
        alpha = 1.05 + 0.95 * math.cos(min(th, 150) / 150 * math.pi)   # Brown & Duda
        return shelf(mono, fsh, max(0.1, alpha))

    L, R = ear(-x), ear(x)
    if z < 0:                                                # pinna shading from behind
        g = 10 ** (-9 * (-z) / 20)
        L, R = shelf(L, 3000, g), shelf(R, 3000, g)
    if el > 20:                                              # crude elevation cue: brighter
        L, R = shelf(L, 7000, 1 + el / 120), shelf(R, 7000, 1 + el / 120)
    n = len(mono) + shift
    Lp, Rp = np.zeros(n), np.zeros(n)
    if x >= 0:   # source on the right: left ear is late
        Rp[:len(R)] = R; Lp[shift:shift + len(L)] = L
    else:
        Lp[:len(L)] = L; Rp[shift:shift + len(R)] = R
    g = 1.0 / max(1.0, dist)
    return np.stack([Lp, Rp], 1) * g


_IR = {}


def impulse_response(seconds):
    key = round(seconds, 2)
    if key not in _IR:
        n = int(seconds * SR)
        t = np.arange(n) / SR
        decay = np.exp(-6.91 * t / seconds)
        ir = np.stack([noise(n) * decay, noise(n) * decay], 1)
        ir = np.stack([lowpass(ir[:, 0], 6000), lowpass(ir[:, 1], 6000)], 1)
        ir /= np.sqrt((ir ** 2).sum(0, keepdims=True)) + 1e-9
        _IR[key] = ir
    return _IR[key]


def reverb(stereo, seconds=1.5, wet=0.3):
    """Dry + convolved wet. The IR has unit energy, so `wet` is the
    reverberant-to-direct amplitude ratio."""
    if wet <= 0:
        return stereo
    ir = impulse_response(seconds)
    n = len(stereo) + len(ir) - 1
    nfft = 1 << (n - 1).bit_length()
    out = np.zeros((n, 2))
    for c in range(2):
        mono_in = stereo.mean(1)
        out[:, c] = np.fft.irfft(np.fft.rfft(mono_in, nfft) * np.fft.rfft(ir[:, c], nfft), nfft)[:n]
    out *= wet
    out[:len(stereo)] += stereo
    return out


def comb(stereo, delay=0.0113, fb=0.6, taps=8):
    out = stereo.copy()
    d = int(delay * SR)
    pad_n = d * taps
    out = np.vstack([out, np.zeros((pad_n, 2))])
    for k in range(1, taps + 1):
        out[k * d:k * d + len(stereo)] += stereo * (fb ** k) * 0.55
    return out


# ---------------------------------------------------------------- spell chant (formant synthesis)
VOWELS = {'a': (800, 1200, 2500), 'i': (300, 2300, 3000), 'u': (350, 1300, 2400),
          'e': (500, 1900, 2500), 'o': (500, 800, 2400), 'n': (280, 1000, 2300)}
F_BW = (90, 120, 180)
F_GAIN = (1.0, 0.55, 0.3)


def chant(syllables, scale_midis, seed=0):
    """Sing a spell. `syllables` come from world.syllables(); returns mono."""
    rng = np.random.default_rng(seed)
    base = 0.24
    segs = []   # (dur, vowel or None, consonant, midi)
    deg = 4
    voiced = [s for s in syllables if 'pause' not in s]
    k = 0
    for s in syllables:
        if 'pause' in s:
            segs.append((s['pause'], None, '', None)); continue
        k += 1
        last = k == len(voiced)
        deg = 0 if last else int(np.clip(deg + rng.choice([-2, -1, -1, 1, 1, 2, 0]), 0, 7))
        d = base * s['len'] * (2.4 if last else 1)
        segs.append((d, s['v'], s['c'], scale_midis[deg] - 12))
    total = sum(d for d, *_ in segs) + 0.5
    n = int(total * SR)
    f0 = np.full(n, 110.0)
    F = np.zeros((3, n)); F[:] = np.array(VOWELS['a'])[:, None]
    amp = np.zeros(n)
    cons = np.zeros(n)
    i = 0
    last_f, last_F = 110.0, np.array(VOWELS['a'], float)
    for d, v, c, m in segs:
        j = min(n, i + int(d * SR))
        if v is None:
            f0[i:j] = last_f; F[:, i:j] = last_F[:, None]
        else:
            if c:
                cl = int((0.06 if c == 'f' else 0.025) * SR)
                burst = bandpass(noise(cl), 4200 if c == 'f' else 1800, 1.2) * perc(cl, 0.002, 0.05)
                cons[i:i + cl] += burst[:max(0, min(cl, n - i))] * (0.5 if c == 'f' else 0.8)
            last_f = mtof(m); last_F = np.array(VOWELS[v], float)
            f0[i:j] = last_f; F[:, i:j] = last_F[:, None]
            amp[i:j] = 0.45 if v == 'n' else 1.0
        i = j
    f0[i:] = last_f; F[:, i:] = last_F[:, None]
    # smooth pitch, formants and amplitude (~30 ms) for legato singing
    ker = np.ones(int(0.03 * SR)); ker /= ker.sum()
    sm = lambda a: np.convolve(a, ker, 'same')
    f0 = sm(f0); amp = sm(amp); F = np.vstack([sm(F[r]) for r in range(3)])
    t = np.arange(n) / SR
    f0v = f0 * (1 + 0.012 * np.sin(2 * np.pi * 5.4 * t))
    out = np.zeros(n)
    for ratio, level in ((1.0, 1.0), (1.5, 0.35)):           # a voice and a fifth above
        ph = 2 * np.pi * np.cumsum(f0v * ratio) / SR
        fk = f0v * ratio
        for h in range(1, 41):
            fh = fk * h
            if np.all(fh > 6000):
                break
            A = sum(g / (1 + ((fh - F[r]) / F_BW[r]) ** 2) for r, g in enumerate(F_GAIN))
            out += level * A * np.sin(h * ph) / h ** 0.6 * (fh < 6000)
    out = normalize(out * amp, 0.7) + cons * 0.25
    return out


# ---------------------------------------------------------------- creature calls
def bell(f, dur=2.6, partials=((1, 1), (2.76, 0.5), (5.4, 0.3), (8.93, 0.15)), gain=1.0):
    t = tsec(dur)
    return gain * sum(a * np.sin(2 * np.pi * f * r * t) * np.exp(-t * (1.2 + r * 0.6)) for r, a in partials) * perc(len(t), 0.003, dur)


def kick(f0=95, f1=42, dur=0.3):
    return glide(f0, f1, dur, attack=0.002, decay=dur * 0.6)


def clicks(n=12, gap=0.028, freq=5000):
    out = np.zeros(int((n * gap + 0.05) * SR))
    for k in range(n):
        i = int(k * gap * SR)
        c = bandpass(noise(400), freq, 2) * perc(400, 0.0005, 0.006)
        out[i:i + 400] += c
    return out


def crackle(dur=1.2):
    n = int(dur * SR)
    out = np.zeros(n)
    for _ in range(int(60 * dur)):
        i = RNG.integers(0, n - 300)
        out[i:i + 300] += noise(300) * np.exp(-np.arange(300) / 40) * RNG.uniform(0.3, 1)
    return out


def creature_call(cid, scale, loud=False):
    """Return a mono call for creature `cid` using the current scale (midi list)."""
    deg = int(RNG.integers(0, 8))
    f = mtof(scale[deg])
    if cid == 'lumiel':
        return mix(*[delayed(glide(2600 + RNG.random() * 900, 4300 + RNG.random() * 700, 0.07, attack=0.003, decay=0.07), k * 0.12)
                     for k in range(2 + int(RNG.integers(0, 3)))]) * 0.5
    if cid == 'fox':
        return glide(f * 0.75, f * 0.6, 0.8, partials=[(n + 1, 1 / (n + 1)) for n in range(9)], attack=0.03) * 0.5
    if cid == 'whale':
        return glide(150 + RNG.random() * 40, 85, 3.2, partials=((1, 1), (2.01, 0.35), (3.02, 0.12)), attack=0.8)
    if cid == 'phoenix':
        notes = []
        for k, d in enumerate((0, 2, 4, 7)):
            fm = mtof(scale[min(7, (deg + d) % 8)] + 12)
            notes.append(delayed(glide(fm, fm, 0.25, partials=((1, 1), (3, 0.11), (5, 0.04)), attack=0.005, decay=0.25), k * 0.09))
        return mix(*notes) * 0.5
    if cid == 'jelly':
        return bell(f * 2) * 0.45
    if cid == 'drako':
        roar = glide(105, 70, 1.1, partials=[(n, 1 / n) for n in range(1, 12)], attack=0.05) * 0.4 if (loud or RNG.random() < 0.12) else np.zeros(1)
        return mix(kick(), roar)
    if cid == 'hare':
        return mix(*[delayed(bell(2200 + RNG.random() * 1400, 0.25, ((1, 1), (2.4, 0.4), (3.9, 0.2))), k * 0.035) for k in range(5)]) * 0.3
    if cid == 'fly':
        n = 6 if loud else 1 + int(RNG.integers(0, 2))
        out = []
        for k in range(n):
            fm = mtof(scale[[0, 2, 4, 5, 7][int(RNG.integers(0, 5))]] + 24)
            out.append(delayed(np.sin(2 * np.pi * fm * tsec(0.5)) * perc(int(0.5 * SR), 0.01, 0.4), k * 0.12))
        return mix(*out) * 0.25
    if cid == 'ryu':
        a, b = f, mtof(scale[min(7, deg + 2)])
        tone = glide(a, b, 1.6, partials=((1, 1), (2, 0.15)), attack=0.25)
        breath = bandpass(noise(len(tone)), a * 2, 3) * adsr(len(tone), 0.2, 0.4, 0.6, 0.5) * 0.25
        return tone * 0.7 + breath
    if cid == 'owl':
        h1 = glide(390, 350, 0.45, partials=((1, 1), (2, 0.12)), attack=0.05)
        h2 = glide(370, 330, 0.7, partials=((1, 1), (2, 0.12)), attack=0.06)
        return mix(h1, delayed(h2, 0.6)) * 0.8
    if cid == 'dolphin':
        return mix(clicks(), delayed(glide(6000, 9500, 0.35, attack=0.02) * 0.25, 0.45), delayed(glide(9500, 7000, 0.3, attack=0.02) * 0.25, 0.8))
    if cid == 'turtle':
        return bell(98, 6.0, ((1, 1), (2.0, 0.5), (2.76, 0.45), (4.07, 0.3), (5.4, 0.2), (6.9, 0.1)))
    return np.zeros(1)
