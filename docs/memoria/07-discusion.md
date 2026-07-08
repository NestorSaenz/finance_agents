# 7. Discusión

Más allá de los resultados, conviene detenerse en lo que ha dejado el proceso: qué he aprendido
construyendo Safi y qué riesgos, éticos y técnicos, rodean a una solución de este tipo, junto con la
forma en que se han abordado.

## 7.1. Lecciones aprendidas

La lección que más me marcó fue **ajustar la complejidad de la solución a la del problema, y no al
revés**. Empecé con una arquitectura de cinco agentes y planificación explícita porque sonaba
ambiciosa, pero al enfrentarla al problema real descubrí que la mayoría de las peticiones de finanzas
personales son de una sola operación. Simplificar a un clasificador ligero más un agente ReAct no fue
renunciar a nada, sino acertar con el tamaño del problema. Me llevo la idea de que la sofisticación no
se demuestra añadiendo piezas, sino eligiendo las justas.

La segunda lección tiene que ver con **diseñar alrededor de las limitaciones del modelo** en lugar de
pelearme con ellas. Cuando el modelo inventaba identificadores o interpretaba mal las fechas, la
tentación era insistir con el prompt. Lo que funcionó de verdad fue cambiar el diseño: resolver los
movimientos por su descripción, aportar la fecha actual, fijar reglas explícitas. Entendí que un
modelo de lenguaje no es un componente determinista al que se le pueda exigir precisión absoluta, sino
uno probabilístico alrededor del cual hay que construir con red de seguridad.

También aprendí, de forma muy práctica, **el valor de una buena arquitectura**. Colocar cada proveedor
externo detrás de una interfaz me pareció al principio un trámite, pero fue justo lo que me permitió
cambiar de Cohere a Vertex y de Pinecone a pgvector sin reescribir la lógica de negocio. Esa misma
disciplina, junto con las pruebas automatizadas, me dio la confianza para refactorizar a fondo un
proyecto que cambió mucho por el camino.

Otras dos ideas me acompañarán en futuros trabajos. Una es medir desde el principio: incorporar la
observabilidad pronto me dio datos reales de coste y comportamiento en lugar de intuiciones, y con
ellos pude justificar decisiones como el enrutamiento por complejidad. La otra es que el uso real vale
más que cualquier laboratorio: probar la aplicación en mi propio entorno familiar sacó a la luz
problemas de tono y de comportamiento que ninguna prueba unitaria habría revelado.

## 7.2. Riesgos, ética y mitigaciones

Trabajar con datos financieros personales obliga a tomarse en serio la ética y la privacidad. El
riesgo más evidente es el mal uso o la fuga de información sensible. La respuesta pasa por el
aislamiento estricto de los datos de cada usuario, la autenticación como puerta de entrada y la
externalización de las credenciales fuera del código, todo ello alineado con los principios de
minimización y control del usuario que promueve el RGPD.

A este se suman los riesgos propios de apoyarse en modelos de lenguaje. Las alucinaciones, es decir,
respuestas plausibles pero falsas, se mitigan fundando las respuestas en los datos reales mediante RAG
y prohibiendo al asistente inventar información. La inyección de prompts, por la que un usuario podría
intentar manipular el comportamiento del sistema con instrucciones escondidas en su mensaje, se
contiene tratando ese contenido como datos y no como órdenes. Los sesgos heredados del entrenamiento
del modelo son una limitación que asumo de forma consciente, y que aconseja mantener la prudencia en
cualquier recomendación. Por eso el asistente deja claro que no es un asesor financiero certificado y
que sus análisis son orientativos.

Existe además un riesgo de dependencia de proveedores externos, tanto por coste como por
disponibilidad. Se mitiga con la cadena de respaldo entre modelos y con el diseño intercambiable que
permite sustituir un proveedor por otro. Y existe un riesgo de coste descontrolado si una conversación
entrara en bucle, que se acota con límites de vueltas, de recursión y de tiempo.

Queda un punto que prefiero señalar con honestidad. Al trazar las conversaciones con una herramienta
de observabilidad en la nube, cierta información financiera del usuario viaja a un servicio externo.
En el contexto de este proyecto se trata de datos del propio autor, en su propia instancia y a
pequeña escala, por lo que se considera asumible. Si la aplicación se orientara a un uso comercial más
amplio, la vía adecuada sería alojar la observabilidad en infraestructura propia para que esos datos no
salieran del entorno controlado. Reconocer esta limitación forma parte, también, de un uso responsable
de la tecnología.
