/* Fixed observer: exported records only. No physiological solver or network access. */
"use strict";
(function () {
  const SCHEMA = "cardiac-observer/v1";
  const MAX_FILE_BYTES = 64 * 1024 * 1024;
  const MAX_TABLE_ROWS = 300000;
  const MAX_NODES = 6000000;
  const DEFAULT_TRACKS = ["ecg_ii", "p_root", "p_descending", "p_lv", "q_ao", "v_lv", "v_balloon"];
  const EVENT_LABELS = { QRS_ONSET: "QRS 起点", DP_LV_AO_REVERSE: "LV/Ao 压差反向", QAO_ZERO: "主动脉出流零交叉", AORTIC_CLOSE_02: "有效开口关闭 2%", AORTIC_OPEN_05: "有效开口开放 5%" };

  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function plain(value) { return value !== null && typeof value === "object" && !Array.isArray(value) && (Object.getPrototypeOf(value) === Object.prototype || Object.getPrototypeOf(value) === null); }
  function escapeText(value) { return String(value).replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])); }
  function numberText(value) { return finite(value) ? String(value) : "未提供"; }
  function shortNumber(value) { if (!finite(value)) return "未提供"; if (value === 0) return "0"; return Number(value.toPrecision(6)).toString(); }
  function compactTime(value) { return finite(value) ? Number(value.toPrecision(8)).toString() : "—"; }
  function array(value) { return Array.isArray(value) ? value : []; }

  function validateTable(table, label) {
    if (table == null) return;
    if (!plain(table) || !Array.isArray(table.columns) || !Array.isArray(table.rows)) throw new Error(label + " 缺少 columns / rows");
    if (table.columns.length > 128 || table.columns.some(c => typeof c !== "string" || !c || c.length > 160) || new Set(table.columns).size !== table.columns.length) throw new Error(label + " 列名无效或重复");
    if (table.rows.length > MAX_TABLE_ROWS) throw new Error(label + " 行数超出读取上限");
    for (const row of table.rows) {
      if (!Array.isArray(row) || row.length !== table.columns.length || row.some(v => v !== null && !finite(v))) throw new Error(label + " 包含长度不符、非有限值或非数值记录");
    }
  }

  function validateBundle(bundle) {
    if (!plain(bundle) || bundle.schema !== SCHEMA) throw new Error("不支持的数据包 schema；需要 " + SCHEMA);
    // Iterative bounds avoid recursion overflow and reject executable / cyclic objects.
    const stack = [[bundle, 0]];
    const seen = new Set();
    let visited = 0;
    while (stack.length) {
      const [value, depth] = stack.pop();
      if (++visited > MAX_NODES || depth > 28) throw new Error("数据包大小或嵌套深度超出读取上限");
      if (typeof value === "number" && !finite(value)) throw new Error("数据包包含 NaN / Infinity");
      if (typeof value === "string" && value.length > 500000) throw new Error("数据包文本字段过长");
      if (value === null || ["string", "number", "boolean"].includes(typeof value)) continue;
      if (!Array.isArray(value) && !plain(value)) throw new Error("数据包包含非 JSON 值");
      if (seen.has(value)) throw new Error("数据包包含循环或共享对象；请使用独立 JSON 记录");
      seen.add(value);
      if (Array.isArray(value)) {
        if (value.length > MAX_TABLE_ROWS) throw new Error("数据包数组长度超出读取上限");
        for (let i = value.length - 1; i >= 0; i--) stack.push([value[i], depth + 1]);
      } else {
        for (const key of Object.keys(value)) {
          if (["__proto__", "prototype", "constructor"].includes(key)) throw new Error("数据包含保留字段");
          stack.push([value[key], depth + 1]);
        }
      }
    }
    if (!plain(bundle.run) || typeof bundle.run.id !== "string" || !bundle.run.id) throw new Error("缺少运行身份 run.id");
    if (bundle.heart != null) {
      if (!plain(bundle.heart) || !plain(bundle.heart.cases) || !Array.isArray(bundle.heart.channels)) throw new Error("heart 结构无效");
      const channelKeys = new Set();
      for (const channel of bundle.heart.channels) {
        if (!plain(channel) || typeof channel.key !== "string" || (channel.unit !== null && typeof channel.unit !== "string") || channelKeys.has(channel.key)) throw new Error("心脏通道名或单位无效");
        channelKeys.add(channel.key);
      }
      for (const [key, item] of Object.entries(bundle.heart.cases)) {
        if (!plain(item)) throw new Error("心脏分支必须是记录对象");
        validateTable(item, "heart." + key);
        if (!item.columns.includes("time_us")) throw new Error("心脏记录没有 time_us");
        const timeIndex = item.columns.indexOf("time_us");
        let previous = -Infinity;
        for (const row of item.rows) {
          if (!Number.isSafeInteger(row[timeIndex]) || row[timeIndex] <= previous) throw new Error("心脏 time_us 必须为递增的安全整数");
          previous = row[timeIndex];
        }
        for (const field of ["window_us", "metric_window_us"]) if (item[field] != null) {
          const window = item[field];
          if (!Array.isArray(window) || window.length !== 2 || !window.every(Number.isSafeInteger) || window[0] > window[1]) throw new Error("心脏完整统计窗字段无效");
          if (item.rows.length && (window[0] !== item.rows[0][timeIndex] || window[1] !== item.rows[item.rows.length - 1][timeIndex])) throw new Error("完整统计窗与实际导出时间不符");
        }
        for (const sample of array(item.samples)) {
          if (!plain(sample) || typeof sample.channel_id !== "string" || typeof sample.units !== "string" || (sample.value !== null && !finite(sample.value)) || !Number.isSafeInteger(sample.t_available_us) || (sample.source_time_us != null && !Number.isSafeInteger(sample.source_time_us))) throw new Error("已交付 Sample 字段无效");
        }
        for (const event of array(item.events)) if (!plain(event) || typeof event.name !== "string" || !Number.isSafeInteger(event.at_us)) throw new Error("事件字段或时钟无效");
        for (const command of array(item.commands)) if (!plain(command) || (command.at_us != null && !Number.isSafeInteger(command.at_us))) throw new Error("命令字段或时钟无效");
      }
    }
    if (bundle.arterial1d != null) {
      if (!plain(bundle.arterial1d) || !Array.isArray(bundle.arterial1d.runs)) throw new Error("arterial1d 结构无效");
      const ids = new Set();
      for (const run of bundle.arterial1d.runs) {
        if (!plain(run) || typeof run.id !== "string" || ids.has(run.id)) throw new Error("1D run 身份无效或重复");
        ids.add(run.id);
        validateTable(run.trace, run.id + ".trace");
        validateTable(run.profiles, run.id + ".profiles");
      }
    }
    if (bundle.comparison_baseline != null) {
      if (bundle.comparison_baseline.comparison_baseline != null) throw new Error("预载比较包不能再嵌套基线");
      validateBundle(bundle.comparison_baseline);
    }
    return bundle;
  }

  function rejectDuplicateKeys(text) {
    const containers = [];
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (char === "{" || char === "[") containers.push(char === "{" ? new Set() : null);
      else if (char === "}" || char === "]") containers.pop();
      else if (char === '"') {
        const begin = i;
        for (i++; i < text.length; i++) { if (text[i] === "\\") { i++; continue; } if (text[i] === '"') break; }
        let next = i + 1;
        while (/\s/.test(text[next] || "") && next < text.length) next++;
        if (text[next] === ":") {
          const key = JSON.parse(text.slice(begin, i + 1)), keys = containers[containers.length - 1];
          if (keys?.has(key)) throw new Error("JSON 对象包含重复键：" + key);
          keys?.add(key);
        }
      }
    }
  }

  function parseBundle(text, bytes) {
    if ((finite(bytes) && bytes > MAX_FILE_BYTES) || text.length > MAX_FILE_BYTES) throw new Error("数据包超过 64 MiB 读取上限");
    let result;
    try { result = JSON.parse(text); } catch (_) { throw new Error("无法读取 JSON；请选择完整的观察器数据包"); }
    rejectDuplicateKeys(text);
    return validateBundle(result);
  }

  function seriesFromTable(table, key, xKey = "time_s", xScale = 1) {
    if (!table) return [];
    const xi = array(table.columns).indexOf(xKey), yi = array(table.columns).indexOf(key);
    if (xi < 0 || yi < 0) return [];
    const points = [];
    for (let i = 0; i < table.rows.length; i++) {
      const row = table.rows[i];
      if (finite(row[xi])) points.push({ x: row[xi] * xScale, y: finite(row[yi]) ? row[yi] : null, rawTime: row[xi], row: i });
    }
    return points;
  }

  function sampleSeries(samples, channel, clock = "available") {
    const key = clock === "source" ? "source_time_us" : "t_available_us";
    const output = [];
    for (const sample of array(samples)) if (sample.channel_id === channel && finite(sample[key])) output.push({ x: sample[key] / 1e6, y: finite(sample.value) ? sample.value : null, rawTime: sample[key], sample });
    // Source clocks can be nonmonotonic; order for reading, do not invent timing.
    return output.sort((a, b) => a.x - b.x);
  }

  function rangeOf(series, axis = "y", start = -Infinity, end = Infinity) {
    let min = Infinity, max = -Infinity, count = 0;
    for (const points of series) for (const point of points) if (point.x >= start && point.x <= end && finite(point[axis])) {
      if (point[axis] < min) min = point[axis];
      if (point[axis] > max) max = point[axis];
      count++;
    }
    return count ? { min, max, count } : null;
  }

  function extremaSample(points, budget = 1600) {
    if (!Number.isInteger(budget) || budget < 4) throw new Error("显示抽样预算至少为 4");
    if (points.length <= budget) return points.slice();
    const indicesToKeep = [0], bins = Math.max(1, Math.floor((budget - 3) / 4));
    const stride = (points.length - 2) / bins;
    for (let bin = 0; bin < bins; bin++) {
      const begin = 1 + Math.floor(bin * stride), end = Math.min(points.length - 1, 1 + Math.floor((bin + 1) * stride));
      let minIndex = -1, maxIndex = -1;
      for (let i = begin; i < end; i++) {
        if (!finite(points[i].y)) continue;
        if (minIndex < 0 || points[i].y < points[minIndex].y) minIndex = i;
        if (maxIndex < 0 || points[i].y > points[maxIndex].y) maxIndex = i;
      }
      const indices = [...new Set([minIndex, maxIndex].filter(i => i >= 0))].sort((a, b) => a - b);
      for (const i of indices) indicesToKeep.push(i);
    }
    indicesToKeep.push(points.length - 1);
    const output = [];
    let previous = -1;
    for (const index of indicesToKeep) {
      // Check every omitted interval: even multiple gaps in one bucket cannot
      // reconnect retained finite extrema across an absent record.
      for (let i = previous + 1; i < index; i++) if (!finite(points[i].y)) { output.push(points[i]); break; }
      output.push(points[index]); previous = index;
    }
    return output;
  }

  function nearestPoint(points, x) {
    if (!finite(x) || !points.length) return null;
    // Deliberately use all raw points, not render sampling; earliest wins ties.
    let best = null, distance = Infinity;
    for (const point of points) if (finite(point.x)) {
      const d = Math.abs(point.x - x);
      if (d < distance) { distance = d; best = point; }
    }
    return best;
  }

  function differenceSeries(a, b, unitA, unitB) {
    if (unitA !== unitB) return { points: [], matched: 0, missingA: b.length, missingB: a.length, reason: "单位不一致，拒绝差值" };
    const byTime = new Map();
    for (const point of a) {
      if (byTime.has(point.x)) return { points: [], matched: 0, missingA: b.length, missingB: a.length, reason: "A 横轴存在重复坐标，无法唯一匹配" };
      byTime.set(point.x, point);
    }
    const points = [], used = new Set(), seenB = new Set();
    let missingA = 0;
    for (const point of b) {
      if (seenB.has(point.x)) return { points: [], matched: 0, missingA: b.length, missingB: a.length, reason: "B 横轴存在重复坐标，无法唯一匹配" };
      seenB.add(point.x);
      const other = byTime.get(point.x);
      if (!other) { missingA++; points.push({ x: point.x, y: null, rawTime: point.rawTime }); continue; }
      used.add(point.x);
      const delta = finite(point.y) && finite(other.y) ? point.y - other.y : null;
      points.push({ x: point.x, y: finite(delta) ? delta : null, rawTime: point.rawTime });
    }
    for (const point of a) if (!seenB.has(point.x)) points.push({ x: point.x, y: null, rawTime: point.rawTime });
    points.sort((aPoint, bPoint) => aPoint.x - bPoint.x);
    return { points, matched: points.filter(p => finite(p.y)).length, missingA, missingB: a.length - used.size, reason: used.size ? "仅使用完全相同的导出坐标" : "没有相同导出坐标；不插值或时移" };
  }

  function profileTimes(table) {
    if (!table) return [];
    const ti = table.columns.indexOf("time_s");
    if (ti < 0) return [];
    const values = new Set();
    for (const row of table.rows) if (finite(row[ti])) values.add(row[ti]);
    return [...values].sort((a, b) => a - b);
  }

  function profileAt(table, time) {
    if (!table || !finite(time)) return null;
    const ti = table.columns.indexOf("time_s");
    if (ti < 0) return null;
    return { ...table, rows: table.rows.filter(row => row[ti] === time) };
  }

  function canonical(value) {
    if (Array.isArray(value)) return "[" + value.map(canonical).join(",") + "]";
    if (plain(value)) return "{" + Object.keys(value).sort().map(key => JSON.stringify(key) + ":" + canonical(value[key])).join(",") + "}";
    return JSON.stringify(value);
  }

  function comparisonNotes(a, b) {
    const notes = [];
    const pa = a.run.provenance || {}, pb = b.run.provenance || {};
    const ha = pa.heart || {}, hb = pb.heart || {};
    for (const [key, label] of [["model_config", "模型参数"], ["engine_config", "积分 / 随机源 / 命令配置"], ["sensors", "传感器配置"], ["controller", "控制器"]]) {
      if (ha[key] == null || hb[key] == null) notes.push(label + "：至少一包未提供，无法核实相同");
      else notes.push(label + "：" + (canonical(ha[key]) === canonical(hb[key]) ? "导出值相同" : "导出值不同，差异不能归因于单项改动"));
    }
    if (pa.initial_state?.cross_iteration === true && pb.initial_state?.cross_iteration === true && pa.initial_state?.identity && pa.initial_state.identity === pb.initial_state?.identity) notes.push("跨迭代初态：已导出相同身份；仍以快照协议适用域为限");
    else notes.push("跨迭代初态：未证明一致；同次 demo 的共享分叉不等于跨版本快照相同");
    if (a.run.source_sha256 == null || b.run.source_sha256 == null) notes.push("源码身份：至少一包未提供");
    else notes.push("打包源码哈希：" + (canonical(a.run.source_sha256) === canonical(b.run.source_sha256) ? "相同" : "不同") + "；历史运行归属须另看 source_status");
    for (const [label, item] of [["A", a], ["B", b]]) if (item.run.source_status !== "RECORDED_SOURCE_MATCH") notes.push(label + " 来源状态：" + (item.run.source_status || "未提供"));
    if (a.run.id === b.run.id) notes.push("A / B 为同一 run ID；这是同包阅读对照，不是新迭代证据");
    return notes;
  }

  function metricComparison(aCase, bCase, aDefinitions = {}, bDefinitions = {}) {
    const keys = new Set([...Object.keys(aCase?.metrics || {}), ...Object.keys(bCase?.metrics || {})]);
    const results = [];
    const wa = aCase?.metric_window_us || aCase?.window_us, wb = bCase?.metric_window_us || bCase?.window_us;
    for (const key of keys) {
      const da = aDefinitions[key], db = bDefinitions[key], a = aCase?.metrics?.[key], b = bCase?.metrics?.[key];
      let reason = "同单位、定义及统计窗；原始 B − A";
      let comparable = finite(a) && finite(b);
      if (!comparable) reason = "至少一侧缺少有限数值";
      else if (!da || !db || !da.unit || da.unit !== db.unit) { comparable = false; reason = "单位缺失或不同"; }
      else if (!da.definition || canonical(da) !== canonical(db)) { comparable = false; reason = "指标定义或方法缺失 / 不同"; }
      else if (!wa || !wb || canonical(wa) !== canonical(wb)) { comparable = false; reason = "完整统计窗缺失或不同"; }
      const difference = comparable ? b - a : null;
      if (difference !== null && !finite(difference)) { comparable = false; reason = "数值差超出可表示范围"; }
      results.push({ key, label: db?.label || da?.label || key, unit: db?.unit || da?.unit || "未提供", a, b, difference: comparable ? difference : null, reason });
    }
    return results;
  }

  const exported = { SCHEMA, MAX_FILE_BYTES, parseBundle, validateBundle, validateTable, escapeText, finite, seriesFromTable, sampleSeries, rangeOf, extremaSample, nearestPoint, differenceSeries, profileTimes, profileAt, canonical, comparisonNotes, metricComparison };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  if (typeof document === "undefined") return;

  const $ = id => document.getElementById(id);
  const state = { current: null, a: null, b: null, tracks: new Set(DEFAULT_TRACKS), start: 0, end: 1, cursorA: null, cursorB: null, heartCache: new Map() };

  function notify(message, error = false) { $("message").textContent = message; $("message").classList.toggle("error", error); $("message").hidden = !message; }
  function writeJson(id, value) { $(id).textContent = JSON.stringify(value, null, 2); }
  function optionList(id, choices, preferred) {
    const select = $(id), old = preferred === undefined ? select.value : String(preferred);
    select.replaceChildren();
    for (const choice of choices) {
      const option = document.createElement("option");
      option.value = String(choice.value); option.textContent = String(choice.label);
      select.append(option);
    }
    if (choices.some(choice => String(choice.value) === old)) select.value = old;
  }
  function table(id, headings, rows) {
    const target = $(id), head = document.createElement("thead"), tr = document.createElement("tr"), body = document.createElement("tbody");
    for (const text of headings) { const th = document.createElement("th"); th.textContent = text; tr.append(th); }
    head.append(tr);
    for (const values of rows) {
      const line = document.createElement("tr");
      for (const value of values) {
        const td = document.createElement("td");
        if (plain(value) && Object.hasOwn(value, "text")) { td.textContent = value.text; if (value.className) td.className = value.className; if (value.title) td.title = value.title; }
        else td.textContent = value == null ? "未提供" : String(value);
        line.append(td);
      }
      body.append(line);
    }
    if (!rows.length) { const line = document.createElement("tr"), td = document.createElement("td"); td.colSpan = headings.length; td.textContent = "未提供记录"; line.append(td); body.append(line); }
    target.replaceChildren(head, body);
  }
  const num = value => ({ text: numberText(value), className: "num" });

  function boundsForCase(item) {
    const index = item.columns.indexOf("time_us");
    return item.rows.length ? [item.rows[0][index] / 1e6, item.rows[item.rows.length - 1][index] / 1e6] : [0, 1];
  }
  function currentCase() { return state.current?.heart?.cases?.[$("heart-case").value] || null; }
  function channels() { return array(state.current?.heart?.channels).filter(channel => channel.key !== "time_us"); }
  function truth(item, key) {
    let itemCache = state.heartCache.get(item);
    if (!itemCache) { itemCache = new Map(); state.heartCache.set(item, itemCache); }
    if (!itemCache.has(key)) itemCache.set(key, seriesFromTable(item, key, "time_us", 1e-6));
    return itemCache.get(key);
  }

  function setCurrent(bundle) {
    state.current = bundle; state.b = bundle; state.heartCache.clear();
    if (bundle.comparison_baseline) state.a = bundle.comparison_baseline;
    $("download-current").disabled = false;
    $("run-label").textContent = bundle.run.label || bundle.run.id;
    $("run-id").textContent = bundle.run.id;
    renderIdentity(); initHeart(); initArterial(); initCompare();
    notify("已载入 " + bundle.run.id + "。显示原始导出；文件哈希与源代码身份见来源详情。");
  }
  function renderIdentity() {
    const bundle = state.current, container = $("identity-summary"); container.replaceChildren();
    function p(text, className) { const el = document.createElement("p"); el.textContent = text; if (className) el.className = className; container.append(el); }
    p("运行：" + bundle.run.id + " · 数据包生成：" + (bundle.run.generated_utc || "未提供"));
    p("来源状态：" + (bundle.run.source_status || "未提供") + "。打包 Git 身份不替代历史运行源码身份。", "callout" + (String(bundle.run.source_status).includes("MISMATCH") ? " danger" : ""));
    p("核心显示单位：心脏 mmHg / mL / s，接口整数 μs；独立 1D 使用 SI。已交付 AP / ECG 与真值分开，源时刻缺失不补造。");
    p("独立 1D 尚未与 0D 演示耦合；当前为工程场景。没有患者 / 实际执行器校准，也没有临床验证完成的结论。");
    const notes = [...array(bundle.warnings), ...array(bundle.capabilities).map(v => typeof v === "string" ? v : JSON.stringify(v))];
    if (notes.length) { const ul = document.createElement("ul"); for (const note of notes) { const li = document.createElement("li"); li.textContent = note; ul.append(li); } container.append(ul); }
    writeJson("identity-json", bundle.run);
  }

  function initHeart() {
    const cases = state.current?.heart?.cases || {}, keys = Object.keys(cases).filter(key => cases[key].rows.length);
    $("heart-empty").hidden = !!keys.length; $("heart-content").hidden = !keys.length;
    if (!keys.length) return;
    optionList("heart-case", keys.map(key => ({ value: key, label: cases[key].label || key })));
    const trackContainer = $("heart-tracks"); trackContainer.replaceChildren();
    const groups = new Map();
    for (const channel of channels()) { const group = channel.group || "其他"; if (!groups.has(group)) groups.set(group, []); groups.get(group).push(channel); }
    for (const [name, group] of groups) {
      const row = document.createElement("div"), title = document.createElement("strong"), choices = document.createElement("div");
      row.className = "track-group"; title.textContent = name; choices.className = "track-options";
      for (const channel of group) {
        const label = document.createElement("label"), input = document.createElement("input"), span = document.createElement("span");
        input.type = "checkbox"; input.checked = state.tracks.has(channel.key); input.value = channel.key;
        span.textContent = (channel.label || channel.key) + " / " + (channel.unit || "未提供");
        input.addEventListener("change", () => { if (input.checked) state.tracks.add(channel.key); else state.tracks.delete(channel.key); renderHeart(); });
        label.append(input, span); choices.append(label);
      }
      row.append(title, choices); trackContainer.append(row);
    }
    resetHeartWindow(); initSampleOptions(); renderHeart();
  }
  function initSampleOptions() {
    const samples = array(currentCase()?.samples), unique = new Map();
    for (const sample of samples) if (!unique.has(sample.channel_id)) unique.set(sample.channel_id, sample.units);
    optionList("heart-sample", [{ value: "", label: "隐藏已交付样本" }, ...[...unique].map(([id, unit]) => ({ value: id, label: id + " / " + unit }))]);
  }
  function resetHeartWindow() {
    const item = currentCase(); if (!item) return;
    const [start, end] = boundsForCase(item);
    state.start = $("heart-window").value === "all" ? start : Math.max(start, end - 2); state.end = end;
    state.cursorA = state.start; state.cursorB = state.end;
    syncHeartInputs();
  }
  function syncHeartInputs() { $("heart-start").value = compactTime(state.start); $("heart-end").value = compactTime(state.end); $("cursor-a").value = compactTime(state.cursorA); $("cursor-b").value = compactTime(state.cursorB); }

  function visiblePoints(points, start, end) { return points.filter(point => point.x >= start && point.x <= end); }
  function fraction(value, min, max) { if (min === max) return .5; return (value / 2 - min / 2) / (max / 2 - min / 2); }
  function padded(range) {
    if (!range) return [0, 1];
    if (range.min === range.max) { const pad = Math.max(Math.abs(range.min) * .06, .01); return [finite(range.min - pad) ? range.min - pad : range.min, finite(range.max + pad) ? range.max + pad : range.max]; }
    const pad = (range.max / 2 - range.min / 2) * .15;
    return [finite(range.min - pad) ? range.min - pad : range.min, finite(range.max + pad) ? range.max + pad : range.max];
  }
  function svgText(x, y, text, klass = "axis-label", anchor = "start") { return '<text x="' + x + '" y="' + y + '" class="' + klass + '" text-anchor="' + anchor + '">' + escapeText(text) + "</text>"; }
  function pathFor(points, x, y) {
    let d = "", open = false;
    for (const point of points) {
      if (!finite(point.y)) { open = false; continue; }
      const px = x(point.x), py = y(point.y);
      if (!finite(px) || !finite(py)) { open = false; continue; }
      d += (open ? "L" : "M") + px.toFixed(2) + "," + py.toFixed(2); open = true;
    }
    return d;
  }
  function drawTracks(id, tracks, options = {}) {
    const svg = $(id), width = 1100, left = 160, right = 1078, rowHeight = options.rowHeight || 128;
    let start = options.start, end = options.end;
    const fullX = rangeOf(tracks.flatMap(track => track.series).map(series => series.points), "x");
    if (!finite(start)) start = fullX?.min ?? 0;
    if (!finite(end)) end = fullX?.max ?? 1;
    if (start === end) { start -= .001; end += .001; }
    const height = Math.max(100, tracks.length * rowHeight + 38), x = value => left + fraction(value, start, end) * (right - left);
    svg.setAttribute("viewBox", "0 0 " + width + " " + height); svg.setAttribute("preserveAspectRatio", "none"); svg.style.height = height + "px";
    let content = "";
    if (!tracks.length) content = svgText(width / 2, 52, "请至少选择一条轨道；没有数据时不绘制波形", "missing-label", "middle");
    const ticks = 5;
    for (let trackIndex = 0; trackIndex < tracks.length; trackIndex++) {
      const track = tracks[trackIndex], top = trackIndex * rowHeight + 12, bottom = top + rowHeight - 28;
      const rawSeries = track.series.map(series => visiblePoints(series.points, start, end));
      const range = rangeOf(rawSeries), [min, max] = padded(range), y = value => bottom - fraction(value, min, max) * (bottom - top - 6);
      const clip = id + "-clip-" + trackIndex;
      content += '<defs><clipPath id="' + clip + '"><rect x="' + left + '" y="' + top + '" width="' + (right - left) + '" height="' + (bottom - top + 3) + '"/></clipPath></defs>';
      content += svgText(7, top + 16, track.label, "track-label") + svgText(7, top + 34, track.unit);
      for (let i = 0; i < 3; i++) {
        const value = min * (1 - i / 2) + max * (i / 2), yy = y(value);
        content += '<line class="grid" x1="' + left + '" x2="' + right + '" y1="' + yy + '" y2="' + yy + '"/>' + svgText(left - 8, yy + 4, shortNumber(value), "axis-label", "end");
      }
      for (let i = 0; i <= ticks; i++) {
        const xx = left + i * (right - left) / ticks;
        content += '<line class="grid" x1="' + xx + '" x2="' + xx + '" y1="' + top + '" y2="' + bottom + '" opacity=".55"/>';
      }
      if (!range) content += svgText((left + right) / 2, top + 45, "此窗口没有有限原始样本", "missing-label", "middle");
      for (let seriesIndex = 0; seriesIndex < track.series.length; seriesIndex++) {
        const series = track.series[seriesIndex], points = extremaSample(rawSeries[seriesIndex]);
        content += '<path class="trace-path ' + (series.reference ? "series-reference" : "series-primary") + '" clip-path="url(#' + clip + ')" d="' + pathFor(points, x, y) + '"/>';
        if (options.points && !series.reference && rawSeries[seriesIndex].length <= 2200) for (const point of rawSeries[seriesIndex]) if (finite(point.y)) content += '<circle class="trace-dot" cx="' + x(point.x) + '" cy="' + y(point.y) + '" r="1.8" clip-path="url(#' + clip + ')"/>';
      }
    }
    for (let i = 0; i <= ticks; i++) { const value = start * (1 - i / ticks) + end * i / ticks; content += svgText(left + i * (right - left) / ticks, height - 10, compactTime(value) + " " + (options.xUnit || "s"), "axis-label", "middle"); }
    for (const marker of array(options.markers)) if (marker.x >= start && marker.x <= end) content += '<line class="marker-line ' + (marker.command ? "command-marker" : "") + '" x1="' + x(marker.x) + '" x2="' + x(marker.x) + '" y1="5" y2="' + (height - 32) + '"><title>' + escapeText(marker.label) + "</title></line>";
    for (const [label, value] of array(options.cursors)) if (finite(value) && value >= start && value <= end) content += '<line class="cursor-line" x1="' + x(value) + '" x2="' + x(value) + '" y1="3" y2="' + (height - 32) + '"/>' + svgText(x(value) + 4, 11, label);
    svg.innerHTML = content; // Only generated numeric coordinates and escapeText labels.
    svg.dataset.axisStart = String(start); svg.dataset.axisEnd = String(end); svg.dataset.axisLeft = String(left); svg.dataset.axisRight = String(right);
  }

  function renderHeart() {
    const item = currentCase(); if (!item) return;
    $("heart-source").textContent = "当前分支来源：" + (item.source_status || "未提供") + "。旧 0D 记录仅绑定部分源码；打包身份不补充缺失的历史身份。";
    $("heart-source").classList.toggle("danger", String(item.source_status).includes("MISMATCH"));
    const baseline = state.current.heart.cases.baseline, overlay = $("heart-overlay").checked && $("heart-case").value !== "baseline" && baseline;
    const selectedChannels = channels().filter(channel => state.tracks.has(channel.key));
    const tracks = selectedChannels.map(channel => ({ label: channel.label || channel.key, unit: channel.unit || "未提供", series: [...(overlay ? [{ points: truth(baseline, channel.key), reference: true }] : []), { points: truth(item, channel.key) }] }));
    const sampleId = $("heart-sample").value, clock = $("heart-clock").value;
    if (sampleId) {
      const sample = array(item.samples).find(value => value.channel_id === sampleId);
      tracks.push({ label: "交付 · " + sampleId, unit: (sample?.units || "未提供") + (clock === "source" ? " · 源时刻" : " · 交付时刻"), series: [{ points: sampleSeries(item.samples, sampleId, clock) }] });
    }
    const markers = $("heart-markers").checked ? [...array(item.events).map(event => ({ x: event.at_us / 1e6, label: (EVENT_LABELS[event.name] || event.name) + " · " + event.at_us + " μs" })), ...array(item.commands).filter(command => finite(command.at_us)).map(command => ({ x: command.at_us / 1e6, label: "命令 " + (command.status || "未提供") + " · " + command.at_us + " μs", command: true }))] : [];
    drawTracks("heart-plot", tracks, { start: state.start, end: state.end, points: $("heart-points").checked, markers, cursors: [["A", state.cursorA], ["B", state.cursorB]] });
    const noSource = sampleId && clock === "source" && !sampleSeries(item.samples, sampleId, clock).length;
    $("heart-plot-note").textContent = "真值：整数微秒换算为 s；" + (sampleId ? (clock === "source" ? "已交付样本按原 source_time_us 显示；源时钟不保证与物理时钟相同。" : "已交付样本按 t_available_us 显示；不把源时刻作为控制器可读时刻。") : "已交付样本当前隐藏。") + (noSource ? " 当前源时刻未提供，保持空轨道。" : "") + " 密集波形按局部最小/最大值显示抽样；读数使用全部原样本。";
    renderCursors(selectedChannels, sampleId, clock); renderMetrics(item); renderPv(item); renderEvents(item);
  }
  function renderCursors(selectedChannels, sampleId, clock) {
    const item = currentCase();
    function reading(points, time, rawUnit = "μs") {
      const point = nearestPoint(points, time);
      if (!point) return "未提供";
      const sample = point.sample;
      const detail = sample ? " [序号 " + (sample.sequence_id ?? "未提供") + "；源时钟 " + (sample.source_clock_id ?? "未提供") + "；质量 " + (sample.observable_quality ?? "未提供") + "]" : "";
      return numberText(point.y) + " @ " + numberText(point.rawTime) + " " + rawUnit + detail;
    }
    const rows = selectedChannels.map(channel => [channel.label || channel.key, channel.unit, { text: reading(truth(item, channel.key), state.cursorA), className: "num" }, { text: reading(truth(item, channel.key), state.cursorB), className: "num" }]);
    if (sampleId) {
      const points = sampleSeries(item.samples, sampleId, clock), unit = points[0]?.sample?.units || "未提供";
      rows.push(["交付 · " + sampleId + " / " + (clock === "source" ? "源时刻" : "交付时刻"), unit, { text: reading(points, state.cursorA), className: "num" }, { text: reading(points, state.cursorB), className: "num" }]);
    }
    table("cursor-table", ["通道", "单位", "A 最近样本值 @ 原时刻", "B 最近样本值 @ 原时刻"], rows);
    $("cursor-delta").textContent = "游标 B − A = " + shortNumber((state.cursorB - state.cursorA) * 1000) + " ms";
  }
  function renderMetrics(item) {
    const definitions = state.current.heart.metric_definitions || {}, window = item.metric_window_us || item.window_us;
    $("metric-window").textContent = window ? "统计窗 " + window[0] + "—" + window[1] + " μs（" + shortNumber((window[1] - window[0]) / 1e6) + " s）。缩放和游标不改变这些指标。" : "完整指标统计窗未提供；缩放不重算。";
    const container = $("heart-metrics"); container.replaceChildren();
    for (const [key, value] of Object.entries(item.metrics || {})) {
      const definition = definitions[key] || {}, card = document.createElement("div"), result = document.createElement("b"), label = document.createElement("span"), explanation = document.createElement("small");
      card.className = "metric"; result.textContent = shortNumber(value) + " " + (definition.unit || ""); result.title = "原始值：" + numberText(value); label.textContent = definition.label || key; explanation.textContent = definition.definition || "指标定义未提供";
      card.append(result, label, explanation); container.append(card);
    }
  }
  function renderPv(item) {
    const pi = item.columns.indexOf("p_lv"), vi = item.columns.indexOf("v_lv"), ti = item.columns.indexOf("time_us"), points = [];
    if (pi >= 0 && vi >= 0) for (const row of item.rows) if (row[ti] / 1e6 >= state.start && row[ti] / 1e6 <= state.end && finite(row[pi]) && finite(row[vi])) points.push({ x: row[vi], y: row[pi] });
    const svg = $("pv-plot"), width = 600, height = 270, left = 65, right = 578, top = 20, bottom = 226;
    svg.setAttribute("viewBox", "0 0 " + width + " " + height);
    const xr = rangeOf([points], "x"), yr = rangeOf([points]);
    if (!xr || !yr) { svg.innerHTML = svgText(300, 120, "当前窗未提供有限 P/V 数据", "missing-label", "middle"); return; }
    const [xmin, xmax] = padded(xr), [ymin, ymax] = padded(yr), x = value => left + fraction(value, xmin, xmax) * (right - left), y = value => bottom - fraction(value, ymin, ymax) * (bottom - top);
    let content = "";
    for (let i = 0; i <= 4; i++) {
      const xx = left + i * (right - left) / 4, yy = bottom - i * (bottom - top) / 4;
      content += '<line class="grid" x1="' + xx + '" x2="' + xx + '" y1="' + top + '" y2="' + bottom + '"/><line class="grid" x1="' + left + '" x2="' + right + '" y1="' + yy + '" y2="' + yy + '"/>';
      content += svgText(xx, bottom + 18, shortNumber(xmin * (1 - i / 4) + xmax * i / 4), "axis-label", "middle") + svgText(left - 7, yy + 4, shortNumber(ymin * (1 - i / 4) + ymax * i / 4), "axis-label", "end");
    }
    content += '<path class="trace-path series-primary" d="' + pathFor(extremaSample(points), x, y) + '"/>';
    for (const [label, point] of [["起", points[0]], ["止", points[points.length - 1]]]) content += '<circle class="trace-dot" cx="' + x(point.x) + '" cy="' + y(point.y) + '" r="3"/>' + svgText(x(point.x) + 5, y(point.y) - 5, label);
    content += svgText(305, 265, "左室容积 / mL", "axis-label", "middle") + svgText(8, 13, "压力 / mmHg");
    svg.innerHTML = content;
  }
  function renderEvents(item) {
    const events = array(item.events), commands = array(item.commands);
    $("event-heading").textContent = "事件 · " + events.length + " 条导出记录";
    table("heart-events", ["事件", "原始时刻 / μs", "定义"], events.map(event => [EVENT_LABELS[event.name] || event.name, num(event.at_us), event.definition || event.name]));
    $("command-heading").textContent = "命令日志 · " + commands.length + " 条记录";
    table("heart-commands", ["命令 ID", "状态", "原始时刻 / μs", "原因"], commands.map(command => [command.command_id || "未提供", command.status || "未提供", num(command.at_us), command.reason || "未提供"]));
  }

  function arterialRuns(bundle = state.current) { return array(bundle?.arterial1d?.runs); }
  function currentArterialRun() { return arterialRuns().find(run => run.id === $("arterial-run").value); }
  function initArterial() {
    const runs = arterialRuns(); $("arterial-empty").hidden = !!runs.length; $("arterial-content").hidden = !runs.length;
    if (!runs.length) return;
    const suites = [...new Set(runs.map(run => run.suite || "未分类"))];
    const labels = { matched: "传播 / 匹配终端", reflections: "终端反射", junction: "对称分叉", boileau: "Boileau 公开单脉冲" };
    optionList("arterial-suite", suites.map(suite => ({ value: suite, label: labels[suite] || suite }))); updateArterialMethods();
  }
  function updateArterialMethods() {
    const runs = arterialRuns().filter(run => (run.suite || "未分类") === $("arterial-suite").value), methods = [...new Set(runs.map(run => run.method || "未提供"))];
    const existing = $("arterial-method").value;
    const latest = runs.find(run => !run.historical)?.method;
    optionList("arterial-method", methods.map(method => ({ value: method, label: method })), methods.includes(existing) ? existing : latest); updateArterialRuns();
  }
  function updateArterialRuns() {
    const runs = arterialRuns().filter(run => (run.suite || "未分类") === $("arterial-suite").value && (run.method || "未提供") === $("arterial-method").value);
    let finest = runs[0];
    for (const run of runs) if (finite(run.cells) && (!finite(finest?.cells) || run.cells > finest.cells)) finest = run;
    const existing = $("arterial-run").value;
    optionList("arterial-run", runs.map(run => ({ value: run.id, label: (run.cells ?? "?") + " 格 · " + (run.label || run.id) })), runs.some(run => run.id === existing) ? existing : finest?.id); updateArterialFields();
  }
  function fieldOptions(tables) {
    const fields = new Map();
    for (const item of tables) if (item) for (const key of item.columns) if (!["time_s", "x_m", "probe_x_m"].includes(key) && !key.startsWith("reference_") && key !== "error_pa") fields.set(key, item.units?.[key] || "未提供");
    return [...fields].map(([value, unit]) => ({ value, label: value + " / " + unit }));
  }
  function updateArterialFields() {
    const run = currentArterialRun(); if (!run) return;
    const options = fieldOptions([run.trace, run.profiles]); optionList("arterial-field", options, options.some(item => item.value === "pressure_pa") ? "pressure_pa" : undefined);
    optionList("profile-time", profileTimes(run.profiles).map(time => ({ value: time, label: numberText(time) }))); renderArterial();
  }
  function referenceField(table, key) {
    if (key === "pressure_pa" && table?.columns.includes("reference_pa")) return "reference_pa";
    return null;
  }
  function runTrack(table, key, xKey = "time_s") {
    const reference = referenceField(table, key);
    return { label: key, unit: table?.units?.[key] || "未提供", series: [...(reference ? [{ points: seriesFromTable(table, reference, xKey), reference: true }] : []), { points: seriesFromTable(table, key, xKey) }] };
  }
  function findSummaryMetrics(value, path = "", output = [], depth = 0) {
    if (!plain(value) || depth > 4) return output;
    for (const [key, item] of Object.entries(value)) {
      const full = path ? path + "." + key : key;
      if ((finite(item) || item === null) && /error|residual|minimum|maximum|_min_|_max_|peak|arrival|reflection/.test(key) && !/sha|hash/.test(key)) output.push([full, item]);
      else if (plain(item)) findSummaryMetrics(item, full, output, depth + 1);
    }
    return output;
  }
  function renderArterial() {
    const run = currentArterialRun(); if (!run) return;
    const key = $("arterial-field").value, time = Number($("profile-time").value), times = profileTimes(run.profiles), status = $("arterial-status");
    status.classList.toggle("danger", String(run.status).startsWith("FAIL") || String(run.source_status).includes("MISMATCH"));
    status.replaceChildren();
    const title = document.createElement("strong"); title.textContent = run.status + " · " + (run.source_status || "来源未提供"); status.append(title);
    const description = document.createElement("p"); description.textContent = (run.historical ? "保留的历史方法结果。" : "") + "声明范围内的软件 / 数值检查；不能代表心脏耦合或临床通过。"; status.append(description);
    if (array(run.failures).length) { const ul = document.createElement("ul"); for (const failure of run.failures) { const li = document.createElement("li"); li.textContent = failure; ul.append(li); } status.append(ul); }
    $("trace-empty").hidden = !!run.trace; $("arterial-trace").hidden = !run.trace;
    if (run.trace) drawTracks("arterial-trace", [runTrack(run.trace, key)], { rowHeight: 270, xUnit: "s" });
    $("trace-note").textContent = run.trace ? "横轴为 time_s；纵轴使用导出 SI 单位。" + (referenceField(run.trace, key) ? " 实线：求解器；虚线：同文件 reference_pa。" : " 当前量未提供对应参考曲线。") : "未提供探针时间序列；没有合成或补出波形。";
    $("profile-empty").hidden = !!run.profiles; $("arterial-profile").hidden = !run.profiles; $("profile-time").disabled = !run.profiles;
    if (run.profiles) drawTracks("arterial-profile", [runTrack(profileAt(run.profiles, time), key, "x_m")], { rowHeight: 270, xUnit: "m" });
    $("profile-note").textContent = run.profiles ? "横轴 x_m / m；真实导出时刻 t = " + numberText(time) + " s。共 " + times.length + " 个实际剖面时刻，不在时刻之间插值。" + (run.suite === "boileau" ? " Boileau 的八个空间剖面不是连续时间探针。" : "") + " 负压、超调与振铃保留。" : "未提供空间剖面。";
    const group = arterialRuns().filter(other => other.suite === run.suite), rows = [];
    for (const other of group) {
      const metrics = findSummaryMetrics(other.summary);
      const text = metrics.slice(0, 9).map(([name, value]) => name + " = " + numberText(value)).join("; ");
      rows.push([other.method || "未提供", other.cells ?? "未提供", { text: other.status || "未声明", className: String(other.status).startsWith("FAIL") ? "result-fail" : "" }, text || "见 run 原始摘要", other.source_status || "未提供"]);
    }
    table("arterial-results", ["方法", "网格", "原始状态", "原始误差 / 极值（保留字段名中的单位）", "来源"], rows);
    writeJson("arterial-summary", { id: run.id, source_status: run.source_status, source_identity: run.source_identity, failures: run.failures, summary: run.summary });
  }

  function initCompare() {
    $("compare-a-label").textContent = state.a ? (state.a.run.label || state.a.run.id) + " · " + state.a.run.id : "尚未载入；选择或拖入 JSON 数据包";
    $("compare-b-label").textContent = state.b ? (state.b.run.label || state.b.run.id) + " · " + state.b.run.id : "尚未载入";
    const ready = !!(state.a && state.b); $("compare-empty").hidden = ready; $("compare-content").hidden = !ready;
    if (!ready) return;
    updateCompareSelectors();
  }
  function updateCompareSelectors() {
    if (!state.a || !state.b) return;
    const mode = $("compare-mode").value, heart = mode === "heart";
    $("compare-case-label").hidden = !heart; $("compare-run-a-label").hidden = heart; $("compare-run-b-label").hidden = heart; $("compare-time-label").hidden = mode !== "profile";
    if (heart) {
      const aCases = state.a.heart?.cases || {}, bCases = state.b.heart?.cases || {}, common = Object.keys(aCases).filter(key => Object.hasOwn(bCases, key));
      optionList("compare-case", common.map(key => ({ value: key, label: bCases[key].label || key })));
    } else {
      const prop = mode === "trace" ? "trace" : "profiles";
      for (const [slot, bundle] of [["a", state.a], ["b", state.b]]) optionList("compare-run-" + slot, arterialRuns(bundle).filter(run => run[prop]).map(run => ({ value: run.id, label: run.suite + " · " + run.method + " · " + run.cells + " 格 · " + run.id })));
    }
    updateCompareFields();
  }
  function compareInputs() {
    const mode = $("compare-mode").value;
    if (mode === "heart") {
      const key = $("compare-case").value;
      return { a: state.a?.heart?.cases?.[key], b: state.b?.heart?.cases?.[key], xKey: "time_us", scale: 1e-6, unitX: "s" };
    }
    const prop = mode === "trace" ? "trace" : "profiles", ra = arterialRuns(state.a).find(run => run.id === $("compare-run-a").value), rb = arterialRuns(state.b).find(run => run.id === $("compare-run-b").value);
    return { a: ra?.[prop], b: rb?.[prop], ra, rb, xKey: mode === "trace" ? "time_s" : "x_m", scale: 1, unitX: mode === "trace" ? "s" : "m" };
  }
  function updateCompareFields() {
    const inputs = compareInputs(), mode = $("compare-mode").value;
    const common = inputs.a && inputs.b ? inputs.a.columns.filter(key => inputs.b.columns.includes(key) && !["time_us", "time_s", "x_m", "probe_x_m"].includes(key)) : [];
    const channel = key => array(state.b?.heart?.channels).find(item => item.key === key);
    optionList("compare-field", common.map(key => ({ value: key, label: (mode === "heart" ? channel(key)?.label || key : key) + " / " + (mode === "heart" ? channel(key)?.unit || "未提供" : inputs.b.units?.[key] || "未提供") })));
    if (mode === "profile") { const bTimes = new Set(profileTimes(inputs.b)); optionList("compare-time", profileTimes(inputs.a).filter(time => bTimes.has(time)).map(time => ({ value: time, label: numberText(time) }))); }
    renderCompare();
  }
  function renderCompare() {
    if (!state.a || !state.b) return;
    const mode = $("compare-mode").value, inputs = compareInputs(), key = $("compare-field").value, notes = comparisonNotes(state.a, state.b);
    let a = inputs.a, b = inputs.b;
    if (mode === "profile") {
      const time = $("compare-time").value;
      if (!time) { a = null; b = null; notes.push("没有共有的真实剖面时刻；拒绝在时间上插值。"); }
      else { a = profileAt(a, Number(time)); b = profileAt(b, Number(time)); }
    }
    const ca = array(state.a?.heart?.channels).find(channel => channel.key === key), cb = array(state.b?.heart?.channels).find(channel => channel.key === key);
    const unitA = mode === "heart" ? ca?.unit : a?.units?.[key], unitB = mode === "heart" ? cb?.unit : b?.units?.[key];
    const pointsA = seriesFromTable(a, key, inputs.xKey, inputs.scale), pointsB = seriesFromTable(b, key, inputs.xKey, inputs.scale);
    let allowed = !!a && !!b && !!unitA && unitA === unitB;
    if (!a || !b) notes.push("所选分支或运行至少有一侧未提供，保持空图。");
    if (!unitA || !unitB || unitA !== unitB) notes.push("所选量的单位缺失或不一致；不叠加或计算差值。");
    if (mode === "heart") notes.push("所选分支来源：A " + (a?.source_status || "未提供") + "；B " + (b?.source_status || "未提供"));
    if (mode !== "heart" && inputs.ra && inputs.rb) {
      notes.push("A / B 1D 套件：" + inputs.ra.suite + " / " + inputs.rb.suite + "；方法：" + inputs.ra.method + " / " + inputs.rb.method + "；网格：" + inputs.ra.cells + " / " + inputs.rb.cells);
      if (inputs.ra.suite !== inputs.rb.suite) { allowed = false; notes.push("套件不同，场景不一致；停止波形差值。"); }
      notes.push("1D 运行来源：A " + (inputs.ra.source_status || "未提供") + "；B " + (inputs.rb.source_status || "未提供"));
    }
    const container = $("comparability"); container.replaceChildren();
    const ul = document.createElement("ul"); for (const note of notes) { const li = document.createElement("li"); li.textContent = note; ul.append(li); } container.append(ul);
    const difference = allowed ? differenceSeries(pointsA, pointsB, unitA, unitB) : { points: [], matched: 0, missingA: pointsB.length, missingB: pointsA.length, reason: "记录或单位不兼容，未计算差值" };
    drawTracks("compare-plot", [{ label: key || "未提供共有通道", unit: unitB || "未提供", series: allowed ? [{ points: pointsA, reference: true }, { points: pointsB }] : [] }], { rowHeight: 270, xUnit: inputs.unitX });
    drawTracks("difference-plot", [{ label: "B − A", unit: unitB || "未提供", series: [{ points: difference.points }] }], { rowHeight: 210, xUnit: inputs.unitX });
    $("difference-note").textContent = difference.reason + "。有限差值点 " + difference.matched + "；B 点缺 A 对应坐标 " + difference.missingA + "，A 点缺 B 对应坐标 " + difference.missingB + "。没有对应记录保持缺失。";
    if (mode === "heart") {
      const metricRows = metricComparison(inputs.a, inputs.b, state.a.heart?.metric_definitions, state.b.heart?.metric_definitions);
      table("compare-metrics", ["指标", "单位", "A 原始值", "B 原始值", "B − A", "可比条件"], metricRows.map(row => [row.label, row.unit, num(row.a), num(row.b), num(row.difference), row.reason]));
    } else table("compare-metrics", ["范围", "说明"], [["1D", "原始数值误差、到达缺失、声明状态等见独立 1D 页与下方原始运行摘要；不将不同网格或指标定义混算为单一改进分数。"]]);
    function runIdentity(run) { if (!run) return undefined; const { trace, profiles, ...identity } = run; void trace; void profiles; return identity; }
    writeJson("compare-identity", { A: { run: state.a.run, selected_1d: runIdentity(inputs.ra) }, B: { run: state.b.run, selected_1d: runIdentity(inputs.rb) } });
  }

  async function loadFile(file, slot) {
    if (!file) return;
    try {
      if (!file.name.toLowerCase().endsWith(".json")) throw new Error("请选择 .json 数据包");
      if (file.size > MAX_FILE_BYTES) throw new Error("数据包超过 64 MiB 读取上限");
      const bundle = parseBundle(await file.text(), file.size);
      if (slot === "current") setCurrent(bundle);
      else { state[slot] = bundle; initCompare(); notify("已载入比较 " + slot.toUpperCase() + "：" + bundle.run.id); }
    } catch (error) { notify(error.message, true); }
  }
  function setTab(name) {
    for (const button of document.querySelectorAll("[data-tab]")) { const selected = button.dataset.tab === name; button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1; $("panel-" + button.dataset.tab).hidden = !selected; }
  }
  for (const button of document.querySelectorAll("[data-tab]")) {
    button.addEventListener("click", () => setTab(button.dataset.tab));
    button.addEventListener("keydown", event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; event.preventDefault(); const buttons = [...document.querySelectorAll("[data-tab]")], index = buttons.indexOf(button), next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length; setTab(buttons[next].dataset.tab); buttons[next].focus(); });
  }
  $("identity-toggle").addEventListener("click", () => { const open = $("identity").hidden; $("identity").hidden = !open; $("identity-toggle").setAttribute("aria-expanded", String(open)); });
  $("theme").addEventListener("click", () => { const dark = document.documentElement.dataset.theme !== "dark"; document.documentElement.dataset.theme = dark ? "dark" : "light"; $("theme").setAttribute("aria-pressed", String(dark)); $("theme").textContent = dark ? "浅色" : "深色"; });
  for (const slot of ["current", "a", "b"]) $("load-" + slot).addEventListener("change", event => loadFile(event.target.files[0], slot));
  for (const drop of document.querySelectorAll("[data-slot]")) {
    drop.addEventListener("dragover", event => { event.preventDefault(); drop.classList.add("drag-over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("drag-over"));
    drop.addEventListener("drop", event => { event.preventDefault(); drop.classList.remove("drag-over"); if (event.dataTransfer.files.length !== 1) notify("每次拖入一个 JSON 数据包", true); else loadFile(event.dataTransfer.files[0], drop.dataset.slot); });
  }
  $("download-current").addEventListener("click", () => {
    if (!state.current) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.current)], { type: "application/json" })), link = document.createElement("a");
    link.href = url; link.download = state.current.run.id.replace(/[^a-z0-9_.-]/gi, "_").slice(0, 100) + ".json"; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $("heart-case").addEventListener("change", () => { resetHeartWindow(); initSampleOptions(); renderHeart(); });
  $("heart-window").addEventListener("change", () => { resetHeartWindow(); renderHeart(); });
  for (const id of ["heart-overlay", "heart-sample", "heart-clock", "heart-markers", "heart-points"]) $(id).addEventListener("change", renderHeart);
  for (const id of ["heart-start", "heart-end"]) $(id).addEventListener("change", () => {
    const start = Number($("heart-start").value), end = Number($("heart-end").value), item = currentCase();
    if (!item) return;
    const bounds = boundsForCase(item);
    if (!finite(start) || !finite(end) || start >= end || start < bounds[0] || end > bounds[1]) { notify("显示窗需要在完整导出时间内，且起点小于终点。", true); syncHeartInputs(); return; }
    state.start = start; state.end = end; renderHeart(); notify("");
  });
  function zoom(factor) {
    const item = currentCase(); if (!item) return;
    const [lo, hi] = boundsForCase(item), mid = (state.start + state.end) / 2, width = Math.min(hi - lo, Math.max(.000001, (state.end - state.start) * factor));
    state.start = Math.max(lo, Math.min(hi - width, mid - width / 2)); state.end = state.start + width; syncHeartInputs(); renderHeart();
  }
  $("zoom-in").addEventListener("click", () => zoom(.5)); $("zoom-out").addEventListener("click", () => zoom(2));
  $("heart-reset").addEventListener("click", () => { $("heart-window").value = "all"; resetHeartWindow(); renderHeart(); });
  for (const key of ["a", "b"]) $("cursor-" + key).addEventListener("change", () => { const value = Number($("cursor-" + key).value); if (!finite(value)) { notify("游标时刻必须是有限数值", true); return; } state[key === "a" ? "cursorA" : "cursorB"] = value; renderHeart(); });
  $("heart-plot").addEventListener("click", event => {
    const svg = $("heart-plot"), rect = svg.getBoundingClientRect(), coordinate = (event.clientX - rect.left) / rect.width * 1100, left = Number(svg.dataset.axisLeft), right = Number(svg.dataset.axisRight);
    if (coordinate < left || coordinate > right) return;
    const value = state.start + (coordinate - left) / (right - left) * (state.end - state.start);
    state[$("cursor-active").value === "a" ? "cursorA" : "cursorB"] = value; syncHeartInputs(); renderHeart();
  });
  $("arterial-suite").addEventListener("change", updateArterialMethods); $("arterial-method").addEventListener("change", updateArterialRuns); $("arterial-run").addEventListener("change", updateArterialFields);
  for (const id of ["arterial-field", "profile-time"]) $(id).addEventListener("change", renderArterial);
  $("compare-use-current").addEventListener("click", () => { state.b = state.current; initCompare(); });
  $("compare-mode").addEventListener("change", updateCompareSelectors);
  for (const id of ["compare-case", "compare-run-a", "compare-run-b"]) $(id).addEventListener("change", updateCompareFields);
  for (const id of ["compare-field", "compare-time"]) $(id).addEventListener("change", renderCompare);
  const embedded = $("observer-bundle").textContent.trim();
  if (embedded && !embedded.startsWith("__") && embedded !== "{}") {
    try { setCurrent(parseBundle(embedded)); } catch (error) { notify("内嵌数据包未载入：" + error.message, true); }
  }
})();
