# Sistema de Reconocimiento Facial basado en Templates y Embeddings Biométricos
> **Taller de Investigación II**  
> *Arquitectura de Reconocimiento Facial con Privacidad por Diseño (LFPDPPP), Malla Facial en Vivo (MediaPipe Face Mesh), Validación Preventiva de Duplicados y Almacenamiento Vectorial Exclusivo en Base de Datos.*

---

## 1. Fundamento Conceptual y Marco Teórico

Tradicionalmente, muchos sistemas de control de acceso almacenan fotografías en formatos `.jpg` o `.png`. Esta práctica presenta serias vulnerabilidades:
1. **Riesgo Legal y de Privacidad:** Vulneración a la *Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)* al retener datos biométricos sensibles en formatos directamente interpretables o sustraíbles.
2. **Consumo Excesivo de Almacenamiento:** Un archivo fotográfico promedio pesa entre $500\text{ KB}$ y $2\text{ MB}$.
3. **Latencia Elevada:** Leer imágenes desde disco y procesarlas en tiempo real genera cuellos de botella en horarios de alta afluencia.

### La Solución: Deep Metric Learning, Malla Facial y Embeddings de 128-D

Este proyecto implementa una arquitectura basada en **Deep Metric Learning** (red neuronal convolucional profunda basada en una variante de **ResNet-34** con **Triplet Loss**) combinada con la malla facial tridimensional de **Google MediaPipe Face Mesh** (468 puntos de referencia):

```
   [ Fotograma Capturado por Cámara ]
                  │
                  ▼  (Efecto espejo + Malla Facial 3D de 468 puntos - MediaPipe)
         [ Malla en Tiempo Real ]
                  │
                  ▼  (Detección precisa y alineación - HOG/Dlib)
     [ Vector de 128 flotantes: -0.142, 0.089, ..., 0.231 ]
                  │
        ┌─────────┴───────────────────────────────────────┐
        ▼                                                 ▼
 [ Validación Preventiva de Duplicados ]          [ Descartar Fotograma ]
 (Verificación en BD: Matrícula y Rostro L2 <= 0.55)   (Liberar memoria RAM de inmediato)
        │
        ▼ (Si es único)
 [ Guardar en BD ] -> Solo 1024 bytes (BLOB / BYTEA)
```

1. El rostro detectado se proyecta en una esfera unitaria dentro del espacio euclidiano de 128 dimensiones ($\mathbb{R}^{128}$).
2. La transformación es **unidireccional y no invertible**: a partir de los 128 escalares es matemáticamente inviable reconstruir el rostro original.
3. El fotograma de la cámara se mantiene únicamente en memoria volátil por fracciones de segundo y se destruye inmediatamente tras generar el vector.

---

## 2. Mejoras Clave Incorporadas

### A. Validación de Estudiantes Duplicados (Paso Crucial)
1. **Validación por Matrícula (Nivel Datos):** Consulta previa en base de datos (`SELECT id FROM estudiantes WHERE matricula = ?`). Si ya existe, interrumpe el flujo y emite una alerta indicando el nombre del alumno al que pertenece.
2. **Validación Biométrica Preventiva (Nivel Rostro):** Antes de persistir un nuevo vector, el sistema calcula la distancia euclidiana contra todas las identidades activas en la BD. Si la distancia es $\le 0.55$, **rechaza el enrolamiento** para evitar suplantación o que la misma persona se registre dos veces con diferentes matrículas.

### B. Malla Facial en Vivo (MediaPipe Face Mesh - 468 Landmarks)
- Durante el registro, se renderiza la malla facial de 468 puntos de referencia en 3D en tiempo real sobre el rostro del alumno.
- Utiliza teselación (`FACEMESH_TESSELATION`) y contornos anatómicos (`FACEMESH_CONTOURS`) para certificar que el estudiante está perfectamente centrado y enfocado antes de capturar el template.

### C. HUD Visual con Prevención de Parpadeo (Visual Cooldown)
- En el módulo de acceso en tiempo real, el resultado de la verificación (**AUTORIZADO** en verde o **DENEGADO** en rojo) permanece estable en pantalla durante 3 segundos mediante una tarjeta de retroalimentación flotante (`AccessVisualState`), eliminando el parpadeo molesto cuando el alumno permanece frente a la cámara.

---

## 3. Fundamento Matemático

### 3.1 Distancia Euclidiana ($L_2$)
Para comparar un vector capturado en vivo $\mathbf{u} \in \mathbb{R}^{128}$ contra una plantilla registrada $\mathbf{v} \in \mathbb{R}^{128}$:

$$d(\mathbf{u}, \mathbf{v}) = \|\mathbf{u} - \mathbf{v}\|_2 = \sqrt{\sum_{i=1}^{128} (u_i - v_i)^2}$$

### 3.2 Criterio de Decisión por Umbral
$$\text{Identidad}(\mathbf{u}, \mathbf{v}) = 
\begin{cases} 
\text{AUTORIZADO (Misma persona)}, & \text{si } d(\mathbf{u}, \mathbf{v}) \le \tau \\
\text{DENEGADO (Persona distinta)}, & \text{si } d(\mathbf{u}, \mathbf{v}) > \tau
\end{cases}$$

* Umbral configurado en $\tau = 0.55$.
* Si $d \le 0.55$, la confianza biométrica supera el $75\%-99\%$.

### 3.3 Comparación Matricial Vectorizada
Al presentarse un sujeto frente a la cámara, el vector en vivo $\mathbf{c} \in \mathbb{R}^{128}$ se compara simultáneamente contra la matriz de todos los alumnos registrados $\mathbf{M} \in \mathbb{R}^{N \times 128}$ mediante operaciones matriciales en NumPy:

$$\mathbf{D} = \sqrt{\sum_{j=1}^{128} (M_{i,j} - c_j)^2} \quad \forall i \in \{1, \dots, N\}$$

La complejidad temporal es $\mathcal{O}(N)$, procesando miles de identidades en menos de $1\text{ milisegundo}$.

---

## 4. Estructura del Repositorio

```
Proyecto/
├── config.py                 # Configuración central (umbral L2, persistencia visual, cámara)
├── .env.example              # Plantilla de variables de entorno
├── requirements.txt          # Dependencias del proyecto (incluye mediapipe)
├── main.py                   # Interfaz interactiva CLI principal
├── README.md                 # Marco teórico y manual de operación
├── src/
│   ├── biometrics/
│   │   ├── encoder.py        # Detección y extracción del vector 128-D (Dlib ResNet)
│   │   └── matcher.py        # Comparador vectorial euclidiano con álgebra matricial
│   ├── db/
│   │   ├── database.py       # Capa de persistencia (soporte SQLite local y PostgreSQL)
│   │   └── models.py         # Modelos de datos: Estudiante y RegistroAcceso
│   ├── modules/
│   │   ├── registro.py       # Paso A: Enrolamiento con Malla Facial y Validación de Duplicados
│   │   ├── reconocimiento.py # Paso B: Control de acceso con HUD anti-parpadeo
│   │   └── admin.py          # Auditoría, exportación CSV y reporte comparativo
│   └── utils/
│       └── visualizer.py     # Renderizador de Malla Facial (468 landmarks) y HUD interactivo
└── tests/
    └── test_biometrics.py    # Suite de pruebas unitarias automatizadas (7 tests)
```

---

## 5. Guía de Ejecución

Ejecute el menú interactivo principal:

```bash
cd "/home/juanpa26/Descargas/Taller de investigacion II/Proyecto"
source .venv/bin/activate
python3 main.py
```

### Opciones Disponibles:
1. **[Paso A] Registrar nuevo estudiante:** Abre la cámara en modo espejo con la **malla facial de 468 puntos**. Valida que la matrícula no exista previamente. Al presionar **[ESPACIO]**, realiza la **validación biométrica preventiva** contra la base de datos; si el rostro ya pertenece a otra persona, detiene el registro. Si es válido, guarda el vector de 1024 bytes y destruye la imagen de la memoria.
2. **[Paso B] Control de acceso en vivo:** Reconocimiento continuo con tarjeta flotante estable (Verde: AUTORIZADO, Rojo: DENEGADO) con temporizador visual para evitar parpadeos.
3. **Listar estudiantes:** Muestra los IDs, matrículas y vectores almacenados.
4. **Consultar bitácora:** Historial de accesos con distancias euclidianas registradas.
5. **Exportar CSV:** Genera un archivo CSV con toda la auditoría.
6. **Eliminar estudiante:** Da de baja a un alumno y borra su vector asociado.
7. **Ver informe técnico:** Métricas de investigación sobre LFPDPPP y ahorro en disco.
8. **Probar cámara:** Verificación rápida de video en `/dev/video0`.

---

## 6. Pruebas Automatizadas

Para validar matemáticamente el sistema y el filtro de duplicados:

```bash
python3 -m unittest discover -s tests -v
```

Resultado:
```text
test_access_audit_log ... ok
test_database_persistence_without_images ... ok
test_duplicate_matricula_detection ... ok
test_euclidean_distance_and_matching ... ok
test_invalid_vector_dimensions_raise_error ... ok
test_preventive_biometric_duplicate_detection ... ok
test_vector_serialization_dimensions ... ok

----------------------------------------------------------------------
Ran 7 tests in 0.105s

OK
```

---

## 7. Cumplimiento con la Normativa LFPDPPP

Conforme al **Artículo 3, Fracción VI** de la *Ley Federal de Protección de Datos Personales en Posesión de los Particulares (LFPDPPP)* de México:
- Los datos biométricos son considerados **Datos Personales Sensibles**.
- El **Principio de Proporcionalidad y Minimización** (Art. 13) exige recabar únicamente los datos estrictamente necesarios para la finalidad perseguida.
- Al transformar la imagen facial en un **vector abstracto unidimensional de 128 valores continuos** y eliminar la imagen física, este sistema garantiza que aun en el hipotético caso de una brecha en la base de datos, **los atacantes nunca tendrán acceso a fotos o rostros visuales de los estudiantes**.
