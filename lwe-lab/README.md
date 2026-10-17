# LWE Lab

Laboratorio de *Learning With Errors* de punta a punta: el cifrado de Regev
(la base de ML-KEM / Kyber), con sus ataques del más tonto al más sofisticado.
Solo necesita Python 3 y numpy.

```bash
pip install numpy
python3 lwe_lab.py selftest     # comprobaciones internas (~10 s)
python3 lwe_lab.py demo         # recorrido narrado con n=4, q=53 (~1 s)
python3 lwe_lab.py scale        # crece n de 4 a 40 y mide cada ataque (~40 s)
python3 lwe_lab.py leak         # qué pasa si se filtra parte del secreto (~15 s)
```

## Qué mirar

| Comando | Qué enseña |
|---|---|
| `demo` | Cómo se guarda el secreto `s`, qué se publica `(A, b)`, cómo se cifra un bit y por qué el error `e` es el candado. Después, cada ataque sobre la misma instancia y el atacante leyendo el mensaje. |
| `scale` | Con `q=97` LLL rompe todo hasta `n=32` en segundos y falla en `n=40`; la enumeración exacta se queda sin presupuesto. Fuerza bruta y Arora-Ge quedan fuera mucho antes. La última columna estima el bloque BKZ que haría falta y su coste `2^(0.292·β)`. |
| `leak` | En `n=40` el ataque falla; con 8 coordenadas de `s` filtradas, LLL vuelve a ganar. Cada coordenada conocida divide la fuerza bruta entre `q` y agranda la brecha del retículo. |

## Ataques implementados

0. **Sin errores**: eliminación gaussiana mod q. Instantáneo. Muestra por qué sin `e` no hay candado.
1. **Fuerza bruta**: prueba todos los `s`. Coste `q^n`.
2. **Arora-Ge**: cada pista da un polinomio de grado `2·eta+1`; se linealiza. Polinomial, pero necesita `C(n+2eta+1, 2eta+1)` pistas, que un esquema real no da.
3. **LLL** sobre el retículo de Kannan: el vector `(e, 1)` es mucho más corto que el resto y LLL lo encuentra mientras `n` es pequeño frente a `q`.
4. **Enumeración exacta** (Schnorr-Euchner / Gama-Nguyen-Regev) tras LLL: siempre funciona con tiempo suficiente; el número de nodos crece exponencialmente. Es lo que BKZ hace por bloques.
5. **Fuga**: conocer `k` coordenadas de `s` reduce el problema a `n-k`.

## Parámetros útiles

```bash
python3 lwe_lab.py scale --q 3329 --ns 16,32,48          # módulo de Kyber: LLL aguanta más n
python3 lwe_lab.py scale --eta 1 --ns 4,8,12,16            # error pequeño: Arora-Ge gana más lejos
python3 lwe_lab.py scale --ns 40 --max-nodes 20000000      # insistir con la enumeración
python3 lwe_lab.py demo --n 6 --q 97 --m 18 --eta 2 --msg "miau"
```

Lo que no hace: no usa secretos pequeños ni polinomios (módulos) como ML-KEM, y no implementa BKZ
completo. Para eso, el siguiente paso es `fpylll` (BKZ real) y el `lattice-estimator`.
