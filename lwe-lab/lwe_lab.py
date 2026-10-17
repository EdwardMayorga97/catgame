#!/usr/bin/env python3
"""
LWE Lab: laboratorio de Learning With Errors de punta a punta.

Simula el esquema de cifrado de Regev (la base de ML-KEM / Kyber):
  - generación de claves (cómo se guarda el secreto),
  - cifrado y descifrado (cómo se recupera el mensaje),
  - y los ataques, del más tonto al más sofisticado:
      0. sin errores  -> eliminación gaussiana (muestra por qué el error es el candado)
      1. fuerza bruta -> probar todos los secretos (q^n)
      2. Arora-Ge     -> linealización; polinomial si el error es pequeño y hay muchas muestras
      3. LLL          -> reducción de retículos (polinomial; falla cuando n crece frente a q)
      4. enumeración  -> vector más corto exacto tras LLL (exponencial; el corazón de BKZ)
      5. fuga         -> conocer parte del secreto reduce la dimensión del problema

Solo necesita numpy.

Uso:
  python3 lwe_lab.py demo                      # recorrido narrado con una instancia pequeña
  python3 lwe_lab.py scale                     # crece n y mide cada ataque
  python3 lwe_lab.py scale --q 3329 --ns 8,16,24,32
  python3 lwe_lab.py leak --n 40 --k 8         # qué pasa si se filtra parte del secreto
  python3 lwe_lab.py wave                      # ondas + pliegues + FFT (ataque dual) y su muro
  python3 lwe_lab.py selftest                  # comprobaciones internas
"""

import argparse
import itertools
import math
import sys
import time

import numpy as np


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def is_prime(n):
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True


def next_prime(n):
    while not is_prime(n):
        n += 1
    return n


def centered(x, q):
    """Representante de x mod q en el intervalo (-q/2, q/2]."""
    return ((np.asarray(x) + q // 2) % q) - q // 2


def fmt_count(log10):
    """Formatea una cantidad dada por su log10."""
    if log10 < 9:
        return f"{int(round(10 ** log10)):,}".replace(",", ".")
    return f"10^{log10:.0f}"


def fmt_time(sec=None, log10=None, short=False):
    """Formatea segundos. Para cantidades enormes se pasa log10 de los segundos."""
    if log10 is None:
        log10 = math.log10(sec) if sec > 0 else -9
    if log10 > 300:
        sec = float("inf")
    elif sec is None:
        sec = 10 ** log10
    if sec < 1e-3:
        return f"{sec * 1e6:.0f} µs"
    if sec < 1:
        return f"{sec * 1e3:.0f} ms"
    if sec < 60:
        return f"{sec:.1f} s"
    if sec < 3600:
        return f"{sec / 60:.1f} min"
    if sec < 86400:
        return f"{sec / 3600:.1f} h"
    if sec < 365.25 * 86400:
        return f"{sec / 86400:.0f} días"
    log10_years = log10 - math.log10(365.25 * 86400)
    if log10_years < 4:
        return f"{10 ** log10_years:,.0f} años".replace(",", ".")
    log10_universe = math.log10(1.38e10)
    if log10_years > log10_universe and not short:
        return f"10^{log10_years:.0f} años (10^{log10_years - log10_universe:.0f} veces la edad del universo)"
    return f"10^{log10_years:.0f} años"


def fmt_int(n):
    return f"{int(n):,}".replace(",", ".")


def vec_str(v, limit=16):
    v = list(np.asarray(v).tolist())
    if len(v) > limit:
        return "[" + " ".join(f"{x:>3}" for x in v[:limit]) + " ...]"
    return "[" + " ".join(f"{x:>3}" for x in v) + "]"


# ---------------------------------------------------------------------------
# Álgebra lineal módulo q (q primo)
# ---------------------------------------------------------------------------

def rref_mod_q(M, q):
    """Forma escalonada reducida de M módulo q. Devuelve (R, columnas pivote)."""
    M = np.array(M, dtype=np.int64) % q
    rows, cols = M.shape
    pivots = []
    r = 0
    for c in range(cols):
        if r >= rows:
            break
        nz = np.nonzero(M[r:, c])[0]
        if len(nz) == 0:
            continue
        p = r + nz[0]
        if p != r:
            M[[r, p]] = M[[p, r]]
        inv = pow(int(M[r, c]), -1, q)
        M[r] = (M[r] * inv) % q
        others = np.nonzero(M[:, c])[0]
        others = others[others != r]
        if len(others):
            M[others] = (M[others] - np.outer(M[others, c], M[r])) % q
        pivots.append(c)
        r += 1
    return M, pivots


def solve_mod_q(M, rhs, q):
    """Resuelve M x = rhs (mod q). Devuelve (x, columnas libres) o None si es inconsistente."""
    M = np.asarray(M, dtype=np.int64)
    rhs = np.asarray(rhs, dtype=np.int64).reshape(-1, 1)
    aug = np.hstack([M, rhs])
    R, pivots = rref_mod_q(aug, q)
    cols = M.shape[1]
    if cols in pivots:
        return None
    x = np.zeros(cols, dtype=np.int64)
    for i, c in enumerate(pivots):
        x[c] = R[i, cols]
    free = [c for c in range(cols) if c not in pivots]
    return x, free


def inverse_mod_q(M, q):
    """Inversa de una matriz cuadrada módulo q, o None si es singular."""
    M = np.asarray(M, dtype=np.int64)
    n = M.shape[0]
    aug = np.hstack([M, np.eye(n, dtype=np.int64)])
    R, pivots = rref_mod_q(aug, q)
    if pivots[:n] != list(range(n)):
        return None
    return R[:, n:]


# ---------------------------------------------------------------------------
# Esquema LWE (cifrado de Regev, el abuelo de ML-KEM)
# ---------------------------------------------------------------------------

class Params:
    def __init__(self, n, q, m, eta):
        self.n = n      # dimensión del secreto
        self.q = q      # módulo (primo)
        self.m = m      # número de muestras (filas de A) en la clave pública
        self.eta = eta  # el error vive en [-eta, eta] (binomial centrada, como Kyber)
        if not is_prime(q):
            raise ValueError(f"q={q} debe ser primo")

    def __str__(self):
        return f"n={self.n}, q={self.q}, m={self.m}, eta={self.eta}"


def sample_error(rng, size, eta):
    """Binomial centrada: suma de eta pares (bit - bit). Rango [-eta, eta], varianza eta/2."""
    if eta == 0:
        return np.zeros(size, dtype=np.int64)
    a = rng.integers(0, 2, size=(eta, size))
    b = rng.integers(0, 2, size=(eta, size))
    return (a - b).sum(axis=0).astype(np.int64)


def lwe_samples(rng, s, m, P):
    """m pistas sobre s: (A, b) con b = A·s + e (mod q). Esto es lo único que ve el atacante."""
    A = rng.integers(0, P.q, size=(m, P.n), dtype=np.int64)
    e = sample_error(rng, m, P.eta)
    b = (A @ s + e) % P.q
    return A, b, e


def keygen(rng, P):
    s = rng.integers(0, P.q, size=P.n, dtype=np.int64)   # secreto uniforme (Regev)
    A, b, e = lwe_samples(rng, s, P.m, P)
    return s, (A, b), e


def encrypt_bit(rng, pk, bit, P):
    A, b = pk
    r = rng.integers(0, 2, size=P.m, dtype=np.int64)      # qué pistas se suman
    u = (r @ A) % P.q
    v = (r @ b + bit * (P.q // 2)) % P.q
    return u, v


def decrypt_bit(s, ct, P):
    u, v = ct
    w = int(centered((v - u @ s) % P.q, P.q))               # = r·e + bit·q/2 (ruido pequeño)
    return 1 if abs(w) > P.q / 4 else 0


def encrypt_text(rng, pk, text, P):
    bits = []
    for byte in text.encode("utf-8"):
        bits.extend((byte >> (7 - i)) & 1 for i in range(8))
    return [encrypt_bit(rng, pk, bit, P) for bit in bits]


def decrypt_text(s, cts, P):
    bits = [decrypt_bit(s, ct, P) for ct in cts]
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for bit in bits[i:i + 8]:
            byte = (byte << 1) | bit
        out.append(byte)
    return out.decode("utf-8", errors="replace")


def key_sizes(P):
    bits_q = math.ceil(math.log2(P.q))
    sk = P.n * bits_q / 8
    pk = (P.m * P.n + P.m) * bits_q / 8
    return sk, pk


def noise_margin(P):
    """Ruido típico y máximo del descifrado frente al umbral q/4."""
    sigma = math.sqrt(P.m * P.eta) / 2          # desviación típica de r·e
    worst = P.m * P.eta
    return sigma, worst, P.q / 4


# ---------------------------------------------------------------------------
# Ataques
# ---------------------------------------------------------------------------

def check_secret(A, b, s, q, eta):
    """¿Este s explica las pistas con un error pequeño?"""
    if s is None:
        return False
    r = centered((b - A @ s) % q, q)
    return bool(np.all(np.abs(r) <= eta))


def attack_no_error(A, b, q):
    """Eliminación gaussiana: solo funciona si no hay error."""
    sol = solve_mod_q(A, b, q)
    if sol is None:
        return None, "sistema inconsistente (las pistas se contradicen por el error)"
    s, free = sol
    if free:
        return s, f"{len(free)} incógnitas libres: faltan pistas"
    return s, "solución única"


def attack_bruteforce(A, b, q, eta, max_candidates=8_000_000):
    """Prueba todos los secretos posibles. Coste: q^n."""
    m, n = A.shape
    total = q ** n
    if total > max_candidates:
        return {"ok": False, "skipped": True, "total": total}
    t0 = time.perf_counter()
    kb = 1
    while kb < n and q ** (kb + 1) <= 65536:
        kb += 1
    tail = np.array(list(itertools.product(range(q), repeat=kb)), dtype=np.int64)
    A_head, A_tail = A[:, :n - kb], A[:, n - kb:]
    T = (A_tail @ tail.T) % q
    tested = 0
    for head in itertools.product(range(q), repeat=n - kb):
        base = (b - A_head @ np.array(head, dtype=np.int64)) % q
        R = np.abs(centered((base[:, None] - T) % q, q))
        ok = np.all(R <= eta, axis=0)
        tested += tail.shape[0]
        if ok.any():
            s = np.concatenate([np.array(head, dtype=np.int64), tail[np.argmax(ok)]])
            dt = time.perf_counter() - t0
            return {"ok": True, "s": s, "tested": tested, "total": total,
                    "time": dt, "rate": tested / max(dt, 1e-9)}
    dt = time.perf_counter() - t0
    return {"ok": False, "tested": tested, "total": total, "time": dt, "rate": tested / max(dt, 1e-9)}


def _poly_mul(p, l, q):
    out = {}
    for m1, c1 in p.items():
        for m2, c2 in l.items():
            key = tuple(sorted(m1 + m2))
            out[key] = (out.get(key, 0) + c1 * c2) % q
    return out


def arora_ge_needed(n, eta):
    d = 2 * eta + 1
    return math.comb(n + d, d) - 1


def attack_arora_ge(A, b, q, eta, max_monomials=1500):
    """Arora-Ge: cada pista da un polinomio de grado 2·eta+1 en s; se linealiza y se resuelve."""
    m, n = A.shape
    needed = arora_ge_needed(n, eta)
    if needed > max_monomials:
        return {"ok": False, "reason": "demasiados monomios", "needed": needed, "have": m}
    if m < needed:
        return {"ok": False, "reason": "faltan muestras", "needed": needed, "have": m}
    t0 = time.perf_counter()
    d = 2 * eta + 1
    monos = []
    for deg in range(1, d + 1):
        monos.extend(itertools.combinations_with_replacement(range(n), deg))
    idx = {mono: i for i, mono in enumerate(monos)}
    M = np.zeros((m, len(monos)), dtype=np.int64)
    rhs = np.zeros(m, dtype=np.int64)
    for i in range(m):
        poly = {(): 1}
        for k in range(-eta, eta + 1):
            lin = {(): int((b[i] - k) % q)}
            for j in range(n):
                lin[(j,)] = int((-A[i, j]) % q)
            poly = _poly_mul(poly, lin, q)
        for mono, c in poly.items():
            if mono == ():
                rhs[i] = (-c) % q
            else:
                M[i, idx[mono]] = c
    sol = solve_mod_q(M, rhs, q)
    dt = time.perf_counter() - t0
    if sol is None:
        return {"ok": False, "reason": "sistema inconsistente", "needed": needed, "have": m, "time": dt}
    x, free = sol
    lin_cols = [idx[(j,)] for j in range(n)]
    if any(c in free for c in lin_cols):
        return {"ok": False, "reason": "faltan muestras independientes", "needed": needed, "have": m, "time": dt}
    s = x[lin_cols]
    return {"ok": check_secret(A, b, s, q, eta), "s": s, "needed": needed, "have": m,
            "monomials": len(monos), "time": dt}


def lll_reduce(B, delta=0.99):
    """LLL con Gram-Schmidt en coma flotante. Filas = vectores de la base."""
    B = np.array(B, dtype=np.int64)
    n = B.shape[0]
    Bf = B.astype(np.float64)
    Bstar = np.zeros_like(Bf)
    mu = np.zeros((n, n))
    nrm = np.zeros(n)

    def gs(i):
        v = Bf[i].copy()
        if i > 0:
            mu[i, :i] = (Bstar[:i] @ Bf[i]) / nrm[:i]
            v -= mu[i, :i] @ Bstar[:i]
        Bstar[i] = v
        nrm[i] = v @ v

    for i in range(n):
        gs(i)
    k = 1
    iters = 0
    cap = 200_000 * n
    while k < n:
        iters += 1
        if iters > cap:
            raise RuntimeError("LLL no converge (precisión numérica)")
        for j in range(k - 1, -1, -1):
            r = int(round(mu[k, j]))
            if r:
                B[k] -= r * B[j]
                Bf[k] = B[k]
                mu[k, :j] -= r * mu[j, :j]
                mu[k, j] -= r
        if nrm[k] >= (delta - mu[k, k - 1] ** 2) * nrm[k - 1]:
            k += 1
        else:
            B[[k - 1, k]] = B[[k, k - 1]]
            Bf[[k - 1, k]] = Bf[[k, k - 1]]
            gs(k - 1)
            gs(k)
            if k + 1 < n:
                mu[k + 1:, k - 1] = (Bf[k + 1:] @ Bstar[k - 1]) / nrm[k - 1]
                mu[k + 1:, k] = (Bf[k + 1:] @ Bstar[k]) / nrm[k]
            k = max(k - 1, 1)
    return B


def enum_svp(B, R2, max_nodes=None):
    """Enumeración de Schnorr-Euchner (versión Gama-Nguyen-Regev) sobre una base reducida.

    Busca el vector no nulo más corto de norma² <= R2. Devuelve (coeficientes, nodos, completo).
    El coste crece exponencialmente con la dimensión: esto es lo que hace BKZ por bloques.
    """
    B = np.asarray(B, dtype=np.int64)
    n = B.shape[0]
    Bf = B.astype(np.float64)
    Bstar = np.zeros_like(Bf)
    mu = np.zeros((n, n))
    nrm = np.zeros(n)
    for i in range(n):
        v = Bf[i].copy()
        if i > 0:
            mu[i, :i] = (Bstar[:i] @ Bf[i]) / nrm[:i]
            v -= mu[i, :i] @ Bstar[:i]
        Bstar[i] = v
        nrm[i] = v @ v

    # Índices 1..n como en el artículo original (índice 0 sin usar)
    mu1 = [[0.0] * (n + 2) for _ in range(n + 2)]
    for i in range(1, n + 1):
        for k in range(1, i):
            mu1[i][k] = mu[i - 1, k - 1]
    rr = [0.0] + [float(x) for x in nrm] + [0.0]
    sigma = [[0.0] * (n + 2) for _ in range(n + 2)]
    rvec = list(range(n + 1))
    rho = [0.0] * (n + 2)
    c = [0.0] * (n + 2)
    x = [0] * (n + 2)
    w = [0] * (n + 2)
    x[1] = 1
    last_nonzero = 1
    k = 1
    best = None
    bestR2 = float(R2)
    nodes = 0
    while True:
        nodes += 1
        if max_nodes and nodes > max_nodes:
            return best, nodes, False
        diff = x[k] - c[k]
        rho[k] = rho[k + 1] + diff * diff * rr[k]
        if rho[k] <= bestR2:
            if k > 1:
                k -= 1
                rvec[k - 1] = max(rvec[k - 1], rvec[k])
                for i in range(rvec[k], k, -1):
                    sigma[k][i] = sigma[k][i + 1] + x[i] * mu1[i][k]
                c[k] = -sigma[k][k + 1]
                x[k] = int(round(c[k]))
                w[k] = 1
                continue
            if rho[1] > 1e-9:
                best = np.array(x[1:n + 1], dtype=np.int64)
                bestR2 = rho[1] * (1 - 1e-9)
        k += 1
        if k == n + 1:
            return best, nodes, True
        rvec[k - 1] = k
        if k >= last_nonzero:
            last_nonzero = k
            x[k] += 1
        else:
            if x[k] > c[k]:
                x[k] -= w[k]
            else:
                x[k] += w[k]
            w[k] += 1


def build_embedding(A, b, q, rng):
    """Retículo de Kannan: contiene el vector corto (e, 1) escondido entre vectores de tamaño ~q."""
    m, n = A.shape
    perm = np.arange(m)
    inv = None
    for _ in range(50):
        inv = inverse_mod_q(A[perm[:n]], q)
        if inv is not None:
            break
        rng.shuffle(perm)
    if inv is None:
        raise RuntimeError("no se encontraron n filas independientes de A")
    A_p, b_p = A[perm], b[perm]
    C = (A_p[n:] @ inv) % q                     # (m-n) x n
    basis = np.zeros((m + 1, m + 1), dtype=np.int64)
    for i in range(n):
        basis[i, i] = 1
        basis[i, n:m] = C[:, i]
    for j in range(m - n):
        basis[n + j, n + j] = q
    basis[m, :m] = b_p
    basis[m, m] = 1
    return basis, A_p, b_p, perm


def attack_lattice(A, b, q, eta, rng, use_enum=True, max_nodes=2_000_000):
    """Ataque primal: LLL y, si hace falta, enumeración exacta del vector más corto."""
    m, n = A.shape
    basis, A_p, b_p, _ = build_embedding(A, b, q, rng)

    def try_vec(v):
        if abs(int(v[m])) != 1:
            return None
        e = v[:m] * int(v[m])
        if np.max(np.abs(e)) > eta:
            return None
        sol = solve_mod_q(A_p, (b_p - e) % q, q)
        if sol is None or sol[1]:
            return None
        s = sol[0]
        return s if check_secret(A, b, s, q, eta) else None

    out = {"dim": m + 1, "ok": False, "method": None, "lll_time": 0.0, "enum_time": 0.0,
           "enum_nodes": 0, "enum_complete": None, "s": None}
    t0 = time.perf_counter()
    R = lll_reduce(basis)
    out["lll_time"] = time.perf_counter() - t0
    for v in R:
        s = try_vec(v)
        if s is not None:
            out.update(ok=True, method="LLL", s=s)
            return out
    if not use_enum:
        return out
    # Primero un radio probable (||e||² ronda m·eta/2); si no aparece, el radio máximo posible.
    t0 = time.perf_counter()
    radii = [1.6 * (m * eta / 2 + 1), m * eta * eta + 1.5]
    for R2 in radii:
        xs, nodes, complete = enum_svp(R, R2, max_nodes)
        out["enum_nodes"] += nodes
        out["enum_complete"] = complete
        if xs is not None:
            s = try_vec(xs @ R)
            if s is not None:
                out.update(ok=True, method="LLL+enum", s=s)
                break
        if not complete:
            break
    out["enum_time"] = time.perf_counter() - t0
    return out


def primal_beta_estimate(n, m_avail, q, eta):
    """Estimación clásica (Alkim-Ducas-Pöppelmann-Schwabe 2016) del bloque BKZ necesario.

    Devuelve (beta, m usado). beta=2 significa que LLL basta. El coste de BKZ con cribado
    es ~2^(0.292·beta) operaciones: ahí está la dificultad exponencial del problema real.
    """
    sigma = math.sqrt(eta / 2)
    d40 = ((40 / (2 * math.pi * math.e)) * (math.pi * 40) ** (1 / 40)) ** (1 / (2 * 39))

    def delta(beta):
        if beta < 40:
            return 1.0219 + (d40 - 1.0219) * (beta - 2) / 38
        return ((beta / (2 * math.pi * math.e)) * (math.pi * beta) ** (1 / beta)) ** (1 / (2 * (beta - 1)))

    best = None
    for m in range(n + 1, m_avail + 1):
        d = m + 1
        log_det = (m - n) * math.log(q) / d
        for beta in range(2, d + 1):
            lhs = math.log(math.sqrt(beta) * sigma)
            rhs = (2 * beta - d - 1) * math.log(delta(beta)) + log_det
            if lhs <= rhs:
                if best is None or beta < best[0]:
                    best = (beta, m)
                break
    return best if best else (m_avail + 1, m_avail)


def attack_with_leak(A, b, q, eta, s_true, leaked_idx, rng, **kw):
    """Híbrido: el atacante conoce s en las posiciones leaked_idx y ataca el resto."""
    m, n = A.shape
    leaked_idx = sorted(leaked_idx)
    rest = [j for j in range(n) if j not in leaked_idx]
    b2 = (b - A[:, leaked_idx] @ s_true[leaked_idx]) % q
    A2 = A[:, rest]
    out = attack_lattice(A2, b2, q, eta, rng, **kw)
    if out["ok"]:
        s = np.zeros(n, dtype=np.int64)
        s[leaked_idx] = s_true[leaked_idx]
        s[rest] = out["s"]
        out["s"] = s
        out["ok"] = check_secret(A, b, s, q, eta)
    return out


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def hr(title=None):
    print()
    print("=" * 78)
    if title:
        print(title)
        print("=" * 78)


def cmd_demo(args):
    rng = np.random.default_rng(args.seed)
    P = Params(args.n, args.q, args.m, args.eta)
    hr(f"1. PARÁMETROS  ({P})")
    sk_bytes, pk_bytes = key_sizes(P)
    print(f"Secreto: {P.n} números mod {P.q}. Clave pública: {P.m} pistas de {P.n + 1} números.")
    print(f"Tamaño guardado: clave secreta ≈ {sk_bytes:.0f} bytes, clave pública ≈ {pk_bytes:.0f} bytes.")
    print(f"Referencia ML-KEM-512: n=512, q=3329, eta=3 -> sk 1632 bytes, pk 800 bytes.")
    print(f"Espacio de claves: q^n = {P.q}^{P.n} = {fmt_count(P.n * math.log10(P.q))} secretos posibles.")

    hr("2. GENERACIÓN DE CLAVES (cómo se guarda el secreto)")
    s, (A, b), e = keygen(rng, P)
    print(f"s (SECRETO, se guarda y nunca se envía) = {vec_str(s)}")
    print(f"A (pública, {P.m}x{P.n} aleatoria), primeras filas:")
    for i in range(min(3, P.m)):
        print(f"    a_{i} = {vec_str(A[i])}   a_{i}·s = {int(A[i] @ s) % P.q:>3}   + e_{i}={int(e[i]):>2}  -> b_{i} = {int(b[i]):>3}")
    print(f"e (error, se tira después de usarlo)     = {vec_str(e)}")
    print(f"b = A·s + e mod q (pública)              = {vec_str(b)}")
    print("Clave pública = (A, b). Sin e, cualquiera despeja s en milisegundos. Con e, hay que adivinar.")

    hr("3. CIFRAR Y DESCIFRAR (cómo se recupera el mensaje)")
    msg = args.msg
    cts = encrypt_text(rng, (A, b), msg, P)
    u0, v0 = cts[0]
    print(f"Mensaje: {msg!r} -> {len(cts)} bits, cada bit se cifra por separado.")
    print(f"Bit 0 cifrado: u = {vec_str(u0)}, v = {int(v0)}")
    print("  (u, v) = suma aleatoria de pistas de la clave pública, más q/2 si el bit es 1.")
    sigma, worst, thr = noise_margin(P)
    w = int(centered((v0 - u0 @ s) % P.q, P.q))
    print(f"Descifrar: v - u·s = {w} (mod q, centrado). Si |valor| > q/4 = {thr:.1f} el bit es 1.")
    print(f"Ruido r·e: típico ±{sigma:.1f}, máximo {worst}; umbral {thr:.1f}. "
          f"{'OK' if worst < thr else 'AVISO: puede fallar algún bit'}")
    rec = decrypt_text(s, cts, P)
    print(f"Descifrado con s: {rec!r}  {'✓' if rec == msg else '✗'}")

    hr("4. ATAQUES (el atacante solo tiene A, b y los cifrados)")

    print("\n[0] Sin errores: eliminación gaussiana")
    P0 = Params(P.n, P.q, P.m, 0)
    s0, (A0, b0), _ = keygen(np.random.default_rng(args.seed + 1), P0)
    t0 = time.perf_counter()
    s_hat, note = attack_no_error(A0, b0, P.q)
    dt = time.perf_counter() - t0
    print(f"    instancia con eta=0: s recuperado = {vec_str(s_hat)} ({note}) en {fmt_time(dt)} "
          f"{'✓' if np.array_equal(s_hat, s0) else '✗'}")
    s_hat, note = attack_no_error(A, b, P.q)
    print(f"    instancia real (eta={P.eta}): {note}. "
          f"{'s correcto' if s_hat is not None and np.array_equal(s_hat, s) else 'no sirve'}.")
    print("    Lección: el error es el candado. Convierte álgebra de secundaria en un problema duro.")

    print("\n[1] Fuerza bruta sobre s")
    res = attack_bruteforce(A, b, P.q, P.eta, max_candidates=args.max_bf)
    if res.get("skipped"):
        print(f"    omitido: {fmt_count(math.log10(res['total']))} candidatos supera el tope (--max-bf).")
        bf_rate = 2e6
    else:
        bf_rate = res["rate"]
        print(f"    probados {fmt_int(res['tested'])} de {fmt_int(res['total'])} candidatos en {fmt_time(res['time'])} "
              f"({fmt_int(bf_rate)}/s) -> {'✓ s encontrado' if res['ok'] else '✗'}")
    for n2 in (8, 16, 32, 512):
        print(f"    a este ritmo, n={n2:>3}: {fmt_time(log10=n2 * math.log10(P.q) - math.log10(bf_rate))}")

    print("\n[2] Arora-Ge (linealización)")
    needed = arora_ge_needed(P.n, P.eta)
    print(f"    grado del polinomio por pista: {2 * P.eta + 1}; monomios: {needed}; pistas en la clave pública: {P.m}.")
    m_oracle = needed + 10
    A_o, b_o, _ = lwe_samples(np.random.default_rng(args.seed + 2), s, m_oracle, P)
    print(f"    supongamos que el atacante consigue {m_oracle} pistas con el MISMO secreto (un esquema real no las da):")
    res = attack_arora_ge(A_o, b_o, P.q, P.eta, max_monomials=args.max_monomials)
    if res["ok"]:
        print(f"    s recuperado = {vec_str(res['s'])} en {fmt_time(res['time'])} ✓")
    else:
        print(f"    falla: {res['reason']} (necesita {res['needed']}, tiene {res['have']})")
    for n2, eta2 in ((16, 1), (16, 2), (64, 2), (512, 3)):
        print(f"    n={n2:>3}, eta={eta2}: necesita {fmt_count(math.log10(arora_ge_needed(n2, eta2)))} pistas")
    print("    Lección: con error pequeño y muchas pistas se rompe en tiempo polinomial. Por eso")
    print("    los esquemas reales limitan las pistas y usan eta >= 2.")

    print("\n[3] Reducción de retículos (LLL) con las pistas de la clave pública")
    res = attack_lattice(A, b, P.q, P.eta, rng, use_enum=False)
    print(f"    retículo de dimensión {res['dim']}; LLL en {fmt_time(res['lll_time'])} -> "
          f"{'✓ s = ' + vec_str(res['s']) if res['ok'] else '✗ no apareció (e,1) en la base'}")
    gh = math.sqrt((P.m + 1) / (2 * math.pi * math.e)) * P.q ** ((P.m - P.n) / (P.m + 1))
    print(f"    norma de (e,1) ≈ {math.sqrt(P.m * P.eta / 2 + 1):.1f}; vector corto 'normal' del retículo ≈ {gh:.1f}.")
    print("    LLL encuentra la aguja cuando es mucho más corta que el resto. Al crecer n, la diferencia")
    print("    se achica y LLL deja de verla.")

    print("\n[4] Enumeración exacta del vector más corto (lo que BKZ hace por bloques)")
    basis, A_p, b_p, perm = build_embedding(A, b, P.q, rng)
    R = lll_reduce(basis)
    t0 = time.perf_counter()
    xs, nodes, complete = enum_svp(R, P.m * P.eta ** 2 + 1.5, max_nodes=args.max_nodes)
    dt = time.perf_counter() - t0
    v = xs @ R if xs is not None else None
    print(f"    nodos explorados: {fmt_int(nodes)} en {fmt_time(dt)}; vector más corto hallado: "
          f"{vec_str(v) if v is not None else 'ninguno'}")
    print(f"    (e, 1) real en el mismo orden        = {vec_str(np.append(e[perm], 1))}")
    print("    El número de nodos crece como 2^(dim·log dim): aquí está la dificultad exponencial.")

    print("\n[5] Fuga de parte del secreto")
    k = max(1, P.n // 2)
    leaked = list(range(k))
    res = attack_with_leak(A, b, P.q, P.eta, s, leaked, rng, use_enum=False)
    print(f"    el atacante conoce {k} de {P.n} coordenadas de s (p. ej. por un canal lateral).")
    print(f"    problema restante: n={P.n - k}, espacio {fmt_count((P.n - k) * math.log10(P.q))} en vez de "
          f"{fmt_count(P.n * math.log10(P.q))}; LLL en {fmt_time(res['lll_time'])} -> {'✓' if res['ok'] else '✗'}")

    hr("5. EL ATACANTE LEE EL MENSAJE")
    res = attack_lattice(A, b, P.q, P.eta, rng, use_enum=True, max_nodes=args.max_nodes)
    if res["ok"]:
        print(f"s recuperado con {res['method']}: {vec_str(res['s'])}")
        print(f"mensaje descifrado por el atacante: {decrypt_text(res['s'], cts, P)!r}")
    else:
        print("ningún ataque recuperó s con estos parámetros.")


def mark(result, s_true):
    """✓ si recuperó el secreto real, ~ si encontró otro consistente, ✗ si nada."""
    if not result.get("ok"):
        return "✗"
    return "✓" if np.array_equal(result["s"], s_true) else "~"


def beta_str(n, m, q, eta):
    beta, m_used = primal_beta_estimate(n, m, q, eta)
    if beta < 40:
        return "β<40: LLL o BKZ pequeño"
    cost = 0.292 * beta
    return f"β={beta} (m={m_used}) ≈2^{cost:.0f} ops"


def cmd_scale(args):
    ns = [int(x) for x in args.ns.split(",")]
    print(f"q={args.q}, eta={args.eta}, m={args.m_mult}·n, semilla={args.seed}")
    print("Fuerza bruta: medida si q^n <= tope, estimada si no. Arora-Ge usa un oráculo con las pistas que necesita.")
    print("✓ = recuperó el secreto real, ~ = encontró otro secreto consistente (pocas pistas), ✗ = falló, tope = se agotó --max-nodes.")
    print("Última columna: bloque BKZ que haría falta según la estimación estándar (asintótica: por debajo de β≈40")
    print("no afina, y puede decir 'LLL' donde LLL ya falla) y su coste con cribado, 2^(0.292·β) operaciones.")
    print()
    head = (f"{'n':>3} {'m':>4} {'dim':>4} {'claves':>12} {'fuerza bruta':>20} {'Arora-Ge':>26} "
            f"{'LLL':>12} {'enumeración':>30} {'BKZ estimado':>28}")
    print(head)
    print("-" * len(head))
    bf_rate = None
    for n in ns:
        m = args.m_mult * n
        P = Params(n, args.q, m, args.eta)
        rng = np.random.default_rng(args.seed + n)
        s, (A, b), e = keygen(rng, P)
        keys = fmt_count(n * math.log10(P.q))

        res = attack_bruteforce(A, b, P.q, P.eta, max_candidates=args.max_bf)
        if res.get("skipped"):
            rate = bf_rate or 2e6
            bf = f"≈{fmt_time(log10=n * math.log10(P.q) - math.log10(rate), short=True)} (est.)"
        else:
            bf_rate = res["rate"]
            bf = f"{fmt_time(res['time'])} {mark(res, s)}"

        needed = arora_ge_needed(n, P.eta)
        if needed > args.max_monomials:
            ag = f"necesita {fmt_count(math.log10(needed))} pistas"
        else:
            A_o, b_o, _ = lwe_samples(rng, s, needed + 10, P)
            r2 = attack_arora_ge(A_o, b_o, P.q, P.eta, max_monomials=args.max_monomials)
            ag = f"{fmt_time(r2.get('time', 0))} con {needed} pistas {mark(r2, s)}"

        r3 = attack_lattice(A, b, P.q, P.eta, rng, use_enum=True, max_nodes=args.max_nodes)
        lll = f"{fmt_time(r3['lll_time'])} {mark(r3, s) if r3['method'] == 'LLL' else '✗'}"
        if r3["method"] == "LLL":
            en = "no hizo falta"
        else:
            mk = mark(r3, s) if r3["ok"] else ("tope" if not r3["enum_complete"] else "✗")
            en = f"{fmt_int(r3['enum_nodes'])} nodos, {fmt_time(r3['enum_time'])} {mk}"
        print(f"{n:>3} {m:>4} {m + 1:>4} {keys:>12} {bf:>20} {ag:>26} {lll:>12} {en:>30} "
              f"{beta_str(n, m, P.q, P.eta):>28}", flush=True)
    print()
    print("Referencia con este mismo esquema a tamaño real (solo estimación, no se ejecuta):")
    for n, q, eta in ((128, args.q, args.eta), (256, 3329, 3), (512, 3329, 3)):
        m = args.m_mult * n
        print(f"  n={n:>3}, q={q}, eta={eta}, m={m}: claves {fmt_count(n * math.log10(q))}, {beta_str(n, m, q, eta)}")
    print("ML-KEM-512 (n=512, q=3329, eta=3, secreto pequeño): el estándar estima β≈400, unas 2^140 operaciones.")
    print("Prueba: --q 3329 (como Kyber) para ver cómo cambia LLL; --eta 1 para ver a Arora-Ge ganar; --max-nodes 20000000 para insistir con la enumeración.")


def cmd_leak(args):
    P = Params(args.n, args.q, args.m_mult * args.n, args.eta)
    rng = np.random.default_rng(args.seed)
    s, (A, b), e = keygen(rng, P)
    print(f"{P}; el atacante conoce k={args.k} de n={args.n} coordenadas de s")
    print()
    r0 = attack_lattice(A, b, P.q, P.eta, rng, use_enum=True, max_nodes=args.max_nodes)
    print(f"sin fuga : dim {r0['dim']:>3}, LLL {fmt_time(r0['lll_time']):>8}, "
          f"enum {fmt_int(r0['enum_nodes']):>12} nodos {fmt_time(r0['enum_time']):>8} -> "
          f"{mark(r0, s)} {r0['method'] or ''}   {beta_str(args.n, P.m, P.q, P.eta)}")
    for k in sorted(set([args.k, args.n // 4, args.n // 2, 3 * args.n // 4])):
        if k <= 0 or k >= args.n:
            continue
        leaked = list(rng.choice(args.n, size=k, replace=False))
        r = attack_with_leak(A, b, P.q, P.eta, s, leaked, rng, use_enum=True, max_nodes=args.max_nodes)
        print(f"fuga k={k:>2}: dim {r['dim']:>3}, LLL {fmt_time(r['lll_time']):>8}, "
              f"enum {fmt_int(r['enum_nodes']):>12} nodos {fmt_time(r['enum_time']):>8} -> "
              f"{mark(r, s)} {r['method'] or ''}   {beta_str(args.n - k, P.m, P.q, P.eta)}   "
              f"(fuerza bruta restante: {fmt_count((args.n - k) * math.log10(P.q))})")
    print()
    print("Cada coordenada filtrada divide el espacio de fuerza bruta entre q y agranda la brecha del retículo:")
    print("el vector (e,1) destaca más entre los demás y LLL/BKZ lo encuentra con menos esfuerzo.")


# ---------------------------------------------------------------------------
# Experimento "ondas": ataque dual con plegado y transformada de Fourier
# ---------------------------------------------------------------------------

def dual_basis(A_K, q, rng):
    """Base del retículo de pliegues {w en Z^m : w·A_K = 0 (mod q)}. Tiene det q^k."""
    m, k = A_K.shape
    perm = np.arange(m)
    inv = None
    for _ in range(50):
        inv = inverse_mod_q(A_K[perm[:k]].T, q)
        if inv is not None:
            break
        rng.shuffle(perm)
    if inv is None:
        raise RuntimeError("A_K no tiene k filas independientes")
    A2 = A_K[perm[k:]]                                  # (m-k) x k
    C = (-(inv @ A2.T)) % q                             # k x (m-k): w1 = C·w2
    basis = np.zeros((m, m), dtype=np.int64)
    for j in range(m - k):
        basis[j, :k] = C[:, j]
        basis[j, k + j] = 1
    for i in range(k):
        basis[m - k + i, i] = q
    return basis, perm


def wave_signal(sigma2, w2, q):
    """Fuerza de la onda plegada: E[cos(2π·w·e/q)] = exp(-2π²·σ²·|w|²/q²)."""
    return math.exp(-2 * math.pi ** 2 * sigma2 * w2 / q ** 2)


def attack_wave(A, b, q, eta, s_true, keep, rng, max_waves=4000):
    """Pliega n-keep coordenadas con vectores duales cortos y busca el resto con una FFT.

    Cada vector dual w convierte las m pistas en UNA pista plegada sobre keep incógnitas,
    con error w·e. La FFT evalúa todas las q^keep opciones a la vez: la onda se refuerza
    en el secreto verdadero y se cancela en los demás.
    """
    m, n = A.shape
    k = n - keep
    K = list(range(k))
    Rr = list(range(k, n))
    sigma2 = eta / 2
    t0 = time.perf_counter()
    if k == 0:
        W = np.eye(m, dtype=np.int64)
        lll_t = 0.0
    else:
        basis, perm = dual_basis(A[:, K], q, rng)
        Rb = lll_reduce(basis)
        lll_t = time.perf_counter() - t0
        rows = [Rb[i] for i in range(m)]
        extra = []
        for i in range(m):
            for j in range(i + 1, m):
                extra.append(rows[i] + rows[j])
                extra.append(rows[i] - rows[j])
                if len(rows) + len(extra) >= max_waves:
                    break
            if len(rows) + len(extra) >= max_waves:
                break
        Wp = np.array(rows + extra, dtype=np.int64)
        W = np.zeros_like(Wp)
        W[:, perm] = Wp
        assert not np.any((W @ A[:, K]) % q), "el pliegue no anula las coordenadas"
    norms2 = (W.astype(np.float64) ** 2).sum(axis=1)
    order = np.argsort(norms2)
    W, norms2 = W[order], norms2[order]
    # Filtro adaptado: cada onda pesa lo que su señal esperada. Las ondas largas no estorban.
    eps = np.exp(-2 * math.pi ** 2 * sigma2 * norms2 / q ** 2)
    a_fold = (W @ A[:, Rr]) % q                          # N x keep
    b_fold = (W @ b) % q
    F = np.zeros((q,) * keep, dtype=np.complex128)
    np.add.at(F, tuple(a_fold.T), eps * np.exp(2j * np.pi * b_fold / q))
    score = np.real(np.fft.fftn(F))
    s_R = tuple(int(x) for x in s_true[Rr])
    best = np.unravel_index(np.argmax(score), score.shape)
    z = (score[s_R] - score.mean()) / score.std()
    energy = float((eps ** 2).sum())                     # señal² acumulada
    gh2 = (m / (2 * math.pi * math.e)) * q ** (2 * k / m) if k else 1.0
    eps_gh = wave_signal(sigma2, gh2, q)
    return {
        "k": k, "keep": keep, "N": len(W), "w2_min": float(norms2[0]), "gh2": gh2,
        "eps_min": float(eps[0]), "eps_gh": eps_gh,
        "z_pred": math.sqrt(2 * energy), "z_ideal": math.sqrt(2 * len(W) * eps_gh ** 2),
        "z": float(z), "ok": best == s_R, "fft_size": q ** keep,
        "time": time.perf_counter() - t0, "lll_time": lll_t,
    }


def cmd_wave(args):
    ns = [int(x) for x in args.ns.split(",")]
    print(f"q={args.q}, eta={args.eta}, m={args.m_mult}·n, se dejan {args.keep} incógnitas para la FFT")
    print("Onda plegada w: señal(w) = exp(-2π²·σ²·|w|²/q²). Con filtro adaptado, pico esperado z = sqrt(2·Σ señal(w)²).")
    print("|w|² ideal = lo que daría un resolutor perfecto de SVP (heurística gaussiana); z ideal = el pico que vería con las mismas ondas.")
    print()
    head = (f"{'n':>3} {'m':>4} {'plegadas':>8} {'FFT':>7} {'|w|² LLL':>9} {'|w|² ideal':>10} "
            f"{'señal LLL':>10} {'señal ideal':>11} {'ondas':>6} {'z pred':>7} {'z medido':>8} {'z ideal':>8} {'ok':>3} {'tiempo':>7}")
    print(head)
    print("-" * len(head))
    for n in ns:
        keep = min(args.keep, n)
        P = Params(n, args.q, args.m_mult * n, args.eta)
        rng = np.random.default_rng(args.seed + n)
        s, (A, b), e = keygen(rng, P)
        r = attack_wave(A, b, P.q, P.eta, s, keep, rng, max_waves=args.max_waves)
        print(f"{n:>3} {P.m:>4} {r['k']:>8} {fmt_count(math.log10(r['fft_size'])):>7} {r['w2_min']:>9.0f} "
              f"{r['gh2']:>10.0f} {r['eps_min']:>10.1e} {r['eps_gh']:>11.2f} {r['N']:>6} {r['z_pred']:>7.1f} "
              f"{r['z']:>8.1f} {r['z_ideal']:>8.1f} {'✓' if r['ok'] else '✗':>3} {fmt_time(r['time']):>7}", flush=True)
    print()
    print("Lectura: 'z medido' sigue a 'z pred': la fórmula de la onda es correcta. El pico se hunde porque")
    print("LLL deja de encontrar pliegues cortos (|w|² LLL se aleja de |w|² ideal) y la señal cae como exp(-|w|²).")
    print("Con los mismos 4000 pliegues pero de longitud ideal, el pico seguiría siendo enorme ('z ideal').")
    print("Encontrar esos pliegues ideales ES el problema del vector más corto: BKZ, coste 2^(0,292·β).")


def cmd_selftest(args):
    rng = np.random.default_rng(7)
    fails = 0

    def check(name, cond):
        nonlocal fails
        print(f"  {'OK ' if cond else 'FAIL'} {name}")
        if not cond:
            fails += 1

    check("next_prime", next_prime(50) == 53 and next_prime(3329) == 3329)

    for n, q, m, eta in ((4, 53, 12, 1), (8, 97, 16, 2), (12, 3329, 24, 3)):
        P = Params(n, q, m, eta)
        s, pk, _ = keygen(rng, P)
        msg = "Gaticos y Cookies"
        check(f"cifrado/descifrado {P}", decrypt_text(s, encrypt_text(rng, pk, msg, P), P) == msg)

    M = rng.integers(0, 53, size=(6, 6))
    inv = inverse_mod_q(M, 53)
    check("inversa mod q", inv is None or np.array_equal((M @ inv) % 53, np.eye(6, dtype=np.int64)))
    x = rng.integers(0, 53, size=6)
    sol = solve_mod_q(M, (M @ x) % 53, 53)
    check("solve mod q", sol is not None and (inv is None or np.array_equal(sol[0], x)))

    B = rng.integers(-20, 21, size=(8, 8))
    R = lll_reduce(B)
    detB = round(abs(np.linalg.det(B.astype(float))))
    detR = round(abs(np.linalg.det(R.astype(float))))
    check("LLL conserva el retículo (det) y acorta el primer vector",
          detB == detR and np.linalg.norm(R[0]) <= np.linalg.norm(B[0]) + 1e-9)

    ok = True
    for trial in range(5):
        B = rng.integers(-15, 16, size=(6, 6))
        if abs(np.linalg.det(B.astype(float))) < 0.5:
            continue
        R = lll_reduce(B)
        xs, nodes, complete = enum_svp(R, float(R[0] @ R[0]) + 0.5)
        best_enum = int((xs @ R) @ (xs @ R))
        best_bf = min(int(v @ v) for cf in itertools.product(range(-4, 5), repeat=6)
                      if any(cf) for v in [np.array(cf) @ R])
        ok &= complete and best_enum == best_bf
    check("enumeración == fuerza bruta sobre coeficientes (dim 6)", ok)

    P = Params(4, 53, 12, 1)
    s, (A, b), e = keygen(rng, P)
    r = attack_bruteforce(A, b, P.q, P.eta)
    check("fuerza bruta recupera s", r["ok"] and np.array_equal(r["s"], s))
    A_o, b_o, _ = lwe_samples(rng, s, arora_ge_needed(4, 1) + 10, P)
    r = attack_arora_ge(A_o, b_o, P.q, P.eta)
    check("Arora-Ge recupera s", r["ok"] and np.array_equal(r["s"], s))
    r = attack_lattice(A, b, P.q, P.eta, rng)
    check("LLL recupera s", r["ok"] and np.array_equal(r["s"], s))
    r = attack_with_leak(A, b, P.q, P.eta, s, [0, 2], rng)
    check("ataque con fuga recupera s", r["ok"] and np.array_equal(r["s"], s))

    P = Params(16, 97, 32, 2)
    s, (A, b), e = keygen(rng, P)
    r = attack_lattice(A, b, P.q, P.eta, rng, use_enum=True, max_nodes=2_000_000)
    check(f"ataque primal n=16 q=97 ({r['method']})", r["ok"] and np.array_equal(r["s"], s))

    print()
    print("todo OK" if fails == 0 else f"{fails} comprobaciones fallaron")
    return 0 if fails == 0 else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="recorrido narrado con una instancia pequeña")
    d.add_argument("--n", type=int, default=4)
    d.add_argument("--q", type=int, default=53)
    d.add_argument("--m", type=int, default=12)
    d.add_argument("--eta", type=int, default=1)
    d.add_argument("--msg", default="HOLA GATO")
    d.add_argument("--seed", type=int, default=1)
    d.add_argument("--max-bf", type=int, default=8_000_000)
    d.add_argument("--max-monomials", type=int, default=1500)
    d.add_argument("--max-nodes", type=int, default=2_000_000)

    sc = sub.add_parser("scale", help="crece n y mide cada ataque")
    sc.add_argument("--ns", default="4,8,12,16,20,24,32,40")
    sc.add_argument("--q", type=int, default=97)
    sc.add_argument("--eta", type=int, default=2)
    sc.add_argument("--m-mult", type=int, default=2, help="m = m_mult * n")
    sc.add_argument("--seed", type=int, default=1)
    sc.add_argument("--max-bf", type=int, default=8_000_000)
    sc.add_argument("--max-monomials", type=int, default=1500)
    sc.add_argument("--max-nodes", type=int, default=2_000_000)

    lk = sub.add_parser("leak", help="qué pasa si se filtra parte del secreto")
    lk.add_argument("--n", type=int, default=40)
    lk.add_argument("--k", type=int, default=8)
    lk.add_argument("--q", type=int, default=97)
    lk.add_argument("--eta", type=int, default=2)
    lk.add_argument("--m-mult", type=int, default=2)
    lk.add_argument("--seed", type=int, default=1)
    lk.add_argument("--max-nodes", type=int, default=2_000_000)

    wv = sub.add_parser("wave", help="ondas + pliegues + FFT: el ataque dual, y dónde se rompe")
    wv.add_argument("--ns", default="3,8,12,16,24,32,40")
    wv.add_argument("--keep", type=int, default=2, help="incógnitas que quedan para la FFT (<= 3)")
    wv.add_argument("--q", type=int, default=97)
    wv.add_argument("--eta", type=int, default=2)
    wv.add_argument("--m-mult", type=int, default=2)
    wv.add_argument("--seed", type=int, default=1)
    wv.add_argument("--max-waves", type=int, default=4000)

    sub.add_parser("selftest", help="comprobaciones internas")

    args = ap.parse_args()
    if args.cmd == "demo":
        cmd_demo(args)
    elif args.cmd == "scale":
        cmd_scale(args)
    elif args.cmd == "leak":
        cmd_leak(args)
    elif args.cmd == "wave":
        cmd_wave(args)
    elif args.cmd == "selftest":
        sys.exit(cmd_selftest(args))


if __name__ == "__main__":
    main()
