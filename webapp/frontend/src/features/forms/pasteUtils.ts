export function parseCellNum(raw: string): number | null {
  const cleaned = raw.trim().replace(/\s+/g, "").replace(",", ".");
  if (!cleaned) return null;
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function splitRows(rawText: string): string[][] {
  return rawText
    .replace(/\r\n?/g, "\n")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.includes("\t")) return line.split("\t").map((c) => c.trim());
      if (line.includes(";")) return line.split(";").map((c) => c.trim());
      return line.split(/\s{2,}|\s+/).map((c) => c.trim());
    })
    .filter((cols) => cols.length > 0);
}

function looksLikeTime(token: string): boolean {
  return /^\d{1,2}:\d{2}(:\d{2})?$/.test(token.trim());
}

function hasAtLeastOneNumber(cols: string[]): boolean {
  return cols.some((c) => parseCellNum(c) !== null);
}

export function isTabularClipboard(text: string): boolean {
  const normalized = text.replace(/\r\n?/g, "\n").trim();
  if (!normalized) return false;
  return normalized.includes("\t") || normalized.includes("\n");
}

export function parseFillingPaste(rawText: string): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const cols of splitRows(rawText)) {
    if (!hasAtLeastOneNumber(cols)) continue;
    const hasTime = looksLikeTime(cols[0]);
    const nums = (hasTime ? cols.slice(1) : cols).map(parseCellNum);
    if (nums.every((n) => n === null)) continue;
    out.push({
      time_str: hasTime ? cols[0] : "",
      meter_reading_m3: nums[0] ?? null,
      delta_volume_m3: nums[1] ?? null,
      total_volume_m3: nums[2] ?? nums[0] ?? null,
      water_inlet_temp_c: nums[3] ?? null,
      water_pressure_bar: nums[4] ?? null,
      note: (hasTime ? cols[6] : cols[5]) ?? "",
    });
  }
  return out;
}

export function parseMonitoringPaste(rawText: string): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const cols of splitRows(rawText)) {
    if (!hasAtLeastOneNumber(cols)) continue;
    const hasTime = looksLikeTime(cols[0]);
    const rest = hasTime ? cols.slice(1) : cols;
    const nums = rest.map(parseCellNum);
    if (nums.every((n) => n === null)) continue;
    const soil1 = nums[2] ?? null;
    const pipe1 = nums[3] ?? null;
    const soil2 = nums[4] ?? null;
    const pipe2 = nums[5] ?? null;
    const avgSoil = nums[6] ?? nums[8] ?? soil1;
    const avgPipe = nums[7] ?? nums[9] ?? pipe1;
    out.push({
      time_str: hasTime ? cols[0] : "",
      pressure_bar: nums[0] ?? null,
      ambient_temp_c: nums[1] ?? null,
      soil_1_c: soil1,
      pipe_1_c: pipe1,
      soil_2_c: soil2,
      pipe_2_c: pipe2,
      avg_soil_c: avgSoil,
      avg_pipe_c: avgPipe,
    });
  }
  return out;
}

export function parsePressurizationPaste(rawText: string): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const cols of splitRows(rawText)) {
    if (!hasAtLeastOneNumber(cols)) continue;
    const hasTime = looksLikeTime(cols[0]);
    const nums = (hasTime ? cols.slice(1) : cols).map(parseCellNum);
    if (nums.every((n) => n === null)) continue;
    out.push({
      time_str: hasTime ? cols[0] : "",
      p_initial_bar: nums[0] ?? null,
      p_final_bar: nums[1] ?? null,
      step_water_m3: nums[2] ?? null,
      total_water_m3: nums[3] ?? null,
      water_temp_c: nums[4] ?? null,
      note: "",
    });
  }
  return out;
}

export function parseMeasurementsPaste(rawText: string): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const cols of splitRows(rawText)) {
    const nums = cols.map(parseCellNum);
    if (nums.filter((n) => n !== null).length < 2) continue;
    out.push({
      pipe_top_elev_m: nums[0] ?? null,
      station_m: nums[1] ?? null,
      max_pressure_bar: nums[2] ?? null,
      max_smys_pct: nums[3] ?? null,
      min_pressure_bar: nums[4] ?? null,
      min_smys_pct: nums[5] ?? null,
      note: "",
    });
  }
  return out;
}

export function parsePigRunsPaste(rawText: string): Array<Record<string, unknown>> {
  const out: Array<Record<string, unknown>> = [];
  for (const cols of splitRows(rawText)) {
    if (cols.length < 2) continue;
    const pigType = cols[0];
    if (/pig\s*tipi/i.test(pigType)) continue;
    const launch = cols[1] ?? "";
    const receive = cols[2] ?? "";
    const dur = parseCellNum(cols[3] ?? "");
    const note = cols.slice(4).join(" ");
    if (!launch && !receive && dur === null) continue;
    out.push({
      pig_type: pigType || "Pig",
      launch_time: launch,
      receive_time: receive,
      duration_min: dur,
      note,
    });
  }
  return out;
}
