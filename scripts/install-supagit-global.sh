#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
global_skill_dir="${HOME}/.agents/skills/supagit"
global_bin_dir="${HOME}/.local/bin"
global_claude_commands="${HOME}/.claude/commands"
legacy_skill_dir="${HOME}/.agents/skills/gitgitgit"
legacy_bin="${global_bin_dir}/gitgitgit"
legacy_command="${global_claude_commands}/gitgitgit.md"
source_marker="${global_skill_dir}/source-root"
zprofile="${HOME}/.zprofile"
path_line='export PATH="$HOME/.local/bin:$PATH"'

mkdir -p "$global_skill_dir" "$global_bin_dir" "$global_claude_commands"

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
install -m 755 "$repo_root/scripts/supagit" "$global_skill_dir/supagit"
install -m 644 "$repo_root/docs/supagit-agent-command.md" "$global_skill_dir/SKILL.md"
printf '%s\n' "$repo_root" > "$source_marker"

cat > "$global_bin_dir/supagit" <<'EOF'
#!/bin/sh
set -eu

global_skill_dir="${HOME}/.agents/skills/supagit"
global_source_root=""
source_marker_needs_install=true
colour_enabled=true
for arg in "$@"; do
  case "$arg" in
    --no-color|--color=never)
      colour_enabled=false
      ;;
  esac
done
if [ "${NO_COLOR+x}" = x ] || [ "${TERM:-}" = dumb ]; then
  colour_enabled=false
fi

colour_line() {
  colour=$1
  shift
  if [ "$colour_enabled" = true ]; then
    printf '\033[%sm%s\033[0m\n' "$colour" "$*"
  else
    printf '%s\n' "$*"
  fi
}

if [ -f "$global_skill_dir/source-root" ]; then
  global_source_root=$(sed -n '1p' "$global_skill_dir/source-root")
  if [ -n "$global_source_root" ] \
    && { [ ! -x "$global_source_root/scripts/install-supagit-global.sh" ] \
      || [ ! -f "$global_source_root/scripts/supagit.py" ] \
      || [ ! -f "$global_source_root/scripts/supagit_layout.py" ] \
      || [ ! -f "$global_source_root/scripts/supagit_inventory.py" ] \
      || [ ! -f "$global_source_root/scripts/supagit_menu.py" ] \
      || [ ! -f "$global_source_root/scripts/supagit_sweep.py" ] \
      || [ ! -f "$global_source_root/scripts/supagit" ] \
      || [ ! -f "$global_source_root/docs/supagit-agent-command.md" ]; }; then
    global_source_root=""
  else
    source_marker_needs_install=false
  fi
fi
if [ -z "$global_source_root" ] \
  && [ -f "scripts/install-supagit-global.sh" ] \
  && [ -f "scripts/supagit.py" ]; then
  global_source_root=$(CDPATH= cd -- "$(dirname -- "scripts/install-supagit-global.sh")/.." && pwd)
fi

if [ -n "$global_source_root" ] \
  && [ -x "$global_source_root/scripts/install-supagit-global.sh" ] \
  && [ -f "$global_source_root/scripts/supagit.py" ] \
  && [ -f "$global_source_root/scripts/supagit_layout.py" ] \
  && [ -f "$global_source_root/scripts/supagit_inventory.py" ] \
  && [ -f "$global_source_root/scripts/supagit_menu.py" ] \
  && [ -f "$global_source_root/scripts/supagit_sweep.py" ] \
  && [ -f "$global_source_root/scripts/supagit" ] \
  && [ -f "$global_source_root/docs/supagit-agent-command.md" ]; then
  needs_install=$source_marker_needs_install
  if ! cmp -s "$global_source_root/scripts/supagit.py" "$global_skill_dir/supagit.py" \
    || ! cmp -s "$global_source_root/scripts/supagit_layout.py" "$global_skill_dir/supagit_layout.py" \
    || ! cmp -s "$global_source_root/scripts/supagit_inventory.py" "$global_skill_dir/supagit_inventory.py" \
    || ! cmp -s "$global_source_root/scripts/supagit_menu.py" "$global_skill_dir/supagit_menu.py" \
    || ! cmp -s "$global_source_root/scripts/supagit_sweep.py" "$global_skill_dir/supagit_sweep.py" \
    || ! cmp -s "$global_source_root/scripts/supagit" "$global_skill_dir/supagit" \
    || ! cmp -s "$global_source_root/docs/supagit-agent-command.md" "$global_skill_dir/SKILL.md"; then
    needs_install=true
  fi
  if [ "$needs_install" = true ]; then
    colour_line 32 '[supagit] Updating the global skill from the registered source.'
    if ! "$global_source_root/scripts/install-supagit-global.sh"; then
      colour_line 31 '[supagit] ERROR: automatic global-skill update failed.' >&2
      exit 1
    fi
  fi
fi

if [ ! -f "$global_skill_dir/supagit.py" ]; then
  colour_line 31 '[supagit] ERROR: global skill is not installed and no source was found.' >&2
  exit 1
fi

exec python3 "$global_skill_dir/supagit.py" "$@"
EOF
chmod 755 "$global_bin_dir/supagit"
install -m 644 "$repo_root/docs/supagit-agent-command.md" "$global_claude_commands/supagit.md"

if [ ! -f "$zprofile" ]; then
  printf '%s\n' "$path_line" > "$zprofile"
  path_status="created"
elif ! grep -Fqx "$path_line" "$zprofile"; then
  printf '\n%s\n' "$path_line" >> "$zprofile"
  path_status="updated"
else
  path_status="already contained ~/.local/bin"
fi

printf '%s\n' "Installed: $global_bin_dir/supagit"
printf '%s\n' "Global skill: $global_skill_dir/SKILL.md"
printf '%s\n' "PATH in ~/.zprofile: $path_status"
printf '%s\n' 'Open a new Terminal or run: . ~/.zprofile'
