"""Continuous closed-circulation 0D prototype, not the final 0D/1D model.

Nine finite-volume compartments; four finite-opening valves; one inertial
arterial connection. A midpoint frozen-coefficient scheme transports equal
integrated flow volumes out of one compartment and into the next.
Optional balloon coupling is an UNCALIBRATED M2 integration experiment.
"""
from dataclasses import dataclass, field, fields
from math import exp, expm1, isfinite

from .components import gate_step, inertial_step, positive, relax, valve_resistance

NODES = ("lv", "root", "descending", "systemic_vein", "ra", "rv",
         "pulmonary_artery", "pulmonary_vein", "la")
# Edges with inertia: mitral, aortic valve, aortic connection, tricuspid, pulmonary valve.
DYNAMIC_EDGES = ((8, 0), (0, 1), (1, 2), (4, 5), (5, 6))
VALVE_FLOW_INDEX = (0, 1, 3, 4)
VALVE_NAMES = ("mitral", "aortic", "tricuspid", "pulmonary")
RESISTIVE_EDGES = ((2, 3), (3, 4), (6, 7), (7, 8))
INITIAL_VOLUMES = (120., 70., 150., 3000., 55., 120., 150., 500., 60.)


@dataclass(frozen=True)
class ModelConfig:
    """All defaults are synthetic engineering parameters, not patient calibration."""
    e_lv: float = 2.1
    e_rv: float = 0.50
    r_systemic: float = 1.1
    r_pulmonary: float = 0.09
    c_root: float = 0.22
    c_descending: float = 0.85
    r_link: float = 0.08
    l_link: float = 0.0007
    tau_rise: float = 0.050
    tau_relax: float = 0.035
    tau_recovery: float = 0.60
    balloon_capacity: float = 40.0
    balloon_enabled: bool = False

    def __post_init__(self) -> None:
        for f in fields(self):
            if f.name != "balloon_enabled":
                positive(f.name, getattr(self, f.name))
        if not isinstance(self.balloon_enabled, bool):
            raise ValueError("balloon_enabled must be bool")
        if self.balloon_capacity > 60:
            raise ValueError("prototype only supports balloon capacity <=60 mL")


@dataclass
class CoreState:
    volumes: list[float] = field(default_factory=lambda: list(INITIAL_VOLUMES))
    flows: list[float] = field(default_factory=lambda: [0., 0., 0., 0., 0.])
    gates: list[float] = field(default_factory=lambda: [0., 0., 0., 0.])
    activation: list[float] = field(default_factory=lambda: [0., 0.])  # atrial, ventricular
    calcium_proxy: list[float] = field(default_factory=lambda: [0., 0.])
    recovery: float = 1.0
    balloon_v: float = 0.0


class NumericalFailure(RuntimeError):
    """Invalid integration state; never repaired by pressure/volume clipping."""


class Model:
    def __init__(self, config: ModelConfig | None = None) -> None:
        self.config = config or ModelConfig()
        self.state = CoreState()
        self.targets = [0., 0.]
        self.inflate = False
        self.initial_blood_volume = self.blood_volume()

    def blood_volume(self) -> float:
        return sum(self.state.volumes) - self.state.balloon_v

    def excite(self, chamber: str) -> None:
        if chamber == "atrial":
            self.targets[0] = 1.0
        elif chamber == "ventricular":
            # Interval-dependent recovery is a structural prototype, not calibrated PESP.
            self.targets[1] = 0.55 + 0.45 * self.state.recovery
            self.state.recovery *= 0.50
        else:
            raise ValueError("chamber must be atrial or ventricular")

    def release(self, chamber: str) -> None:
        if chamber not in ("atrial", "ventricular"):
            raise ValueError("unknown chamber")
        self.targets[0 if chamber == "atrial" else 1] = 0.0

    def pressures(self, s: CoreState | None = None) -> list[float]:
        s = s or self.state
        v, (a, c), p = s.volumes, s.activation, self.config
        # External pressure is zero in this prototype, so gauge and transmural coincide.
        lv = .05 * (v[0] - 10) + .12 * expm1(.022 * (v[0] - 10))
        rv = .025 * (v[5] - 15) + .04 * expm1(.018 * (v[5] - 15))
        return [lv + p.e_lv * c * (v[0] - 10),
                (v[1] - 50) / p.c_root, (v[2] - 75) / p.c_descending,
                (v[3] - 2600) / 80, (.10 + .25*a) * (v[4] - 20),
                rv + p.e_rv * c * (v[5] - 15),
                (v[6] - 80) / 5, (v[7] - 320) / 20,
                (.16 + .35*a) * (v[8] - 20)]

    def obstruction(self, s: CoreState) -> float:
        fraction = s.balloon_v / s.volumes[2]
        if not 0 <= fraction < .9:
            raise NumericalFailure("balloon occupies >=90% of segment volume; model out of domain")
        # Fixed-length cylindrical surrogate. Not a validated annular-flow formula.
        return (1 - fraction) ** -2

    def _balloon(self, s: CoreState, local_p: float, h: float) -> float:
        if not self.config.balloon_enabled:
            return 0.0
        if self.inflate:
            # Piecewise bounded equilibrium is a constitutive limit, not solver clipping.
            load_fraction = min(1., max(0., (260. - local_p) / 120.))
            target = self.config.balloon_capacity * load_fraction
            tau = .025 * (1 + max(local_p - 80., 0.) / 160.)
        else:
            target = 0.0
            tau = .025 / (1 + max(local_p, 0.) / 160.)
        return relax(s.balloon_v, target, tau, h)

    def _transport(self, old: CoreState, coefficients: CoreState, h: float) -> CoreState:
        p = self.pressures(coefficients)
        activation, calcium = [], []
        for i in range(2):
            # Exact two-stage activation at a frozen drive/phase time constant.
            # The proxy is NOT a calibrated intracellular calcium concentration.
            target = self.targets[i]
            tau = (self.config.tau_rise if target > old.calcium_proxy[i]
                   else self.config.tau_relax)
            decay = exp(-h/tau)
            calcium.append(target+(old.calcium_proxy[i]-target)*decay)
            activation.append(target+((old.activation[i]-target)
                               +(old.calcium_proxy[i]-target)*h/tau)*decay)
        gates = [gate_step(old.gates[k], p[DYNAMIC_EDGES[j][0]]-p[DYNAMIC_EDGES[j][1]], h)
                 for k, j in enumerate(VALVE_FLOW_INDEX)]
        resistances = [valve_resistance(coefficients.gates[0], .012),
                       valve_resistance(coefficients.gates[1], .035),
                       self.config.r_link * self.obstruction(coefficients),
                       valve_resistance(coefficients.gates[2], .009),
                       valve_resistance(coefficients.gates[3], .012)]
        inertances = (.00020, .00040, self.config.l_link, .00020, .00015)
        volumes, flows = old.volumes.copy(), []
        for j, (i, k) in enumerate(DYNAMIC_EDGES):
            q, integral = inertial_step(old.flows[j], p[i]-p[k], resistances[j],
                                        inertances[j], h)
            flows.append(q)
            volumes[i] -= integral
            volumes[k] += integral
        rs = (self.config.r_systemic*self.obstruction(coefficients), .02,
              self.config.r_pulmonary, .02)
        for (i, k), r in zip(RESISTIVE_EDGES, rs):
            integral = (p[i] - p[k]) / r * h
            volumes[i] -= integral
            volumes[k] += integral
        vb = self._balloon(old, p[2], h)
        volumes[2] += vb - old.balloon_v
        return CoreState(volumes, flows, gates, activation, calcium,
                         relax(old.recovery, 1, self.config.tau_recovery, h), vb)

    def advance(self, dt_s: float) -> None:
        positive("dt_s", dt_s)
        if dt_s > .00025 + 1e-15:
            raise ValueError("prototype core maximum step is 0.25 ms")
        try:
            midpoint = self._transport(self.state, self.state, dt_s/2)
            candidate = self._transport(self.state, midpoint, dt_s)
            values = (candidate.volumes + candidate.flows + candidate.gates
                      + candidate.activation + candidate.calcium_proxy
                      + [candidate.recovery, candidate.balloon_v])
            pp = self.pressures(candidate)
        except (OverflowError, ValueError, ZeroDivisionError) as exc:
            raise NumericalFailure(str(exc)) from exc
        if (not all(isfinite(v) for v in values + pp) or min(candidate.volumes) <= 0
                or max(abs(x) for x in pp) > 2000):
            raise NumericalFailure("invalid state; no pressure or volume clipping performed")
        self.state = candidate

    def observe(self) -> dict[str, float]:
        p = self.pressures()
        s = self.state
        out = {f"p_{n}": v for n, v in zip(NODES, p)}
        out.update({f"v_{n}": v for n, v in zip(NODES, s.volumes)})
        out.update({f"z_{n}": v for n, v in zip(VALVE_NAMES, s.gates)})
        out.update(q_mv=s.flows[0], q_ao=s.flows[1], q_link=s.flows[2],
                   a_atrial=s.activation[0], a_ventricular=s.activation[1],
                   recovery=s.recovery, v_balloon=s.balloon_v,
                   blood_volume=self.blood_volume(),
                   mass_error=self.blood_volume()-self.initial_blood_volume)
        return out
