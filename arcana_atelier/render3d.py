"""A tiny software 3D renderer for the Sanctuary.

No OpenGL: an orbit camera, a perspective projection done in numpy, wireframes
drawn with pygame lines, and a "light sculpture" of up to 30 000 points written
additively straight into the pixel array.
"""
import math
import numpy as np
import pygame
from .config import COL
from . import world

MAXP = 30000


class Camera:
    def __init__(self):
        self.theta, self.phi, self.r = 0.7, 1.12, 14.0
        self.target = np.array([0.0, 2.0, 0.0])
        self.fov = math.radians(55)

    @property
    def pos(self):
        return self.target + self.r * np.array([math.sin(self.phi) * math.sin(self.theta),
                                                 math.cos(self.phi),
                                                 math.sin(self.phi) * math.cos(self.theta)])

    def basis(self):
        f = self.target - self.pos
        f /= np.linalg.norm(f)
        r = np.cross(f, [0, 1, 0]); r /= np.linalg.norm(r)
        u = np.cross(r, f)
        return f, r, u

    def project(self, P, w, h):
        """P: (n,3) world points -> (sx, sy, depth, visible) for a w x h view."""
        P = np.atleast_2d(np.asarray(P, float))
        f, r, u = self.basis()
        d = P - self.pos
        z = d @ f; x = d @ r; y = d @ u
        s = (h / 2) / math.tan(self.fov / 2)
        vis = z > 0.1
        zz = np.where(vis, z, 1)
        return w / 2 + x / zz * s, h / 2 - y / zz * s, z, vis

    def ray(self, sx, sy, w, h):
        f, r, u = self.basis()
        s = (h / 2) / math.tan(self.fov / 2)
        d = f + r * (sx - w / 2) / s + u * (h / 2 - sy) / s
        return self.pos, d / np.linalg.norm(d)


def ring(cx, cy, cz, rx, ry, rz, axis='y', n=24):
    a = np.linspace(0, 2 * math.pi, n + 1)
    if axis == 'y':
        return np.c_[cx + rx * np.cos(a), np.full(n + 1, cy), cz + rz * np.sin(a)]
    if axis == 'x':
        return np.c_[np.full(n + 1, cx), cy + ry * np.cos(a), cz + rz * np.sin(a)]
    return np.c_[cx + rx * np.cos(a), cy + ry * np.sin(a), np.full(n + 1, cz)]


def ellipsoid(rx, ry, rz, n=18):
    return [ring(0, 0, 0, rx, ry, rz, 'y', n), ring(0, 0, 0, rx, ry, rz, 'x', n), ring(0, 0, 0, rx, ry, rz, 'z', n)]


def creature_model(cid, t):
    """Local polylines (in metres, facing -z) for a creature at time t."""
    s = math.sin
    L = []
    if cid in ('lumiel', 'phoenix'):
        sc = 1.0 if cid == 'lumiel' else 1.8
        L += [x * sc for x in ellipsoid(0.08, 0.08, 0.22, 10)]
        flap = s(t * (18 if cid == 'lumiel' else 8)) * 0.35
        for side in (-1, 1):
            L.append(np.array([[0, 0, 0], [side * 0.5 * sc, flap * sc, 0.1 * sc], [side * 0.12 * sc, 0, 0.22 * sc], [0, 0, 0]]))
    elif cid == 'fox':
        L += [np.c_[x[:, 0], x[:, 1], x[:, 2]] for x in ellipsoid(0.28, 0.21, 0.52)]
        L += [x + [0, 0.25, -0.6] for x in ellipsoid(0.18, 0.18, 0.18, 12)]
        for k in range(9):
            a = (k - 4) * 0.28
            pts = [(math.sin(a) * j / 9 * 0.9 + s(t * 3 + j * 0.5 + k) * 0.15 * j / 9, 0.15 + j / 9 * 0.55, 0.5 + j / 9 * 0.6) for j in range(10)]
            L.append(np.array(pts))
    elif cid == 'whale':
        L += [x for x in ellipsoid(1.1, 1.0, 3.2, 24)]
        L.append(np.array([[0, 0, 3.0], [1.4, 0.15 * s(t), 3.9], [0, 0, 3.5], [-1.4, 0.15 * s(t), 3.9], [0, 0, 3.0]]))
    elif cid == 'jelly':
        a = np.linspace(0, math.pi, 13)
        for ang in np.linspace(0, math.pi, 4, endpoint=False):
            L.append(np.c_[0.55 * np.cos(a) * math.cos(ang), 0.55 * np.sin(a) * 0.8, 0.55 * np.cos(a) * math.sin(ang)])
        L.append(ring(0, 0, 0, 0.55, 0, 0.55))
        for k in range(8):
            q = k / 8 * 2 * math.pi
            L.append(np.array([(math.cos(q) * 0.35 + s(t * 2 + j * 0.6 + k) * 0.08 * j / 9, -j / 9 * 1.2, math.sin(q) * 0.35) for j in range(10)]))
    elif cid == 'drako':
        b = np.array([[-.4, -.25, -.7], [.4, -.25, -.7], [.4, .25, -.7], [-.4, .25, -.7], [-.4, -.25, -.7], [-.4, -.25, .7], [.4, -.25, .7], [.4, .25, .7], [-.4, .25, .7], [-.4, -.25, .7]])
        L += [b, np.array([[.4, -.25, -.7], [.4, -.25, .7]]), np.array([[.4, .25, -.7], [.4, .25, .7]]), np.array([[-.4, .25, -.7], [-.4, .25, .7]])]
        L += [x + [0, 0.25, -0.9] for x in ellipsoid(0.22, 0.2, 0.25, 10)]
        for k in range(4):
            L.append(np.array([[-0.1, 0.25, -0.4 + k * 0.3], [0, 0.6, -0.4 + k * 0.3], [0.1, 0.25, -0.4 + k * 0.3]]))
    elif cid == 'hare':
        L += ellipsoid(0.28, 0.25, 0.35, 12)
        L += [x + [0, 0.2, -0.3] for x in ellipsoid(0.17, 0.17, 0.17, 10)]
        for side in (-1, 1):
            L.append(np.array([[side * 0.07, 0.3, -0.3], [side * 0.12, 0.75, -0.25]]))
    elif cid == 'fly':
        for k in range(16):
            u = t * 0.9 + k * 1.7; rr = 0.4 + (k % 5) * 0.2
            p = np.array([math.sin(u * 1.3) * rr, math.sin(u * 0.9 + k) * 0.5, math.cos(u * 1.1) * rr])
            L.append(np.array([p, p + [0.02, 0.02, 0]]))
    elif cid == 'owl':
        L += ellipsoid(0.34, 0.45, 0.3, 14)
        L += [x + [0, 0.52, 0] for x in ellipsoid(0.28, 0.28, 0.28, 12)]
        for side in (-1, 1):
            L.append(ring(side * 0.11, 0.56, -0.25, 0.08, 0.08, 0, 'z', 10))
            L.append(np.array([[side * 0.12, 0.72, 0], [side * 0.17, 0.92, 0], [side * 0.22, 0.74, 0]]))
    elif cid == 'dolphin':
        L += ellipsoid(0.28, 0.24, 0.8, 16)
        L.append(np.array([[0, 0.2, 0], [0, 0.55, 0.15], [0, 0.2, 0.3]]))
        L.append(np.array([[0, 0, 0.75], [0.45, 0, 1.05], [-0.45, 0, 1.05], [0, 0, 0.75]]))
    elif cid == 'turtle':
        a = np.linspace(0, math.pi / 2, 9)
        for ang in np.linspace(0, math.pi, 4, endpoint=False):
            L.append(np.c_[0.75 * np.cos(a) * math.cos(ang), 0.5 * np.sin(a), 0.9 * np.cos(a) * math.sin(ang)])
            L.append(np.c_[-0.75 * np.cos(a) * math.cos(ang), 0.5 * np.sin(a), -0.9 * np.cos(a) * math.sin(ang)])
        L.append(ring(0, 0, 0, 0.75, 0, 0.9))
        L += [x + [0, 0.1, -1.0] for x in ellipsoid(0.18, 0.15, 0.2, 10)]
        sw = math.sin(t * 1.6) * 0.25
        L.append(np.array([[0, 0.5, 0], [math.sin(sw) * 0.6, 0.5 + math.cos(sw) * 0.6, 0]]))
        L.append(ring(math.sin(sw) * 0.55, 0.5 + math.cos(sw) * 0.5, 0, 0.25, 0, 0.25, 'y', 16))
    elif cid == 'ryu':
        pass   # drawn from its trail history
    return L


class Sanctuary:
    def __init__(self):
        self.cam = Camera()
        self.pts = np.zeros((MAXP, 3), np.float32)
        self.cols = np.zeros((MAXP, 3), np.float32)
        self.n = 0
        self.bursts = []        # dicts with pos, vel, col, life
        self.spin = True
        rng = np.random.default_rng(42)
        th = rng.uniform(0, 2 * math.pi, 700); ph = np.arccos(rng.uniform(-0.2, 1, 700)); d = rng.uniform(60, 110, 700)
        self.stars = np.c_[d * np.sin(ph) * np.cos(th), np.abs(d * np.cos(ph)) + 5, d * np.sin(ph) * np.sin(th)]
        self.shake = 0.0

    # --- light sculpture ---
    def sculpt(self, p, col, n=1, spread=0.0):
        for _ in range(n):
            i = self.n % MAXP
            self.pts[i] = np.asarray(p) + (np.random.uniform(-0.5, 0.5, 3) * spread if spread else 0)
            b = 0.6 + 0.4 * np.random.random()
            self.cols[i] = np.asarray(col, float) * b
            self.n += 1

    def clear(self):
        self.n = 0

    def burst(self, p, col, n=60):
        v = np.random.normal(0, 1, (n, 3)); v /= np.linalg.norm(v, axis=1, keepdims=True)
        v *= np.random.uniform(0.6, 3.0, (n, 1))
        self.bursts.append(dict(p=np.tile(np.asarray(p, float), (n, 1)), v=v, col=np.asarray(col, float), life=1.0))

    # --- drawing ---
    def draw(self, surf, now, dt, glyph, orb_world, orb_col, active, creatures):
        w, h = surf.get_size()
        cam = self.cam
        if self.spin:
            cam.theta += dt * 0.05
        surf.fill((5, 4, 11))
        # stars
        sx, sy, z, vis = cam.project(self.stars, w, h)
        px = pygame.surfarray.pixels3d(surf)
        ok = vis & (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
        px[sx[ok].astype(int), sy[ok].astype(int)] = (150, 145, 190)
        del px
        # ground: polar grid
        for R in range(3, 19, 3):
            self._poly(surf, ring(0, 0, 0, R, 0, R, 'y', 72), (30, 25, 58) if R != 3 else (110, 88, 50), w, h)
        for k in range(24):
            a = k / 24 * 2 * math.pi
            self._poly(surf, np.array([[3 * math.cos(a), 0, 3 * math.sin(a)], [18 * math.cos(a), 0, 18 * math.sin(a)]]), (24, 20, 47), w, h)
        # the magic circle glowing on the floor
        if glyph is not None:
            rot = now * 0.08
            g = glyph.recon
            P = np.c_[(g[:, 0] * math.cos(rot) - g[:, 1] * math.sin(rot)) * 2.9, np.full(len(g), 0.03), (g[:, 0] * math.sin(rot) + g[:, 1] * math.cos(rot)) * 2.9]
            self._poly(surf, np.vstack([P, P[:1]]), COL['gold'], w, h, width=2)
        # light sculpture + bursts (additive pixels)
        n = min(self.n, MAXP)
        px = pygame.surfarray.pixels3d(surf)
        if n:
            self._add_points(px, self.pts[:n], self.cols[:n], w, h, glow=True)
        alive = []
        for b in self.bursts:
            b['life'] -= dt * 0.8
            if b['life'] <= 0:
                continue
            b['p'] += b['v'] * dt; b['v'][:, 1] -= 1.2 * dt
            self._add_points(px, b['p'], np.tile(b['col'] * b['life'], (len(b['p']), 1)), w, h, glow=False)
            alive.append(b)
        self.bursts = alive
        del px
        # creatures
        for cid, st in creatures.items():
            info = world.CREATURE_BY_ID[cid]
            pos, prev = st['pos'], st.get('prev', st['pos'])
            vx, vz = pos[0] - prev[0], pos[2] - prev[2]
            yaw = math.atan2(-vx, -vz) if abs(vx) + abs(vz) > 1e-5 else st.get('yaw', 0.0)
            st['yaw'] = yaw
            if cid == 'ryu' and st.get('hist'):
                hist = st['hist'][::3][:16]
                pts = np.array(hist)
                self._poly(surf, pts, info['col'], w, h, width=3)
                for k, p in enumerate(hist):
                    r = 0.42 * (1 - k / 18)
                    self._poly(surf, ring(p[0], p[1], p[2], r, r, r, 'z', 10), info['col'], w, h)
                continue
            cy, sy_ = math.cos(yaw), math.sin(yaw)
            for poly in creature_model(cid, now):
                P = np.asarray(poly, float)
                X = P[:, 0] * cy + P[:, 2] * sy_
                Z = -P[:, 0] * sy_ + P[:, 2] * cy
                self._poly(surf, np.c_[X + pos[0], P[:, 1] + pos[1], Z + pos[2]], info['col'], w, h)
        # spell orb
        if orb_world is not None:
            o = np.asarray(orb_world)
            r = 0.42 * (1.25 if active else 1.0)
            for ax in 'xyz':
                self._poly(surf, ring(o[0], o[1], o[2], r, r, r, ax, 16), orb_col, w, h)
            ox, oy, oz, ov = cam.project(o[None], w, h)
            if ov[0]:
                pygame.draw.circle(surf, (255, 255, 255), (int(ox[0]), int(oy[0])), max(2, int(160 / max(oz[0], 1))))

    def _poly(self, surf, P, col, w, h, width=1):
        sx, sy, z, vis = self.cam.project(P, w, h)
        for i in range(len(sx) - 1):
            if vis[i] and vis[i + 1]:
                a, b = (sx[i], sy[i]), (sx[i + 1], sy[i + 1])
                if max(abs(a[0]), abs(a[1]), abs(b[0]), abs(b[1])) < 1e5:
                    if width == 1:
                        pygame.draw.aaline(surf, col, a, b)
                    else:
                        pygame.draw.line(surf, col, a, b, width)

    def _add_points(self, px, P, C, w, h, glow):
        sx, sy, z, vis = self.cam.project(P, w, h)
        ok = vis & (sx >= 1) & (sx < w - 1) & (sy >= 1) & (sy < h - 1)
        xs, ys = sx[ok].astype(int), sy[ok].astype(int)
        c = C[ok]
        fade = np.clip(1.6 - z[ok] / 30, 0.3, 1.0)[:, None]
        c = c * fade
        px[xs, ys] = np.minimum(255, px[xs, ys] + c).astype(np.uint8)
        if glow:
            half = (c * 0.35)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                px[xs + dx, ys + dy] = np.minimum(255, px[xs + dx, ys + dy] + half).astype(np.uint8)
