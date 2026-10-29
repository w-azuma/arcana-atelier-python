"""The magical world: elements, scales, spells, the spell parser and the creatures."""
import math
from .config import hexrgb

ELEMENTS = {
    'fire':  dict(sym='火', name='焔', col=hexrgb('#ff7a45'), noun='焔歌', ir=0.7, wet=0.18, lp=3800, note='螺旋を描いて頭上へ立ちのぼり、爆ぜる。残響は短く乾いている。'),
    'water': dict(sym='水', name='水', col=hexrgb('#46b8ff'), noun='水鏡', ir=2.4, wet=0.55, lp=6000, vib=25, note='前方でゆらめき、音程がさざ波のように揺れる。深い残響。'),
    'wind':  dict(sym='風', name='風', col=hexrgb('#7dffcb'), noun='風詠み', ir=1.2, wet=0.30, lp=14000, doppler=True, note='楕円軌道で頭のまわりを駆け抜け、ドップラー効果で音程が上下する。'),
    'bolt':  dict(sym='雷', name='雷', col=hexrgb('#ffe45c'), noun='雷鳴', ir=3.4, wet=0.50, lp=14000, echo=True, jump=True, note='一音ごとに瞬間移動し、山びこのようなエコーを残す。'),
    'ice':   dict(sym='氷', name='氷', col=hexrgb('#b8f1ff'), noun='氷晶', ir=1.6, wet=0.35, lp=16000, comb=True, note='斜め上で凍りつき、短い反射が重なる金属的なきらめき。'),
    'light': dict(sym='光', name='光', col=hexrgb('#fff3c4'), noun='聖光', ir=4.2, wet=0.60, lp=16000, layer=2.0, note='頭上高くを巡り、1オクターブ上が重なる。聖堂の長い残響。'),
    'dark':  dict(sym='闇', name='闇', col=hexrgb('#b46cff'), noun='冥響', ir=3.0, wet=0.45, lp=1400, layer=0.5, note='背後の低い位置を這い、1オクターブ下とこもった響き。'),
    'earth': dict(sym='地', name='大地', col=hexrgb('#c9a46b'), noun='地鳴り', ir=1.0, wet=0.25, lp=2600, note='足もとから響き、重い足音のリズムで揺れる。'),
}

SCALES = {
    'penta':  ('五音', 'マイナーペンタ', [0, 3, 5, 7, 10, 12, 15, 17]),
    'yo':     ('陽', '民謡の陽音階', [0, 2, 5, 7, 9, 12, 14, 17]),
    'miyako': ('都節', 'さくらの音階', [0, 1, 5, 7, 8, 12, 13, 17]),
    'ryukyu': ('琉球', '沖縄音階', [0, 4, 5, 7, 11, 12, 16, 17]),
    'whole':  ('全音', 'ホールトーン', [0, 2, 4, 6, 8, 10, 12, 14]),
    'arab':   ('砂漠', 'ダブルハーモニック', [0, 1, 4, 5, 7, 8, 11, 12]),
}
NOTE_JP = ['ラ', 'ラ#', 'シ', 'ド', 'ド#', 'レ', 'レ#', 'ミ', 'ファ', 'ファ#', 'ソ', 'ソ#']


def scale_midis(key):
    return [57 + o for o in SCALES[key][2]]


def orb_position(element, t, orb):
    """Where the spell's sound is, relative to the listener: (az deg, el deg, dist m)."""
    az, el, d = orb
    if element == 'fire':
        return (((t * 100) % 360) - 180, -15 + ((t * 22) % 75), 1.4 + 0.2 * math.sin(t * 3))
    if element == 'water':
        return (math.sin(t * 0.5) * 110, 12 * math.sin(t * 1.1), 2 + 0.6 * math.sin(t * 0.7))
    if element == 'wind':
        w = t * 2.2; x = 3.2 * math.sin(w); z = -1.1 * math.cos(w)
        return (math.degrees(math.atan2(x, -z)), 8 * math.sin(t * 1.7), math.hypot(x, z))
    if element == 'ice':
        return (35 + 3 * math.sin(t * 0.7), 30 + 2 * math.sin(t * 1.3), 1.6)
    if element == 'light':
        return (((t * 45) % 360) - 180, 62 + 8 * math.sin(t * 0.8), 2.2)
    if element == 'dark':
        a = 180 + 60 * math.sin(t * 0.35)
        return (a - 360 if a > 180 else a, -35 + 8 * math.sin(t * 0.9), 2.6 + 0.4 * math.sin(t * 0.5))
    if element == 'earth':
        step = math.floor(t / 0.5); ph = (t % 0.5) / 0.5
        return (math.sin(step * 0.9) * 40, -55 + 6 * math.exp(-ph * 6), 1.8 + 0.6 * math.sin(step * 0.7))
    return (az, el, d)   # bolt: set on each note


# ---------------------------------------------------------------- spells
SPELLS = [
    ('ルミナ・ソノーラ', 'light', '光の音を放ち、空中に光の花を咲かせる'),
    ('イグニス・カンタ', 'fire', '炎の歌。音が螺旋を描いて燃え上がる'),
    ('アクア・レゾナ', 'water', '水の共鳴。音が波紋のように揺れ広がる'),
    ('ヴェントゥス・アリア', 'wind', '風の旋律。音が頭のまわりを駆け抜ける'),
    ('グラキエス・トナーレ', 'ice', '氷の響き。音が結晶になって凍りつく'),
    ('フルメン・トニトルス', 'bolt', '雷鳴。音が稲妻のように飛び移る'),
    ('ノクス・ウンブラ', 'dark', '夜の影。低く暗い響きが背後を這う'),
    ('テラ・グラーヴェ', 'earth', '大地の重み。足もとから地鳴りが響く'),
    ('ピンゲ・カエルム', 'fx:paint', '魔法動物が絵を描くのを始める／止める'),
    ('コルス・オムニア', 'fx:chorus', '呼んだ魔法動物が一斉に鳴く'),
    ('レクイエス', 'fx:rest', '魔法動物を帰し、静けさを取り戻す'),
]

ROW = {'a': 'アカサタナハマヤラワガザダバパャァ', 'i': 'イキシチニヒミリギジヂビピィ', 'u': 'ウクスツヌフムユルグズヅブプュゥヴ',
       'e': 'エケセテネヘメレゲゼデベペェ', 'o': 'オコソトノホモヨロヲゴゾドボポョォ'}
PLOS = 'カキクケコガギグゲゴタチツテトダヂヅデドパピプペポバビブベボ'
FRIC = 'サシスセソザジズゼゾハヒフヘホヴ'


def to_kata(t):
    return ''.join(chr(ord(c) + 0x60) if 0x3041 <= ord(c) <= 0x3096 else c for c in t)


def norm(t):
    return ''.join(c for c in to_kata(t) if c not in ' 　・、。.,!！?？ー-')


def vowel_of(ch):
    for v, row in ROW.items():
        if ch in row:
            return v
    return None


def syllables(text):
    """Kana or romaji -> list of {'v','c','len'} or {'pause'}."""
    t = to_kata(text.strip())
    out = []
    for i, ch in enumerate(t):
        lc = ch.lower()
        if ch in 'ャュョァィゥェォ' and out and 'pause' not in out[-1]:
            out[-1]['v'] = vowel_of(ch); continue
        if ch in 'ー〜~':
            if out and 'pause' not in out[-1]:
                out[-1]['len'] += 0.8
            continue
        if ch == 'ッ':
            out.append({'pause': 0.12}); continue
        if ch == 'ン':
            out.append({'v': 'n', 'c': '', 'len': 0.8}); continue
        if ch in ' 　・、。,.!！?？-':
            out.append({'pause': 0.18}); continue
        v = vowel_of(ch)
        if v:
            out.append({'v': v, 'c': 'p' if ch in PLOS else 'f' if ch in FRIC else '', 'len': 1.0}); continue
        if lc in 'aiueo':
            if out and out[-1].get('pending'):
                out[-1]['v'] = lc; out[-1]['pending'] = False
            else:
                out.append({'v': lc, 'c': '', 'len': 1.0})
            continue
        if 'a' <= lc <= 'z':
            nxt = t[i + 1].lower() if i + 1 < len(t) else ''
            if lc == 'n' and nxt not in 'aiueo':
                out.append({'v': 'n', 'c': '', 'len': 0.7}); continue
            if out and out[-1].get('pending'):
                continue
            out.append({'v': 'a', 'c': 'p' if lc in 'ptkbdgqc' else 'f' if lc in 'szfhvxj' else '', 'len': 1.0, 'pending': True})
    for s in out:
        s.pop('pending', None)
    return out


def text_hash(t):
    h = 7
    for c in t:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h


# ---------------------------------------------------------------- creatures
CREATURES = [
    dict(id='lumiel', name='リュミエル', kind='光の小鳥', col=hexrgb('#fff0b8'), el='light', every=1.4, d='8の字を描いて頭上を飛び、きらめく高音でさえずる'),
    dict(id='fox', name='ソナギツネ', kind='九尾の音狐', col=hexrgb('#ff9a5a'), el='fire', every=3.8, d='9本の尾は9本の倍音。倍音の和音で鳴く'),
    dict(id='whale', name='ソラクジラ', kind='空を泳ぐ鯨', col=hexrgb('#5ab4ff'), el='water', every=7.5, d='上空を回遊し、低く長い歌を響かせる'),
    dict(id='phoenix', name='フェニクス', kind='不死鳥', col=hexrgb('#ff5a3a'), el='fire', every=4.2, d='螺旋を描いて昇り、炎となって弾け、蘇る'),
    dict(id='jelly', name='ハーモクラゲ', kind='倍音クラゲ', col=hexrgb('#7af0ff'), el='ice', every=2.6, d='漂いながら、倍音のずれた鐘の音で光る'),
    dict(id='drako', name='ティンパノドラコ', kind='太鼓竜', col=hexrgb('#d8a35a'), el='earth', every=2.5, d='地面を踏み鳴らして太鼓のリズムを刻む'),
    dict(id='hare', name='ユキウサギ', kind='鈴の雪兎', col=hexrgb('#e8f6ff'), el='ice', every=2.2, d='跳ねるたびに首の鈴がシャラリと鳴る'),
    dict(id='fly', name='ホタルビ', kind='蛍火の群れ', col=hexrgb('#d4ff6a'), el='light', every=0.6, d='光の群れ。五音音階の小さな音を灯す'),
    dict(id='ryu', name='カゼリュウ', kind='風を渡る龍', col=hexrgb('#7dffcb'), el='wind', every=6.0, d='長い体で空を渡り、尺八のような息を響かせる'),
    dict(id='owl', name='ツキフクロウ', kind='月の梟', col=hexrgb('#c8b8ff'), el='dark', every=5.2, d='高い枝で首をかしげ、低くホー、ホーと鳴く'),
    dict(id='dolphin', name='ウタイルカ', kind='歌うイルカ', col=hexrgb('#46d0ff'), el='water', every=3.8, d='跳ねながら、反響定位のクリックと口笛で歌う'),
    dict(id='turtle', name='カネガメ', kind='鐘を背負う亀', col=hexrgb('#f5c26b'), el='earth', every=10.5, d='背中の釣り鐘を揺らし、深い鐘の音を響かせる'),
]
CREATURE_BY_ID = {c['id']: c for c in CREATURES}

_PERCH = [(-6, 4.2, -5), (6, 4.6, -4), (5, 3.8, 5), (-5, 4.4, 5), (0, 5.2, -8)]


def creature_pos(cid, t):
    """World position (x, y, z) in metres. y is height above the floor."""
    s, c = math.sin, math.cos
    if cid == 'lumiel': return (4.5 * s(0.7 * t), 3.6 + 0.6 * s(2.1 * t), 2.6 * s(1.4 * t))
    if cid == 'fox': a = t * 0.6; return (5 * c(a), abs(s(t * 4.2)) * 0.5 + 0.35, 5 * s(a))
    if cid == 'whale': a = t * 0.07; return (11 * c(a), 8.5 + s(t * 0.3), 11 * s(a))
    if cid == 'phoenix':
        p = (t % 11) / 11; a = p * math.pi * 4; r = 2.2 + p * 1.6
        return (r * c(a), 0.4 + p * 9, r * s(a))
    if cid == 'jelly': return (-3 + 1.6 * s(0.21 * t), 2.4 + 0.5 * s(1.1 * t), 3 + 1.6 * c(0.17 * t))
    if cid == 'drako': a = t * 0.22; return (6.5 * c(a), 0.55 + 0.08 * abs(s(t * math.pi * 2)), 6.5 * s(a))
    if cid == 'hare': return (3.2 * s(t * 0.31) + 1.2 * s(t * 0.83), 0.3 + 0.55 * abs(s(t * 3.1)), 3.2 * c(t * 0.27) + 1.2 * c(t * 0.71))
    if cid == 'fly': return (2.5 * s(0.3 * t), 1.8 + 0.5 * s(0.7 * t), -3 + 2 * c(0.25 * t))
    if cid == 'ryu': return (8 * s(0.23 * t), 5.2 + 2 * s(0.4 * t), 6 * s(0.31 * t + 1))
    if cid == 'owl':
        seg = int(t // 14); ph = (t % 14) / 14; a = _PERCH[seg % 5]; b = _PERCH[(seg + 1) % 5]
        if ph < 0.86: return a
        k = (ph - 0.86) / 0.14; e = k * k * (3 - 2 * k)
        return (a[0] + (b[0] - a[0]) * e, a[1] + (b[1] - a[1]) * e + s(math.pi * k) * 1.5, a[2] + (b[2] - a[2]) * e)
    if cid == 'dolphin': a = t * 0.45; return (7 * c(a), 0.3 + 1.8 * max(0.0, s(t * 1.3)), 7 * s(a))
    if cid == 'turtle': a = t * 0.05; return (3.6 * c(a), 0.45, 3.6 * s(a))
    return (0, 1, 0)
