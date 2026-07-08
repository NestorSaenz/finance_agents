# 5. Evaluación y experimentos

Evaluar un asistente conversacional que opera sobre datos estructurados no es lo mismo que evaluar
un modelo con un *benchmark* académico: aquí no interesa tanto una métrica única de "acierto" del
modelo como comprobar que el sistema, en su conjunto, hace lo correcto, de forma fiable y a un coste
razonable. Por eso la evaluación combina tres frentes: la verificación técnica del código, la
validación funcional del comportamiento y la observación del coste y el rendimiento en ejecución
real.

## 5.1. Estrategia y métricas

La estrategia de evaluación se apoya en las siguientes métricas e instrumentos:

- **Cobertura de pruebas y análisis estático.** Número de pruebas automatizadas que pasan, y
  resultado del analizador de tipos y del *linter*. Miden la solidez y la mantenibilidad del código.
- **Validación funcional por requisito.** Para cada requisito funcional (capítulo 3) se comprueba que
  el sistema produce el resultado esperado ante interacciones representativas. Es una evaluación
  cualitativa de extremo a extremo, sobre datos reales.
- **Coste y latencia.** A través de la observabilidad (Langfuse) se registran, por conversación y por
  llamada al modelo, el número de tokens, el coste asociado y la latencia. Permite valorar la
  eficiencia y el efecto de las decisiones de diseño orientadas al coste.

## 5.2. Resultados

### Resultados cuantitativos (verificación técnica)

La verificación técnica arroja resultados sólidos y reproducibles:

- La *suite* de pruebas del backend pasa por completo (**288 pruebas**), cubriendo repositorios,
  servicios, herramientas del agente, rutas y flujos de extremo a extremo con dobles de prueba que
  sustituyen a los proveedores externos.
- La *suite* del frontend pasa igualmente (**30 pruebas**), centradas en el cliente de API, el
  contexto de autenticación y los componentes del chat.
- El analizador de tipos en modo estricto no reporta ningún error (**0 errores** sobre el conjunto de
  archivos del backend) y el *linter* está limpio.

Estos números no son un fin en sí mismos, pero respaldan un requisito no funcional importante —la
mantenibilidad— y dan confianza para introducir cambios sin romper lo existente, algo que se aprovechó
repetidamente a lo largo del desarrollo.

### Resultados cualitativos (validación funcional)

La comprobación funcional se realizó ejercitando el sistema con interacciones representativas de cada
capacidad. La tabla resume algunos casos y su resultado observado.

| Capacidad | Interacción de ejemplo | Resultado observado |
|---|---|---|
| Registro (RF1) | "gasté 80 en cine" | Movimiento registrado como gasto |
| Categorización RAG (RF3) | "pagué 200 en el supermercado" | Categoría asignada: *alimentación* |
| Categoría propia (RF3) | "gasté 50.000 en jardinería" | Categoría *jardinería* conservada (no forzada a "otros") |
| Consulta multi-turno (RF9) | "¿en qué categoría quedó ese gasto?" | Responde desde la base de datos, con el gasto del turno anterior |
| Análisis (RF7) | "¿en qué gasto más?" | Desglose por categoría con importes y porcentajes |
| Corrección/borrado (RF2) | "elimina la de YouTube" | Localiza el movimiento por descripción y pide confirmación |
| Ingesta por imagen (RF8) | (captura de un Excel) | Extrae los movimientos y los propone antes de guardar |
| Fuera de alcance | "escríbeme un poema" | Rechazo cortés sin invocar el modelo caro |

En todos los casos el comportamiento observado se corresponde con el requisito, incluido el manejo de
las situaciones límite que se detallan más abajo.

### Coste y latencia

La observabilidad permite cuantificar el comportamiento en producción, y los datos confirman el
efecto del **enrutamiento por complejidad**. Las llamadas de clasificación, resueltas con el modelo
económico (gemini-2.5-flash-lite), cuestan del orden de 0,00004 USD cada una; las del agente, con el
modelo capaz (gemini-2.5-flash), rondan los 0,0008 USD. Dicho de otro modo, el modelo económico
resulta unas **veinte veces más barato** por llamada, lo que justifica reservar el modelo grande solo
para la parte que realmente lo necesita. Una conversación típica —una clasificación más una o dos
llamadas del agente— cuesta en torno a una **milésima de dólar** (≈ 0,001 USD), muy por debajo de un
céntimo. En cuanto a la latencia, cada llamada al modelo se resuelve habitualmente entre **0,4 y 3,7
segundos**; a ello se añade, solo en la primera petición tras un periodo de inactividad, el arranque
en frío de Cloud Run —del orden de diez a veinte segundos—, inherente al escalado a cero.

La tabla siguiente recoge el coste y la latencia observados por nivel de modelo, que ilustran la
diferencia entre ambos.

| Modelo | Papel | Coste aprox. por llamada | Latencia por llamada |
|---|---|---|---|
| gemini-2.5-flash-lite | Clasificación (económico) | ≈ 0,00004 USD | ≈ 0,4 – 3,7 s |
| gemini-2.5-flash | Agente (capaz) | ≈ 0,0008 USD | ≈ 0,7 – 3,2 s |

## 5.3. Análisis de errores y limitaciones

Buena parte del aprendizaje del proyecto vino de los fallos detectados al probar el sistema con datos
reales. Documentarlos es tan valioso como los aciertos, porque muestran cómo se adaptó el diseño a las
limitaciones reales de los modelos.

- **Identificadores inventados o alterados.** El modelo, al intentar corregir o borrar un movimiento,
  inventaba o modificaba los identificadores. La solución no fue insistir con el prompt, sino cambiar
  el diseño: las operaciones de corrección y borrado se resuelven por la descripción del movimiento, y
  es el sistema quien encuentra el registro. El modelo dejó de manejar identificadores.
- **Fechas relativas erróneas.** Sin conocer la fecha actual, el modelo situaba "ayer" en un día
  arbitrario. Se corrigió inyectando la fecha de hoy en el contexto del agente.
- **Registros duplicados desde el historial.** El agente reinterpretaba movimientos de turnos
  anteriores y los registraba de nuevo. Se resolvió con una regla explícita de actuar únicamente sobre
  la última petición del usuario.
- **Diferencias entre proveedores.** El formato de las llamadas a herramientas difería entre
  proveedores, lo que rompía el protocolo multivuelta en uno de ellos. Se optó por un enfoque
  independiente del proveedor, más robusto frente a estas diferencias.
- **Precisión monetaria.** El uso inicial de coma flotante para el dinero podía introducir errores de
  redondeo; se migró a aritmética decimal exacta.

En cuanto a las **limitaciones** conocidas, conviene ser explícito. Las alertas de presupuesto se
evalúan bajo demanda, al consultar, y no como una notificación proactiva. No hay integración bancaria:
los datos los aporta el usuario. La categorización automática está pensada para descripciones breves y
puede fallar ante textos ambiguos, en cuyo caso recae en la categoría "otros". No se realizó una
evaluación con un conjunto etiquetado de gran tamaño, sino una validación funcional representativa; una
medición más formal de la precisión de la categorización queda como trabajo futuro. Por último, al
apoyarse en modelos de lenguaje, el sistema hereda su naturaleza no determinista, mitigada —que no
eliminada— con las reglas y salvaguardas descritas.
