#!/bin/sh
# First-time (or refresh) install for users who do not already have a clone.
# Safe to re-run: updates the registered source clone, then reinstalls globally.
#
# Typical one-liner (after the repository is public):
#   curl -fsSL https://raw.githubusercontent.com/emiliosevilla/supagit/main/scripts/bootstrap.sh | sh
# Optional language:
#   curl -fsSL …/bootstrap.sh | sh -s -- --lang es
set -eu

repo_url="${SUPAGIT_REPO_URL:-https://github.com/emiliosevilla/supagit.git}"
install_dir="${SUPAGIT_SOURCE_DIR:-${HOME}/.local/share/supagit}"
branch="${SUPAGIT_BRANCH:-main}"
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
      printf '%s\n' "Clones or updates ${repo_url} into ${install_dir}, then runs install-supagit-global.sh."
      printf '%s\n' "Override with SUPAGIT_REPO_URL, SUPAGIT_SOURCE_DIR, SUPAGIT_BRANCH."
      exit 0
      ;;
    *)
      printf '%s\n' "ERROR: unknown argument: $1" >&2
      printf '%s\n' "Usage: $0 [--lang en|es]" >&2
      exit 1
      ;;
  esac
done

if ! command -v git >/dev/null 2>&1; then
  printf '%s\n' "ERROR: git is required to install supagit." >&2
  exit 1
fi

if [ -d "${install_dir}/.git" ]; then
  printf '%s\n' "Updating existing source clone at ${install_dir}…"
  git -C "${install_dir}" fetch origin "${branch}"
  git -C "${install_dir}" checkout "${branch}"
  git -C "${install_dir}" pull --ff-only origin "${branch}"
else
  printf '%s\n' "Cloning ${repo_url} (${branch}) into ${install_dir}…"
  mkdir -p "$(dirname -- "${install_dir}")"
  git clone --branch "${branch}" --single-branch "${repo_url}" "${install_dir}"
fi

installer="${install_dir}/scripts/install-supagit-global.sh"
if [ ! -x "${installer}" ]; then
  printf '%s\n' "ERROR: installer missing or not executable: ${installer}" >&2
  exit 1
fi

if [ -n "${lang}" ]; then
  exec sh "${installer}" --lang "${lang}"
fi
exec sh "${installer}"
