"""
Copyright (c) 2013-present Matic Kukovec.
Released under the GNU GPL3 license.

For more information check the 'LICENSE.txt' file.
For complete license information of the dependencies, check the 'additional_licenses' directory.

Code-formatting and analysis tools.

Wraps formatters (black, autopep8, clang-format, zig, nim) and
linters (ruff, pyflakes). Also manages the file-system path watcher.
Namespace class attached to the MainWindow instance.
"""

import os
from typing import Any, Iterator, Optional

import qt
import constants
import data
import functions
import settings
from components.pathwatcher import FileEvent, PathWatcher


class Tools:
    """
    Helper functions for everything
    """

    # Class variables
    _parent: Any
    path_watcher: PathWatcher

    def __init__(self, parent: Any) -> None:
        """
        Initialization of the Tools object instance
        """
        # Get the reference to the MainWindow parent object instance
        self._parent = parent

        # Debounce timers: normalized path → single-shot QTimer
        self._reload_timers: dict[str, qt.QTimer] = {}

        # Initialize the file-system watcher
        self.path_watcher = PathWatcher()
        self.path_watcher.file_changed.connect(self.__file_change_handler)
        signal_dispatcher: Any = data.signal_dispatcher
        signal_dispatcher.editor_initialized.connect(self.pathwatcher_add)
        signal_dispatcher.editor_file_saved_as.connect(self.pathwatcher_add)
        signal_dispatcher.editor_deleted.connect(self.pathwatcher_remove)

        # Periodic mtime re-check as a safety net for file-system events the
        # watcher missed (it only watches the open file's parent directory).
        self._mtime_poll_timer = qt.QTimer(self._parent)
        self._mtime_poll_timer.setInterval(settings.get("file-watch-mtime-poll-ms"))
        self._mtime_poll_timer.timeout.connect(self._poll_editor_mtimes)
        self._mtime_poll_timer.start()

    def _iter_tabs(self) -> Iterator[Any]:
        """Yield every tab widget across all tab widgets in the main window."""
        for tab_widget in self._parent.get_all_windows():
            for i in range(tab_widget.count()):
                yield tab_widget.widget(i)

    def _tab_path(self, tab: Any) -> Optional[str]:
        """Return the normalized save path of a tab, or None if it has none."""
        save_path = getattr(tab, "save_path", None)
        if not save_path:
            return None
        return functions.normalize_path(save_path)

    def _reload_tab(self, tab: Any) -> None:
        """Reload a tab from its file on disk by whatever API it exposes."""
        if hasattr(tab, "reload_file"):
            tab.reload_file()
        elif hasattr(tab, "reload_from_disk"):
            tab.reload_from_disk()

    def _schedule_reload(self, path: str) -> None:
        normalized = functions.normalize_path(path)
        timer = self._reload_timers.get(normalized)
        if timer is not None:
            timer.stop()
        else:
            timer = qt.QTimer(self._parent)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda p=normalized: self._do_reload(p))
            self._reload_timers[normalized] = timer
        timer.start(200)

    def _do_reload(self, normalized_path: str) -> None:
        self._reload_timers.pop(normalized_path, None)
        for tab in self._iter_tabs():
            try:
                if self._tab_path(tab) == normalized_path:
                    self._reload_tab(tab)
            except Exception:
                pass

    def _poll_editor_mtimes(self) -> None:
        """Periodically fall back on mtime comparison for missed events."""
        for tab in self._iter_tabs():
            try:
                save_path: Optional[str] = getattr(tab, "save_path", None)
                modification_time = getattr(tab, "modification_time", None)
                if not save_path or modification_time is None:
                    continue
                current_mtime = os.path.getmtime(save_path)
                if current_mtime > modification_time:
                    self._schedule_reload(save_path)
            except (OSError, ValueError):
                continue

    def __file_change_handler(
        self,
        event_type: FileEvent,
        source: str,
        destination: Optional[str],
        modification_time: Optional[float],
    ) -> None:
        """Handle all file events with consistent signature."""

        match event_type:
            case FileEvent.CREATED:
                self._schedule_reload(source)

            case FileEvent.MODIFIED:
                self._schedule_reload(source)

            case FileEvent.DELETED:
                # Intentionally a no-op. See pathwatcher.py:__handle_change for
                # the rationale — the file stays in monitoring so CREATED events
                # from atomic-write tools trigger reload.
                #
                # Previously this loop found the matching editor and called
                # _signal_text_changed(e) which set save_status=MODIFIED and
                # added "*" to the tab name. This was wrong because:
                #
                # 1. External formatters use atomic-write (delete + create).
                #    The DELETED is transient — the file is re-created in
                #    milliseconds. The "*" was a false positive.
                #
                # 2. Setting save_status=MODIFIED here caused reload_file() to
                #    prompt "File modified, reload anyway?" when the subsequent
                #    CREATED handler tried to reload. The prompt was spurious
                #    since the user never touched the editor.
                #
                # True deletions (not followed by CREATED) are surfaced when
                # the user attempts to save — the OS returns a file-not-found
                # error, which is clearer than a silent "*" marker.
                pass

            case FileEvent.MOVED:
                source_norm = functions.normalize_path(source)
                destination_norm = (
                    functions.normalize_path(destination) if destination else None
                )
                followed = False
                for tab in self._iter_tabs():
                    try:
                        tab_save = self._tab_path(tab)
                        if tab_save is None:
                            continue
                        if (
                            destination_norm is not None
                            and tab_save == source_norm
                            and destination_norm != source_norm
                        ):
                            # The open file itself was moved; follow it so the
                            # tab keeps editing the relocated file.
                            if not followed:
                                self.path_watcher.update_file_path(
                                    source_norm, destination_norm
                                )
                                followed = True
                            new_path = functions.unixify_path(destination)
                            tab.save_path = new_path
                            tab.name = os.path.basename(new_path)
                            tab_widget = tab.parent()
                            if tab_widget is not None and hasattr(
                                tab_widget, "setTabText"
                            ):
                                index = tab_widget.indexOf(tab)
                                if index != -1:
                                    tab_widget.setTabText(index, tab.name)
                            self._reload_tab(tab)
                        elif tab_save == source_norm or tab_save == destination_norm:
                            # Another file was moved onto one of our open files.
                            self._reload_tab(tab)
                    except Exception:
                        pass

            case _:
                raise Exception(f"Unknown FileEvent: {event_type}")

    def pathwatcher_add(self, path: str) -> bool:
        return self.path_watcher.add_file(path)

    def pathwatcher_remove(self, path: str) -> bool:
        normalized = functions.normalize_path(path)
        timer = self._reload_timers.pop(normalized, None)
        if timer is not None:
            timer.stop()
        return self.path_watcher.remove_file(path)

    def pretty_print_text(self, _type: constants.FormatterType, **kwargs: Any) -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "text"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return

        if _type == constants.FormatterType.JSON:
            prettyfied_string = components.codequality.pretty_print_json(
                tab.text(), **kwargs
            )
        elif _type == constants.FormatterType.XML:
            prettyfied_string = components.codequality.pretty_print_xml(
                tab.text(), **kwargs
            )
        elif _type == constants.FormatterType.HTML_Python_Standard_Library:
            prettyfied_string = components.codequality.pretty_print_html_python_stdlib(
                tab.text()
            )
        elif _type == constants.FormatterType.HTML_BeautifulSoup:
            prettyfied_string = (
                components.codequality.custom_format_html_document_beautifulsoup(
                    tab.text(), **kwargs
                )
            )
        else:
            self._parent.display.repl_display_error(
                f"Unknown pretty_print type: '{_type}'"
            )
            return

        tab.set_all_text(prettyfied_string)

    def format_python_all_text(self, library: str) -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "text"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return

        first_line: int = tab.firstVisibleLine()
        cursor_line: int
        cursor_index: int
        cursor_line, cursor_index = tab.getCursorPosition()
        code: str = tab.text()

        formatted_code: str = components.codequality.format_python_code(code, library)

        tab.set_all_text(formatted_code)

        tab.setCursorPosition(cursor_line, cursor_index)
        tab.setFirstVisibleLine(first_line)

    def format_python_selected_text(self, library: str) -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "selectedText") or not hasattr(tab, "hasSelectedText"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return
        elif not tab.hasSelectedText():
            self._parent.display.repl_display_error("No text selected in the editor!)")
            return

        code: str = tab.selectedText()

        formatted_code: str = components.codequality.format_python_code(code, library)

        tab.replaceSelectedText(formatted_code)

    def format_c_cpp_all_text(self, library: str, style: str = "LLVM") -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "text"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return

        first_line: int = tab.firstVisibleLine()
        cursor_line: int
        cursor_index: int
        cursor_line, cursor_index = tab.getCursorPosition()
        code: str = tab.text()

        if library == "clang-format":
            formatted_code: str = components.codequality.format_clangformat_c_cpp(
                source_code=code, style=style
            )

        else:
            raise Exception(
                f"[C/C++-FORMATTING] Unknown foramtter library selected: '{library}'"
            )

        tab.set_all_text(formatted_code)

        tab.setCursorPosition(cursor_line, cursor_index)
        tab.setFirstVisibleLine(first_line)

    def format_zig_all_text(
        self,
    ) -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "text"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return

        first_line: int = tab.firstVisibleLine()
        cursor_line: int
        cursor_index: int
        cursor_line, cursor_index = tab.getCursorPosition()
        code: str = tab.text()

        formatted_code: str = components.codequality.format_zig_code(
            zig_code_string=code
        )

        tab.set_all_text(formatted_code)

        tab.setCursorPosition(cursor_line, cursor_index)
        tab.setFirstVisibleLine(first_line)

    def format_nim_file(
        self,
    ) -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "save_path"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return

        first_line: int = tab.firstVisibleLine()
        cursor_line: int
        cursor_index: int
        cursor_line, cursor_index = tab.getCursorPosition()
        nim_file_path: str = tab.save_path

        components.codequality.format_nim_file(file_path=nim_file_path)

        tab.setCursorPosition(cursor_line, cursor_index)
        tab.setFirstVisibleLine(first_line)

    def analyze_python_file(self, library: str) -> None:
        import components.codequality

        tab = self._parent.get_tab_by_indication()

        if not hasattr(tab, "save_path"):
            self._parent.display.repl_display_error(
                f"Indicated tab is not an editor! ('{tab.__class__.__name__}')"
            )
            return

        file_path: str = tab.save_path

        exit_code: int
        if library == "ruff":
            analysis_results_or_error: str
            exit_code, analysis_results_or_error = (
                components.codequality.analyze_ruff_file(file_path)
            )
            if exit_code != 0:
                self._parent.display.repl_display_message("Ruff results:")
                self._parent.display.repl_display_message(analysis_results_or_error)
            else:
                self._parent.display.repl_display_success("Ruff says everything is ok.")

        elif library == "pyflakes":
            stdout: str
            stderr: str
            exit_code, stdout, stderr = components.codequality.analyze_pyflakes_file(
                file_path
            )
            if exit_code != 0:
                self._parent.display.repl_display_message("Pyflakes results:")
                self._parent.display.repl_display_message(stdout)
            else:
                self._parent.display.repl_display_success(
                    "Pyflakes says everything is ok."
                )

        else:
            raise Exception(
                f"[PYTHON-ANALYZING] Unknown analyzer library selected: '{library}'"
            )
