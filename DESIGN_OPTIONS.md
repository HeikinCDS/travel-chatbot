# JomVoyage design backup

The website always displays the Modern design. There is no public design selector.
Older browser preferences for Classic are ignored. Conversation history, language,
larger text, high contrast and trip preferences are not changed.

The header mark reads JV. Accessibility controls have borders, and the decorative
hero illustration has been removed. The original static/styles.css remains
unchanged as the base for modern.css.

## Offline backup

backups/classic-design-2026-09-02.zip contains the exact original template,
stylesheet and chat script. It is not served to visitors. Extract into a separate
folder to inspect; do not overwrite newer application files without reviewing
the differences.

The local Git tag design-before-refresh-2026-09-02 at commit 4291520 also preserves
the entire original project, not just the front-end files.

To inspect the original project separately without overwriting current work:

```powershell
git worktree add --detach "../jomvoyage-classic-preview" design-before-refresh-2026-09-02
```

The checkpoint is local until explicitly pushed:

```powershell
git push origin design-before-refresh-2026-09-02
```

Do not reset the current working tree to preview the old design.

## Checks

```powershell
python -m unittest discover -s tests -p test_app.py -v
node --test tests/design.test.cjs
```

Browser checks cover the simplified header, absent selector and illustration,
ignored legacy Classic preference, high contrast, larger text and narrow layouts.
Screenshot review files are kept in the operating system's temporary folder
outside the project. No dataset or recommendation logic was changed.
