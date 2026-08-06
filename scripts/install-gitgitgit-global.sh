#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
global_skill_dir="${HOME}/.agents/skills/gitgitgit"
global_bin_dir="${HOME}/.local/bin"
global_claude_commands="${HOME}/.claude/commands"
source_marker="${global_skill_dir}/source-root"
zprofile="${HOME}/.zprofile"
path_line='export PATH="$HOME/.local/bin:$PATH"'

mkdir -p "$global_skill_dir" "$global_bin_dir" "$global_claude_commands"

install -m 755 "$repo_root/scripts/gitgitgit.py" "$global_skill_dir/gitgitgit.py"
install -m 755 "$repo_root/scripts/gitgitgit" "$global_skill_dir/gitgitgit"
install -m 644 "$repo_root/docs/gitgitgit-agent-command.md" "$global_skill_dir/SKILL.md"
printf '%s\n' "$repo_root" > "$source_marker"

cat > "$global_bin_dir/gitgitgit" <<'EOF'
#!/bin/sh
set -eu

global_skill_dir="${HOME}/.agents/skills/gitgitgit"
global_source_root=""
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
fi
if [ -z "$global_source_root" ] \
  && [ -f "scripts/install-gitgitgit-global.sh" ] \
  && [ -f "scripts/gitgitgit.py" ]; then
  global_source_root=$(CDPATH= cd -- "$(dirname -- "scripts/install-gitgitgit-global.sh")/.." && pwd)
fi

if [ -n "$global_source_root" ] \
  && [ -x "$global_source_root/scripts/install-gitgitgit-global.sh" ] \
  && [ -f "$global_source_root/scripts/gitgitgit.py" ] \
  && [ -f "$global_source_root/scripts/gitgitgit" ] \
  && [ -f "$global_source_root/docs/gitgitgit-agent-command.md" ]; then
  needs_install=false
  if ! cmp -s "$global_source_root/scripts/gitgitgit.py" "$global_skill_dir/gitgitgit.py" \
    || ! cmp -s "$global_source_root/scripts/gitgitgit" "$global_skill_dir/gitgitgit" \
    || ! cmp -s "$global_source_root/docs/gitgitgit-agent-command.md" "$global_skill_dir/SKILL.md"; then
    needs_install=true
  fi
  if [ "$needs_install" = true ]; then
    colour_line 32 '[gitgitgit] Updating the global skill from the registered source.'
    if ! "$global_source_root/scripts/install-gitgitgit-global.sh"; then
      colour_line 31 '[gitgitgit] ERROR: automatic global-skill update failed.' >&2
      exit 1
    fi
  fi
fi

if [ ! -f "$global_skill_dir/gitgitgit.py" ]; then
  colour_line 31 '[gitgitgit] ERROR: global skill is not installed and no source was found.' >&2
  exit 1
fi

exec python3 "$global_skill_dir/gitgitgit.py" "$@"
EOF
chmod 755 "$global_bin_dir/gitgitgit"
install -m 644 "$repo_root/docs/gitgitgit-agent-command.md" "$global_claude_commands/gitgitgit.md"

if [ ! -f "$zprofile" ]; then
  printf '%s\n' "$path_line" > "$zprofile"
  path_status="created"
elif ! grep -Fqx "$path_line" "$zprofile"; then
  printf '\n%s\n' "$path_line" >> "$zprofile"
  path_status="updated"
else
  path_status="already contained ~/.local/bin"
fi

printf '%s\n' "Installed: $global_bin_dir/gitgitgit"
printf '%s\n' "Global skill: $global_skill_dir/SKILL.md"
printf '%s\n' "PATH in ~/.zprofile: $path_status"
printf '%s\n' 'Open a new Terminal or run: . ~/.zprofile'
