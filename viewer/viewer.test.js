"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const observer = require("./viewer.js");

function fixture(id = "test-record-not-physical-evidence") {
  return {
    schema: observer.SCHEMA,
    run: { id, source_status: "NOT_RECORDED", provenance: { heart: {}, initial_state: { cross_iteration: null } } },
    heart: {
      channels: [{ key: "pressure", label: "unit-test field", unit: "Pa", group: "test" }],
      cases: { baseline: { columns: ["time_us", "pressure"], rows: [[1000000, 1.2345678901234567], [1000001, -0.25]], samples: [], events: [], commands: [], metrics: {}, window_us: [1000000, 1000001] } },
      metric_definitions: {}
    },
    arterial1d: { runs: [] }, warnings: [], capabilities: []
  };
}

test("a schema-valid record preserves raw numeric precision and negative values", () => {
  const source = fixture(), parsed = observer.parseBundle(JSON.stringify(source));
  assert.equal(parsed.heart.cases.baseline.rows[0][1], source.heart.cases.baseline.rows[0][1]);
  assert.equal(parsed.heart.cases.baseline.rows[1][1], -0.25);
});

test("unknown schema, malformed JSON, file size and nonfinite numbers are rejected", () => {
  assert.throws(() => observer.parseBundle("{}"), /schema/);
  assert.throws(() => observer.parseBundle("{broken"), /JSON/);
  assert.throws(() => observer.parseBundle("{}", observer.MAX_FILE_BYTES + 1), /64 MiB/);
  const source = fixture(); source.heart.cases.baseline.rows[0][1] = Infinity;
  assert.throws(() => observer.validateBundle(source), /Infinity/);
});

test("duplicate JSON keys, including escaped keys, are rejected before evidence is selected", () => {
  assert.throws(() => observer.parseBundle('{"schema":"wrong","schema":"cardiac-observer/v1"}'), /重复键/);
  assert.throws(() => observer.parseBundle('{"schema":"wrong","sch\\u0065ma":"cardiac-observer/v1"}'), /重复键/);
  const source = fixture(); source.run.label = 'text with {"look":"not an object"} and \\ escapes';
  assert.equal(observer.parseBundle(JSON.stringify(source)).run.label, source.run.label);
});

test("malformed tables, duplicate columns and noninteger / reversed physical clocks fail", () => {
  const cases = [
    item => { item.columns = ["time_us", "time_us"]; },
    item => { item.rows[0] = [1000000]; },
    item => { item.rows[0][0] = 1000000.5; },
    item => { item.rows[1][0] = 999999; },
    item => { item.rows[1][0] = item.rows[0][0]; },
    item => { item.rows[0][1] = "1.2"; }
  ];
  for (const modify of cases) { const source = fixture(); modify(source.heart.cases.baseline); assert.throws(() => observer.validateBundle(source)); }
});

test("missing table values stay null and unknown channel units remain unknown", () => {
  const source = fixture(); source.heart.channels[0].unit = null; source.heart.cases.baseline.rows[0][1] = null;
  observer.validateBundle(source);
  assert.equal(observer.seriesFromTable(source.heart.cases.baseline, "pressure", "time_us", 1e-6)[0].y, null);
  assert.deepEqual(observer.seriesFromTable(source.heart.cases.baseline, "absent"), []);
});

test("a claimed full metric window must match actual exported physical times", () => {
  const source = fixture(); source.heart.cases.baseline.metric_window_us = [0, 1000001];
  assert.throws(() => observer.validateBundle(source), /统计窗/);
  source.heart.cases.baseline.metric_window_us = [1000000, 1000001];
  observer.validateBundle(source);
});

test("imported text is escaped in SVG; external markup is never inserted raw", () => {
  const input = '<script>alert("x")</script><img src=x onerror=1>&\'';
  const escaped = observer.escapeText(input);
  assert.ok(!escaped.includes("<")); assert.ok(!escaped.includes('"')); assert.ok(escaped.includes("&lt;script&gt;"));
});

test("cyclic objects, reserved prototype fields and excessive nesting fail safely", () => {
  const circular = fixture(); circular.run.extra = circular;
  assert.throws(() => observer.validateBundle(circular), /循环/);
  assert.throws(() => observer.parseBundle('{"schema":"cardiac-observer/v1","run":{"id":"x","__proto__":{}}}'), /保留字段/);
  const deep = fixture(); let current = deep.run;
  for (let i = 0; i < 40; i++) { current.extra = {}; current = current.extra; }
  assert.throws(() => observer.validateBundle(deep), /深度/);
});

test("optional preloaded baseline is independently validated and cannot nest indefinitely", () => {
  const source = fixture("B"); source.comparison_baseline = fixture("A");
  observer.validateBundle(source);
  source.comparison_baseline.comparison_baseline = fixture("nested");
  assert.throws(() => observer.validateBundle(source), /嵌套基线/);
});

test("delivered and source clocks are distinct; missing source clock does not use available time", () => {
  const samples = [
    { channel_id: "AP", units: "mmHg", value: 100, t_available_us: 1000500, source_time_us: 999000 },
    { channel_id: "AP", units: "mmHg", value: 101, t_available_us: 1001500, source_time_us: null },
    { channel_id: "ECG", units: "mV", value: .4, t_available_us: 1000500, source_time_us: 1000000 }
  ];
  assert.deepEqual(observer.sampleSeries(samples, "AP", "available").map(p => p.rawTime), [1000500, 1001500]);
  assert.deepEqual(observer.sampleSeries(samples, "AP", "source").map(p => p.rawTime), [999000]);
  assert.equal(observer.sampleSeries(samples, "AP", "source")[0].x, .999);
});

test("negative source clock offsets remain valid alongside positive delivery clocks", () => {
  const source = fixture();
  source.heart.cases.baseline.samples = [{ channel_id: "ECG", units: "mV", sequence_id: 1, value: .4, t_available_us: 100, source_time_us: -900, source_clock_id: "offset-clock", observable_quality: "valid" }];
  observer.validateBundle(source);
  assert.equal(observer.sampleSeries(source.heart.cases.baseline.samples, "ECG", "available")[0].rawTime, 100);
  assert.equal(observer.sampleSeries(source.heart.cases.baseline.samples, "ECG", "source")[0].rawTime, -900);
  assert.equal(observer.sampleSeries(source.heart.cases.baseline.samples, "ECG", "source")[0].x, -.0009);
});

test("double cursor lookup uses raw samples and exposes original timestamps, earliest wins tie", () => {
  const points = [{ x: 0, y: .1, rawTime: 0 }, { x: .001, y: 900, rawTime: 1000 }, { x: .002, y: null, rawTime: 2000 }];
  assert.equal(observer.nearestPoint(points, .00099).y, 900);
  assert.equal(observer.nearestPoint(points, .00199).y, null);
  assert.equal(observer.nearestPoint(points, .0005).rawTime, 0);
  assert.equal(observer.nearestPoint([], 1), null);
});

test("large render sampling preserves global extrema and first / last samples without spread", () => {
  const points = Array.from({ length: 200000 }, (_, i) => ({ x: i, y: i % 10 }));
  points[73457].y = -300; points[114298].y = 500;
  const sampled = observer.extremaSample(points, 1600);
  assert.ok(sampled.length <= 1600); assert.equal(sampled[0], points[0]); assert.equal(sampled.at(-1), points.at(-1));
  assert.ok(sampled.includes(points[73457])); assert.ok(sampled.includes(points[114298]));
  assert.deepEqual(observer.rangeOf([points]), { min: -300, max: 500, count: points.length });
});

test("render sampling never joins retained extrema across omitted missing intervals", () => {
  const points = Array.from({ length: 4000 }, (_, i) => ({ x: i, y: i % 31 === 0 ? null : Math.sin(i) }));
  const sampled = observer.extremaSample(points, 80);
  let previous = null;
  for (const point of sampled) {
    if (point.y === null) { previous = null; continue; }
    if (previous) assert.ok(!points.slice(previous.x + 1, point.x).some(p => p.y === null));
    previous = point;
  }
});

test("exact coordinate comparison preserves unmatched / missing gaps and does not interpolate", () => {
  const a = [{ x: 1, y: 2 }, { x: 2, y: 3 }, { x: 3, y: 4 }, { x: 4, y: null }];
  const b = [{ x: 1, y: 2.5 }, { x: 2.5, y: 7 }, { x: 3, y: 3 }, { x: 4, y: 3 }];
  const result = observer.differenceSeries(a, b, "Pa", "Pa");
  assert.deepEqual(result.points.map(p => [p.x, p.y]), [[1, .5], [2, null], [2.5, null], [3, -1], [4, null]]);
  assert.equal(result.matched, 2); assert.equal(result.missingA, 1); assert.equal(result.missingB, 1);
});

test("different units and ambiguous duplicate coordinates prevent numeric differences", () => {
  assert.equal(observer.differenceSeries([{ x: 1, y: 1 }], [{ x: 1, y: 1 }], "Pa", "mmHg").points.length, 0);
  assert.match(observer.differenceSeries([{ x: 1, y: 1 }, { x: 1, y: 2 }], [], "Pa", "Pa").reason, /重复/);
  assert.match(observer.differenceSeries([], [{ x: 1, y: 1 }, { x: 1, y: 2 }], "Pa", "Pa").reason, /重复/);
  assert.equal(observer.differenceSeries([{ x: 1, y: 1 }], [{ x: 1.00000001, y: 1 }], "Pa", "Pa").matched, 0);
});

test("spatial profiles select only actual exported times and retain negative ringing", () => {
  const table = { columns: ["time_s", "x_m", "pressure_pa"], rows: [[.1, 0, -.02], [.1, 1, 3], [.3, 0, -1]] };
  assert.deepEqual(observer.profileTimes(table), [.1, .3]);
  assert.equal(observer.profileAt(table, .2).rows.length, 0);
  assert.equal(observer.seriesFromTable(observer.profileAt(table, .1), "pressure_pa", "x_m")[0].y, -.02);
});

test("full-window metric differences require equal units, definitions, method and window", () => {
  const a = { metrics: { metric: 3 }, metric_window_us: [0, 1000] }, b = { metrics: { metric: 4 }, metric_window_us: [0, 1000] };
  const definition = { metric: { label: "test metric", unit: "Pa", definition: "test-only field", method: "export", window: "full_record" } };
  assert.equal(observer.metricComparison(a, b, definition, definition)[0].difference, 1);
  assert.equal(observer.metricComparison(a, b, {}, definition)[0].difference, null);
  const changed = structuredClone(definition); changed.metric.method = "other";
  assert.equal(observer.metricComparison(a, b, definition, changed)[0].difference, null);
  const otherWindow = structuredClone(b); otherWindow.metric_window_us[1] = 2000;
  assert.equal(observer.metricComparison(a, otherWindow, definition, definition)[0].difference, null);
  const missing = structuredClone(b); missing.metrics.metric = null;
  assert.equal(observer.metricComparison(a, missing, definition, definition)[0].difference, null);
});

test("same exported first state never proves same hidden cross-iteration initial state", () => {
  const a = fixture("A"), b = fixture("B");
  a.run.provenance.initial_state = { first_exported_state_equal: true, within_demo_shared: null, cross_iteration: null };
  b.run.provenance.initial_state = structuredClone(a.run.provenance.initial_state);
  const notes = observer.comparisonNotes(a, b).join("\n");
  assert.match(notes, /未证明一致/); assert.match(notes, /至少一包未提供/);
});

test("canonical configuration comparison is independent of object field ordering", () => {
  assert.equal(observer.canonical({ y: [1, null], x: { a: 3, b: 4 } }), observer.canonical({ x: { b: 4, a: 3 }, y: [1, null] }));
});

function reflection(caseName = "closed", cells = 80, method = "muscl_ssprk2") {
  return { id: "test-" + caseName + "-" + cells, suite: "reflections", method, cells,
    summary: { case: caseName, probe_x_m: .75, parameters: { length_m: 1, cells, scheme: method, cfl: .4, inlet: { amplitude_pa: 20 }, outlet: { type: caseName } } } };
}

test("same-grid reflection labels distinguish closed, pressure-release and resistance outlets", () => {
  const labels = ["closed", "pressure_release", "resistance_2z0"].map(name => observer.arterialScenarioLabel(reflection(name)));
  assert.equal(new Set(labels).size, 3);
  assert.match(labels[0], /case=closed.*outlet=closed/);
  assert.match(labels[1], /pressure_release/);
});

test("same suite does not make different reflection terminals comparable", () => {
  const result = observer.arterialScenarioComparison(reflection("closed"), reflection("pressure_release"));
  assert.equal(result.allowed, false);
  assert.match(result.notes.join("\n"), /阻止自动差值.*case 不同/);
  assert.match(result.notes.join("\n"), /终端 \/ outlet 不同/);
});

test("method / grid / CFL differences are described separately from physical parameter changes", () => {
  const a = reflection("closed", 80), b = reflection("closed", 160, "other-test-method");
  b.summary.parameters.cfl = .2;
  let result = observer.arterialScenarioComparison(a, b);
  assert.equal(result.allowed, true); assert.equal(result.kind, "数值方法 / 网格对照");
  assert.match(result.notes.join("\n"), /数值方案变化.*80 → 160/);
  b.summary.parameters.inlet.amplitude_pa = 30;
  result = observer.arterialScenarioComparison(a, b);
  assert.equal(result.allowed, false); assert.match(result.notes.join("\n"), /声明参数不同：inlet/);
});

test("different or unrecorded physical inputs and probe locations prevent automatic differences", () => {
  const a = reflection(), b = reflection();
  b.summary.probe_x_m = .5;
  assert.equal(observer.arterialScenarioComparison(a, b).allowed, false);
  delete b.summary.parameters;
  assert.match(observer.arterialScenarioComparison(a, b).notes.join("\n"), /物理参数至少一侧未记录/);
  b.summary.parameters = {};
  assert.equal(observer.arterialScenarioComparison(a, b).allowed, false);
});

test("public-data comparisons require matching archive, input configuration and reference member", () => {
  const a = reflection(), b = reflection(); a.suite = b.suite = "boileau";
  const input = { archive_sha256: "test-archive", source_config_sha256: "test-config", reference_archive_member: "test-member" };
  a.summary.data_identity = structuredClone(input); b.summary.data_identity = structuredClone(input);
  assert.equal(observer.arterialScenarioComparison(a, b).allowed, true);
  b.summary.data_identity.archive_sha256 = "different-test-archive";
  assert.equal(observer.arterialScenarioComparison(a, b).allowed, false);
  delete b.summary.data_identity;
  assert.equal(observer.arterialScenarioComparison(a, b).allowed, false);
});
