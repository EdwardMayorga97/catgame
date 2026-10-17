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
python3 lwe_lab.py wave         # ondas + pliegues + FFT (ataque dual) y dónde se rompe (~7 s)
python3 lwe_lab.py euclid       # 1 incógnita, primo de Mersenne de 2203 bits: cae en ms
python3 lwe_lab.py ring         # anillo de polinomios: la puerta r=1 y cómo la cierra ML-KEM
python3 lwe_lab.py amplify      # la raíz del muro: eliminar incógnitas multiplica el error (~6 s)
python3 lwe_lab.py sieve        # la criba: partículas que chocan a 60°; exponente medido (~30 s)
python3 lwe_lab.py ringsieve    # ¿la simetría del anillo de ML-KEM cambia el exponente? (~45 s)
python3 lwe_lab.py period       # puerta cuántica: ¿tiene LWE un periodo tipo Shor? (~2 s)
python3 lwe_lab.py module       # puerta algebraica: ¿el rango 2 esconde un sub-retículo denso? (~1 s)
```

## Qué mirar

| Comando | Qué enseña |
|---|---|
| `demo` | Cómo se guarda el secreto `s`, qué se publica `(A, b)`, cómo se cifra un bit y por qué el error `e` es el candado. Después, cada ataque sobre la misma instancia y el atacante leyendo el mensaje. |
| `scale` | Con `q=97` LLL rompe todo hasta `n=32` en segundos y falla en `n=40`; la enumeración exacta se queda sin presupuesto. Fuerza bruta y Arora-Ge quedan fuera mucho antes. La última columna estima el bloque BKZ que haría falta y su coste `2^(0.292·β)`. |
| `leak` | En `n=40` el ataque falla; con 8 coordenadas de `s` filtradas, LLL vuelve a ganar. Cada coordenada conocida divide la fuerza bruta entre `q` y agranda la brecha del retículo. |
| `euclid` | Una sola incógnita con el primo de Mersenne `2^2203 − 1` como módulo y errores de 1.000 bits: Euclides (reducción de Gauss en 2D) la rompe en 6 ms. La dificultad es el número de incógnitas, no el tamaño de los números. |
| `ring` | Ring-LWE de juguete. En `x^n − 1`, sustituir `x = 1` conserva lo pequeño y regala una ecuación sobre el secreto (ataque de Elias–Lauter–Ozman–Stange, 2015). En `x^n + 1`, el anillo de ML-KEM, ninguna raíz lo conserva. |
| `amplify` | El dueño multiplica por 1; el atacante tiene que eliminar incógnitas y multiplica el error por el tamaño de sus multiplicadores. Compara multiplicadores uniformes, LLL e ideales con el umbral `q/4`, y hace la cuenta para ML-KEM-512: existen `2^1024` multiplicadores buenos y nadie sabe encontrar uno. |
| `sieve` | Criba de Gauss: vectores del retículo que chocan y se acortan. Mide cuántas partículas hacen falta por dimensión (≈ `2^(0.21·dim)` en teoría) y explica el exponente con la geometría del choque a 60°. |
| `ringsieve` | El mismo retículo dual construido aleatorio y con la estructura de anillo (cada vector regala sus n rotaciones). Mismo número de partículas al final (mismo exponente); la simetría solo ahorra lanzadas, un factor que crece como n. |
| `period` | La puerta cuántica. Factorizar tiene un peine de Fourier de `r` dientes (verificado: cuenta dientes y factoriza N); LWE tiene un solo pico entre `q^n` candidatos (verificado por enumeración). Shor necesita el peine; LWE no lo tiene, y el anillo solo ofrece `n` rotaciones (polinómico). |
| `module` | La puerta algebraica. Vector más corto / heurística gaussiana en retículos aleatorios y en módulos de rango 2 (ML-KEM), con el mínimo exacto. El módulo no es más denso (su mínimo es igual o mayor): la estructura da multiplicidad `2n` por rotaciones, no densidad. No hay rampa de descenso como la que hundió el rango 1. |
| `wave` | El ataque dual: pliega `n-2` incógnitas con vectores duales cortos `w` y evalúa las `q²` opciones restantes de golpe con una FFT. La señal de cada onda es `exp(-2π²σ²|w|²/q²)`; el pico medido sigue a la fórmula y se hunde en cuanto LLL deja de encontrar pliegues cortos. La columna `fantasma` mide el falso candidato más alto: 7–11 frente a 4,3 si las ondas fueran independientes, el fallo que Ducas y Pulles señalaron en el ataque de MATZOV. |

## Ataques implementados

0. **Sin errores**: eliminación gaussiana mod q. Instantáneo. Muestra por qué sin `e` no hay candado.
1. **Fuerza bruta**: prueba todos los `s`. Coste `q^n`.
2. **Arora-Ge**: cada pista da un polinomio de grado `2·eta+1`; se linealiza. Polinomial, pero necesita `C(n+2eta+1, 2eta+1)` pistas, que un esquema real no da.
3. **LLL** sobre el retículo de Kannan: el vector `(e, 1)` es mucho más corto que el resto y LLL lo encuentra mientras `n` es pequeño frente a `q`.
4. **Enumeración exacta** (Schnorr-Euchner / Gama-Nguyen-Regev) tras LLL: siempre funciona con tiempo suficiente; el número de nodos crece exponencialmente. Es lo que BKZ hace por bloques.
5. **Fuga**: conocer `k` coordenadas de `s` reduce el problema a `n-k`.
6. **Ondas (ataque dual con FFT)**: vectores duales cortos pliegan el problema; una FFT prueba todas las opciones restantes a la vez. Muestra con una fórmula por qué el muro es el vector más corto.

## Parámetros útiles

```bash
python3 lwe_lab.py scale --q 3329 --ns 16,32,48          # módulo de Kyber: LLL aguanta más n
python3 lwe_lab.py scale --eta 1 --ns 4,8,12,16            # error pequeño: Arora-Ge gana más lejos
python3 lwe_lab.py scale --ns 40 --max-nodes 20000000      # insistir con la enumeración
python3 lwe_lab.py demo --n 6 --q 97 --m 18 --eta 2 --msg "miau"
```

Lo que no hace: no usa secretos pequeños ni polinomios (módulos) como ML-KEM, y no implementa BKZ
completo. Para eso, el siguiente paso es `fpylll` (BKZ real) y el `lattice-estimator`.
