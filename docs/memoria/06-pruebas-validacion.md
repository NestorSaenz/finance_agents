# 6. Pruebas y validación de producto

Si el capítulo anterior medía qué resultados da el sistema, este explica cómo se ha comprobado que
funciona de forma fiable y cómo se valida como producto. Se abordan tres planos: la estrategia de
pruebas automatizadas y la validación con usuarios reales, la usabilidad de la interfaz, y la
observabilidad que permite vigilar la aplicación una vez en producción.

## 6.1. Estrategia de pruebas y validación con usuarios

Las pruebas del proyecto siguen la lógica de una pirámide. En la base están las pruebas unitarias,
que verifican de forma aislada los repositorios, los servicios, las herramientas del agente y las
reglas de los prompts. Por encima se sitúan las pruebas de integración, que ejercitan los endpoints
de la API tal como los usaría un cliente. Y en la cima, unas pocas pruebas de extremo a extremo
recorren el grafo completo, desde el mensaje del usuario hasta la respuesta.

La clave que hace estas pruebas rápidas y deterministas es el uso de dobles de prueba. Los
proveedores externos (el modelo de lenguaje, la base de datos y el almacén vectorial) se sustituyen
por implementaciones falsas que respetan las mismas interfaces del sistema. Gracias a ello, la
batería completa se ejecuta sin conexión, sin claves y sin coste, y siempre con el mismo resultado.
Este enfoque también permitió comprobar propiedades de seguridad de forma explícita, como que el
identificador de usuario procede siempre de la autenticación y nunca de los argumentos del modelo.

Cada nueva funcionalidad se incorporó acompañada de sus pruebas, y no se avanzaba a la siguiente
hasta tenerlas en verde. Esa disciplina resultó decisiva en un proyecto que evolucionó mucho: fue lo
que permitió refactorizar la arquitectura o cambiar de proveedor con la confianza de no romper lo ya
construido.

Ahora bien, la validación más significativa de un producto como este no está solo en las pruebas
automáticas, sino en su uso real. El proyecto nace de una necesidad concreta del entorno familiar del
autor, que hasta ahora llevaba las cuentas en una hoja de cálculo, y ese es también su primer banco
de pruebas. Varias de las mejoras aplicadas surgieron precisamente de usarlo de verdad: el tono
inicial resultaba demasiado robótico y se suavizó, la aplicación registraba movimientos por
duplicado al reinterpretar el historial y se corrigió, o las fechas relativas se interpretaban mal
hasta que se le aportó la fecha actual. Esa retroalimentación entre uso real y ajuste del sistema es
una forma de validación difícil de sustituir por una prueba de laboratorio.

## 6.2. Usabilidad e interfaz

Safi ofrece dos superficies complementarias. La principal es el chat, donde el usuario interactúa en
lenguaje natural. La segunda es un panel de resumen (dashboard) que traduce los datos a una vista
visual.

La experiencia conversacional se diseñó siguiendo unos principios claros. El usuario no rellena
formularios, sino que escribe como hablaría. Antes de cualquier acción destructiva, como eliminar un
movimiento, el asistente pide confirmación mostrando lo que ha entendido. El tono es cercano y usa el
nombre de la persona cuando lo conoce, evitando el registro frío de un formulario. La pantalla
inicial ofrece sugerencias para empezar, cada mensaje muestra su hora, y un botón permite adjuntar
una imagen para la ingesta de movimientos.

El dashboard, por su parte, presenta lo presupuestado frente a lo gastado, el reparto entre pagos con
crédito y en efectivo, y el estado de las tarjetas. Como toda vista que depende de datos, contempla de
forma explícita sus estados de carga, error y vacío, de modo que la interfaz siempre comunica algo
útil aunque la información aún no esté disponible.

Tres criterios atraviesan todo el frontend. Es responsive y está pensado primero para el móvil, de
manera que se ve correctamente tanto en un teléfono como en un ordenador. Cuida la accesibilidad, con
etiquetas asociadas a los campos, elementos operables por teclado, contraste suficiente y respeto por
la preferencia de movimiento reducido. Y mantiene una identidad visual coherente, con la marca Safi y
una paleta propia, en lugar de estilos improvisados. El proceso de bienvenida (onboarding) es
opcional, para que quien quiera empezar a usar la aplicación de inmediato pueda saltárselo.

## 6.3. Observabilidad en producción

Una aplicación desplegada necesita poder observarse, y más si tiene un coste por uso. Safi combina
tres herramientas para ello. Langfuse traza cada conversación y cada llamada al modelo, registrando
el modelo empleado, los tokens, el coste y la latencia, e indicando incluso qué eslabón de la cadena
de respaldo atendió la petición. Es la herramienta que hizo posible el análisis de coste del capítulo
anterior y la que permite depurar el comportamiento real cuando algo no encaja. Sentry se encarga del
seguimiento de errores, notificando las excepciones que se produzcan en producción. Y Grafana recoge
métricas de operación de la infraestructura.

A esto se suma un registro de eventos (logging) estructurado que deja traza de las operaciones
relevantes sin exponer nunca datos sensibles ni credenciales, y unos endpoints de estado que permiten
comprobar que el servicio está vivo y que su base de datos responde. En conjunto, estos elementos dan
la visibilidad necesaria para operar la aplicación con confianza y para seguir mejorándola a partir de
datos reales.
