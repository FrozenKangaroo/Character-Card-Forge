# Character Card Forge

Character Card Forge is a local desktop app for creating AI character cards with an OpenAI-compatible API. It is aimed at roleplay frontends such as Front Porch AI, SillyTavern, Hammer AI, and other Character Card V2-compatible tools.

The app runs locally with Python and PyWebView. The app folder is treated as read-only, so settings, templates, generated images, cached browser data, and exported character cards are stored in a per-user writable data folder. This makes packaged builds such as AppImage, macOS app bundles, and Windows portable/exe bundles work correctly.

## Features

- AI-assisted character card generation from a plain concept.
- Full mode for larger models and Lite mode for smaller models.
- Editable prompt template with enable/disable controls for sections and fields.
- Compact default template designed for smaller context windows.
- Optional Q&A expansion before generation.
- Follow-up revision after generation.
- Character Card V2 JSON and PNG export.
- Front Porch AI export, including database export and emotion/avatar images.
- Optional Stable Diffusion / SD Forge image generation.
- Optional vision image analysis for reference images.
- Saved project bundles so a generated card can be reopened and revised later.
- Character Browser with date/alphabetical sorting, live search, tag include/exclude filters, and tag display.
- Alphabet jump strip for large alphabetical libraries.

## Requirements

- Python 3.10 or newer.
- Internet access for the text model API you choose.
- An OpenAI-compatible `/chat/completions` API endpoint.
- Optional: SD Forge / Automatic1111 compatible server for image generation.
- Optional: Front Porch AI data folder for direct Front Porch export.

## Windows setup

1. Install Python 3.10 or newer from the official Python website.
2. During install, tick **Add python.exe to PATH**.
3. Extract this zip anywhere you like. The app stores writable data in your user data folder, not beside the app files.
4. Double-click `setup.bat`.
5. Double-click `start.bat`.

After the first setup, you normally only need `start.bat`.

## macOS setup

For normal macOS users:

1. Install Python 3.10 or newer from the official Python website or Homebrew.
2. Extract this zip anywhere you like. The app stores writable data in your user data folder, not beside the app files.
3. Double-click `setup.command`.
4. Double-click `start.command`.

If macOS blocks the script because it was downloaded from the internet, right-click the file and choose **Open**, or run it from Terminal.

Terminal alternative:

```bash
chmod +x setup.command start.command
./setup.command
./start.command
```

## Linux setup

```bash
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

The Linux/macOS scripts create a local `.venv` and install the Python dependencies from `requirements.txt`.

## First run

Open **AI Settings** and set:

- API Base URL, for example `https://nano-gpt.com/api/v1` or your local OpenAI-compatible server.
- API Key, if your provider requires one.
- Model name.
- Generation mode: use **Lite** for smaller models or smaller context windows.

Then go back to the concept page, enter a character idea, and generate the card.


## Character Browser

The Character Browser shows autosaved character projects from the writable user exports folder.

- Sort by newest, oldest, A-Z, or Z-A.
- Use live search to search character names, browser summaries, output previews, folders, and tags.
- Use **Filter Tags** to include or exclude as many tags as you want. Click a tag once to include it, twice to exclude it, and a third time to clear it. The tag list is context-aware: once filters/search are active, it only shows tags that still exist on the matching characters, while keeping active filters visible so they can be removed.
- Search still respects the active tag filter.
- When sorting alphabetically and the library has more than 50 characters, an A-Z jump strip appears above the grid.
- Selecting a character shows its browser summary and all saved tags under the description box.

## Front Porch AI export

To export directly into Front Porch AI:

1. Open the Front Porch version you want to target.
2. Go to that Front Porch version's settings and find its data folder.
3. In Character Card Forge, open **Settings**.
4. Set **Stable Front Porch Data Folder** and/or **Beta Front Porch Data Folder**.
5. Choose **Front Porch Export Target** before exporting.
6. Use **Scan Selected Target**, **Scan Stable**, or **Scan Beta** to verify the database.
7. Export the card to Front Porch.

Character Card Forge uses the selected target to choose the matching database:

```text
<Stable Front Porch Data Folder>/KoboldManager/front_porch.db
<Beta Front Porch Data Folder>/KoboldManager/front_porch_beta.db
<Selected Front Porch Data Folder>/KoboldManager/Characters/
```

Emotion/avatar images are linked through Front Porch's `avatar_images` table and saved under the character's `avatars` subfolder.

## Smaller-context default template

The public default template is intentionally trimmed down. It enables only the basics:

- Name
- Description
- Personality
- Scenario
- First Message
- Example Dialogues
- Tags

Longer sections such as Lorebook, Custom System Prompt, State Tracking, Alternative First Messages, and Stable Diffusion Prompt are included but disabled by default. Turn them on only when the target model has enough context or the card needs those features.

## Files and folders

The application folder contains only the program and bundled defaults:

```text
app.py                  Main backend app
frontend/               Browser/PyWebView interface
data/                   Bundled default settings/templates only
setup.sh                Linux setup
start.sh                Linux start
setup.command           macOS double-click setup
start.command           macOS double-click start
setup-mac.sh            macOS terminal setup alias
start-mac.sh            macOS terminal start alias
setup.bat               Windows setup
start.bat               Windows start
```

Writable user data is stored outside the app folder so packaged builds can run from read-only locations such as AppImage mounts.

Default writable location:

```text
~/Documents/Character Card Forge/
```

If `Documents` is unavailable on Linux, the fallback is:

```text
~/.local/share/Character Card Forge/
```

Inside that writable folder:

```text
data/settings.json              Local settings
data/template.json              Editable prompt template
data/templates/                 Saved custom templates
data/character_library.sqlite3  Character Browser cache/library
exports/                        Exported character cards and saved projects
```

Advanced/portable override:

```bash
CCF_DATA_DIR="/path/to/my/Character Card Forge data" ./start.sh
```

On Windows PowerShell:

```powershell
$env:CCF_DATA_DIR="D:\Character Card Forge Data"; .\start.bat
```


## AppImage / packaged builds

Character Card Forge is safe to package as an AppImage or similar read-only bundle. At startup it now:

- treats the app/program directory as read-only
- creates writable folders in the user data location
- copies bundled default settings/templates into user data only if they do not already exist
- writes SQLite cache, generated images, imports, logs, templates, and exports outside the AppImage mount
- disables Python bytecode writes beside `app.py`

This avoids errors caused by trying to create `data/`, `exports/`, `__pycache__/`, or generated image folders inside a read-only AppImage directory.

## Updating

When replacing the app folder with a newer version, your settings, templates, saved projects, and generated cards are preserved automatically because they live in the writable user data folder, not in the app folder.

If dependencies change, run the setup script again:

Windows:

```bat
setup.bat
```

Linux:

```bash
./setup.sh
```

macOS:

```bash
./setup.command
```


## Character Browser Tag Tools

The Character Browser includes a faceted tag filter for larger libraries:

- Sort tag chips alphabetically or by most-used.
- Each tag chip shows a count in brackets for how many currently matching characters use that displayed tag.
- Include or exclude multiple tags at once.
- Live search still respects active include/exclude filters.
- Tag merges are display-only aliases: merge a noisy original tag into a cleaner browser tag without editing the real tags saved on the character.
- **AI Tag Cleanup** can suggest merge/rename candidates for near-duplicate tags. Use Merge Only for display aliases, or Rename to update the real saved card tags.
- Selected characters show both the original real tag and any merged display tag, with merged display tags highlighted separately.
- **AI Description** refreshes the selected character summary so the browser describes the scenario and character dynamic instead of only physical metadata.

Example: merge `blonde-girl`, `blonde female`, and `yellow hair` into `blonde`. The browser tag list becomes cleaner, while each character keeps its original tags until you explicitly edit them.

## Troubleshooting

If the app does not start on Windows, run `start.bat` from Command Prompt so the error stays visible.

If Python is not found, reinstall Python and tick **Add python.exe to PATH**.

If the PyWebView window fails to open, rerun setup so PyQt6 and PyQt6-WebEngine are installed into the local `.venv`.

If Front Porch emotion images show as entries but not images, re-export the character with this version or newer. Older exports may have placed the files one folder too high.

## License / redistribution

Only redistribute this package if you have the right to share all included files. Do not include private API keys, personal settings, private character exports, or generated images you do not want to publish.

## v0.9.7 AI tag cleanup and AI browser descriptions

- Added **AI Tag Cleanup** in the Character Browser tag filter panel.
- The app scans existing real tags with the configured AI model and suggests close duplicates or redundant variants.
- Suggestions can be applied as **Merge Only**, which keeps real character tags unchanged and only changes browser display aliases.
- Suggestions can also be applied as **Rename**, which updates the real tags inside saved character projects, `latest_output.md`, and the latest Card V2 PNG.
- Added **AI Description** for the selected character. This reads the saved card and generates a short Character Browser description about the scenario, character overview, and RP hook.
- Metadata/fallback descriptions are still used when no AI-generated browser description exists.

## v0.9.6 Context-aware tag filtering

- The Character Browser tag filter list now behaves like faceted search.
- Including a tag narrows the available tag list to tags found on characters that match the included tag.
- Excluding a tag also narrows the available tag list to tags found on the remaining characters.
- Active include/exclude tags stay visible even when their source cards are hidden, so they can always be cleared.

## v0.9.4 Character Browser tag editing

- Selected characters now show clickable tags. Clicking a tag applies it as an include filter in the Character Browser.
- Character tiles also have clickable tag chips for quick filtering.
- The selected-character panel now includes **Edit Tags**, allowing tags to be added, removed, and saved without loading the full workspace.
- Saving tags updates the saved project metadata, the generated output's `Tags` section, `latest_output.md`, and the latest Card V2 PNG.

## v0.9.8 Character Browser QoL

- Added local-only delete for saved Character Card Forge directories from Character Browser. This does not touch Front Porch AI database entries.
- Added multi-select in Character Browser. Selected cards can be deleted locally, batch-exported as PNG, batch-exported to Front Porch AI, or moved together.
- Added virtual folders. These are browser-only organization folders and do not move the real files on disk.
- Added folder-aware search/filter scopes:
  - Global: search and filter all cards.
  - Current folder: search and filter only the selected virtual folder.
  - Current folder + subfolders: include the selected folder and its children.
- The smart tag filter list now respects the active folder scope, so hidden/shown tags are based on the cards currently in scope.


## v0.9.10

- Improved Character Card PNG loading for V2/V3 cards that store metadata in compressed, URL-safe base64, or alternate PNG text chunks.
- Added fallback loading from sidecar files such as `CharacterName.extracted.json` when a PNG metadata extractor can read the card but the PNG chunk is non-standard.

## v0.9.11 browser folder/description polish

- Virtual folders now appear directly in the Character Browser grid before character cards.
- Folder tiles can show a small preview collage from characters inside the folder.
- Folders remain virtual and can still be selected from the folder dropdown.
- Added a **Show subfolders** checkbox beside **Saved Characters** to show or hide nested folder tiles.
- Selected character descriptions now show whether the browser description is **AI generated** or **extracted from card**.
- The destructive multi-select delete button was renamed to **Delete Physical Saved Card Folders** to clarify it deletes real local Character Card Forge saved/export directories, not virtual folders or Front Porch entries.


## 0.9.12

- Fixed virtual folder browsing so Root / Unfiled no longer leaks characters stored in subfolders.
- Fixed the folder dropdown so selecting a folder changes the folder being viewed.
- Fixed Show subfolders so it controls nested folder/card visibility in the current folder view.
- Added rename and delete actions for virtual folders.
- Deleting a virtual folder moves affected characters back to Root / Unfiled and does not delete physical folders or Front Porch entries.
- New virtual folders are created inside the currently viewed virtual folder.


### 0.9.13

- Added clickable breadcrumb navigation above the Character Browser grid so nested virtual folders are easy to back out of.
- Added an Up button when viewing a subfolder.


## v0.9.14

- Fixed virtual folder moves still appearing in the previous folder after rescanning physical saved character directories.
- Virtual folder assignments are now cached separately from scanned project files, so browser organization wins over disk layout.
- Moving characters to Root / Unfiled now clears the cached virtual-folder assignment.


## v0.9.17 UI cleanup

- Reworked the Main Concept page into a two-column dashboard so Concept Attachments are visible without scrolling past card-import tools.
- Moved existing-card/image import tools into compact collapsible panels. No features were removed.
- Reworked Character Browser controls into a cleaner command bar with primary search/sort/folder controls visible first and advanced options tucked into a collapsible panel.
- Multi-select actions now live in a collapsible action panel that opens automatically when cards are selected.
- Improved smaller-window responsiveness for Concept, Character Browser, settings grids, card grids, and side panels.
- Added a rotating Tip Box for new users with useful workflow tips.

## Character Browser database

From v0.9.15, the Character Browser uses a local SQLite database at `data/character_library.sqlite3` for virtual folder membership. The app still scans the physical `exports/` directory to discover saved character projects, but folder assignments are now stored in SQLite and are no longer guessed from the physical folder layout. This fixes moved cards reappearing in Root / Unfiled after refresh.

Virtual folders remain browser-only. They do not move physical files on disk and they do not touch Front Porch AI entries.


## Character Browser SQLite cache

Character Browser now uses `data/character_library.sqlite3` as a cached index. The app still scans `exports/` to discover saved projects, but it stores card names, tags, browser descriptions, thumbnail image data, virtual folder membership, and hash checks in SQLite. If a project JSON, latest card PNG, or selected source image changes on disk, the next browser refresh or character open detects the hash change and refreshes the cached row. Editing the output text also autosaves back into the project and refreshes the SQLite cache after a short delay.

## v0.9.18 quality fixes

- Q&A generation now verifies that every enabled Q&A question has an answer before final card generation starts.
- If the AI skips one or more Q&A questions, the app automatically asks the AI again for only the missing answers.
- Added a **Delete Saved Card** button for the currently selected Character Browser card. This deletes only the local Character Card Forge saved/export folder and does not touch Front Porch AI entries.
- Tightened tag cleanup so prompt instructions such as `8-12 lowercase hyphen-separated tags` or `maximum 15` are not saved as real character tags.


## v0.9.19 - AI task interface unlock

- AI generation tasks no longer lock the entire interface.
- While a text/vision/SD/AI cleanup task is running, only other AI-powered controls are disabled.
- Non-AI actions such as browsing characters, editing text, copying, exporting, selecting images, and organizing folders remain usable where safe.
- Non-AI file/write operations can still use a full temporary lock when needed.


## v0.9.20

- Fixed Stable Diffusion Prompt helper text leaking into generated card output.
- Stable Diffusion prompt extraction now strips echoed ordering guidance before sending prompts to SD Forge / Automatic1111.
- The generation prompt now tells models not to echo helper text in the Stable Diffusion section.

## v0.9.21 generation flow polish

- Starting **Generate Card** now clears stale Q&A answers, full text output, generated card images, selected quick-save image state, and previous emotion image results.
- Added optional **Stream AI text into output boxes** in AI Settings. When enabled, Q&A answers and the final card text appear while the model is responding.
- Emotion image generation now reports whether it is generating AI prompts or SD images.
- Emotion images appear one by one as they finish instead of waiting for the whole batch.
- If emotion image generation is stopped, any images already generated remain visible and can still be saved/exported.


## v0.9.22

- Fixed emotion prompt generation streaming into and replacing the main Full Text Output.
- Internal AI helper calls no longer stream into visible Q&A/Output boxes unless explicitly routed there.


## v0.9.25 note

- Stable Diffusion prompt generation now deduplicates and caps negative prompt tags before saving or sending prompts to SD Forge / Automatic1111. This prevents runaway repeated negative prompts when a text model loops on cleanup tags.


## AppImage / packaged writable data

Character Card Forge treats bundled app files as read-only. In AppImage/PyInstaller builds, user data is written outside the mounted app folder. The app refuses to use `sys._MEIPASS`, `_internal`, `/tmp/.mount_*`, or the app bundle folder as the data root unless `CCF_ALLOW_BUNDLE_DATA_DIR=1` is explicitly set.

Default writable data locations:

- Linux: `~/Documents/Character Card Forge/`, falling back to `~/.local/share/Character Card Forge/`
- macOS: `~/Library/Application Support/Character Card Forge/`
- Windows: `%APPDATA%\Character Card Forge\`

You can override the writable data location with `CCF_DATA_DIR` or `CHARACTER_CARD_FORGE_DATA_DIR`.


## v0.9.30 packaging note

If you build an AppImage or PyInstaller bundle, delete old build artifacts before rebuilding:

```bash
rm -rf build dist __pycache__
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

The release zip no longer includes `__pycache__` or `.pyc` files. Stale bytecode can cause an AppImage to keep running old startup path code even when `app.py` has been fixed.


### v0.9.35

- AppImage/frozen builds now force the classic PyWebView file picker for all backend file buttons and drop-zone clicks. This avoids invisible kdialog/zenity launches inside packaged builds. Normal source runs can still use host-native pickers.


## v0.9.39 Settings / Tags / Browser Privacy

- AI Settings is now labelled Settings.
- Added Data Files Folder setting. Changing it copies existing user data and requires an app restart.
- Added Restrict Tags mode so generated cards can only use tags from an allowed list; invalid tags are removed after generation.
- Added Character Browser NSFW handling: show normally, blur images, or hide matching cards.

## v0.9.40 - Split multi-character concepts into separate cards

- Added a new **Split into Multiple Cards** card mode for multi-character concepts.
- Added a matching **Multi-Character Setting Logic** option for split-card workflows.
- Split-card generation identifies main characters and generates one focused single-character card per character.
- During each split-card pass, the focused character becomes the main card character, while other characters are preserved as lorebook/background/supporting references.
- Output areas now support character tabs, so Q&A Answers, Full Text Output, Emotion Images, and Quick Save / Image can be switched per generated card.



## Version 1.0.3

- Replaced emoji-based Character Browser action buttons with inline SVG icons so AI Description, Load Workspace, and Delete render reliably in PyWebView/AppImage builds.
- Added a Character Browser loading modal when opening or manually refreshing the browser, making slower library scans visibly active instead of looking frozen.
- Updated release version to `1.0.3`, removed beta suffix, and made the app read its displayed version from the `VERSION` file instead of hard-coded frontend/backend fallbacks.
- Fixed packaged-build version detection so AppImage/PyInstaller builds can read `VERSION` from bundled resources, `_internal`, the executable folder, or the AppDir root instead of falling back to a stale displayed value.

## Version 1.0.3-beta12

- Consolidated the selected-card actions in Character Browser into compact icon buttons.
- Moved AI Description, Load Workspace, and Delete Saved Card icons above the selected card description so they no longer crowd the selected-card header.
- Added accessible labels and hover tooltips for each icon action.
- Styled AI, load, and delete actions with distinct compact icon treatments for clearer small-window use.
- Updated app version, sidebar version fallback, VERSION file, README, and frontend cache-busting to `1.0.3-beta12`.

## Version 1.0.3-beta11

- Fixed Front Porch main image export still falling back to a blank image when the saved card image only existed in Character Card Forge's workspace asset database or embedded base64 data.
- Added a stricter Front Porch image resolver that checks the selected local path, loaded project fields, saved workspace asset blobs, saved project JSON, generated-image base64, tab-level generated images, and deep embedded `data:image/...` values before export.
- Front Porch export now refuses to write a blank card image when an expected image cannot be resolved, and logs `front_porch_image_resolution_failed` diagnostics instead.
- Front Porch card PNG writing now requires a verified image source for Front Porch exports, while normal Chara Card PNG export can still use the blank placeholder when no image is selected.
- Updated app version, sidebar version fallback, VERSION file, README, and frontend cache-busting to `1.0.3-beta11`.

## Version 1.0.3-beta9

- Fixed Front Porch exports creating blank main images when the selected card image was still a remote/generated URL.
- Card image URLs are now downloaded/materialized into the local card image folder before saving, loading, Chara PNG writing, or Front Porch export.
- Loading older workspaces with URL-based card images now converts the image back to a stable local file path when possible.
- Importing an image URL through the Concept import flow now stores the downloaded local image path instead of keeping the URL in `cardImagePath`.
- Front Porch export now stops with a clear error if a selected image cannot be found/downloaded, instead of silently exporting a blank placeholder image.

## Version 1.0.3-beta7

- Added a Front Porch export target picker when both Stable and Beta Front Porch data folders are configured.
- **Export to Front Porch AI** now offers: Stable, Beta, or Both.
- **Export Selected to Front Porch** uses the same target picker for batch exports.
- Exporting to Both writes each selected card to both configured Front Porch databases, creating separate timestamped backups for each target.
- The exporter temporarily applies the chosen target during export, then restores the previously selected Front Porch target/settings afterward.
- Backend Front Porch project export is now tolerant of optional target/settings arguments for future bridge compatibility.

## Version 1.0.3-beta6

- Fixed Generate Card modal Q&A bridge error: `Api.generate_qa_context() takes 4 positional arguments but 6 were given`.
- Custom per-card Q&A questions are now merged into a temporary frontend Q&A template before calling the backend.
- Restored the backend call to the original 3-argument PyWebView signature for better AppImage/stale-build compatibility.
- Backend Q&A bridge is now tolerant of extra positional arguments if an older/newer frontend mix happens during packaging.

## Version 1.0.3-beta5

- Renamed the **Character Description** concept subtab to **Vision** to better match the image-analysis workflow.
- Added a **Generate Card Options** modal that appears before generation starts.
- Added per-card temporary generation notes that are injected into the current generation only and are not saved to settings or templates.
- Added per-card custom Q&A questions, one per line, that are merged with normal Q&A for the current generation only.
- Custom Q&A is useful for card-specific details such as asking an IT character what their first computer was.
- Improved small-window layout for selected character actions in Character Browser so AI Description, Delete Saved Card, and Load Workspace wrap instead of being pushed off-screen.
- Reworked Concept, Prompt Template, Settings, and Output subtabs to use left/right arrow scrolling when there are more tabs than fit on screen.
- Hidden visible subtab scrollbars to keep smaller windows cleaner.
- Updated app version, sidebar version fallback, VERSION file, README, and frontend cache-busting to `1.0.3-beta5`.


## Version 1.0.3-beta4

- Fixed README release history so the full-card vision feature is listed as `1.0.3-beta1` and the browse-button fix remains `1.0.3-beta2`.
- Added default Idea Generator settings keys to `data/settings.json` for clearer fresh installs and packaged builds.
- Improved the Idea Generator Settings editor so switching fields auto-applies the currently edited field before loading the next one.
- This prevents unsaved in-editor changes from being overwritten when moving from one Idea Generator field to another.
- Updated app version, sidebar version fallback, VERSION file, and frontend cache-busting to `1.0.3-beta4`.


## Version 1.0.3-beta3

- Expanded the Idea Generator with configurable option lists per field.
- Added an **Idea Generator** tab in Settings where each field's dropdown options can be edited one-per-line.
- Added reset controls for a selected Idea Generator field and for all Idea Generator option lists.
- Added multi-select support for Idea Generator fields, with Personality, Subject Of, Engages In, and Engages In (Sexual) enabled by default.
- Multi-select fields now show picked values as removable chips while keeping the dropdown searchable and scroll-limited.
- Split the crowded Settings page into organized tabs: AI / Models, Vision, Stable Diffusion, Front Porch, Data / Browser, Tags, and Idea Generator.
- Updated app version, sidebar version fallback, VERSION file, and frontend cache-busting to `1.0.3-beta3`.


## Version 1.0.3-beta2

- Fixed Character Description / Concept browse buttons after the full-card vision update.
- Select Vision Image, vision drop-zone click, concept attachment browse, card image browse, saved-card load, and builder/concept card loaders now use the backend native picker path instead of relying on hidden browser file inputs.
- Kept drag-and-drop and hidden file inputs as fallback paths.
- Updated cache-busting and version display to `1.0.3-beta2`.


## Version 1.0.3-beta1

- Expanded Vision Image Analysis with a new **Analyze Full Card → Concept** action.
- The original **Analyze Image** flow still focuses only on the visible character design.
- The new full-card mode analyzes the whole image/card, including character design, visible action, expression, props, background, setting, mood, lighting, symbols, composition, and legible text when possible.
- Full-card analysis generates a structured Main Concept with character, visual design, personality/vibe, setting, what is happening in the card, relationship to `{{user}}`, core conflict/hook, scenario starting point, and details to preserve.
- The generated full-card concept is written directly into the Main Concept box, with an option to replace or append if the box already contains text.
- Vision prompts now support separate character-only and full-card analysis modes while keeping SFW retry handling for refused vision responses.
- Updated app version, sidebar version fallback, and frontend cache-busting to `1.0.3-beta1`.

## Version 1.0.2

- Added Nano-GPT model token auto-fetching from detailed model catalog endpoints, including canonical, subscription, and paid model lists.
- Token fetching now reads documented `context_length` and `max_output_tokens` values and applies them to Max Input Tokens and Max Output Tokens.
- Added visible token fetch status/debug controls in Settings so successful matches and log details are easy to inspect.
- Improved Settings layout so token fetch results do not stretch API fields or break the grid.
- Added separate Stable and Beta Front Porch data folders plus an export target selector.
- Front Porch scanning now checks the selected target quickly and chooses the expected database: `front_porch.db` for Stable and `front_porch_beta.db` for Beta.
- Expanded the Idea Generator with more relationship, setting, core conflict, personality, subject, engagement, and sexual engagement options.
- Large Idea Generator dropdowns are searchable and capped to avoid oversized menus.
- Updated AppImage/source version display and cache-busting to the stable 1.0.2 release.


## Version 1.0.0

- Added URL imports for existing Character Card V2/V3 PNG/JSON/TXT/MD cards.
- Added URL support for loading cards into Main Concept and Builders.
- Added URL support for vision/image analysis workflows.
- Added URL support for card images used by PNG export / import card tools.
- Added URL attachment support for concept files.
