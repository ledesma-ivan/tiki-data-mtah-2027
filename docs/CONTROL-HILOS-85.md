# Prueba de paralelismo - #85

Solo selección abierta; excluido Metrica Game 2. No se evaluaron B ni reserva ni se seleccionó un modelo.
Filas y orden idénticos, hojas 63, lambda 10, corte 5 s; solo cambia la cantidad de hilos OpenMP.
Comparación de hashes del modelo exportado y scores enteros en un subconjunto fijo de features de entrenamiento.

| Peso | Hilos | Segundos | SHA256 | Scores distintos frente a 1 hilo |
|---|---|---|---|---|
| 1 | 1 | 58.83 | `fe185f32e856163254c0b99282f720f954b568498761b2a1f5205adcf826059a` | 0 |
| 1 | 4 | 21.61 | `fe185f32e856163254c0b99282f720f954b568498761b2a1f5205adcf826059a` | 0 |
| 1 | 12 | 18.18 | `fe185f32e856163254c0b99282f720f954b568498761b2a1f5205adcf826059a` | 0 |
| 3 | 1 | 52.84 | `7e606bc4857af1665c08264f3a9cd7e50132bd8b0f3be69fb8d4643f034fe2e2` | 0 |
| 3 | 4 | 19.27 | `7e606bc4857af1665c08264f3a9cd7e50132bd8b0f3be69fb8d4643f034fe2e2` | 0 |
| 3 | 12 | 18.95 | `7e606bc4857af1665c08264f3a9cd7e50132bd8b0f3be69fb8d4643f034fe2e2` | 0 |

Tiempo total: 251.8 s.
