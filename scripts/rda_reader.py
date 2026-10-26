"""Minimal reader for R .rda/.rds files (XDR format) -> pandas DataFrames."""
import gzip, bz2, lzma, struct, sys
import pandas as pd
import numpy as np

NA_INT = -2147483648


class R:
    def __init__(self, b):
        self.b = b; self.p = 0; self.refs = []

    def int(self):
        v = struct.unpack('>i', self.b[self.p:self.p + 4])[0]; self.p += 4; return v

    def ints(self, n):
        a = np.frombuffer(self.b, '>i4', n, self.p).astype('int64'); self.p += 4 * n; return a

    def reals(self, n):
        a = np.frombuffer(self.b, '>f8', n, self.p).astype('float64'); self.p += 8 * n; return a

    def item(self):
        flags = self.int()
        t = flags & 0xFF
        has_attr = bool(flags & (1 << 9)); has_tag = bool(flags & (1 << 10))
        if t == 254 or t == 0: return None  # NILVALUE
        if t in (242, 241, 253, 251, 252, 250): return ('ENV', t)
        if t == 255:
            idx = flags >> 8
            if idx == 0: idx = self.int()
            return self.refs[idx - 1]
        if t in (247, 249):  # namespace/package
            self.int(); n = self.int(); vals = [self.item() for _ in range(n)]
            v = ('NS', vals); self.refs.append(v); return v
        if t == 1:  # SYMSXP
            v = ('SYM', self.item()); self.refs.append(v); return v
        if t == 4:  # ENVSXP
            v = {'_env': True}; self.refs.append(v); self.int()
            enc = self.item(); fr = self.item(); hashtab = self.item(); attr = self.item()
            return v
        if t in (2, 3, 5, 6, 17):  # pairlist-like
            attr = self.item() if has_attr else None
            tag = self.item() if has_tag else None
            car = self.item(); cdr = self.item()
            out = [(tag[1] if isinstance(tag, tuple) and tag[0] == 'SYM' else tag, car)]
            if isinstance(cdr, PL): out += cdr.items
            return PL(out)
        if t == 9:  # CHARSXP
            n = self.int()
            if n == -1: return None
            s = self.b[self.p:self.p + n].decode('utf-8', 'replace'); self.p += n; return s
        if t in (10, 13):
            n = self.int(); v = self.ints(n)
            return self.wrap(v, has_attr, 'lgl' if t == 10 else 'int')
        if t == 14:
            n = self.int(); v = self.reals(n); return self.wrap(v, has_attr, 'real')
        if t == 16:
            n = self.int(); v = [self.item() for _ in range(n)]; return self.wrap(v, has_attr, 'str')
        if t in (19, 20):
            n = self.int(); v = [self.item() for _ in range(n)]; return self.wrap(v, has_attr, 'list')
        if t == 238:  # ALTREP
            info = self.item(); state = self.item(); attr = self.item()
            cls = info.items[0][1][1] if isinstance(info, PL) else None
            if cls == 'compact_intseq':
                n, start, step = state.v
                v = np.arange(int(start), int(start) + int(n) * int(step), int(step))
                return RV(v, 'int', attr)
            if cls == 'compact_realseq':
                n, start, step = state.v
                return RV(start + step * np.arange(int(n)), 'real', attr)
            if cls in ('wrap_integer', 'wrap_real', 'wrap_string', 'wrap_logical'):
                inner = state.v[0] if isinstance(state, RV) else state
                return inner
            if cls == 'deferred_string':
                arg = state.items[0][1] if isinstance(state, PL) else state
                vals = arg.v if isinstance(arg, RV) else arg
                return RV([str(int(x)) if isinstance(x, (int, np.integer)) else str(x) for x in vals], 'str', attr)
            raise ValueError(f'ALTREP {cls}')
        if t == 24:  # RAWSXP
            n = self.int(); v = self.b[self.p:self.p + n]; self.p += n; return self.wrap(v, has_attr, 'raw')
        raise ValueError(f'unhandled type {t} at {self.p}')

    def wrap(self, v, has_attr, kind):
        attr = self.item() if has_attr else None
        return RV(v, kind, attr)


class PL:
    def __init__(self, items): self.items = items
    def get(self, k):
        for kk, v in self.items:
            if kk == k: return v


class RV:
    def __init__(self, v, kind, attr): self.v = v; self.kind = kind; self.attr = attr
    def a(self, k): return self.attr.get(k) if isinstance(self.attr, PL) else None


def to_py(x):
    if isinstance(x, RV):
        if x.kind == 'list':
            names = x.a('names'); cls = x.a('class')
            clsv = list(cls.v) if isinstance(cls, RV) else []
            if 'data.frame' in clsv:
                cols = {}
                for nm, col in zip(names.v, x.v): cols[nm] = col_to_series(col)
                return pd.DataFrame(cols)
            return {n: to_py(c) for n, c in zip(names.v if names else range(len(x.v)), x.v)}
        return col_to_series(x)
    return x


def col_to_series(c):
    if not isinstance(c, RV): return c
    lv = c.a('levels'); cls = c.a('class')
    clsv = list(cls.v) if isinstance(cls, RV) else []
    if c.kind in ('int', 'lgl'):
        v = c.v.astype('float64'); v[c.v == NA_INT] = np.nan
        if lv is not None:
            levels = list(lv.v)
            return pd.Series([levels[int(i) - 1] if not np.isnan(i) else None for i in v])
        if c.kind == 'lgl': return pd.Series(v)
        return pd.Series(v)
    if c.kind == 'real':
        s = pd.Series(c.v)
        if 'Date' in clsv: return pd.to_datetime(s, unit='D', origin='1970-01-01', errors='coerce')
        return s
    if c.kind == 'str': return pd.Series(c.v)
    return pd.Series([to_py(e) for e in c.v])


def read(path):
    raw = open(path, 'rb').read()
    if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
    elif raw[:3] == b'BZh': raw = bz2.decompress(raw)
    elif raw[:6] == b'\xfd7zXZ\x00': raw = lzma.decompress(raw)
    rda = raw[:5] in (b'RDX2\n', b'RDX3\n')
    if rda: raw = raw[5:]
    assert raw[:2] == b'X\n', raw[:10]
    r = R(raw[2:])
    ver = r.int(); r.int(); r.int()
    if ver == 3:
        n = r.int(); r.p += n
    obj = r.item()
    if rda:
        return {k: to_py(v) for k, v in obj.items}
    return to_py(obj)


if __name__ == '__main__':
    out = read(sys.argv[1])
    for k, v in (out.items() if isinstance(out, dict) else [('obj', out)]):
        print(k, type(v), getattr(v, 'shape', ''))
        if isinstance(v, pd.DataFrame): print(v.head(5).to_string()); print(v.dtypes.to_string())
