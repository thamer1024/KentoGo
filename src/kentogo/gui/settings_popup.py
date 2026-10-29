"""The settings screens, made to look like KaTrain's settings popups.

As in KaTrain, the settings are split into screens that are opened from the
menu (see settings_form.PAGES):

- 一般・エンジン設定: like KaTrain's "General & Engine settings": "KataGo設定"
  with a "ローカルエンジン" tab and the paths of KataGo's files at the top,
  then "一般設定" and "エンジン設定" side by side. Path inputs say
  "ファイルがありません" when the file does not exist, as in KaTrain.
- 推奨設定: a button for each kind of computer, which replaces the numbers of visits
  with the recommended ones (see katago.presets) after asking, and saves them at once.
  The last row has a button that measures KataGo's speed on this computer, and then
  asks to use the preset that fits it.
- 出題・判定設定: like KaTrain's "Teaching/Analysis settings": how problems are
  chosen and asked, and how answers are judged.
- AI解説設定: which AI and model the AI commentary uses (the values are used as they are
  written, so any model that the AI publishes can be used), the environment variable of the
  API key, and a button that opens the user's prompt file.
- 復習設定: reviews, the order of new problems and reviews, the limit, and two
  buttons that set aside all current problems or bring all problems back
  (they ask first, write to the history at once, and are used when the quiz is started next).

Each screen has the "設定を更新" button at the bottom. The inputs are listed in
settings_form.FIELDS, which also turns their texts into settings. Wrong inputs
are not saved: they are colored, and the message at the bottom tells which ones
are wrong. Saved settings are used at once: a practice that is open keeps its
settings, and the new ones are used when a practice is opened next. A change that
makes the next quiz read all SGF files again (the games folder or the conditions
for choosing problems) is saved only after the user says yes.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from kivy.metrics import dp, sp
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from kentogo.app_settings import AppSettings
from kentogo.gui import texts, theme
from kentogo.gui.check_box import MaterialCheckBox
from kentogo.gui.dialogs import bind_dialog_keys, confirm, show_message
from kentogo.gui.settings_form import (
    FIELDS,
    GROUP_COMMENTARY,
    GROUP_ENGINE,
    GROUP_GENERAL,
    GROUP_JUDGE,
    GROUP_KATAGO,
    GROUP_QUIZ,
    GROUP_REVIEW,
    GROUP_SEICHI,
    KIND_BOOL,
    KIND_CHOICE,
    KIND_FILE,
    KIND_FLOAT,
    KIND_FOLDER,
    KIND_INT,
    PAGE_COMMENTARY,
    PAGE_GENERAL,
    PAGE_PRESETS,
    PAGE_QUIZ,
    PAGE_REVIEW,
    PAGE_SEICHI,
    FieldSpec,
    FormError,
    count_games,
    form_values,
    needs_rereading,
    path_exists,
    settings_from_form,
    values_from_katrain,
)
from kentogo.gui.widgets import fitting_label, flat_button, in_main_thread, set_background, wrapping_label
from kentogo.katago.locate import KataGoNotFoundError, katrain_package
from kentogo.katago.presets import PRESETS, Preset, apply_preset
from kentogo.katago.speed import MeasuredSpeed
from kentogo.quiz.quiz_settings import QuizSettings

# The part of the window that each page uses (width, height).
PAGE_SIZES = {
    PAGE_GENERAL: (0.92, 0.95),
    PAGE_PRESETS: (0.8, 0.85),
    PAGE_QUIZ: (0.85, 0.85),
    PAGE_REVIEW: (0.7, 0.7),
    PAGE_SEICHI: (0.7, 0.7),
    PAGE_COMMENTARY: (0.85, 0.9),
}

# Sizes, close to KaTrain's.
ROW_HEIGHT = 34  # dp. One row of a settings box.
INPUT_HEIGHT = 32  # dp
HEADER_FONT_SIZE = 22  # sp. "KataGo設定", "出題設定" and so on.
SPACING = 8  # dp
PRESET_ROW_HEIGHT = 48  # dp. The lowest row of the recommended settings (a kind of computer has three lines).

# Colors of the inputs. The text is light on a dark input, as in KaTrain.
INPUT_COLOR = (0.12, 0.16, 0.21, 1)
WRONG_INPUT_COLOR = (0.45, 0.16, 0.16, 1)  # An input whose value cannot be used.
MISSING_PATH_COLOR = (1.0, 0.54, 0.5, 1)  # The text "ファイルがありません", and a missing folder.


class SettingsPopup(Popup):
    """The settings screen.

    Attributes:
        settings: The settings shown when the screen was opened (or saved last).
        inputs: A dict from the key of each input (see settings_form.FIELDS) to its widget.
    """

    def __init__(
        self,
        settings: AppSettings,
        save: Callable[[AppSettings], None],
        exclude_all: Callable[[QuizSettings], int] | None = None,
        include_all: Callable[[], None] | None = None,
        page: str = PAGE_GENERAL,
        edit_prompt: Callable[[], Path] | None = None,
        measure: Callable[[], MeasuredSpeed] | None = None,
        **kwargs,
    ):
        """Make the screen with the current settings. Call open() to show it.

        Args:
            settings: The current settings.
            save: A function that writes new settings to the settings file.
                It may raise OSError or ValueError, which are shown on the screen.
            exclude_all: Sets aside all current problems of the saved settings, and returns how many.
                It runs in a background thread. If None, there is no button for it.
            include_all: Starts all problems again. It runs in a background thread.
                If None, there is no button for it.
            page: Which settings to show, one of settings_form.PAGES.
            edit_prompt: Makes the user's prompt file of the AI commentary if needed, opens it,
                and returns its path. It may raise OSError. If None, there is no button for it.
            measure: Measures KataGo's speed on this computer, for each model; it runs in a
                background thread and may raise any error. If None, there is no button for it.
            **kwargs: Other arguments of Kivy's Popup.
        """
        super().__init__(
            title=texts.text(f"page_{page}"),
            title_size=sp(18),
            size_hint=PAGE_SIZES[page],
            background="",
            background_color=theme.BACKGROUND_COLOR,
            separator_color=theme.BUTTON_COLOR,
            **kwargs,
        )
        self.settings = settings
        self._save = save
        self._exclude_all = exclude_all
        self._include_all = include_all
        self._edit_prompt = edit_prompt
        self._measure = measure
        self.inputs: dict[str, object] = {}
        self._measuring = False  # True while KataGo's speed is measured.
        self._missing_labels: dict[str, Label] = {}
        self.content = self._build(page)
        self.set_values(form_values(settings))
        # Only Esc (close): Return is used while writing in the inputs, so it does not save.
        bind_dialog_keys(self, None, self.dismiss)

    def _build(self, page: str) -> BoxLayout:
        """Make the widgets: the settings of the page in a scroll view, and the buttons at the bottom."""
        body = GridLayout(cols=1, spacing=dp(SPACING), padding=dp(SPACING), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        if page == PAGE_GENERAL:
            self._add_general_page(body)
        elif page == PAGE_QUIZ:
            body.add_widget(_two_columns(_header(texts.text("quiz_settings")), _header(texts.text("judge_settings"))))
            body.add_widget(_two_columns(self._settings_box(GROUP_QUIZ), self._settings_box(GROUP_JUDGE)))
        elif page == PAGE_COMMENTARY:
            self._add_commentary_page(body)
        elif page == PAGE_PRESETS:
            self._add_presets_page(body)
        elif page == PAGE_SEICHI:
            body.add_widget(_header(texts.text("seichi_settings"), halign="left"))
            body.add_widget(self._settings_box(GROUP_SEICHI))
        else:
            body.add_widget(_header(texts.text("review_settings"), halign="left"))
            body.add_widget(self._settings_box(GROUP_REVIEW))
            if self._exclude_all is not None and self._include_all is not None:
                body.add_widget(self._review_actions())
        scroll = ScrollView()
        scroll.add_widget(body)

        self.message_label = wrapping_label(text="", valign="middle")
        bottom = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(SPACING), padding=(dp(SPACING), dp(4)))
        bottom.add_widget(self.message_label)
        if page != PAGE_PRESETS:  # A preset is saved by its own button.
            bottom.add_widget(flat_button(texts.text("update_settings"), self.update_settings, size_hint_x=0.25))
        bottom.add_widget(flat_button(texts.text("close"), self.dismiss, size_hint_x=0.15))
        content = BoxLayout(orientation="vertical")
        content.add_widget(scroll)
        content.add_widget(bottom)
        return content

    def _add_general_page(self, body: GridLayout) -> None:
        """Add the widgets of the general and engine page, laid out as in KaTrain."""
        body.add_widget(_header(texts.text("katago_settings"), halign="left"))
        body.add_widget(self._tab_row())
        for spec in _fields(GROUP_KATAGO):
            body.add_widget(self._path_box(spec))
        body.add_widget(_two_columns(_header(texts.text("general_settings")), _header(texts.text("engine_settings"))))
        body.add_widget(_two_columns(self._settings_box(GROUP_GENERAL), self._settings_box(GROUP_ENGINE)))

    def _add_commentary_page(self, body: GridLayout) -> None:
        """Add the widgets of the AI commentary page: the settings, examples of values, and the prompt file."""
        body.add_widget(_header(texts.text("commentary_settings"), halign="left"))
        body.add_widget(self._settings_box(GROUP_COMMENTARY))
        hint = fitting_label(dp(120))
        hint.text = texts.text("commentary_settings_hint")
        body.add_widget(hint)
        if self._edit_prompt is not None:
            body.add_widget(
                flat_button(texts.text("commentary_edit_prompt"), self.edit_prompt, size_hint_y=None, height=dp(40))
            )

    def _add_presets_page(self, body: GridLayout) -> None:
        """Add the widgets of the recommended settings: an explanation, then a row for each kind of computer."""
        body.add_widget(_header(texts.text("page_presets"), halign="left"))
        hint = fitting_label(dp(60))
        hint.text = texts.text("presets_hint")
        body.add_widget(hint)
        for preset in PRESETS:
            body.add_widget(_choice_row(_preset_text(preset), texts.text("preset_apply"), self._asker(preset)))
        if self._measure is not None:
            measure = f"[b]{texts.text('preset_measure')}[/b]\n{texts.text('preset_measure_note')}"
            body.add_widget(_choice_row(measure, texts.text("preset_measure_button"), self.measure_speed))

    def _asker(self, preset: Preset) -> Callable[[], None]:
        """Return what the button of a preset does: ask before using it."""
        return lambda: self.ask_preset(preset)

    def measure_speed(self) -> None:
        """Measure KataGo's speed in the background, then ask to use the numbers of visits made from it."""
        if self._measuring:
            return  # The button was pressed again while measuring.
        self._measuring = True
        self.message_label.text = texts.text("preset_measuring")

        def work() -> None:
            """Run in the background thread. Errors are shown on the screen."""
            try:
                speed = self._measure()
            except Exception as error:  # KataGo cannot be started, or it does not answer well.
                in_main_thread(self._measure_failed)(str(error) or type(error).__name__)
                return
            in_main_thread(self._measured)(speed)

        threading.Thread(target=work, daemon=True).start()

    def _measured(self, speed: MeasuredSpeed) -> None:
        """Tell the speeds, and ask to use the numbers of visits made from them."""
        self._measuring = False
        self.message_label.text = ""
        preset = speed.preset(self.settings.engine)
        confirm(_measured_text(speed, preset), lambda: self._use_preset(preset), self._cancelled)

    def _measure_failed(self, reason: str) -> None:
        """Tell why the speed could not be measured."""
        self._measuring = False
        self._show_error(texts.text("preset_measure_failed", reason=reason))

    def ask_preset(self, preset: Preset) -> None:
        """Ask before replacing the numbers of visits with those of a preset."""
        confirm(texts.text("preset_question"), lambda: self._use_preset(preset), self._cancelled)

    def _use_preset(self, preset: Preset) -> None:
        """Save the settings with the numbers of visits of a preset (the saved settings, not the inputs, are changed)."""
        self._write(replace(self.settings, engine=apply_preset(self.settings.engine, preset)))

    def edit_prompt(self) -> None:
        """Open the user's prompt file of the AI commentary (it is made from the default the first time)."""
        try:
            path = self._edit_prompt()
        except OSError as error:
            self._show_error(texts.text("commentary_prompt_open_failed", reason=error))
            return
        self.message_label.text = texts.text("commentary_prompt_opened", path=path)

    def _tab_row(self) -> BoxLayout:
        """Make the row of engine tabs. KentoGo has only KaTrain's "local engine" tab."""
        row = BoxLayout(size_hint_y=None, height=dp(40), padding=(dp(SPACING), 0))
        tab = flat_button(texts.text("local_engine"), lambda: None, size_hint_x=0.22)
        tab.background_color = theme.BOX_BACKGROUND_COLOR
        row.add_widget(tab)
        row.add_widget(Label())
        return row

    def _path_box(self, spec: FieldSpec) -> GridLayout:
        """Make the box of one file: the name on the left, and the path input on the right.

        The box of KaTrain's config.json also has the "KaTrainから読み込む" button under
        the name (KaTrain has its download buttons at this place), which reads that file.
        """
        box = GridLayout(cols=2, padding=dp(SPACING) / 2, spacing=dp(4), size_hint_y=None, height=dp(76))
        set_background(box, theme.BOX_BACKGROUND_COLOR)
        left = BoxLayout(orientation="vertical", size_hint_x=0.33, spacing=dp(4))
        left.add_widget(_field_label(spec, halign="center"))
        if spec.key == "katrain_config":
            button = flat_button(texts.text("read_katrain"), self.read_katrain, size_hint=(None, None))
            button.size = (dp(180), dp(30))
            anchor = AnchorLayout(size_hint_y=None, height=dp(32))
            anchor.add_widget(button)
            left.add_widget(anchor)
        right = BoxLayout(orientation="vertical", spacing=dp(2))
        right.add_widget(self._make_input(spec))
        missing = Label(color=MISSING_PATH_COLOR, font_size=sp(13), halign="left", size_hint_y=None, height=dp(18))
        missing.bind(size=lambda widget, size: setattr(widget, "text_size", size))
        self._missing_labels[spec.id] = missing
        right.add_widget(missing)
        right.add_widget(Label())  # Keeps the input at the top.
        box.add_widget(left)
        box.add_widget(right)
        return box

    def _settings_box(self, group: str) -> GridLayout:
        """Make a box with one row for each setting of a group: the name on the left, the input on the right."""
        box = GridLayout(cols=2, padding=dp(SPACING), spacing=dp(4), size_hint_y=None)
        box.row_default_height = dp(ROW_HEIGHT)
        box.row_force_default = True
        box.bind(minimum_height=box.setter("height"))
        set_background(box, theme.BOX_BACKGROUND_COLOR)
        for spec in _fields(group):
            label = _field_label(spec, halign="left")
            label.size_hint_x = 1.5
            box.add_widget(label)
            anchor = AnchorLayout(anchor_x="left")
            anchor.add_widget(self._make_input(spec))
            box.add_widget(anchor)
        return box

    def _make_input(self, spec: FieldSpec):
        """Make the input widget for one setting, and remember it in self.inputs."""
        if spec.kind == KIND_BOOL:
            widget = MaterialCheckBox(size_hint=(None, None), size=(dp(INPUT_HEIGHT), dp(INPUT_HEIGHT)))
        elif spec.kind == KIND_CHOICE:
            labels = [texts.text(f"{spec.id}_{choice}") for choice in spec.choices]
            widget = Spinner(values=labels, size_hint_y=None, height=dp(INPUT_HEIGHT), background_normal="")
            widget.background_color = theme.BUTTON_COLOR
        else:
            widget = TextInput(
                multiline=False,
                write_tab=False,
                size_hint_y=None,
                height=dp(INPUT_HEIGHT),
                padding=(dp(6), dp(6)),
                background_normal="",
                background_active="",
                background_color=INPUT_COLOR,
                foreground_color=theme.TEXT_COLOR,
                cursor_color=theme.TEXT_COLOR,
            )
            if spec.kind in (KIND_INT, KIND_FLOAT):
                widget.size_hint_x = 0.5
            if spec.kind in (KIND_FILE, KIND_FOLDER):
                widget.bind(text=lambda _widget, _text, spec=spec: self._check_path(spec))
        self.inputs[spec.id] = widget
        return widget

    def values(self) -> dict[str, str | bool]:
        """Return the values of all settings, in the form that settings_form.settings_from_form takes.

        Settings that are not on this page keep the values that were saved.
        """
        values = form_values(self.settings)
        for spec in FIELDS:
            widget = self.inputs.get(spec.id)
            if widget is None:
                continue
            if spec.kind == KIND_BOOL:
                values[spec.id] = widget.active
            elif spec.kind == KIND_CHOICE:
                index = widget.values.index(widget.text) if widget.text in widget.values else 0
                values[spec.id] = spec.choices[index]
            else:
                values[spec.id] = widget.text
        return values

    def set_values(self, values: dict[str, str | bool]) -> None:
        """Put values into the inputs of this page. Keys that are not given keep their values."""
        for spec in FIELDS:
            widget = self.inputs.get(spec.id)
            if widget is None or spec.id not in values:
                continue
            if spec.kind == KIND_BOOL:
                widget.active = bool(values[spec.id])
            elif spec.kind == KIND_CHOICE:
                widget.text = widget.values[spec.choices.index(values[spec.id])]
            else:
                widget.text = str(values[spec.id])
        self._mark_wrong(set())

    def update_settings(self) -> None:
        """Save the values of the inputs. If some are wrong, nothing is saved, and they are shown.

        If the change makes the next start read all SGF files again, the user is
        asked first, and the settings are saved only when the user says yes.
        """
        try:
            settings = settings_from_form(self.values(), self.settings)
        except FormError as error:
            self._mark_wrong(set(error.errors))
            labels = texts.list_text([_label_text(key) for key in error.errors if key]) or str(error)
            self.message_label.text = texts.text("settings_invalid", labels=labels)
            return
        self._mark_wrong(set())
        if needs_rereading(self.settings.quiz, settings.quiz):
            question = texts.text("reread_question", count=count_games(settings.quiz.games_folder))
            confirm(question, on_yes=lambda: self._write(settings), on_no=self._cancelled)
        else:
            self._write(settings)

    def _write(self, settings: AppSettings) -> None:
        """Save the settings (they are used at once, so nothing is said), or show why they could not be saved."""
        try:
            self._save(settings)
        except (OSError, ValueError) as error:
            self._show_error(texts.text("settings_save_failed", reason=error))
            return
        self.settings = settings  # Saving again without changes does not ask again.
        self.message_label.text = ""

    def _review_actions(self) -> BoxLayout:
        """Make the two buttons that set aside all problems, or bring all problems back."""
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(SPACING))
        row.add_widget(flat_button(texts.text("exclude_all"), self.exclude_all))
        row.add_widget(flat_button(texts.text("include_all"), self.include_all))
        return row

    def exclude_all(self) -> None:
        """After asking, set aside all current problems (of the saved settings) in the history."""

        def run() -> str:
            """Set them aside, and return the message that tells how many."""
            return texts.text("excluded_done", count=self._exclude_all(self.settings.quiz))

        question = texts.text("exclude_question")
        confirm(question, lambda: self._run_in_background(run), self._cancelled, texts.text("yes_run"))

    def include_all(self) -> None:
        """After asking, start all problems again in the history."""

        def run() -> str:
            """Bring all problems back, and return the message."""
            self._include_all()
            return texts.text("included_done")

        question = texts.text("include_question")
        confirm(question, lambda: self._run_in_background(run), self._cancelled, texts.text("yes_run"))

    def _run_in_background(self, action: Callable[[], str]) -> None:
        """Run an action that may take long in a background thread, and show its message when it is done.

        Reading many games can take long, so the screen must not stop while it runs.
        """
        self.message_label.text = texts.text("working")
        show = in_main_thread(lambda message: setattr(self.message_label, "text", message))

        def work() -> None:
            """Run in the background thread. Errors are shown on the screen."""
            try:
                show(action())
            except Exception as error:  # The settings screen must stay usable.
                in_main_thread(self._show_error)(texts.text("action_failed", reason=error))

        threading.Thread(target=work, daemon=True).start()

    def _show_error(self, message: str) -> None:
        """Show an error under the inputs, and in a dialog where it can be copied (and on the console)."""
        self.message_label.text = message
        show_message(texts.text("error_title"), message)

    def _cancelled(self) -> None:
        """Tell that the settings were not saved, because the user said no."""
        self.message_label.text = texts.text("settings_cancelled")

    def read_katrain(self) -> None:
        """Copy the engine settings from KaTrain's config.json into the inputs (they are not saved yet).

        The config.json named in its input is read, even if that input is not saved yet.
        """
        engine = self.settings.engine
        katrain_config = self.inputs["katrain_config"].text.strip() or engine.katrain_config
        try:
            values = values_from_katrain(replace(self.settings, engine=replace(engine, katrain_config=katrain_config)))
        except (KataGoNotFoundError, ValueError) as error:
            self._show_error(texts.text("katrain_read_failed", reason=error))
            return
        self.set_values(values)
        self.message_label.text = texts.text("katrain_read")

    def _check_path(self, spec: FieldSpec) -> None:
        """Show that a path input names nothing: KataGo's files get "ファイルがありません" under the input,
        and the games folder gets a red text."""
        text = self.inputs[spec.id].text
        # Paths inside the KaTrain program ("katrain/...") are looked for in KaTrain's folder.
        folder = self.inputs.get("katrain_folder")
        inside_katrain = folder is not None and text.strip().startswith("katrain")
        exists = path_exists(text, spec.kind, katrain_package(folder.text) if inside_katrain else None)
        if spec.id in self._missing_labels:
            self._missing_labels[spec.id].text = "" if exists else texts.text("file_not_found")
        else:
            self.inputs[spec.id].foreground_color = theme.TEXT_COLOR if exists else MISSING_PATH_COLOR
        if spec.key == "katrain_folder":
            # KataGo's files may be inside the new folder.
            for other in FIELDS:
                if other.kind == KIND_FILE and other.id in self.inputs:
                    self._check_path(other)

    def _mark_wrong(self, keys: set[str]) -> None:
        """Color the text inputs whose keys are given, and give the others their usual color."""
        for key, widget in self.inputs.items():
            if isinstance(widget, TextInput):
                widget.background_color = WRONG_INPUT_COLOR if key in keys else INPUT_COLOR


def _fields(group: str) -> list[FieldSpec]:
    """Return the settings of one group, in the order of FIELDS."""
    return [spec for spec in FIELDS if spec.group == group]


def _choice_row(text: str, button_text: str, action: Callable[[], None]) -> BoxLayout:
    """Make a row of the recommended settings: a text on the left, and a button on the right.

    The text wraps in a narrow window, and the row grows with it (the page scrolls).
    """
    padding = dp(SPACING) / 2
    row = BoxLayout(size_hint_y=None, spacing=dp(SPACING), padding=padding)
    set_background(row, theme.BOX_BACKGROUND_COLOR)
    label = fitting_label(dp(PRESET_ROW_HEIGHT))
    label.text = text
    label.bind(height=lambda _label, height: setattr(row, "height", height + 2 * padding))
    row.height = label.height + 2 * padding
    row.add_widget(label)
    anchor = AnchorLayout(size_hint_x=None, width=dp(96))
    button = flat_button(button_text, action, size_hint=(1, None))
    button.height = dp(40)
    anchor.add_widget(button)
    row.add_widget(anchor)
    return row


def _measured_text(speed: MeasuredSpeed, preset: Preset) -> str:
    """Return the question after measuring: the speeds, and the numbers of visits that will be set."""
    values = {"speed": round(speed.main), "main": preset.max_visits, "estimate": preset.estimate_visits}
    if speed.compare is None:
        return texts.text("preset_measured", **values)
    return texts.text(
        "preset_measured_compare", **values, compare_speed=round(speed.compare), compare=preset.compare_max_visits
    )


def _preset_text(preset: Preset) -> str:
    """Return the name of a kind of computer, examples of it, and its numbers of visits, on three lines."""
    numbers = texts.text(
        "preset_values", main=preset.max_visits, compare=preset.compare_max_visits, estimate=preset.estimate_visits
    )
    name = texts.text(f"preset_{preset.key}")
    examples = texts.text(f"preset_{preset.key}_examples")
    return f"[b]{name}[/b]\n{examples}\n{numbers}"


def _label_text(key: str) -> str:
    """Return the name of a setting, as shown on the screen."""
    return texts.text(f"field_{key}")


def _field_label(spec: FieldSpec, halign: str) -> Label:
    """Make the label with the name of a setting. Long names wrap."""
    label = Label(text=_label_text(spec.id), halign=halign, valign="middle", color=theme.TEXT_COLOR)
    label.bind(size=lambda widget, size: setattr(widget, "text_size", size))
    return label


def _header(text: str, halign: str = "center") -> Label:
    """Make a large header, such as "KataGo設定"."""
    label = Label(text=text, font_size=sp(HEADER_FONT_SIZE), halign=halign, valign="middle", color=theme.TEXT_COLOR)
    label.size_hint_y = None
    label.height = dp(36)
    label.bind(size=lambda widget, size: setattr(widget, "text_size", size))
    return label


def _two_columns(left, right) -> GridLayout:
    """Put two widgets side by side, as tall as the taller one. Both must have size_hint_y None."""
    grid = GridLayout(cols=2, spacing=dp(20), padding=(dp(SPACING), 0), size_hint_y=None)
    grid.bind(minimum_height=grid.setter("height"))
    grid.add_widget(left)
    grid.add_widget(right)
    return grid
