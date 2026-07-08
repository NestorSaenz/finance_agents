# 1. Introducción

## 1.1. Contexto y motivación

Este Trabajo Final de Máster nace de una necesidad que vivo de primera mano. En mi núcleo
familiar llevamos el control de las finanzas del hogar en una hoja de cálculo de Excel: cada
gasto y cada ingreso se anota a mano, se clasifica en una columna de categoría y, a final de
mes, intentamos cuadrar cuánto entró, cuánto salió y en qué se nos fue el dinero. Con el
tiempo comprobé que ese método, aunque funciona, tiene tres problemas que se repiten mes a
mes: exige **disciplina constante** (si dejas de anotar dos días, pierdes el hilo), obliga a
**recordar y respetar una estructura rígida** de categorías y fórmulas, y no ofrece ninguna
**lectura inteligente** de la información —el Excel guarda los números, pero no te dice nada
sobre ellos—.

De esa fricción cotidiana surgió la pregunta que ha guiado todo el proyecto: *¿y si en lugar
de rellenar celdas pudiéramos simplemente escribirle a un asistente, con nuestras propias
palabras, "gasté 200.000 en el supermercado", y que él se encargara de registrarlo,
clasificarlo y, cuando se lo pidamos, explicarnos cómo vamos?* Esa idea —sustituir el
formulario por una conversación— es la que da sentido a **Safi**, el asistente que presento
en esta memoria.

La gestión de las finanzas personales es un problema real y extendido. Las aplicaciones
tradicionales del mercado suelen caer en los mismos inconvenientes que sufría con el Excel:
requieren una entrada manual tediosa, imponen categorías cerradas que no siempre encajan con
la vida de cada familia, y ofrecen análisis genéricos poco accionables. Al mismo tiempo, el
Máster en Ingeniería y Desarrollo de Soluciones de IA Generativa me ha dado las herramientas
para atacar justamente esas carencias: los modelos de lenguaje de gran tamaño (LLM) permiten
entender el lenguaje natural, las arquitecturas de agentes permiten *ejecutar acciones* a
partir de esa comprensión, y técnicas como RAG o la ingesta multimodal permiten conectar el
modelo con los datos reales del usuario. Unir esa necesidad personal con estos conocimientos
es, en esencia, la motivación de este TFM.

Conviene aclarar el punto de partida para valorar la aportación: **Safi no pretende competir
con la banca ni con soluciones de mercado consolidadas**, sino resolver de forma concreta y
útil un problema que conozco bien. El público objetivo son personas y familias que hoy llevan
sus cuentas "a mano" —en una libreta, en notas del móvil o, como nosotros, en una hoja de
cálculo— y que ganarían mucho con un asistente que entienda lo que escriben, mantenga el orden
por ellos y les devuelva una visión clara de su dinero. En ese sentido, el proyecto tiene
además una vocación práctica más allá del máster: es una herramienta que mi propia familia
puede empezar a usar, y una base sobre la que seguir construyendo.

## 1.2. Objetivos

### Objetivo general

Diseñar y desarrollar **Safi**, un asistente conversacional multiagente basado en IA
Generativa para la gestión de finanzas personales, que permita **registrar, consultar y
analizar** los movimientos económicos mediante lenguaje natural, sustituyendo el control
manual en hojas de cálculo por una experiencia guiada, automatizada y accesible desde la web.

### Objetivos específicos

1. **Arquitectura de agentes.** Diseñar una arquitectura orquestada con LangGraph que combine
   un clasificador de intención económico (enrutador) con un agente de razonamiento y acción
   (ReAct) capaz de invocar herramientas para operar sobre datos reales.
2. **Gestión conversacional del dinero.** Implementar el registro, consulta, corrección y
   eliminación —por lenguaje natural— de transacciones, presupuestos, metas de ahorro y
   tarjetas de crédito.
3. **Categorización inteligente y flexible.** Construir un categorizador automático apoyado en
   RAG (embeddings + búsqueda vectorial) y permitir además **categorías propias** definidas por
   el usuario, sin imponer un esquema rígido.
4. **Capacidades multimodales.** Permitir la carga de una **imagen** (foto o captura de una
   hoja de cálculo) para extraer de ella los movimientos de forma asistida, pidiendo
   confirmación antes de guardar.
5. **Memoria del asistente.** Dotar a Safi de memoria conversacional a corto plazo y de un
   conocimiento persistente del usuario a largo plazo.
6. **Seguridad y multiusuario.** Garantizar autenticación real (JWT) y el aislamiento estricto
   de los datos de cada usuario.
7. **Observabilidad y coste.** Incorporar trazabilidad de extremo a extremo (peticiones,
   tokens y coste) y aplicar estrategias de optimización de coste de los modelos.
8. **Reproducibilidad y despliegue.** Empaquetar y desplegar la solución en la nube de forma
   reproducible, con las credenciales correctamente externalizadas.
9. **Interfaz de usuario.** Ofrecer una interfaz web *responsive* con chat y un panel de
   resumen (dashboard) claros y usables.
10. **Calidad de software.** Mantener una base de código ordenada (arquitectura limpia, tipado
    estricto) y verificada mediante pruebas automatizadas.

## 1.3. Alcance de la solución

El proyecto se plantea como un **Producto Mínimo Viable (MVP) funcional y representativo**, en
línea con lo que solicita la guía del TFM: una aplicación que se pueda ejecutar y que muestre
con claridad el valor de la idea, más que un producto cerrado y listo para el mercado.

**Queda dentro del alcance** la gestión conversacional completa de transacciones, presupuestos,
metas y tarjetas; la categorización automática con soporte de categorías dinámicas; la ingesta
de movimientos por imagen; la memoria a corto y largo plazo; la autenticación multiusuario; la
observabilidad; la interfaz web (chat + dashboard); y el despliegue en la nube.

**Queda fuera del alcance** (por decisión de priorización o por corresponder a fases
posteriores): la integración bancaria automática —los datos los aporta el usuario, no se
conectan cuentas reales—, una aplicación móvil nativa —la interfaz es web *responsive*—, los
modelos de predicción financiera avanzada, y el módulo de **seguimiento de inversiones** que se
contemplaba en el anteproyecto y que finalmente se reubica como línea de trabajo futuro para
concentrar el esfuerzo en el núcleo transaccional, que es donde reside el valor cotidiano de la
herramienta.

Cabe señalar que la solución final **evolucionó respecto a la propuesta inicial**: se sustituyó
parte del stack tecnológico (por ejemplo, el proveedor de modelos y la base de datos vectorial)
y se simplificó la arquitectura de agentes, a la vez que se **incorporaron capacidades no
previstas** —como la ingesta multimodal, las categorías dinámicas o el despliegue en la nube—.
Estas decisiones, y su justificación, se detallan a lo largo de la memoria (especialmente en
los capítulos 3 y 4) y se recogen de forma comparada en las conclusiones.

## 1.4. Estructura de la memoria

Tras esta introducción, el documento aborda el estado del arte y los fundamentos teóricos
(capítulo 2), los requisitos y el diseño de la solución (capítulo 3) y su implementación
(capítulo 4). A continuación se presentan la evaluación y experimentos (capítulo 5) y las
pruebas y validación del producto (capítulo 6), para cerrar con la discusión (capítulo 7) y las
conclusiones y trabajo futuro (capítulo 8). Finalmente se incluyen la bibliografía y los anexos.
