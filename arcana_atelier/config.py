"""Shared constants: sample rate, window size, palette."""

SR = 44100            # audio sample rate (Hz)
W, H = 1440, 900      # window size (px)
FPS = 60

def hexrgb(h: str):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

COL = {
    'bg': (7, 6, 15), 'panel': (14, 12, 29), 'panel2': (21, 18, 48),
    'line': (36, 31, 71), 'line2': (54, 46, 102),
    'fg': (236, 230, 255), 'muted': (140, 133, 179), 'dim': (84, 77, 128),
    'gold': (245, 194, 107), 'violet': (157, 123, 255), 'cyan': (79, 227, 255),
    'rose': (255, 111, 168), 'stop': (255, 93, 122),
}
