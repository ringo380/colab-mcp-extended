# colab-mcp-extended

Extended version of Google's [colab-mcp](https://github.com/googlecolab/colab-mcp) that supports opening specific Drive notebooks instead of always opening the scratchpad.

## Changes from upstream

- `notebook_id` parameter on `open_colab_browser_connection` — pass a Google Drive file ID to open that notebook
- `authuser` parameter — specify which Google account to use (default: 1)
