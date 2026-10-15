"""External scenario schedules and a causally realizable plumbing demonstration.

The controller below is deliberately NOT an optimized/approved IABP algorithm.
Its purpose is exercising sample -> command -> actuator -> circulation feedback.
"""
from .contracts import Command, Sample
from .engine import Engine


def add_sinus_schedule(engine: Engine, duration_us: int, hr: float = 72,
                       first_qrs_us: int = 1_000_000, pr_us: int = 160000) -> None:
    if not 30 <= hr <= 180 or duration_us < 0 or pr_us < 0:
        raise ValueError("invalid engineering schedule")
    rr = 60_000_000 / hr
    k = 0
    while True:
        q = first_qrs_us + round(k*rr)
        if q > duration_us:
            break
        if q-pr_us >= engine.now_us:
            engine.schedule_stimulus(q-pr_us, 'atrial')
        if q >= engine.now_us:
            engine.schedule_stimulus(q, 'ventricular')
        k += 1


class ThresholdDemoController:
    """UNVALIDATED demonstration using only delivered II-lead observations."""
    def __init__(self) -> None:
        self.last_detect_us: int | None = None
        self.count = 0

    def on_samples(self, samples: list[Sample], now_us: int) -> list[Command]:
        commands: list[Command] = []
        for s in samples:
            if s.t_available_us > now_us:
                raise ValueError('future sample provided to controller')
            if s.channel_id != 'ECG_II' or s.value <= .5:
                continue
            if self.last_detect_us is not None and now_us-self.last_detect_us < 300000:
                continue
            rr = 833333 if self.last_detect_us is None else now_us-self.last_detect_us
            self.last_detect_us = now_us
            self.count += 1
            # This schedule is an engineering demo, not a recommendation for a real pump.
            commands.extend([
                Command(f'demo-{self.count}-i','INFLATE',now_us,now_us+300000),
                Command(f'demo-{self.count}-d','DEFLATE',now_us,now_us+max(400000,rr-90000)),
            ])
        return commands
