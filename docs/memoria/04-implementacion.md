# 4. Implementación

Este capítulo baja del diseño al código. Describe cómo está organizado el proyecto, cómo se
integran los modelos de lenguaje, cómo se orquestan los agentes y se gestionan los prompts, qué
mecanismos de seguridad protegen los datos y cómo se despliega todo. El objetivo no es repasar cada
línea, sino explicar las piezas clave y las decisiones que las sostienen.

## 4.1. Estructura del código y componentes

El repositorio separa con claridad el backend, en Python, y el frontend, en TypeScript. El backend
se organiza siguiendo los principios de la arquitectura limpia y el diseño orientado al dominio
(DDD): cada área de negocio es un módulo independiente y las dependencias apuntan siempre hacia el
dominio, nunca al revés.

```
financegpt/
├── app/                      # Backend (FastAPI)
│   ├── api/                  # Rutas HTTP y manejo de errores
│   ├── agents/               # Capa de agentes (LangGraph)
│   │   ├── nodes/            # Clasificador, agente ReAct, ingesta, respuesta
│   │   └── tools/            # Herramientas por dominio + toolkit compuesto
│   ├── src/                  # Módulos de dominio (uno por área)
│   │   ├── transactions/     #   cada uno con: constants, types, models,
│   │   ├── budgets/          #   interfaces, dto, repositories, services,
│   │   ├── goals/            #   dependencies
│   │   ├── cards/
│   │   ├── analysis/
│   │   └── auth/ chat/ memory/ users/
│   ├── shared/               # Clientes (LLM, BD, vectores), interfaces, utilidades
│   └── core/                 # Configuración, logging, excepciones, observabilidad
├── frontend/                 # Aplicación web (Next.js)
│   └── src/{app, components, lib, context}
├── database/migrations/      # Esquema y migraciones SQL
└── tests/                    # Pruebas unitarias e integración
```

Dentro de cada módulo de dominio se repite siempre la misma anatomía, lo que hace el código
predecible: los *models* definen las entidades del dominio, las *interfaces* declaran los contratos
(clases abstractas), los *repositories* implementan el acceso a datos, los *services* contienen la
lógica de negocio, los *dto* describen lo que entra y sale por la API, y *dependencies* conecta todo
mediante inyección de dependencias. La regla que ordena las capas es sencilla y se respeta sin
excepciones: las rutas hablan en DTOs, los servicios en modelos de dominio y los repositorios solo
tocan datos. Ningún componente salta niveles.

Dos criterios transversales acompañan a toda la base de código. El primero es el **tipado estricto**:
el proyecto se valida con un analizador de tipos en modo estricto, sin tipos genéricos ni `Any` fuera
de las fronteras donde son inevitables. El segundo afecta al dinero: los importes se manejan con el
tipo `Decimal` —nunca coma flotante— para evitar errores de redondeo, y se serializan como texto para
que lleguen exactos a la base de datos.

## 4.2. Integración con los modelos

Toda la comunicación con los modelos de lenguaje pasa por una **interfaz común** (`LLMInterface`) que
declara las operaciones necesarias: generar texto y generar con herramientas. Por debajo hay varias
implementaciones —una para Vertex AI (Gemini) y otra para Groq (Llama)— que traducen esa interfaz al
formato propio de cada proveedor. El resto de la aplicación no sabe con qué proveedor habla, y esa es
justamente la propiedad que permitió cambiar de Cohere a Vertex sin tocar la lógica de negocio.

Sobre esa base se construye la **fiabilidad**. Los clientes se encadenan en un mecanismo de respaldo:
si el modelo principal falla —por una caída o una sobrecarga puntual—, la petición se reintenta con
el siguiente de la cadena, primero otro modelo del mismo proveedor y, en último término, un proveedor
distinto. A esto se suma una distinción de **coste**: existe un nivel "económico", para tareas
sencillas como la clasificación, y un nivel "capaz", que solo se usa cuando la tarea lo requiere. La
elección de uno u otro no la decide el modelo, sino el propio flujo.

La integración con las **herramientas** merece detalle porque es el corazón funcional del sistema.
Cada herramienta se describe al modelo con un esquema en el formato estándar de llamada a funciones
(nombre, descripción y parámetros). Cuando el modelo decide usar una, devuelve la llamada y sus
argumentos ya estructurados; el sistema la ejecuta y le devuelve el resultado. Un punto de diseño
importante y deliberado: el identificador del usuario **nunca** forma parte de ese esquema. Se inyecta
en el momento de ejecutar la herramienta, a partir del contexto autenticado, de modo que el modelo no
puede —ni por error ni por manipulación— operar sobre datos de otra persona.

La categorización semántica usa la otra vía de integración, la de *embeddings*: el cliente de
embeddings convierte una descripción en un vector y la búsqueda se resuelve contra pgvector dentro de
la propia base de datos.

## 4.3. Orquestación de agentes y gestión de prompts

El comportamiento del asistente se coordina con un grafo de LangGraph. El punto de entrada es el
**clasificador**: un nodo que, con el modelo económico, determina la intención del mensaje (registrar,
consultar, analizar, categorizar, fuera de tema…) y decide el siguiente paso. La mayoría de las
intenciones desembocan en el **agente ReAct**, el nodo central del sistema.

Ese agente funciona como un bucle acotado. En cada vuelta pide al modelo, con el conjunto de
herramientas disponibles, la siguiente acción; si el modelo solicita herramientas, se ejecutan —y
aquí está una de las claves de rendimiento: las que son independientes se lanzan **en paralelo**, no
en serie—, se le devuelven los resultados y se repite. El bucle termina cuando el modelo ya no pide
más herramientas —su texto es la respuesta— o cuando se alcanza un número máximo de vueltas, un límite
que existe como salvaguarda de coste. Las herramientas se agrupan por dominio (transacciones,
presupuestos, metas, tarjetas y análisis) y se combinan en un *toolkit* compuesto que las presenta al
modelo como un catálogo único.

Un rasgo de diseño que conviene resaltar es cómo se identifican los datos sobre los que actuar.
Corregir o eliminar un movimiento no se hace por identificador —los modelos tienden a inventar o
alterar los UUID—, sino por la **descripción** que da el usuario ("elimina la de YouTube"), y es el
sistema quien resuelve internamente a qué registro corresponde. Es un ejemplo de cómo el diseño se
adapta a las limitaciones reales del modelo en lugar de ignorarlas.

Cuando el mensaje incluye una imagen, el flujo no pasa por el clasificador ni por el agente general,
sino por un **proceso de ingesta** propio: se envía la imagen al modelo de visión con una instrucción
de extracción, se valida su respuesta contra un esquema estructurado y se elabora una propuesta que el
usuario confirma antes de registrar nada.

La **gestión de la memoria** se resuelve en dos planos. La memoria a corto plazo recupera de la base
de datos los últimos mensajes de la conversación y los aporta como contexto. La de largo plazo trabaja
en segundo plano: después de responder, un proceso extrae hechos duraderos sobre el usuario y los
guarda, sin penalizar el tiempo de respuesta del turno.

En cuanto a los **prompts**, no son un texto improvisado: son un componente de ingeniería con reglas
explícitas. Cada agente tiene un prompt de sistema que fija su papel, el formato esperado y una serie
de reglas duras. Entre ellas, tres son especialmente relevantes por su impacto: la regla de **no
inventar** información (usar solo lo que devuelven las herramientas), la de **actuar únicamente sobre
la última petición** (para que el historial no dispare registros repetidos) y la de **confirmar antes
de destruir** (pedir el sí del usuario antes de eliminar). El tono también se instruye: cercano y
natural, con el nombre del usuario cuando se conoce, huyendo del registro robótico. Los prompts
completos se recogen en los anexos.

## 4.4. Mecanismos de seguridad

La seguridad se aborda en varias capas complementarias. El **control de acceso** se apoya en
autenticación por token (JWT) gestionada por el proveedor: cada petición llega con su token, que se
valida antes de operar. Sobre él se construye el **aislamiento entre usuarios**, quizá la garantía más
importante en una aplicación de datos financieros: toda consulta a la base de datos se filtra por el
identificador del usuario autenticado, y —como ya se ha señalado— ese identificador nunca procede del
modelo, sino del contexto de autenticación.

Las **credenciales** se tratan según exige la buena práctica y la propia guía del TFM: ninguna clave
vive en el código. En desarrollo se cargan desde variables de entorno y en producción desde un gestor
de secretos, y el repositorio nunca las contiene.

A las amenazas propias de los modelos se responde de forma concreta. La **inyección de prompts** se
mitiga instruyendo al asistente para tratar el contenido del usuario como datos y no como
instrucciones, e ignorar cualquier orden incrustada que intente cambiar su comportamiento. El
**alcance** se acota en dos frentes: el clasificador desvía las peticiones ajenas a las finanzas hacia
una respuesta de rechazo que no consume el modelo caro, y los prompts refuerzan esa frontera. Por
último, se controla el **coste y los bucles**: además del tope de vueltas del agente, el grafo tiene un
límite de recursión y cada petición se envuelve en un tiempo máximo de espera, de modo que ninguna
conversación pueda dispararse en cómputo o gasto. Todo ello queda, además, bajo observación: cada
llamada al modelo se traza con sus tokens y su coste, lo que permite vigilar el comportamiento real en
producción.

## 4.5. Despliegue e infraestructura

La aplicación se despliega en la nube de forma reproducible. Cada servicio —backend y frontend— se
empaqueta en un contenedor Docker: el backend sobre una imagen ligera de Python, y el frontend con la
salida autónoma de Next.js, que produce un servidor mínimo listo para ejecutarse. Ambos contenedores
se publican en **Google Cloud Run** como dos servicios independientes.

El reparto de responsabilidades entre ambos evita fricciones habituales. El frontend redirige sus
llamadas al backend en el mismo origen, con lo que no hace falta configurar CORS y el token viaja de
forma natural en la cabecera. El backend, a su vez, se autentica frente a Vertex AI mediante la
**cuenta de servicio** del propio Cloud Run, sin archivos de clave: las credenciales de Google se
resuelven por el mecanismo estándar del entorno. El resto de secretos —claves de Supabase, Groq y
Langfuse— se inyectan desde el gestor de secretos de Google, y la configuración no sensible viaja como
variables de entorno.

Cloud Run aporta además dos ventajas que encajan con un proyecto de estas dimensiones: **escala a
cero** cuando no hay tráfico —lo que reduce el coste prácticamente a nada en uso personal— y escala
automáticamente si la demanda creciera. El esquema de la base de datos y sus migraciones se aplican por
separado en Supabase, que es un servicio externo. La guía completa de despliegue, con los comandos
concretos, se incluye en los anexos para garantizar la reproducibilidad que pide la evaluación.
