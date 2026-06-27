## v1.0.11-beta5

- Optimised Character Browser → Load Workspace so it no longer re-indexes the Browser cache before opening a selected card.
- Workspace asset hydration now restores generated/emotion image BLOBs to local cached files instead of serialising every image as a huge data URL through pywebview.
- Generated image and emotion image panels now lazy-load small previews from file paths after the workspace opens.
- Added a 20-second workspace-load watchdog that unlocks the interface and records a debug event if a backend load takes unusually long.
- Added backend timing/debug events for lightweight workspace image hydration and slow project loads.

## v1.0.11-beta4

- Added a Front Porch Character Manager in Settings. Scan Stable or Beta Front Porch databases, review installed characters, multi-select rows, and delete selected characters after a warning/confirmation.
- Front Porch character deletion now creates a capped database backup first, then removes character rows, sessions, messages, avatar rows, card PNGs, and avatar folders where possible.
- Added Import from Front Porch to the Import Card modal. You can scan Stable or Beta Front Porch, select a card, and import it into Character Card Forge / Character Browser.

## v1.0.11-beta2

- Fixed revision output that came back with Markdown wrapper headings such as `# Revised Character Card` / `## Name`.
- CCF now strips the wrapper title and normalises known card section headings back into the app's standard section format.
- Image prompt detection now understands Markdown `#` / `##` section headings as well as plain CCF headings.
- Generate Images is no longer disabled for API image models just because the Stable Diffusion Prompt section is missing; natural-prompt API mode can proceed from the Natural English prompt or current card text.
- Revision prompts now explicitly tell the AI not to add wrapper titles or convert the card into Markdown headings.

## v1.0.11-beta1

- Stable public release of the v1.0.10 cycle.
- Group Card export now supports both stable and beta Front Porch AI builds now that Group Chat is available in stable.
- Removed the `-beta` suffix from the app version and frontend cache-busting.
- Added API Image Model support alongside local SD Forge / Automatic1111 generation.
- Added Image Generation provider setting: Local SD Forge / Automatic1111 or API Image Model.
- Added Image API Base URL / API Key fields, which can fall back to the existing text API settings.
- Added dynamic API image model fetching from OpenAI/NanoGPT-style `/models?detailed=true` metadata.
- API image model picker filters for usable text-to-image / text+image-to-image models and skips obvious tools/upscalers/edit-only routes for this first beta.
- Added API Resolution / Size setting so models can use values such as `1024x1024`, `1:1`, `2k`, `4k`, or `auto` depending on the selected model.
- Added API Prompt Style setting:
  - Auto chooses between Stable Diffusion tag prompts and natural-English prompts based on the model family.
  - Stable Diffusion tag mode sends the existing Positive Prompt / Negative Prompt style.
  - Natural English mode builds a character-card portrait instruction from the card fields and visual prompt notes.
- API image generation accepts cards even if the Stable Diffusion Prompt section is missing; local SD Forge still requires a positive prompt.
- API image responses are parsed flexibly from OpenAI-style `data[].b64_json`, provider URLs, raw base64, raw image bytes, and common nested response shapes.
- Generated API images are saved into the same generated-image workflow as local SD images, so Use This / Card Image / export behaviour remains shared.

## v1.0.9

- Fixed Quick Save / Image Card Image preview showing as broken while the selected image still exported and appeared in Character Browser.
- Local card-image previews now prefer a backend-generated data URL instead of relying on pywebview `file://` loading.
- Typed/pasted local image paths in the Card Image modal are now imported into CCF's managed card-image folder, matching browse/drop behavior.
- Updated frontend cache-busting to v1.0.9 for the public release.

## v1.0.9-beta35

- Improved update checking diagnostics so the Debug Log now records GitHub release/tag fetch success, HTTP failures, network/cert errors, candidate versions, source used, and the active VERSION file.
- Update version parsing now understands tags/release names with prefixes such as `character-card-forge-v1.0.9-beta35` instead of only plain `v1.0.9-beta35`.
- Added a public GitHub HTML tag/release page fallback if the JSON API returns nothing or is blocked.
- Manual **Check Updates** now reports the source and number of candidate versions checked.
- Fixed the “Remind Me Later” session logic so hourly checks do not immediately re-open a dismissed update modal.
- Kept the v1.0.9-beta34 database backup fix: CCF Front Porch DB backups go into `KoboldManager/backups/` and are capped to the latest 10 per database.


- Fixed Front Porch Beta direct Group Card export to match Front Porch-created group DB shape more closely.
- Group IDs now use plain `group_<milliseconds>` instead of `group_<milliseconds>_<suffix>`.
- Legacy `groups.character_ids` is left as `[]` for private `group_members` groups instead of being filled with private member UUIDs.
- Group/member timestamps now mirror Front Porch importer behavior: group rows use seconds, private member rows use `0`.
- Preserved source-card realism/system-prompt keys instead of remapping them to private group-member UUIDs.
- Fixed a Browser export logging bug where a non-Front-Porch project export could reference an undefined target.

## Version 1.0.9-beta25

### v1.0.9-beta25

- Fixed Group Card project creation failing with `name 'group_profile' is not defined`.
- Group Card browser projects now safely recover `groupProfile` from options or embedded payload metadata.
- Updated version files and frontend cache-busting to `1.0.9-beta25`.

### v1.0.9-beta22
- Group Card Front Porch export now supports Stable and Beta targets.
- Added stronger Group Card detection using saved project metadata and group-preview text markers.
- Group member avatars now reject flat placeholder PNGs and try harder to recover real images from saved project data, browser cache thumbnails, existing card PNGs, and nearby image files.
- Exporting an existing Group Card now rewrites the `.group.png` from the refreshed `fpa_group` payload instead of copying an older placeholder-avatar file.
- Direct Group Card export refreshes placeholder/missing `avatar_base64` values from the original member projects before writing `group_members` avatar files.
- Single-card Front Porch export no longer hard-fails just because an image cannot be restored; it falls back to a metadata-safe placeholder like older builds.
- Updated version files and frontend cache-busting to `1.0.9-beta22`.


## v1.0.9-beta30

- Group direct DB export now leaves legacy groups.character_ids/characterIds empty so Front Porch uses group_members as the source of truth for member avatars.
- Added group table/schema export diagnostics for legacy character/avatar columns.

### v1.0.9-beta36
- Fixed Concept → Multi-Card Group Card generation corrupting member 1 output when streaming was enabled.
- The internal Group Card AI combine pass now runs silently instead of streaming its JSON into the visible Full Text Output box.
- Member cards and their focused Q&A tabs remain intact after the group wrapper is created.
