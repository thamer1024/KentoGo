"""Settings of KataGo for KentoGo, kept in the "engine" part of settings.json.

The settings have the same items as KaTrain's local engine settings (KataGo,
model, human-like model, KataGo's settings file, visits and wide root noise),
so that the settings screen can look like KaTrain's. When KentoGo starts for
the first time, they are copied from KaTrain's config.json (see from_katrain).

The territory and the standing (地と形勢) have their own number of visits (estimate_visits),
because they need only a shallow reading.
They can be set at once with the recommended settings of a kind of computer (see katago.presets).
"""

from __future__ import annotations

from dataclasses import dataclass

from kentogo.katago.locate import DEFAULT_KATRAIN_CONFIG

# The settings that are paths of files or folders.
PATH_KEYS = ("katago", "model", "humanlike_model", "config", "katrain_config", "katrain_folder")

# The numbers of visits (each must be 1 or more).
VISITS_KEYS = ("max_visits", "estimate_visits")


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
        max_time: KaTrain's "max_time": the most seconds that KataGo reads one position (KataGo's maxTime);
            it stops there even when it has not read all its visits. 0 means no limit.
        katrain_config: Path of KaTrain's config.json, used to copy KaTrain's settings.
        katrain_folder: The folder of the KaTrain program, for paths that start with "katrain/"
            (KaTrain's own KataGo and models, as in KaTrain's default settings on Windows).
            "" means: look in the usual places (see katago.locate.katrain_package).
        estimate_visits: How many positions KataGo reads for the territory and the standing (地と形勢).
            KaTrain has no such setting, so it is not copied from KaTrain.
        ready_timeout: The most seconds to wait for KataGo to load its model. A computer without a GPU,
            or KataGo's first start (it tunes itself), can take long, so it is a setting.
    """

    use_katago: bool = True
    katago: str = ""
    model: str = ""
    humanlike_model: str = ""
    config: str = ""
    max_visits: int = 500
    wide_root_noise: float = 0.04
    max_time: float = 8.0  # KaTrain's default.
    # Written with "/" on every system (str() would give "\\" on Windows). Windows reads "/" too.
    katrain_config: str = DEFAULT_KATRAIN_CONFIG.as_posix()
    katrain_folder: str = ""
    estimate_visits: int = 100
    ready_timeout: float = 600.0

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
        use_katago = values.get("use_katago", default.use_katago)
        if not isinstance(use_katago, bool):
            raise ValueError(f"wrong engine setting: use_katago must be true or false: {use_katago!r}")
        paths = {}
        for key in PATH_KEYS:
            paths[key] = values.get(key, getattr(default, key))
            if not isinstance(paths[key], str):
                raise ValueError(f"wrong engine setting: {key} must be a path: {paths[key]!r}")
        try:
            visits = {key: int(values.get(key, getattr(default, key))) for key in VISITS_KEYS}
            wide_root_noise = float(values.get("wide_root_noise", default.wide_root_noise))
            max_time = float(values.get("max_time", default.max_time))
            ready_timeout = float(values.get("ready_timeout", default.ready_timeout))
        except (TypeError, ValueError) as error:
            raise ValueError(f"wrong engine setting: {error}") from error
        if max_time < 0:
            raise ValueError(f"wrong engine setting: max_time must not be below 0: {max_time}")
        if ready_timeout <= 0:
            raise ValueError(f"wrong engine setting: ready_timeout must be above 0: {ready_timeout}")
        for key, number in visits.items():
            if number < 1:
                raise ValueError(f"wrong engine setting: {key} must be 1 or more: {number}")
        return cls(
            use_katago=use_katago,
            wide_root_noise=wide_root_noise,
            max_time=max_time,
            ready_timeout=ready_timeout,
            **visits,
            **paths,
        )

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
        for key in ("max_visits", "wide_root_noise", "max_time"):
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
            "max_time": self.max_time,
            "katrain_config": self.katrain_config,
            "katrain_folder": self.katrain_folder,
            "estimate_visits": self.estimate_visits,
            "ready_timeout": self.ready_timeout,
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
