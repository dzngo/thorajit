# Emoji picker

The Streamlit v2 component bundles Emoji Mart 5.6.0 and its data 1.2.1 locally, so selecting an emoji does not require a third-party service at runtime. `emoji_data.json` is also used by Python to validate and reserve choices. The MIT license is in `EMOJI-LICENSE`.

Selecting an emoji applies it immediately. Closing the picker without selecting keeps the previous choice; availability is checked again when the room is joined or the profile is saved.

To rebuild after modifying `emoji_picker_src.js`, install `emoji-mart@5.6.0`, `@emoji-mart/data@1.2.1`, and `esbuild@0.25.12` in a temporary npm project, then run esbuild with that project's `node_modules` in `NODE_PATH`:

```sh
esbuild ui/components/emoji_picker_src.js --bundle --format=esm --minify --outfile=ui/components/emoji_picker_bundle.js
```

If the emoji data version changes, update `emoji_data.json` from the same `@emoji-mart/data` package as the bundle.

## Host roster

`host_roster.py` is a Streamlit v2 component that displays players in columns of five with an inline remove button for each guest. Player names are inserted as text, and the server rechecks the selected player before removal. The host has no remove button.
