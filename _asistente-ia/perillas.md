# Sliders del modo Análisis (Object Tracking)

## Confianza (0.00 – 1.00)
Mínima seguridad que YOLO debe tener para aceptar una detección.

- **Bajo (0.10–0.30)** → detecta casi todo, pero con falsos positivos.
- **Medio (0.40–0.60)** → balance razonable (default: 0.25).
- **Alto (0.70–1.00)** → solo detecciones muy seguras, puede perder objetos chicos.

## Q — Ruido de proceso (0.0 – 10.0)
Qué tan rápido se adapta el Filtro de Kalman a los cambios de movimiento. Controla cuánto "confía en su modelo de velocidad".

- **Bajo (0.1–1.0)** → el bbox verde se mueve **suave** pero va **atrasado** si el objeto se mueve rápido.
- **Alto (5.0–10.0)** → el bbox verde sigue **instantáneo** pero puede ser **nervioso/errático**.

## R — Ruido de medición (0.0 – 20.0)
Cuánto confía Kalman en la medición de YOLO vs su propia predicción.

- **Bajo (0.5–3.0)** → el bbox verde se pega al azul de YOLO (hereda su ruido, rebota).
- **Alto (10.0–20.0)** → el bbox verde **ignora** los saltos de YOLO, es más suave pero puede ignorar cambios reales.

## Relación práctica

| Situación | Confianza | Q | R |
|-----------|-----------|---|---|
| Objeto fácil (persona, mano visible) | 0.50 | 2.0 | 3.0 |
| Objeto chico/difícil (spoon, remote) | 0.15 | 4.0 | 2.0 |
| Mucha oclusión (se esconde seguido) | 0.30 | 3.0 | 10.0 |
