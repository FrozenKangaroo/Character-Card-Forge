# Character Card Forge

Character Card Forge is a local desktop app for creating AI character cards with an OpenAI-compatible API. It is aimed at roleplay frontends such as Front Porch AI, SillyTavern, Hammer AI, and other Character Card V2-compatible tools.

The app runs locally with Python and PyWebView. Your prompts, templates, generated cards, exported PNGs, and settings are stored in the app folder unless you choose external paths inside the app.

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
3. Extract this zip somewhere writable, such as `Documents\Character Card Forge`.
4. Double-click `setup.bat`.
5. Double-click `start.bat`.

After the first setup, you normally only need `start.bat`.

## macOS setup

For normal macOS users:

1. Install Python 3.10 or newer from the official Python website or Homebrew.
2. Extract this zip somewhere writable, such as `Documents/Character Card Forge`.
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

The Character Browser shows autosaved character projects from `exports/`.

- Sort by newest, oldest, A-Z, or Z-A.
- Use live search to search character names, browser summaries, output previews, folders, and tags.
- Use **Filter Tags** to include or exclude as many tags as you want. Click a tag once to include it, twice to exclude it, and a third time to clear it. The tag list is context-aware: once filters/search are active, it only shows tags that still exist on the matching characters, while keeping active filters visible so they can be removed.
- Search still respects the active tag filter.
- When sorting alphabetically and the library has more than 50 characters, an A-Z jump strip appears above the grid.
- Selecting a character shows its browser summary and all saved tags under the description box.

## Front Porch AI export

To export directly into Front Porch AI:

1. Open Front Porch AI.
2. Go to Front Porch settings and find the Front Porch data folder.
3. In Character Card Forge, open **AI Settings**.
4. Set **Front Porch Data Folder** to that folder.
5. Use **Scan Front Porch Folder**.
6. Export the card to Front Porch.

Character Card Forge looks for:

```text
<Front Porch Data Folder>/KoboldManager/front_porch_beta.db
<Front Porch Data Folder>/KoboldManager/front_porch.db
<Front Porch Data Folder>/KoboldManager/Characters/
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

```text
app.py                  Main backend app
frontend/               Browser/PyWebView interface
data/settings.json      Local settings
data/template.json      Default editable prompt template
data/templates/         Saved custom templates
exports/                Exported character cards and projects
setup.sh                Linux setup
start.sh                Linux start
setup.command           macOS double-click setup
start.command           macOS double-click start
setup-mac.sh            macOS terminal setup alias
start-mac.sh            macOS terminal start alias
setup.bat               Windows setup
start.bat               Windows start
```

## Updating

When replacing the app folder with a newer version, keep your existing `data/` and `exports/` folders if you want to preserve settings, templates, saved projects, and generated cards.

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
