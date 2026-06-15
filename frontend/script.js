"use strict";

const $ = (id) => document.getElementById(id);
const state = { location: null, weather: null, result: null, sampleIndex: 0, toastTimer: null };

const inputs = {
  crop: $("cropType"),
  soilMoisture: $("soilMoisture"),
  ndvi: $("ndvi"),
  humidity: $("humidity"),
  qualityScore: $("qualityScore"),
  temperature: $("temperature"),
  rainfall: $("rainfall")
};

const ranges = [
  { input: inputs.soilMoisture, output: $("soilMoistureOutput"), format: (v) => `${v}%` },
  { input: inputs.ndvi, output: $("ndviOutput"), format: (v) => Number(v).toFixed(2) },
  { input: inputs.humidity, output: $("humidityOutput"), format: (v) => `${v}%` },
  { input: inputs.qualityScore, output: $("qualityScoreOutput"), format: (v) => `${v}/100` }
];

function syncRange(item) {
  const min = Number(item.input.min);
  const max = Number(item.input.max);
  const value = Number(item.input.value);
  item.input.style.setProperty("--fill", `${((value - min) / (max - min)) * 100}%`);
  item.output.textContent = item.format(item.input.value);
}

ranges.forEach((item) => {
  syncRange(item);
  item.input.addEventListener("input", () => syncRange(item));
});

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("agrosense-theme", theme);
  if (state.result) drawCharts();
}

const savedTheme = localStorage.getItem("agrosense-theme");
const preferredTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
setTheme(savedTheme || preferredTheme);
$("themeToggle").addEventListener("click", () => setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));

function showToast(message, type = "success") {
  clearTimeout(state.toastTimer);
  $("toastText").textContent = message;
  $("toast").className = `toast show ${type === "error" ? "error" : ""}`;
  state.toastTimer = setTimeout(() => $("toast").classList.remove("show"), 3600);
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  let body = {};
  try { body = await response.json(); } catch (_error) { body = {}; }
  if (!response.ok) {
    const detail = body.fields ? Object.values(body.fields)[0] : null;
    throw new Error(detail || body.error || `Request failed (${response.status})`);
  }
  return body;
}

async function checkApi() {
  const pill = $("apiPill");
  try {
    await api("/api/health");
    pill.className = "api-pill online";
    pill.querySelector("span").textContent = "API online";
  } catch (_error) {
    pill.className = "api-pill offline";
    pill.querySelector("span").textContent = "API offline";
  }
}

function formPayload() {
  return {
    crop: inputs.crop.value,
    soilMoisture: Number(inputs.soilMoisture.value),
    ndvi: Number(inputs.ndvi.value),
    humidity: Number(inputs.humidity.value),
    qualityScore: Number(inputs.qualityScore.value),
    temperature: Number(inputs.temperature.value),
    rainfall: Number(inputs.rainfall.value),
    lat: state.location?.latitude ?? null,
    lon: state.location?.longitude ?? null
  };
}

function setBusy(busy) {
  const button = $("analyzeBtn");
  button.disabled = busy;
  button.classList.toggle("loading", busy);
  button.querySelector(".button-label").textContent = busy ? "Analyzing field" : "Analyze field";
}

$("analysisForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  setBusy(true);
  try {
    state.result = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(formPayload())
    });
    if (state.result.weather) state.weather = state.result.weather;
    renderDashboard(state.result);
    showToast("Field analysis updated successfully.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setBusy(false);
  }
});

function renderDashboard(result) {
  const { analysis, irrigation, disease, market, checklist } = result;
  animateNumber($("healthScore"), Number($("healthScore").textContent) || 0, analysis.score, 900);
  $("scoreGauge").style.setProperty("--score", analysis.score);
  $("healthTitle").textContent = `${analysis.label} ${inputs.crop.value.toLowerCase()} condition`;
  $("healthSummary").textContent = analysis.observations.join(" ");
  $("healthTags").innerHTML = analysis.observations.slice(0, 3).map((item) => `<span>${escapeHtml(shortTag(item))}</span>`).join("");

  const scores = analysis.componentScores;
  $("moistureScore").textContent = `${scores.moisture}%`;
  $("vegetationScore").textContent = `${scores.vegetation}%`;
  $("climateScore").textContent = `${Math.round((scores.humidity + scores.temperature) / 2)}%`;
  $("diseaseMetric").textContent = disease.level;
  $("moistureReading").textContent = `${inputs.soilMoisture.value}% reading`;
  $("ndviReading").textContent = `${Number(inputs.ndvi.value).toFixed(2)} NDVI`;
  $("climateReading").textContent = `${inputs.temperature.value} C / ${inputs.humidity.value}%`;
  $("diseaseReading").textContent = `${disease.score}/100 risk index`;

  renderRecommendations(analysis, irrigation, disease);
  renderMarket(market);
  renderActions(checklist);
  updateWeatherStrip(result.weather);
  drawCharts();
}

function shortTag(text) {
  if (/moisture/i.test(text)) return "Moisture signal";
  if (/NDVI|canopy|vegetation/i.test(text)) return "Canopy signal";
  if (/heat|temperature/i.test(text)) return "Heat signal";
  return "Field signal";
}

function renderRecommendations(analysis, irrigation, disease) {
  $("recommendationEmpty").hidden = true;
  const list = $("recommendationList");
  list.hidden = false;
  const diseaseClass = disease.level.toLowerCase() === "moderate" ? "medium" : disease.level.toLowerCase();
  const healthRisk = analysis.score >= 70 ? "low" : analysis.score >= 50 ? "medium" : "high";
  const cards = [
    { icon: "IR", title: "Irrigation", badge: irrigation.priority, klass: irrigation.priority, text: `${irrigation.reason} ${irrigation.recommendedLitersPerM2 ? `Apply about ${irrigation.recommendedLitersPerM2} L/m2.` : ""}` },
    { icon: "DR", title: "Disease watch", badge: disease.level, klass: diseaseClass, text: `Risk factors: ${disease.factors.join(", ")}. ${disease.actions[0]}.` },
    { icon: "CH", title: "Crop health", badge: analysis.label, klass: healthRisk, text: analysis.summary }
  ];
  list.innerHTML = cards.map((card, index) => `
    <article class="recommendation" style="animation-delay:${index * 80}ms">
      <div class="recommendation-head"><div><span class="recommendation-icon">${card.icon}</span><h3>${escapeHtml(card.title)}</h3></div><span class="risk-badge risk-${card.klass}">${escapeHtml(card.badge)}</span></div>
      <p>${escapeHtml(card.text)}</p>
    </article>`).join("");
}

function renderMarket(market) {
  $("marketPrice").textContent = formatMoney(market.estimatedPrice);
  $("qualityGrade").textContent = `${market.qualityGrade} (${market.qualityScore}/100)`;
  $("marketRange").textContent = `${formatMoney(market.priceRange.low)} - ${formatMoney(market.priceRange.high)}`;
  $("marketAdvice").textContent = market.advice;
  $("modelBadge").textContent = market.modelUsed ? "ML MODEL" : "ESTIMATE";
}

function renderActions(actions) {
  $("actionCount").textContent = actions.length;
  $("actionList").innerHTML = actions.map((action) => `<li>${escapeHtml(action)}</li>`).join("");
}

function formatMoney(value) {
  return new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(value);
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[char]);
}

function animateNumber(element, start, end, duration) {
  const startTime = performance.now();
  const tick = (now) => {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased = 1 - Math.pow(1 - progress, 3);
    element.textContent = Math.round(start + (end - start) * eased);
    if (progress < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

$("locationBtn").addEventListener("click", () => {
  if (!navigator.geolocation) {
    showToast("This browser does not support geolocation.", "error");
    return;
  }
  const button = $("locationBtn");
  button.disabled = true;
  button.textContent = "Finding";
  $("locationDetail").textContent = "Waiting for GPS permission...";
  navigator.geolocation.getCurrentPosition(
    async ({ coords }) => {
      state.location = { latitude: coords.latitude, longitude: coords.longitude };
      $("locationDetail").textContent = `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`;
      try {
        const [location, weather] = await Promise.all([
          api(`/api/location?lat=${coords.latitude}&lon=${coords.longitude}`),
          api(`/api/weather?lat=${coords.latitude}&lon=${coords.longitude}`)
        ]);
        state.location = location;
        state.weather = weather;
        $("locationLabel").textContent = location.label;
        $("locationDetail").textContent = `${coords.latitude.toFixed(4)}, ${coords.longitude.toFixed(4)}`;
        applyWeatherToInputs(weather);
        updateWeatherStrip(weather);
        drawForecastChart();
        showToast("Farm location and local weather loaded.");
      } catch (error) {
        $("locationLabel").textContent = "GPS coordinates detected";
        showToast(error.message, "error");
      } finally {
        button.disabled = false;
        button.textContent = "Refresh";
      }
    },
    (error) => {
      button.disabled = false;
      button.textContent = "Detect";
      $("locationDetail").textContent = "Location permission was not granted";
      showToast(error.message || "Unable to detect location.", "error");
    },
    { enableHighAccuracy: true, timeout: 12000, maximumAge: 300000 }
  );
});

function applyWeatherToInputs(weather) {
  const current = weather.current || {};
  if (Number.isFinite(current.temperature)) inputs.temperature.value = current.temperature;
  if (Number.isFinite(current.humidity)) {
    inputs.humidity.value = current.humidity;
    syncRange(ranges[2]);
  }
  if (Number.isFinite(weather.rainNext3Days)) inputs.rainfall.value = weather.rainNext3Days;
}

function updateWeatherStrip(weather) {
  $("stripTime").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (state.location) $("stripLocation").textContent = state.location.label || `${state.location.latitude.toFixed(3)}, ${state.location.longitude.toFixed(3)}`;
  if (!weather) {
    $("stripTemp").textContent = `${inputs.temperature.value} C`;
    $("stripHumidity").textContent = `${inputs.humidity.value}%`;
    $("stripRain").textContent = `${inputs.rainfall.value} mm`;
    return;
  }
  $("stripTemp").textContent = `${weather.current.temperature} C`;
  $("stripHumidity").textContent = `${weather.current.humidity}%`;
  $("stripRain").textContent = `${weather.rainNext3Days} mm`;
  $("weatherSource").textContent = `${weather.source} / ${weather.timezone || "local time"}`;
}

const samples = [
  { crop: "Wheat", soil: 62, ndvi: .78, humidity: 57, quality: 86, temperature: 27, rainfall: 4 },
  { crop: "Tomato", soil: 28, ndvi: .43, humidity: 34, quality: 58, temperature: 36, rainfall: 0 },
  { crop: "Rice", soil: 84, ndvi: .54, humidity: 89, quality: 67, temperature: 29, rainfall: 32 }
];

$("sampleBtn").addEventListener("click", () => {
  const sample = samples[state.sampleIndex++ % samples.length];
  inputs.crop.value = sample.crop;
  inputs.soilMoisture.value = sample.soil;
  inputs.ndvi.value = sample.ndvi;
  inputs.humidity.value = sample.humidity;
  inputs.qualityScore.value = sample.quality;
  inputs.temperature.value = sample.temperature;
  inputs.rainfall.value = sample.rainfall;
  ranges.forEach(syncRange);
  showToast(`${sample.crop} sample readings loaded.`);
});

$("resetBtn").addEventListener("click", () => {
  inputs.crop.value = "Wheat";
  inputs.soilMoisture.value = 45;
  inputs.ndvi.value = .6;
  inputs.humidity.value = 60;
  inputs.qualityScore.value = 70;
  inputs.temperature.value = 28;
  inputs.rainfall.value = 0;
  ranges.forEach(syncRange);
  state.result = null;
  $("healthScore").textContent = "--";
  $("scoreGauge").style.setProperty("--score", 0);
  $("healthTitle").textContent = "Ready for analysis";
  $("healthSummary").textContent = "Enter field readings to generate a complete health assessment.";
  ["moistureScore", "vegetationScore", "climateScore", "diseaseMetric"].forEach((id) => $(id).textContent = "--");
  $("recommendationEmpty").hidden = false;
  $("recommendationList").hidden = true;
  $("marketPrice").textContent = "--";
  $("actionCount").textContent = "0";
  $("actionList").innerHTML = '<li class="muted-action">Run an analysis to build your plan.</li>';
  clearCanvas($("profileChart"));
  if (!state.weather) clearCanvas($("forecastChart"));
  showToast("Sensor readings reset.");
});

function canvasContext(canvas) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width * ratio));
  canvas.height = Math.max(1, Math.round(rect.height * ratio));
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width: rect.width, height: rect.height };
}

function colors() {
  const style = getComputedStyle(document.documentElement);
  return {
    green: style.getPropertyValue("--green").trim(),
    text: style.getPropertyValue("--text-soft").trim(),
    muted: style.getPropertyValue("--muted").trim(),
    line: style.getPropertyValue("--line").trim(),
    panel: style.getPropertyValue("--panel-solid").trim(),
    blue: style.getPropertyValue("--blue").trim()
  };
}

function drawCharts() {
  drawProfileChart();
  drawForecastChart();
}

function drawProfileChart() {
  if (!state.result) return;
  const canvas = $("profileChart");
  const { context: ctx, width, height } = canvasContext(canvas);
  const c = colors();
  const scores = state.result.analysis.componentScores;
  const values = [scores.moisture, scores.vegetation, scores.humidity, scores.temperature, 100 - state.result.disease.score];
  const labels = ["Moisture", "Vegetation", "Humidity", "Temperature", "Disease safety"];
  const left = width < 440 ? 78 : 100;
  const right = 35;
  const usable = width - left - right;
  const row = height / labels.length;
  ctx.font = "10px DM Sans";
  ctx.textBaseline = "middle";
  values.forEach((value, index) => {
    const y = row * index + row / 2;
    ctx.fillStyle = c.text;
    ctx.textAlign = "left";
    ctx.fillText(labels[index], 0, y);
    ctx.fillStyle = c.line;
    roundedRect(ctx, left, y - 5, usable, 10, 5);
    ctx.fill();
    const gradient = ctx.createLinearGradient(left, 0, left + usable, 0);
    gradient.addColorStop(0, c.green);
    gradient.addColorStop(1, c.blue);
    ctx.fillStyle = gradient;
    roundedRect(ctx, left, y - 5, usable * value / 100, 10, 5);
    ctx.fill();
    ctx.fillStyle = c.muted;
    ctx.textAlign = "right";
    ctx.fillText(`${value}%`, width, y);
  });
}

function drawForecastChart() {
  const weather = state.weather || state.result?.weather;
  if (!weather?.forecast?.length) return;
  const canvas = $("forecastChart");
  const { context: ctx, width, height } = canvasContext(canvas);
  const c = colors();
  const data = weather.forecast.slice(0, 7);
  const padding = { top: 16, right: 12, bottom: 27, left: 10 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const maxTemp = Math.max(...data.map((day) => Number(day.max) || 0), 40);
  const maxRain = Math.max(...data.map((day) => Number(day.rain) || 0), 20);
  const step = chartW / Math.max(1, data.length - 1);

  ctx.strokeStyle = c.line;
  ctx.lineWidth = 1;
  for (let i = 0; i < 4; i += 1) {
    const y = padding.top + chartH * i / 3;
    ctx.beginPath(); ctx.moveTo(padding.left, y); ctx.lineTo(width - padding.right, y); ctx.stroke();
  }

  data.forEach((day, index) => {
    const x = padding.left + index * step;
    const barH = (Number(day.rain) / maxRain) * chartH * .62;
    ctx.fillStyle = `${c.blue}55`;
    roundedRect(ctx, x - 7, padding.top + chartH - barH, 14, barH, 5);
    ctx.fill();
  });

  const gradient = ctx.createLinearGradient(0, padding.top, 0, padding.top + chartH);
  gradient.addColorStop(0, `${c.green}45`);
  gradient.addColorStop(1, `${c.green}00`);
  ctx.beginPath();
  data.forEach((day, index) => {
    const x = padding.left + index * step;
    const y = padding.top + chartH - (Number(day.max) / maxTemp) * chartH;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.lineTo(padding.left + (data.length - 1) * step, padding.top + chartH);
  ctx.lineTo(padding.left, padding.top + chartH);
  ctx.closePath(); ctx.fillStyle = gradient; ctx.fill();

  ctx.beginPath();
  data.forEach((day, index) => {
    const x = padding.left + index * step;
    const y = padding.top + chartH - (Number(day.max) / maxTemp) * chartH;
    index ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = c.green; ctx.lineWidth = 2.5; ctx.lineJoin = "round"; ctx.stroke();

  ctx.font = "9px DM Sans"; ctx.textAlign = "center";
  data.forEach((day, index) => {
    const x = padding.left + index * step;
    const y = padding.top + chartH - (Number(day.max) / maxTemp) * chartH;
    ctx.fillStyle = c.panel; ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = c.green; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = c.muted;
    ctx.fillText(new Date(`${day.date}T00:00:00`).toLocaleDateString([], { weekday: "short" }), x, height - 7);
  });
}

function roundedRect(ctx, x, y, width, height, radius) {
  if (width <= 0 || height <= 0) return;
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

function clearCanvas(canvas) {
  canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
}

document.querySelectorAll(".tilt-card").forEach((card) => {
  card.addEventListener("pointermove", (event) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const rect = card.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width - .5;
    const y = (event.clientY - rect.top) / rect.height - .5;
    card.style.transform = `rotateY(${x * 7}deg) rotateX(${-y * 7}deg) translateY(-2px)`;
  });
  card.addEventListener("pointerleave", () => card.style.transform = "");
});

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => { if (entry.isIntersecting) entry.target.classList.add("visible"); });
}, { threshold: .08 });
document.querySelectorAll(".reveal").forEach((element, index) => {
  element.style.transitionDelay = `${Math.min(index * 45, 250)}ms`;
  observer.observe(element);
});

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(drawCharts, 120);
});

setInterval(() => $("stripTime").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }), 30000);
updateWeatherStrip(null);
checkApi();
