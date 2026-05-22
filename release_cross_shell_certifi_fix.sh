#!/bin/bash
set -e

print_status() {
    echo -e "\033[0;36m=== $1 ===\033[0m"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-N}"
    local answer

    if [ "$default" = "Y" ]; then
        read -p "$prompt [Y/n]: " answer
        answer="${answer:-Y}"
    else
        read -p "$prompt [y/N]: " answer
        answer="${answer:-N}"
    fi

    case "$answer" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

sync_version_files() {
    local new_version="$1"

    print_status "Syncing version/cache-bust files"

    echo "$new_version" > VERSION

    if [ -f "frontend/VERSION" ]; then
        echo "$new_version" > frontend/VERSION
    fi

    if [ -f "frontend/index.html" ]; then
        python3 - "$new_version" <<'PY'
from pathlib import Path
import re
import sys

version = sys.argv[1]
path = Path("frontend/index.html")
text = path.read_text(encoding="utf-8")

# Update common cache-bust patterns:
# app.js?v=1.0.3, app.js?version=1.0.3, styles.css?v=...
text = re.sub(
    r'((?:app|style|styles|theme|ui|frontend)[^"\']*\.(?:js|css)\?(?:v|version)=)[^"\'&<>]+',
    rf'\g<1>{version}',
    text,
)

# Update generic ?v= on local js/css refs.
text = re.sub(
    r'((?:src|href)=["\'][^"\']+\.(?:js|css)\?v=)[^"\']+(["\'])',
    rf'\g<1>{version}\2',
    text,
)

path.write_text(text, encoding="utf-8")
PY
    fi
}

ensure_requirements_certifi() {
    print_status "Checking certifi dependency"

    if [ ! -f "requirements.txt" ]; then
        touch requirements.txt
    fi

    if ! grep -Eiq '^certifi([<>=!~ ]|$)' requirements.txt; then
        echo "certifi>=2024.8.30" >> requirements.txt
        echo "Added certifi>=2024.8.30 to requirements.txt"
    else
        echo "requirements.txt already contains certifi."
    fi
}

patch_build_linux_certifi() {
    print_status "Checking build_linux.sh PyInstaller certifi collection"

    if [ ! -f "build_linux.sh" ]; then
        echo "WARNING: build_linux.sh was not found."
        return 0
    fi

    python3 - "build_linux.sh" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
lines = text.splitlines()
changed = False
out = []

# Keep Linux build_linux.sh multiline-safe. Remove duplicate certifi option lines first.
standalone_certifi = re.compile(r'^\s*--(?:hidden-import|collect-data)(?:[ =])"?certifi"?\s*(?:\\)?\s*$')
for line in lines:
    if standalone_certifi.match(line):
        changed = True
        continue
    out.append(line)

lines = out
out = []
inserted = False

for line in lines:
    if (not inserted) and re.search(r'pyinstaller', line, re.I) and "--noconfirm" in line:
        out.append(line)
        indent = "    "
        out.append(f'{indent}--hidden-import "certifi" \\')
        out.append(f'{indent}--collect-data "certifi" \\')
        inserted = True
        changed = True
    else:
        out.append(line)

if changed:
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("Patched build_linux.sh with certifi collection.")
else:
    print("build_linux.sh already looks okay.")
PY
}

patch_github_workflows_certifi() {
    print_status "Checking GitHub workflow PyInstaller certifi collection"

    local workflow_dir=".github/workflows"
    if [ ! -d "$workflow_dir" ]; then
        echo "No .github/workflows directory found."
        return 0
    fi

    local py_files
    py_files=$(grep -RIl "pyinstaller\|PyInstaller" "$workflow_dir" || true)

    if [ -z "$py_files" ]; then
        echo "No workflow files directly calling pyinstaller were found."
        return 0
    fi

    while IFS= read -r wf; do
        [ -z "$wf" ] && continue

        python3 - "$wf" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
original = text
lines = text.splitlines()
out = []
removed = 0
patched = 0

# IMPORTANT:
# GitHub Actions Windows run blocks usually execute in PowerShell.
# A standalone line like:
#   --hidden-import "certifi" \
# is valid-ish as a continuation argument in bash, but PowerShell parses it
# as a new command beginning with unary -- and fails.
#
# To be cross-shell safe, workflow files get certifi args injected on the same
# pyinstaller command line instead of as separate continuation lines.

standalone_certifi = re.compile(
    r'^\s*--(?:hidden-import|collect-data)(?:[ =])"?certifi"?\s*(?:\\|`)?\s*$',
    re.I,
)

# Remove old/broken standalone certifi lines from previous release script runs.
for line in lines:
    if standalone_certifi.match(line):
        removed += 1
        continue
    out.append(line)

lines = out
out = []

for line in lines:
    lower = line.lower()

    # Skip package installation lines, comments, etc.
    looks_like_pyinstaller_command = (
        "pyinstaller" in lower
        and "--noconfirm" in lower
        and not lower.lstrip().startswith("#")
    )

    if looks_like_pyinstaller_command:
        has_hidden = "--hidden-import" in lower and "certifi" in lower
        has_collect = "--collect-data" in lower and "certifi" in lower

        if not (has_hidden and has_collect):
            # Inject certifi args immediately after the pyinstaller executable/module name.
            # Works for:
            #   pyinstaller --noconfirm ...
            #   pyinstaller.exe --noconfirm ...
            #   ./venv/bin/pyinstaller --noconfirm ...
            #   python -m PyInstaller --noconfirm ...
            line, count = re.subn(
                r'(?i)(pyinstaller(?:\.exe)?)',
                r'\1 --hidden-import certifi --collect-data certifi',
                line,
                count=1,
            )
            if count:
                patched += 1

    out.append(line)

new_text = "\n".join(out) + ("\n" if original.endswith("\n") else "")

if new_text != original:
    path.write_text(new_text, encoding="utf-8")
    print(f"Patched {path}: inline certifi args added to {patched} PyInstaller command(s), removed {removed} standalone certifi line(s).")
else:
    print(f"{path} already looks cross-shell safe for certifi.")
PY
    done <<< "$py_files"

    # Guardrail: fail if a workflow still has a standalone certifi option line.
    local bad_lines
    bad_lines=$(grep -RInE '^[[:space:]]*--(hidden-import|collect-data)([ =])"?certifi"?[[:space:]]*(\\|`)?[[:space:]]*$' "$workflow_dir" || true)
    if [ -n "$bad_lines" ]; then
        echo "ERROR: Standalone certifi PyInstaller argument lines remain in workflow files:"
        echo "$bad_lines"
        echo "These can break Windows PowerShell steps. Put certifi args on the pyinstaller command line instead."
        exit 1
    fi
}

verify_app_source_certifi() {
    print_status "Checking app.py portable CA usage"

    if [ ! -f "app.py" ]; then
        echo "ERROR: app.py not found."
        exit 1
    fi

    if grep -q "certifi" app.py; then
        echo "app.py references certifi."
    else
        echo "WARNING: app.py does not appear to reference certifi."
        echo "The AppImage may still fail SSL verification unless HTTPS requests use certifi.where()."
        if ! prompt_yes_no "Continue anyway?" "N"; then
            exit 1
        fi
    fi
}

run_sanity_checks() {
    print_status "Running sanity checks"

    python3 -m py_compile app.py

    if command -v node >/dev/null 2>&1 && [ -f "frontend/app.js" ]; then
        node --check frontend/app.js
    else
        echo "Node not available or frontend/app.js missing; skipping JS syntax check."
    fi

    if [ -f "frontend/app.js" ]; then
        if ! grep -q "cardRatingDetails" frontend/app.js; then
            echo "WARNING: frontend/app.js does not contain cardRatingDetails."
        fi

        if ! grep -q "Run AI browser analysis" frontend/app.js frontend/index.html 2>/dev/null; then
            echo "WARNING: Could not find 'Run AI browser analysis' in frontend files."
        fi
    fi

    if [ -d ".github/workflows" ]; then
        if grep -RInE '^[[:space:]]*--(hidden-import|collect-data)([ =])"?certifi"?[[:space:]]*(\\|`)?[[:space:]]*$' .github/workflows; then
            echo "ERROR: Found standalone certifi PyInstaller option lines in workflow files."
            echo "This breaks Windows PowerShell. Re-run this release script or patch the workflow manually."
            exit 1
        fi
    fi
}

stage_and_commit() {
    print_status "Staging outstanding project changes"
    git add .

    if ! git diff-index --cached --quiet HEAD; then
        read -p "Enter commit message: " commit_msg
        if [ -z "$commit_msg" ]; then
            commit_msg="Fix cross-platform GitHub Actions release build"
        fi
        git commit -m "$commit_msg"
    else
        echo "No new modifications to commit."
    fi
}

handle_tag_reuse() {
    local tag="$1"

    print_status "Checking release tag availability"

    if git rev-parse "$tag" >/dev/null 2>&1; then
        echo "Local tag $tag already exists."
        if prompt_yes_no "Delete local tag $tag so it can be recreated?" "N"; then
            git tag -d "$tag"
        else
            echo "Release cancelled because local tag already exists."
            exit 1
        fi
    fi

    if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
        echo "Remote tag $tag already exists on origin."
        if prompt_yes_no "Delete remote tag $tag from origin so GitHub Actions can be retriggered?" "N"; then
            git push origin ":refs/tags/$tag"
        else
            echo "Release cancelled because remote tag already exists."
            exit 1
        fi
    fi
}

print_status "Deployment Strategy Selection"
echo "Do you want to trigger a production build on GitHub?"
echo "  [1] Yes - sync version files, patch certifi workflows cross-shell, tag this release, and trigger GitHub Actions"
echo "  [2] No  - just push code changes to the remote repository"
read -p "Select option (1 or 2): " build_choice

if [ "$build_choice" = "1" ]; then
    CURRENT_VER=$(cat VERSION 2>/dev/null || echo "1.0.0")
    echo "Current local version artifact: $CURRENT_VER"
    read -p "Enter new release version (e.g., 1.0.5): " new_version

    if [ -z "$new_version" ]; then
        echo "Error: Version descriptor string cannot be empty for release builds."
        exit 1
    fi

    sync_version_files "$new_version"
    ensure_requirements_certifi
    patch_build_linux_certifi
    patch_github_workflows_certifi
    verify_app_source_certifi
    run_sanity_checks
    stage_and_commit

    print_status "Pushing commits to remote origin main branch"
    git push origin main

    tag="v$new_version"
    handle_tag_reuse "$tag"

    print_status "Creating and transmitting cloud release hook tag $tag"
    git tag -a "$tag" -m "Production milestone release $tag"
    git push origin "$tag"

    echo "========================================================="
    echo "SUCCESS: Code pushed and version tag $tag deployed!"
    echo "GitHub Actions is now compiling your binaries."
    echo "========================================================="
else
    patch_github_workflows_certifi
    run_sanity_checks
    stage_and_commit

    print_status "Pushing updates without triggering release builder"
    git push origin main

    echo "========================================================="
    echo "SUCCESS: Code changes pushed cleanly to GitHub!"
    echo "Build skipped (no release tag was created)."
    echo "========================================================="
fi
