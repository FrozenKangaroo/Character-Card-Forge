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

## Linux setup

```bash
chmod +x setup.sh start.sh
./setup.sh
./start.sh
```

The Linux scripts create a local `.venv` and install the Python dependencies from `requirements.txt`.

## First run

Open **AI Settings** and set:

- API Base URL, for example `https://nano-gpt.com/api/v1` or your local OpenAI-compatible server.
- API Key, if your provider requires one.
- Model name.
- Generation mode: use **Lite** for smaller models or smaller context windows.

Then go back to the concept page, enter a character idea, and generate the card.

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

## Troubleshooting

If the app does not start on Windows, run `start.bat` from Command Prompt so the error stays visible.

If Python is not found, reinstall Python and tick **Add python.exe to PATH**.

If the PyWebView window fails to open, rerun setup so PyQt6 and PyQt6-WebEngine are installed into the local `.venv`.

If Front Porch emotion images show as entries but not images, re-export the character with this version or newer. Older exports may have placed the files one folder too high.

## License / redistribution

Only redistribute this package if you have the right to share all included files. Do not include private API keys, personal settings, private character exports, or generated images you do not want to publish.
