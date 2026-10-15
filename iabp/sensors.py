"""Independent causal measurement chains; anatomy and electronics are separate."""
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from random import Random

from .components import relax
from .contracts import Sample


@dataclass(frozen=True)
class SensorConfig:
    channel_id: str
    site: str  # e.g. p_root, p_descending, ecg_ii; never inferred from sensor type
    units: str
    period_us: int = 1000
    phase_us: int = 0
    tau_us: float = 0.0
    latency_us: int = 0
    noise_std: float = 0.0
    gain: float = 1.0
    offset: float = 0.0
    clock_offset_us: int = 0
    drift_ppm: float = 0.0
    expose_source_time: bool = True
    drop_every: int = 0

    def __post_init__(self) -> None:
        if not self.channel_id or self.site not in ("p_root", "p_descending", "ecg_ii"):
            raise ValueError("unsupported or unnamed channel/site")
        for name in ("period_us", "phase_us", "latency_us", "clock_offset_us", "drop_every"):
            v = getattr(self, name)
            if type(v) is not int:
                raise ValueError(f"{name} must be an integer")
        if self.period_us <= 0 or min(self.phase_us, self.latency_us, self.drop_every) < 0:
            raise ValueError("invalid sampling/latency/drop configuration")
        if not all(isfinite(v) for v in (self.tau_us, self.noise_std, self.gain,
                                         self.offset, self.drift_ppm)):
            raise ValueError("sensor coefficients must be finite")
        if self.tau_us < 0 or self.noise_std < 0 or abs(self.drift_ppm) > 10000:
            raise ValueError("invalid filter, noise or clock drift")
        if self.units != ("mV" if self.site == "ecg_ii" else "mmHg"):
            raise ValueError("signal units do not match site")


class Sensor:
    def __init__(self, config: SensorConfig, seed: int, initial: float) -> None:
        self.config = config
        channel_seed = int.from_bytes(sha256(config.channel_id.encode()).digest()[:8], 'big')
        self.rng = Random(seed ^ channel_seed)
        self.filtered = initial
        self.sequence = 0

    def next_sample_us(self) -> int:
        c = self.config
        return c.phase_us + round(self.sequence * c.period_us / (1 + c.drift_ppm/1e6))

    def advance(self, input_midpoint: float, dt_us: int) -> None:
        self.filtered = (input_midpoint if self.config.tau_us == 0 else
                         relax(self.filtered, input_midpoint, self.config.tau_us, dt_us))

    def sample(self, true_time_us: int, raw_now: float) -> Sample | None:
        c, seq = self.config, self.sequence
        self.sequence += 1
        # Consume each channel's RNG independently, including dropped observations.
        noise = self.rng.gauss(0, c.noise_std)
        value = (raw_now if c.tau_us == 0 else self.filtered) * c.gain + c.offset + noise
        if c.drop_every and (seq + 1) % c.drop_every == 0:
            return None
        source = round(true_time_us*(1+c.drift_ppm/1e6)) + c.clock_offset_us
        return Sample(c.channel_id, c.units, seq, value, true_time_us+c.latency_us,
                      source if c.expose_source_time else None,
                      c.channel_id if c.expose_source_time else None)


def reference_sensors() -> tuple[SensorConfig, ...]:
    """UNMEASURED example transfer functions, not properties of commercial products."""
    return (
        SensorConfig("ECG_II", "ecg_ii", "mV"),
        SensorConfig("AP_TIP_SOLID", "p_descending", "mmHg", tau_us=1000, latency_us=1000),
        SensorConfig("AP_FIBER", "p_descending", "mmHg", tau_us=500, latency_us=2000),
        SensorConfig("AP_MONITOR", "p_root", "mmHg", period_us=4000, tau_us=8000,
                     latency_us=20000, expose_source_time=False),
    )
