# supagit

> Un lanzamiento completo de Git, escrito con una sola palabra.

Cuando un agente de IA realiza manualmente estas operaciones, consume tokens y
tiempo en escribir comandos, explicar cada paso y comprobar el resultado.
`supagit` ejecuta ese trabajo localmente: la operación no consume tokens de IA.

`supagit` concentra en un comando de Terminal las operaciones de Git y las
migraciones del backend configurado. Escribes:

```bash
supagit
```

El programa muestra qué va a hacer, pide confirmación y presenta el resultado
con claridad. Así el agente puede dedicar su contexto a resolver el problema,
no a narrar cada paso de Git ni de la migración del backend.

## Qué aporta

- Cero tokens de IA para ejecutar el flujo operativo.
- Un plan visible antes de modificar el proyecto.
- Mensajes claros cuando algo falla, cambia de forma inesperada o termina bien.
- Flujo guiado para integrar trabajo y promoverlo entre ramas.
- Pull requests cuando GitHub las exige.
- Migraciones del backend, incluidas las de Supabase, sólo si el proyecto las configura.
- Interfaz en inglés o español.

`supagit` trabaja con cuidado: no fuerza pushes, no borra cambios sin permiso y
se detiene ante estados ambiguos. Su objetivo no es ocultar Git, sino convertir
un proceso largo y repetitivo en una acción visible y controlable.

## Empezar

Instala el comando global:

```bash
curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh
```

Entra en el proyecto que quieres publicar y prueba primero el plan:

```bash
cd ruta/de/tu-proyecto
supagit --dry-run
```

Cuando el plan sea correcto:

```bash
supagit
```

Si el proyecto aún no tiene configuración, puedes crearla con:

```bash
supagit init --backend none
```

Para un proyecto con migraciones de Supabase, usa `--backend supabase`.

## Cómo trabaja

`supagit` puede detectar el flujo habitual `dev`, `pre` y `prod`, o usar una
lista definida por el proyecto, por ejemplo:

```json
"branches": ["dev", "staging", "production"]
```

En cada ejecución:

1. Revisa el estado del proyecto y enseña el plan.
2. Integra el trabajo seleccionado.
3. Ejecuta las comprobaciones configuradas.
4. Aplica las migraciones necesarias, si las hay.
5. Promueve los cambios entre las ramas en el orden indicado.

El proceso es interactivo por defecto. Para automatizaciones existen opciones
como `--yes`, `--lang`, `--pipeline`, `--integrate` y `--no-sweep`.

## Documentación

- [Guía para agentes y uso seguro](docs/supagit-agent-command.md)
- [Ejemplo de configuración](.supagit.json.example)
- [Tareas abiertas y terminadas](tasks/task.md)
- [Licencia MIT](LICENSE)

## Participa

Ideas, problemas y mejoras son bienvenidos en
[GitHub](https://github.com/emiliosevilla/supagit).
