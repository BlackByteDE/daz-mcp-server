"""Windows UI Automation helpers for driving native DAZ Studio dialogs that
have no working headless scripting equivalent (Bug-Katalog #22 Teil 2:
``DzWearablesAssetFilter.doSave()`` fails with an unexplained generic error
under every configuration tried; the real "File > Save As > Wearable(s)
Preset" GUI action + its two native dialogs work reliably, so this module
drives *those* instead of the broken script API).

Windows-only (``pywinauto``/``pywin32``). Requires the DAZ Studio process to
be running on the same machine as this MCP server process — there is no
remote-UI-automation path.

All findings here were confirmed live (2026-09-09) against DAZ Studio 6.25,
round-tripped end to end against a real figure with a fitted test prop, then
fully cleaned up. See ``docs/daz-mcp-bridge-bugs.md`` #22 for the full
investigation, including approaches that looked reasonable but did not work.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from fastmcp.exceptions import ToolError

try:
    import win32api
    import win32con
    import win32gui
    import win32process
    import win32com.client
    from pywinauto.application import Application
    from pywinauto.keyboard import send_keys

    _PYWINAUTO_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on non-Windows/no-pywinauto envs
    _PYWINAUTO_AVAILABLE = False


def _require_pywinauto() -> None:
    if not _PYWINAUTO_AVAILABLE:
        raise ToolError(
            "This tool requires pywinauto/pywin32 (Windows-only UI automation) "
            "and a DAZ Studio process running on the same machine as this MCP "
            "server — there is no remote-UI-automation path. Install with "
            "`uv sync` (pywinauto is declared as a Windows-only dependency in "
            "pyproject.toml)."
        )


def require_interactive_desktop() -> None:
    """Fail fast if real mouse/keyboard input is impossible right now.

    Dialogs that need keyboard input (``drive_modifier_asset_save``) cannot
    be driven while the workstation is locked — confirmed live: pywinauto
    then fails mid-dialog with "There is no active desktop". Probing the
    cursor the same way pywinauto does, *before* the dialog is opened,
    avoids leaving a modal dialog up (Bug-Katalog #6).
    """
    _require_pywinauto()
    try:
        win32api.SetCursorPos(win32api.GetCursorPos())
    except Exception as exc:  # pywintypes.error when the desktop is locked
        raise ToolError(
            "No interactive desktop (workstation locked?) — this tool needs real "
            "keyboard/mouse input on the DAZ Studio dialog. Unlock the session and retry."
        ) from exc


def find_daz_studio_pid() -> int:
    """Find the running DAZStudio.exe process ID via WMI (no extra dependency
    beyond pywin32, which pywinauto already requires)."""
    _require_pywinauto()
    wmi = win32com.client.GetObject("winmgmts:")
    for proc in wmi.InstancesOf("Win32_Process"):
        if proc.Name == "DAZStudio.exe":
            return proc.ProcessId
    raise ToolError("DAZStudio.exe process not found — is DAZ Studio running on this machine?")


def _find_window(
    pid: int,
    title_predicate: Callable[[str, str], bool],
    timeout: float,
    poll_interval: float = 0.4,
) -> int:
    """Poll for a visible top-level window owned by ``pid`` whose (title,
    class_name) satisfies ``title_predicate``. Returns its hwnd.

    Polling (not a single check) because the DazScript-side action trigger
    runs asynchronously — the window can take a moment to appear after the
    action fires.
    """
    deadline = time.monotonic() + timeout
    matches: list[int] = []

    def cb(hwnd: int, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:  # pragma: no cover - defensive, matches prior live testing
            return True
        if wpid == pid and win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            cls = win32gui.GetClassName(hwnd)
            if title_predicate(title, cls):
                matches.append(hwnd)
        return True

    while time.monotonic() < deadline:
        matches.clear()
        win32gui.EnumWindows(cb, None)
        if matches:
            return matches[0]
        time.sleep(poll_interval)
    raise ToolError(
        f"Timed out after {timeout}s waiting for the expected DAZ Studio dialog window."
    )


def _wait_until_closed(hwnd: int, timeout: float, poll_interval: float = 0.3) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not win32gui.IsWindow(hwnd):
            return
        time.sleep(poll_interval)
    raise ToolError(
        f"Dialog (hwnd={hwnd}) did not close within {timeout}s after confirming it."
    )


def _set_native_filename_field(hwnd: int, auto_id: str, text: str) -> None:
    """Set the filename field on a native Windows "Filtered Save" (Explorer-
    style, class ``#32770``) common dialog.

    Confirmed live: this field's ``window_text()``/classic ``WM_GETTEXT``
    always return only the static label ("Dateiname:"), never the real
    value — checking success that way is a trap. The real value must be set
    *and read back* via pywinauto's UIA ``ValuePattern``
    (``set_edit_text()`` / ``get_value()``). Plain ``win32gui.SendMessage(...,
    WM_SETTEXT, ...)`` on the inner Edit HWND does **not** work — this is a
    modern ``IFileDialog``-based common dialog (Vista+), which ignores that
    classic message entirely.
    """
    app = Application(backend="uia").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    edit = win.child_window(auto_id=auto_id, control_type="Edit")
    edit.set_edit_text(text)
    actual = edit.get_value()
    if actual != text:
        raise ToolError(
            f"Failed to reliably set the filename field (got {actual!r}, expected {text!r})."
        )


def _click_native_dialog_button(hwnd: int, control_id: int) -> None:
    """Trigger a button on a native "Filtered Save" common dialog.

    Confirmed live: neither pywinauto's UIA ``Invoke()`` pattern nor a raw
    ``BM_CLICK`` sent to the button's own HWND actually triggers the Save
    action on this dialog — both return without error but leave the dialog
    open. What works: ``WM_COMMAND``/``BN_CLICKED``
    (``wParam = MAKELONG(control_id, 0)``) sent to the **dialog window
    itself**, not the button. ``lParam`` (conventionally the control's HWND)
    was confirmed unnecessary — 0 works.
    """
    wparam = win32api.MAKELONG(control_id, 0)
    win32gui.SendMessage(hwnd, win32con.WM_COMMAND, wparam, 0)


def _invoke_qt_button(hwnd: int, auto_id: str) -> None:
    """Click a button on a DAZ Studio-native Qt6 dialog (as opposed to a
    native Windows common dialog). Confirmed live: unlike the native
    "Filtered Save" dialog's buttons, these respond normally to UIA
    ``Invoke()`` — no WM_COMMAND workaround needed here.
    """
    app = Application(backend="uia").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    btn = win.child_window(auto_id=auto_id, control_type="Button")
    btn.invoke()


# Auto_id prefix for every control on the "Wearable(s) Preset Save Options"
# dialog, confirmed live 2026-09-09.
_WEARABLES_DLG = "App.WearablesAssetFilterDialog"
_WEARABLES_ACCEPT_BTN = f"{_WEARABLES_DLG}.BasicDlgButtonGrpBox.BasicDlgAcceptDialogBtn"
_WEARABLES_CANCEL_BTN = f"{_WEARABLES_DLG}.BasicDlgButtonGrpBox.BasicDlgCancelDialogBtn"


# Both "Create New <Thing>" confirmation dialogs (Geometry Shell, Strand-Based
# Hair) are the same underlying Qt6 dialog class (``App.CreateNewItemDlg``),
# confirmed live 2026-09-19 by inspecting both control trees side by side —
# only the window title differs, the Accept button's auto_id path is
# identical on both.
_CREATE_NEW_ITEM_ACCEPT_BTN = (
    "App.CreateNewItemDlg.BasicDlgButtonGrpBox.BasicDlgAcceptDialogBtn"
)
_GEOMETRY_SHELL_DLG_TITLE = "Create New Geometry Shell"
_STRAND_HAIR_DLG_TITLE = "Create New Strand-Based Hair"


def _drive_create_new_item_dialog(dialog_title: str, dialog_timeout: float) -> None:
    """Confirm a "Create New <Thing>" dialog (``App.CreateNewItemDlg``) once
    the DazScript side has already selected the target node and triggered
    the corresponding ``Dz*Action``.

    These dialogs need no field filled in — they come pre-populated with a
    sensible default name/label — so this just waits for the dialog to
    appear and clicks Accept. Confirmed live: unlike the native "Filtered
    Save" common dialog, this is a DAZ Studio-native Qt6 dialog and its
    Accept button responds normally to UIA ``Invoke()``, no WM_COMMAND
    workaround needed.

    Must be called from a worker thread (blocking pywinauto/win32 calls) —
    see ``daz_create_geometry_shell``/``daz_create_strand_hair``'s
    ``asyncio.to_thread`` use.
    """
    _require_pywinauto()
    pid = find_daz_studio_pid()

    hwnd = _find_window(
        pid,
        lambda title, _cls: title == dialog_title,
        dialog_timeout,
    )
    _invoke_qt_button(hwnd, _CREATE_NEW_ITEM_ACCEPT_BTN)
    _wait_until_closed(hwnd, dialog_timeout)


def drive_geometry_shell_create(dialog_timeout: float = 30.0) -> None:
    """Confirm the "Create New Geometry Shell" dialog (``DzNewGeometryShellAction``)."""
    _drive_create_new_item_dialog(_GEOMETRY_SHELL_DLG_TITLE, dialog_timeout)


def drive_strand_hair_create(dialog_timeout: float = 30.0) -> None:
    """Confirm the "Create New Strand-Based Hair" dialog
    (``DzStrandHairCreateNodeAction``). Confirmed live 2026-09-19: same
    dialog class/Accept auto_id as ``drive_geometry_shell_create``, only the
    title differs — see Bug-Katalog #6.
    """
    _drive_create_new_item_dialog(_STRAND_HAIR_DLG_TITLE, dialog_timeout)


def drive_wearable_preset_save(output_path: str, dialog_timeout: float = 30.0) -> dict:
    """Drive the two native dialogs behind "File > Save As > Wearable(s)
    Preset" to completion, once the DazScript side has already selected the
    target figure and triggered ``DzWearablesAssetFilterAction``.

    Must be called from a worker thread (all pywinauto/win32 calls here are
    blocking) — see ``daz_save_wearable_preset``'s ``asyncio.to_thread`` use.

    Bundles **every currently fitted/parented item on the selected figure**
    into the preset — this is the dialog's own default behavior (its node
    checklist has no confirmed UIA toggle mechanism; see module docstring's
    referenced bug entry) and was not overridden. Callers who only want a
    specific item bundled should ensure nothing else is fitted to the figure
    first.
    """
    _require_pywinauto()
    pid = find_daz_studio_pid()

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    save_hwnd = _find_window(
        pid, lambda title, cls: title == "Filtered Save" and cls == "#32770", dialog_timeout
    )
    _set_native_filename_field(save_hwnd, "1001", str(out))
    _click_native_dialog_button(save_hwnd, 1)  # "&Speichern" / Save

    options_hwnd = _find_window(
        pid, lambda title, _cls: title == "Wearable(s) Preset Save Options", dialog_timeout
    )
    _invoke_qt_button(options_hwnd, _WEARABLES_ACCEPT_BTN)
    _wait_until_closed(options_hwnd, dialog_timeout)

    # DAZ Studio finishes writing the file a moment after the dialog visually
    # closes — confirmed live: an immediate one-shot exists() check raced the
    # write and false-negatived on a file that appeared correctly a fraction
    # of a second later. Poll briefly instead of trusting dialog-closed as
    # "file fully written".
    write_deadline = time.monotonic() + min(dialog_timeout, 10.0)
    while not out.exists() and time.monotonic() < write_deadline:
        time.sleep(0.2)
    if not out.exists():
        raise ToolError(
            f"Save dialog sequence completed but the expected output file was not "
            f"found: {out}"
        )
    return {"success": True, "outputPath": str(out)}


# "Modifier Asset(s) Save Options" dialog (DzModifierAssetFilterAction),
# confirmed live 2026-10-02 (Bug-Katalog #37).
_MODIFIER_DLG = "App.MorphAssetFilterDlg"
_MODIFIER_DLG_TITLE = "Modifier Asset(s) Save Options"
_MODIFIER_ACCEPT_BTN = f"{_MODIFIER_DLG}.BasicDlgButtonGrpBox.BasicDlgAcceptDialogBtn"
_MODIFIER_CANCEL_BTN = f"{_MODIFIER_DLG}.BasicDlgButtonGrpBox.BasicDlgCancelDialogBtn"
_MODIFIER_EDIT_FMT = f"{_MODIFIER_DLG}.AssetFilterBaseDataFolderGrp.{{}}.ComboEditInputLEdit"
_MODIFIER_ASSET_DIR_EDIT = _MODIFIER_EDIT_FMT.format("AssetDirectoryCmbEdit")
_MODIFIER_VENDOR_EDIT = _MODIFIER_EDIT_FMT.format("AssetFilterVendorNameCmbEdit")
_MODIFIER_PRODUCT_EDIT = _MODIFIER_EDIT_FMT.format("AssetFilterProductNameCmbEdit")
# Shown *instead of* the options dialog (still modal, RunSilent or not) when
# the node itself was never saved as a Figure/Prop Asset.
_RESOURCE_ERROR_TITLE = "Resource Error"
_WARNING_BOX = "App.WarningMessageBox"


def _dismiss_resource_error(hwnd: int) -> str:
    app = Application(backend="uia").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    text = ""
    try:
        text = win.child_window(auto_id=f"{_WARNING_BOX}.qt_msgbox_label").window_text()
    except Exception:  # noqa: BLE001 - best effort, the dismiss below matters more
        pass
    win.child_window(auto_id=f"{_WARNING_BOX}.qt_msgbox_buttonbox.OkBtn").invoke()
    return text


def _set_qt_edit(win, auto_id: str, text: str) -> None:
    edit = win.child_window(auto_id=auto_id, control_type="Edit")
    edit.set_edit_text(text)
    actual = edit.get_value()
    if actual != text:
        raise ToolError(f"Failed to set dialog field {auto_id!r} (got {actual!r}, expected {text!r}).")


def _select_qt_combo_value(win, auto_id: str, text: str, max_steps: int = 20) -> None:
    """Pick ``text`` in a read-only Qt combo (the Asset Directory field).

    Confirmed live: its inner Edit rejects ``SetValue`` (COMError
    ``0x80131509``, invalid operation), so step through the entries with the
    arrow keys instead until the value matches.
    """
    edit = win.child_window(auto_id=auto_id, control_type="Edit")

    def same(value: str) -> bool:
        return Path(value).resolve() == Path(text).resolve()

    if same(edit.get_value()):
        return
    for key in ("{DOWN}", "{UP}"):
        win.set_focus()
        edit.set_focus()
        for _ in range(max_steps):
            send_keys(key)
            time.sleep(0.15)
            if same(edit.get_value()):
                return
    raise ToolError(f"Could not select {text!r} in the dialog's Asset Directory list.")


def _anchor_top_row(win, attempts: int = 3) -> None:
    """Give the property tree keyboard focus with its top row current.

    ``win.set_focus()`` alone can leave focus in a text field (confirmed
    live — Down/Space then toggled nothing), so click the top row's label
    (row center, not the checkbox) until it reports keyboard focus.
    """
    for _ in range(attempts):
        win.set_focus()
        top = win.descendants(control_type="TreeItem")[0]
        top.click_input()
        time.sleep(0.3)
        try:
            if top.has_keyboard_focus():
                return
        except Exception:  # noqa: BLE001 - focus not reported; result is verified later anyway
            return


def _tick_modifier_tree_items(win, wanted: list[set[str]]) -> list[str]:
    """Check exactly the leaf rows matching ``wanted`` in the dialog's
    property tree (``Node > property group > morph``, everything unchecked
    by default). Returns the row texts that were ticked.

    Confirmed live: UIA ``Expand()``/``Toggle()`` are silent no-ops on this
    custom Qt tree, a double-click does not expand it, and a second click on
    the expander arrow collapses it again. What works is keyboard input with
    the dialog focused: select the top row, ``*`` (numpad multiply = Qt
    "expand all descendants"), then ``Down`` to each target row and
    ``Space`` to toggle its checkbox. Pure keyboard navigation also works
    for rows scrolled out of view, which mouse clicks would not. The
    ``TreeItem`` toggle state *is* readable, so the result is verified.
    """
    items = win.descendants(control_type="TreeItem")
    if not items:
        raise ToolError("Modifier Asset(s) dialog shows no property tree rows for the selected node.")
    # The first click can be swallowed just activating the window (confirmed
    # live: flaky single attempt), so retry until the rows actually appear.
    for _ in range(3):
        _anchor_top_row(win)
        send_keys("{VK_MULTIPLY}")
        time.sleep(0.8)
        items = win.descendants(control_type="TreeItem")
        if len(items) > 1:
            break
    leaves = [i for i, it in enumerate(items) if not it.children(control_type="TreeItem")]
    texts = [it.window_text() for it in items]
    targets: list[int] = []
    for names in wanted:
        hit = next((i for i in leaves if texts[i] in names), None)
        if hit is None:
            raise ToolError(
                f"Morph {sorted(names)} not listed in the Modifier Asset(s) dialog. "
                f"Rows shown: {texts}"
            )
        targets.append(hit)

    # Re-anchor right before navigating so Down counts from the top row.
    _anchor_top_row(win)
    current = 0
    for idx in sorted(set(targets)):
        send_keys("{DOWN}" * (idx - current))
        send_keys("{SPACE}")
        current = idx
        time.sleep(0.15)
    time.sleep(0.4)

    wrong = []
    for i in leaves:
        state = items[i].iface_toggle.CurrentToggleState
        if (state == 1) != (i in targets):
            wrong.append(f"{texts[i]}={state}")
    if wrong:
        raise ToolError(f"Checkbox state in the Modifier Asset(s) dialog did not end up as requested: {wrong}")
    return [texts[i] for i in sorted(set(targets))]


def drive_modifier_asset_save(
    morphs: list[dict],
    vendor_name: str,
    product_name: str,
    base_data_path: str | None,
    dialog_timeout: float = 30.0,
) -> dict:
    """Fill in and accept the "Modifier Asset(s) Save Options" dialog once
    the DazScript side has selected the node and triggered
    ``DzModifierAssetFilterAction`` (Bug-Katalog #37).

    ``morphs`` are ``{"name", "label"}`` dicts from the preflight script; a
    tree row matches either. Unlike the other dialogs in this module this
    one needs keyboard focus (see ``_tick_modifier_tree_items``), so DAZ
    Studio is briefly brought to the foreground. Any failure after the
    dialog appeared cancels it rather than leaving a modal dialog open
    (crash risk, Bug-Katalog #6).

    Must be called from a worker thread — see ``daz_save_modifier_asset``.
    """
    _require_pywinauto()
    pid = find_daz_studio_pid()
    hwnd = _find_window(
        pid,
        lambda title, _cls: title in (_MODIFIER_DLG_TITLE, _RESOURCE_ERROR_TITLE),
        dialog_timeout,
    )
    if win32gui.GetWindowText(hwnd) == _RESOURCE_ERROR_TITLE:
        text = _dismiss_resource_error(hwnd)
        raise ToolError(
            f"DAZ Studio refused to save Modifier Asset(s): {text or 'Resource Error'} "
            "Save the node as a Figure/Prop Asset first (daz_save_prop_asset), or load it "
            "from the content library, so it is backed by an asset."
        )

    app = Application(backend="uia").connect(handle=hwnd)
    win = app.window(handle=hwnd)
    try:
        # Order matters (confirmed live): ticking rows via keyboard does not
        # re-evaluate the Accept button's enabled state, but editing a text
        # field does — so tick first, then fill in the fields.
        ticked = _tick_modifier_tree_items(
            win.wrapper_object(), [{m["name"], m["label"]} for m in morphs]
        )
        if base_data_path is not None:
            _select_qt_combo_value(win, _MODIFIER_ASSET_DIR_EDIT, base_data_path)
        _set_qt_edit(win, _MODIFIER_VENDOR_EDIT, vendor_name)
        _set_qt_edit(win, _MODIFIER_PRODUCT_EDIT, product_name)
        used_dir = win.child_window(auto_id=_MODIFIER_ASSET_DIR_EDIT, control_type="Edit").get_value()
        accept = win.child_window(auto_id=_MODIFIER_ACCEPT_BTN, control_type="Button")
        deadline = time.monotonic() + 3.0
        while not accept.is_enabled() and time.monotonic() < deadline:
            time.sleep(0.2)
        if not accept.is_enabled():
            raise ToolError("Accept stayed disabled in the Modifier Asset(s) dialog after ticking the morphs.")
    except Exception:
        _invoke_qt_button(hwnd, _MODIFIER_CANCEL_BTN)
        raise
    _invoke_qt_button(hwnd, _MODIFIER_ACCEPT_BTN)
    _wait_until_closed(hwnd, dialog_timeout)
    return {"baseDataPath": used_dir, "ticked": ticked}
