"""Settings of KataGo for KentoGo, kept in the "engine" part of settings.json.

The settings have the same items as KaTrain's local engine settings (KataGo,
model, human-like model, KataGo's settings file, visits and wide root noise),
so that the settings screen can look like KaTrain's. When KentoGo starts for
the first time, they are copied from KaTrain's config.json (see from_katrain).

A second model can be set for comparison (for example a normal model, when the
main model is a human-like one). It runs in a second KataGo process, only when
use_compare is on. judge_model chooses which model calculates the losses.
Each model has its own number of visits (max_visits and compare_max_visits),
because the time they take is very different for each model and each computer.
The territory and the standing (地と形勢) have their own number too (estimate_visits).
They can be set at once with the recommended settings of a kind of computer (see katago.presets).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kentogo.katago.locate import DEFAULT_KATRAIN_CONFIG

# Which model calculates the losses of answers.
JUDGE_MAIN = "main"  # The model of the main KataGo (the "model" setting).
JUDGE_COMPARE = "compare"  # The comparison model (needs use_compare and compare_model).
JUDGE_MODELS = (JUDGE_MAIN, JUDGE_COMPARE)

# The settings that are paths of files or folders.
PATH_KEYS = ("katago", "model", "humanlike_model", "config", "katrain_config", "katrain_folder", "compare_model")

# The numbers of visits (each must be 1 or more).
VISITS_KEYS = ("max_visits", "compare_max_visits", "estimate_visits")


@dataclass(frozen=True)
class EngineSettings:
    """Whether and how KentoGo uses KataGo.

    The paths are written in the same way as in KaTrain: "~" means the home folder,
    and an empty KataGo path means the KataGo in the PATH (or the one that comes with KaTrain).

    Attributes:
        use_katago: Calculate with KataGo the answers whose loss is not in the SGF file.
            It can take some seconds for each answer, depending on the computer.
        katago: Path of the KataGo program.
        model: Path of the model.
        humanlike_model: Path of the human-like model, or "" if it is not used.
        config: Path of KataGo's analysis settings file.
        max_visits: How many positions KataGo reads for one analysis with the main model.
        wide_root_noise: KataGo's wideRootNoise setting.
        katrain_config: Path of KaTrain's config.json, used to copy KaTrain's settings.
        katrain_folder: The folder of the KaTrain program, for paths that start with "katrain/"
            (KaTrain's own KataGo and models, as in KaTrain's default settings on Windows).
            "" means: look in the usual places (see katago.locate.katrain_package).
        compare_model: Path of a second model for comparison, or "" if there is none.
        use_compare: Start a second KataGo with compare_model.
        compare_max_visits: How many positions KataGo reads for one analysis with the comparison model.
        judge_model: Which model calculates the losses, one of JUDGE_MODELS.
        estimate_visits: How many positions KataGo reads for the territory and the standing (地と形勢).
            KaTrain has no such setting, so it is not copied from KaTrain.
    """

    use_katago: bool = True
    katago: str = ""
    model: str = ""
    humanlike_model: str = ""
    config: str = ""
    max_visits: int = 500
    wide_root_noise: float = 0.04
    # Written with "/" on every system (str() would give "\\" on Windows). Windows reads "/" too.
    katrain_config: str = DEFAULT_KATRAIN_CONFIG.as_posix()
    katrain_folder: str = ""
    compare_model: str = ""
    use_compare: bool = False
    compare_max_visits: int = 500
    judge_model: str = JUDGE_MAIN
    estimate_visits: int = 100

    @classmethod
    def from_dict(cls, values: dict) -> EngineSettings:
        """Make the settings from the "engine" part of settings.json.

        Args:
            values: The values. Missing keys get the default values, and unknown keys are ignored.

        Returns:
            The settings.

        Raises:
            ValueError: If a value has a wrong type.
        """
        default = cls()
        switches = {}
        for key in ("use_katago", "use_compare"):
            switches[key] = values.get(key, getattr(default, key))
            if not isinstance(switches[key], bool):
                raise ValueError(f"wrong engine setting: {key} must be true or false: {switches[key]!r}")
        judge_model = values.get("judge_model", default.judge_model)
        if judge_model not in JUDGE_MODELS:
            raise ValueError(f"wrong engine setting: judge_model must be one of {JUDGE_MODELS}: {judge_model!r}")
        paths = {}
        for key in PATH_KEYS:
            paths[key] = values.get(key, getattr(default, key))
            if not isinstance(paths[key], str):
                raise ValueError(f"wrong engine setting: {key} must be a path: {paths[key]!r}")
        try:
            visits = {key: int(values.get(key, getattr(default, key))) for key in VISITS_KEYS}
            wide_root_noise = float(values.get("wide_root_noise", default.wide_root_noise))
        except (TypeError, ValueError) as error:
            raise ValueError(f"wrong engine setting: {error}") from error
        for key, number in visits.items():
            if number < 1:
                raise ValueError(f"wrong engine setting: {key} must be 1 or more: {number}")
        return cls(wide_root_noise=wide_root_noise, judge_model=judge_model, **visits, **switches, **paths)

    @classmethod
    def from_katrain(cls, engine: dict, katrain_config: str) -> EngineSettings:
        """Copy the local engine settings of KaTrain.

        Args:
            engine: The "engine" part of KaTrain's config.json (see katago.locate.read_engine_config).
            katrain_config: Path of that config.json, kept to copy the settings again later.

        Returns:
            The settings, with use_katago on.

        Raises:
            ValueError: If a value in KaTrain's settings has a wrong type.
        """
        values = {key: engine[key] for key in ("katago", "model", "humanlike_model", "config") if key in engine}
        for key in ("max_visits", "wide_root_noise"):
            if key in engine:
                values[key] = engine[key]
        return cls.from_dict({**values, "katrain_config": katrain_config})

    def to_dict(self) -> dict:
        """Return the settings as a dict for the "engine" part of settings.json."""
        return {
            "use_katago": self.use_katago,
            "katago": self.katago,
            "model": self.model,
            "humanlike_model": self.humanlike_model,
            "config": self.config,
            "max_visits": self.max_visits,
            "wide_root_noise": self.wide_root_noise,
            "katrain_config": self.katrain_config,
            "katrain_folder": self.katrain_folder,
            "compare_model": self.compare_model,
            "use_compare": self.use_compare,
            "compare_max_visits": self.compare_max_visits,
            "judge_model": self.judge_model,
            "estimate_visits": self.estimate_visits,
        }

    def katrain_engine(self) -> dict:
        """Return the settings in the form of KaTrain's engine settings (for katago.locate.engine_command)."""
        return {
            "backend": "local",
            "katago": self.katago,
            "model": self.model,
            "humanlike_model": self.humanlike_model,
            "config": self.config,
            "max_visits": self.max_visits,
        }

    @property
    def compare_on(self) -> bool:
        """True if the comparison model is turned on and set."""
        return self.use_compare and bool(self.compare_model.strip())

    @property
    def models_differ(self) -> bool:
        """True if the comparison model is turned on and is another file than the main model.

        Two models can be very different in speed, so one number of visits does not fit both.
        """
        same = Path(self.compare_model.strip()).expanduser() == Path(self.model.strip()).expanduser()
        return self.compare_on and not same

    def compare_engine(self) -> dict:
        """Return the settings of the second KataGo, with the comparison model and no human-like model."""
        engine = {**self.katrain_engine(), "model": self.compare_model, "humanlike_model": ""}
        return {**engine, "max_visits": self.compare_max_visits}
