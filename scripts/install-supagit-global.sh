#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
global_skill_dir="${HOME}/.agents/skills/supagit"
codex_skill_dir="${HOME}/.codex/skills/supagit"
global_bin_dir="${HOME}/.local/bin"
global_claude_commands="${HOME}/.claude/commands"
legacy_skill_dir="${HOME}/.agents/skills/gitgitgit"
legacy_bin="${global_bin_dir}/gitgitgit"
legacy_command="${global_claude_commands}/gitgitgit.md"
source_marker="${global_skill_dir}/source-root"
zprofile="${HOME}/.zprofile"
path_line='export PATH="$HOME/.local/bin:$PATH"'

lang=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --lang)
      if [ "$#" -lt 2 ]; then
        printf '%s\n' "ERROR: --lang requires en or es." >&2
        exit 1
      fi
      lang=$2
      shift 2
      ;;
    --lang=*)
      lang=${1#--lang=}
      shift
      ;;
    -h|--help)
      printf '%s\n' "Usage: $0 [--lang en|es]"
      printf '%s\n' "Installs the global supagit command and skill files."
      printf '%s\n' "Language: --lang, SUPAGIT_LANG, or interactive menu on a TTY."
      exit 0
      ;;
    *)
      printf '%s\n' "ERROR: unknown argument: $1" >&2
      printf '%s\n' "Usage: $0 [--lang en|es]" >&2
      exit 1
      ;;
  esac
done

case "${lang}" in
  "")
    env_lang=$(printf '%s' "${SUPAGIT_LANG:-}" | tr '[:upper:]' '[:lower:]')
    case "$env_lang" in
      en|es) lang=$env_lang ;;
      "")
        # Require stdout TTY too: Python auto-update captures stdout (PIPE) and
        # must not block on a hidden language menu while a spinner runs.
        if [ -t 0 ] && [ -t 1 ]; then
          while :; do
            printf '%s' "Language / Idioma:
  (1) English
  (2) Español
Choice [1/2]: "
            read -r lang_choice || lang_choice=1
            case "$lang_choice" in
              1|"") lang=en; break ;;
              2) lang=es; break ;;
              en|EN) lang=en; break ;;
              es|ES) lang=es; break ;;
            esac
          done
        else
          lang=en
        fi
        ;;
      *)
        printf '%s\n' "ERROR: SUPAGIT_LANG must be 'en' or 'es' (got ${SUPAGIT_LANG})." >&2
        exit 1
        ;;
    esac
    ;;
  en|es) ;;
  EN|ES)
    lang=$(printf '%s' "$lang" | tr '[:upper:]' '[:lower:]')
    ;;
  *)
    printf '%s\n' "ERROR: --lang must be 'en' or 'es' (got ${lang})." >&2
    exit 1
    ;;
esac

installer_colour_enabled=true
if [ "${NO_COLOR+x}" = x ] || [ "${TERM:-}" = dumb ]; then
  installer_colour_enabled=false
fi

# Green success line (ANSI 32), matching the global wrapper's colour_line.
print_green() {
  if [ "$installer_colour_enabled" = true ]; then
    printf '\033[32m%s\033[0m\n' "$*"
  else
    printf '%s\n' "$*"
  fi
}

msg() {
  key=$1
  case "$lang:$key" in
    en:installed) printf '%s\n' "Installed: $2" ;;
    es:installed) printf '%s\n' "Instalado: $2" ;;
    en:global_skill) printf '%s\n' "Global skill: $2" ;;
    es:global_skill) printf '%s\n' "Skill global: $2" ;;
    en:path_status) printf '%s\n' "PATH in ~/.zprofile: $2" ;;
    es:path_status) printf '%s\n' "PATH en ~/.zprofile: $2" ;;
    en:path_status_created) printf '%s\n' "created" ;;
    es:path_status_created) printf '%s\n' "creado" ;;
    en:path_status_updated) printf '%s\n' "updated" ;;
    es:path_status_updated) printf '%s\n' "actualizado" ;;
    en:path_status_ok) printf '%s\n' "already contained ~/.local/bin" ;;
    es:path_status_ok) printf '%s\n' "ya contenía ~/.local/bin" ;;
    en:path_need_export_title)
      printf '%s\n' "Installation complete. This terminal still has the old PATH."
      ;;
    es:path_need_export_title)
      printf '%s\n' "Instalación completada. Esta terminal aún tiene el PATH antiguo."
      ;;
    en:path_need_export_hint)
      printf '%s\n' "Run this now to use supagit here without reopening Terminal:"
      ;;
    es:path_need_export_hint)
      printf '%s\n' "Ejecuta esto ahora para usar supagit aquí sin abrir otra Terminal:"
      ;;
    en:path_new_terminals)
      printf '%s\n' "New terminals load ~/.zprofile automatically."
      ;;
    es:path_new_terminals)
      printf '%s\n' "Las terminales nuevas cargan ~/.zprofile automáticamente."
      ;;
    en:path_ready)
      print_green "PATH already configured; you can run supagit from this terminal."
      ;;
    es:path_ready)
      print_green "PATH ya configurado; puedes ejecutar supagit desde esta terminal."
      ;;
    en:path_in_profile_not_shell)
      printf '%s\n' "PATH is in ~/.zprofile but not in this terminal yet."
      ;;
    es:path_in_profile_not_shell)
      printf '%s\n' "PATH está en ~/.zprofile pero aún no en esta terminal."
      ;;
    en:path_export_or_new)
      printf '%s\n' "Run this now, or open a new Terminal:"
      ;;
    es:path_export_or_new)
      printf '%s\n' "Ejecuta esto ahora, o abre una Terminal nueva:"
      ;;
    en:bad_source_title)
      printf '%s\n' "ERROR: this checkout is not the official emiliosevilla/supagit clone."
      ;;
    es:bad_source_title)
      printf '%s\n' "ERROR: este checkout no es el clon oficial emiliosevilla/supagit."
      ;;
    en:bad_source_hint)
      printf '%s\n' "Install with the curl one-liner from the repo README instead:"
      ;;
    es:bad_source_hint)
      printf '%s\n' "Instala con el one-liner curl del README del repositorio:"
      ;;
    en:bad_source_curl)
      printf '%s\n' "  curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh"
      ;;
    es:bad_source_curl)
      printf '%s\n' "  curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh"
      ;;
    *)
      printf '%s\n' "ERROR: missing installer message: $key" >&2
      exit 1
      ;;
  esac
}

abort_bad_source() {
  msg bad_source_title >&2
  msg bad_source_hint >&2
  msg bad_source_curl >&2
  exit 1
}

# Refuse to register a global source-root that is not the real GitHub clone.
if [ ! -f "$repo_root/scripts/supagit.py" ]; then
  abort_bad_source
fi
if ! command -v git >/dev/null 2>&1; then
  abort_bad_source
fi
origin_url=$(git -C "$repo_root" remote get-url origin 2>/dev/null || true)
origin_norm=$(printf '%s' "$origin_url" | tr '[:upper:]' '[:lower:]' | tr ':' '/')
case "$origin_norm" in
  *github.com/emiliosevilla/supagit*) ;;
  *)
    abort_bad_source
    ;;
esac

mkdir -p "$global_skill_dir" "$codex_skill_dir" "$global_bin_dir" "$global_claude_commands"

# Remove only the previous generated supagit artifacts. No project data is touched.
rm -f "$legacy_bin" "$legacy_command" \
  "$legacy_skill_dir/gitgitgit.py" "$legacy_skill_dir/gitgitgit" \
  "$legacy_skill_dir/SKILL.md" "$legacy_skill_dir/source-root"
rmdir "$legacy_skill_dir" 2>/dev/null || true

install -m 755 "$repo_root/scripts/supagit.py" "$global_skill_dir/supagit.py"
install -m 644 "$repo_root/scripts/supagit_layout.py" "$global_skill_dir/supagit_layout.py"
install -m 644 "$repo_root/scripts/supagit_inventory.py" "$global_skill_dir/supagit_inventory.py"
install -m 644 "$repo_root/scripts/supagit_menu.py" "$global_skill_dir/supagit_menu.py"
install -m 644 "$repo_root/scripts/supagit_sweep.py" "$global_skill_dir/supagit_sweep.py"
install -m 644 "$repo_root/scripts/supagit_i18n.py" "$global_skill_dir/supagit_i18n.py"
install -m 644 "$repo_root/scripts/supagit_update.py" "$global_skill_dir/supagit_update.py"
install -m 644 "$repo_root/scripts/supagit_busy.py" "$global_skill_dir/supagit_busy.py"
install -m 644 "$repo_root/scripts/supagit_situation.py" "$global_skill_dir/supagit_situation.py"
install -m 644 "$repo_root/scripts/supagit_supabase.py" "$global_skill_dir/supagit_supabase.py"
install -m 755 "$repo_root/scripts/supagit" "$global_skill_dir/supagit"
install -m 644 "$repo_root/docs/supagit-agent-command.md" "$global_skill_dir/SKILL.md"
install -m 644 "$repo_root/docs/supagit-agent-command.md" "$codex_skill_dir/SKILL.md"
printf '%s\n' "$repo_root" > "$source_marker"

# Update decisions live entirely in Python (maybe_self_update_and_reexec /
# ensure_healthy_source_root → pull_and_reinstall). The wrapper must not cmp
# or reinstall — that stale-source dance can overwrite a fresher skill.
cat > "$global_bin_dir/supagit" <<'EOF'
#!/bin/sh
set -eu
exec python3 "${HOME}/.agents/skills/supagit/supagit.py" "$@"
EOF
chmod 755 "$global_bin_dir/supagit"
install -m 644 "$repo_root/docs/supagit-agent-command.md" "$global_claude_commands/supagit.md"

if [ ! -f "$zprofile" ]; then
  printf '%s\n' "$path_line" > "$zprofile"
  path_status_key=path_status_created
elif ! grep -Fqx "$path_line" "$zprofile"; then
  printf '\n%s\n' "$path_line" >> "$zprofile"
  path_status_key=path_status_updated
else
  path_status_key=path_status_ok
fi

path_status_label=$(msg "$path_status_key")

path_in_current=false
case ":${PATH}:" in
  *:"${HOME}/.local/bin":*) path_in_current=true ;;
esac

msg installed "$global_bin_dir/supagit"
msg global_skill "$global_skill_dir/SKILL.md"
msg path_status "$path_status_label"
case "$path_status_key" in
  path_status_created|path_status_updated)
    msg path_need_export_title
    msg path_need_export_hint
    printf '%s\n' "$path_line"
    msg path_new_terminals
    ;;
  *)
    if [ "$path_in_current" = true ]; then
      msg path_ready
    else
      msg path_in_profile_not_shell
      msg path_export_or_new
      printf '%s\n' "$path_line"
    fi
    ;;
esac
