# 2. Estado del arte y fundamentos teóricos

Antes de entrar en el diseño conviene mirar dos cosas: cómo se resuelve hoy la gestión de las
finanzas personales —y qué le falta a lo que ya existe— y qué conceptos y técnicas hacen posible
un asistente como Safi. Este capítulo recorre ambos frentes. No pretende ser un tratado teórico
exhaustivo, sino dar el contexto justo para entender y justificar las decisiones que se toman más
adelante.

## 2.1. Soluciones existentes para la gestión de finanzas personales

El control del dinero doméstico se aborda hoy, a grandes rasgos, de tres maneras, y cada una
arrastra carencias que explican por qué tiene sentido este proyecto.

La primera son los **métodos manuales**: hojas de cálculo y libretas. Siguen siendo muy comunes
porque son flexibles y no cuestan nada; cada familia adapta sus categorías y sus fórmulas a su
manera. El problema es que toda la carga recae en la persona. Hay que anotar con constancia —si se
dejan dos días, se pierde el hilo—, mantener a mano una estructura que es fácil de romper, y
conformarse con que la hoja guarde los números sin decir nada sobre ellos. Este es, de hecho, el
punto de partida real del trabajo.

La segunda son las **aplicaciones tradicionales de finanzas personales**, como YNAB, Fintonic,
Mobills o Wallet. Aportan interfaces cuidadas, categorización automática y cuadros de mando con
buenas visualizaciones. Aun así comparten limitaciones que pesan para el problema planteado: la
entrada de datos sigue siendo mayoritariamente manual y por formularios, la categorización se
apoya en reglas o catálogos cerrados poco adaptables, y el análisis tiende a ser genérico. Sobre
todo, apenas existe interacción en lenguaje natural. Las que se conectan con la banca, además,
dependen de integraciones que no están disponibles en todos los países ni con todas las entidades.

La tercera, más incipiente, son los **asistentes conversacionales apoyados en IA**. La llegada de
los modelos de lenguaje ha empujado esta tendencia, pero en el terreno concreto de las finanzas
personales todavía está poco desarrollada: rara vez se combina la conversación con la ejecución
real de acciones sobre los datos del usuario, y casi nunca se contempla la entrada multimodal
—por ejemplo, a partir de la foto de una hoja de cálculo—.

De aquí sale el espacio que ocupa Safi. La propuesta se sitúa en el cruce de esas carencias:
sustituir el formulario por la conversación, no solo entender sino actuar sobre los datos
(registrar, consultar, corregir), admitir categorías propias en lugar de un esquema rígido, y
permitir migrar mediante una imagen la información que el usuario ya tiene en su hoja de cálculo.
Esa combinación es la aportación que se desarrolla en los capítulos siguientes.

## 2.2. Modelos de lenguaje y la arquitectura Transformer

Un modelo de lenguaje de gran tamaño (LLM) predice el siguiente *token* a partir de un contexto, y
casi todos los actuales se construyen sobre la arquitectura Transformer (Vaswani et al., 2017). Su
idea central, el mecanismo de atención, permite que cada token pondere su relación con todos los
demás de la entrada; esto captura dependencias a larga distancia y, lo que resultó decisivo, hace
el entrenamiento paralelizable. De la variante autorregresiva (*decoder*) surgen los asistentes
conversacionales que se usan hoy.

Para este proyecto interesa una propiedad concreta que Brown et al. (2020) evidenciaron con GPT-3:
el aprendizaje en contexto. Al crecer en escala, estos modelos resuelven tareas nuevas a partir de
unos pocos ejemplos incluidos en el propio prompt, sin reentrenarse. Es justo lo que hace viable a
Safi sin entrenar un modelo propio: basta con instruir a un modelo generalista. En la práctica se
emplean modelos accedidos por API —Gemini 2.5 a través de Vertex AI como principal y Llama 3.3,
vía Groq, como respaldo—, y todo el comportamiento se consigue con instrucciones, orquestación de
agentes y conexión con los datos reales del usuario.

## 2.3. De comprender a actuar: agentes, ReAct y orquestación

Un LLM, por sí solo, genera texto: no consulta una base de datos ni registra un gasto. Para que un
asistente ejecute acciones sobre datos reales se recurre a los agentes, sistemas en los que el
modelo decide qué **herramientas** invocar —funciones externas que consultan, insertan o
calculan—, observa el resultado y sigue razonando hasta cerrar la tarea.

El patrón de referencia es ReAct (Yao et al., 2023), que alterna pasos de razonamiento con
llamadas a herramientas: el modelo piensa qué necesita, actúa llamando a una herramienta, observa
lo que devuelve y repite. La ventaja frente a responder de una sola vez es que se apoya en
información real en cada paso, en lugar de suponerla. La capacidad de invocar funciones de forma
estructurada —el *tool calling*— fue explorada por Schick et al. (2023) con Toolformer y hoy viene
integrada de serie en los modelos comerciales, que devuelven la llamada y sus argumentos ya
estructurados. A esto se suma una técnica sencilla y efectiva, el razonamiento paso a paso o
*chain-of-thought* (Wei et al., 2022), que mejora el desempeño en tareas con varios pasos lógicos.

La coordinación de estos flujos se apoya en LangGraph (LangChain, 2024), que modela la aplicación
como un grafo de estados y transiciones. Frente a una cadena lineal, el grafo admite bifurcaciones,
ciclos controlados y un estado compartido, algo que encaja con un asistente que unas veces
clasifica, otras registra y otras analiza. En la literatura conviven dos formas de orquestar estos
sistemas: los enfoques multiagente con planificación explícita —un agente planifica, otro ejecuta,
otro replanifica— y los agentes ReAct que unifican razonamiento y acción. La elección entre ambos,
con su justificación, se aborda en el capítulo 3.

## 2.4. Técnicas de adaptación de un modelo generalista

Adaptar un LLM a un dominio concreto admite varios niveles de esfuerzo. El más ligero es la
**ingeniería de prompts**: guiar el comportamiento con instrucciones bien redactadas, ejemplos y
restricciones, sin tocar los pesos del modelo. Es la base sobre la que se define el rol, las reglas
y el tono de cada agente de Safi.

Un peldaño por encima está la **generación aumentada por recuperación** (RAG; Lewis et al., 2020).
En lugar de fiarlo todo al conocimiento memorizado por el modelo, se recupera información relevante
de una fuente externa y se inyecta en el prompt antes de generar la respuesta. RAG reduce las
alucinaciones y permite trabajar con datos propios sin reentrenar. En este proyecto se usa para la
categorización semántica: la descripción de un gasto se compara con ejemplos de categorías
almacenados como vectores y se le asigna la más parecida.

El nivel de mayor control es el **ajuste fino** y sus variantes eficientes, como LoRA (Hu et al.,
2021), que reentrenan el modelo para especializarlo. Ofrecen precisión, pero exigen datos
etiquetados, cómputo y un mantenimiento continuo. Para el alcance de este TFM se descartó: la
combinación de *prompting* y RAG cubre las necesidades del dominio sin la carga de entrenar y
versionar modelos propios. Es una decisión de coste-beneficio que se retoma en el capítulo 3.

## 2.5. Representaciones vectoriales, búsqueda semántica y multimodalidad

RAG se sostiene sobre las **representaciones vectoriales** (*embeddings*): funciones que convierten
un texto en un vector de modo que los textos parecidos queden cerca en el espacio, cercanía que
suele medirse con la similitud del coseno (Reimers y Gurevych, 2019). Recuperar los vectores más
próximos de forma eficiente es un problema de búsqueda aproximada de vecinos, para el que existen
bases de datos e índices especializados (Johnson et al., 2019). En Safi los *embeddings* se generan
con gemini-embedding-001 (768 dimensiones) y se almacenan con pgvector, una extensión de
PostgreSQL. La razón de no recurrir a un servicio vectorial dedicado es sencilla: el dominio es
sobre todo dato estructurado —importes, fechas, categorías—, donde SQL manda, y la búsqueda
semántica es un apoyo, no el eje. Concentrar todo en una sola base de datos simplifica la
arquitectura.

En cuanto a la **multimodalidad**, los modelos que alinean imagen y lenguaje —cuyo precedente
conocido es CLIP (Radford et al., 2021)— han evolucionado hasta que los modelos comerciales
actuales, Gemini entre ellos (Gemini Team, Google, 2023), aceptan imágenes junto al texto en la
misma petición. Safi aprovecha esa capacidad para uno de sus rasgos propios: que el usuario adjunte
la foto o captura de su hoja de cálculo y el modelo extraiga de ella los movimientos, que luego se
confirman antes de guardarse. Es la conexión más directa entre el estado del arte y el problema del
que parte el trabajo.

## 2.6. Observabilidad de aplicaciones con LLM

Una aplicación con LLM se comporta de forma no determinista y tiene un coste por uso, medido en
tokens, que conviene vigilar. Por eso se ha asentado una práctica propia de estos sistemas: trazar
cada llamada al modelo con su número de tokens, su coste, su latencia y su resultado. Safi emplea
Langfuse para trazar cada conversación y cada generación —tokens y coste incluidos—, junto con
Sentry para el seguimiento de errores y Grafana para las métricas de operación. El detalle se
aborda en los capítulos 4 y 6.

## 2.7. Marco legal y ético

El proyecto maneja información financiera personal, un dato sensible que obliga a cuidar varios
frentes. En materia de **privacidad**, el tratamiento se alinea con los principios del Reglamento
General de Protección de Datos (Reglamento (UE) 2016/679): se guarda solo lo necesario para la
funcionalidad, con una finalidad acotada y con el usuario como dueño de su información; cada usuario
accede únicamente a sus datos, algo que se garantiza por autenticación y aislamiento por
identificador (capítulo 4). Las **credenciales** —claves de API y secretos— nunca viajan en el
código: se externalizan mediante variables de entorno y un gestor de secretos, como pide la propia
guía del TFM.

Quedan además los **riesgos propios de los LLM**. Las alucinaciones se mitigan con RAG y con una
regla explícita de no inventar datos; los sesgos heredados del preentrenamiento se asumen como
limitación conocida; y la inyección de prompts —recogida en el OWASP Top 10 para aplicaciones LLM
(OWASP, 2023)— se contiene tratando el contenido del usuario como datos y nunca como instrucciones.
Por último, una cuestión de **transparencia**: Safi no es un asesor financiero certificado y sus
análisis son orientativos, algo que el propio asistente deja claro. Ninguno de estos principios es
un añadido decorativo; todos condicionan decisiones concretas que reaparecen en los capítulos
siguientes.
