/* Radars acessíveis de contexto do humor: presença e impacto. */
(() => {
  "use strict";

  const SVG_NS = "http://www.w3.org/2000/svg";
  const COLORS = [
    "--lav", "--cyan", "--amber", "--green", "--coral", "--violet",
  ];

  function clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  function readData(node) {
    try {
      return JSON.parse(node.dataset.radar || "[]");
    } catch (_error) {
      return [];
    }
  }

  function createSvg(node, items, mode, overall) {
    if (!node || !items.length) return;
    const width = 360;
    const height = 300;
    const cx = 180;
    const cy = 145;
    const radius = 106;
    const axes = items.length;
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute(
      "aria-label",
      mode === "impact"
        ? "Radar do humor médio por contexto, comparado à média geral."
        : "Radar da frequência dos contextos nos últimos sete dias."
    );
    node.replaceChildren(svg);

    const point = (index, value) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / axes;
      return [
        cx + Math.cos(angle) * radius * value,
        cy + Math.sin(angle) * radius * value,
      ];
    };
    const path = (points) =>
      points
        .map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`)
        .join(" ") + " Z";
    const add = (tag, attrs, text) => {
      const element = document.createElementNS(SVG_NS, tag);
      Object.entries(attrs || {}).forEach(([key, value]) =>
        element.setAttribute(key, value)
      );
      if (text != null) element.textContent = text;
      svg.appendChild(element);
      return element;
    };

    for (let ring = 1; ring <= 4; ring += 1) {
      add("path", {
        d: path(
          items.map((_, index) => point(index, ring / 4))
        ),
        class: "mood-radar-grid",
      });
    }
    items.forEach((_, index) => {
      const [x, y] = point(index, 1);
      add("line", {
        x1: cx,
        y1: cy,
        x2: x,
        y2: y,
        class: "mood-radar-axis",
      });
    });

    if (mode === "impact" && Number(overall)) {
      const baseline = clamp(Number(overall) / 5, 0, 1);
      add("path", {
        d: path(items.map((_, index) => point(index, baseline))),
        class: "mood-radar-baseline",
      });
    }

    const showPrevious = node.dataset.previous === "1";
    if (showPrevious && items.some((item) => item.previous_frequency_value > 0)) {
      const previousPoints = items.map((item, index) =>
        point(index, clamp(Number(item.previous_frequency_value) / 100, 0, 1))
      );
      add("path", {
        d: path(previousPoints),
        class: "mood-radar-previous",
      });
    }

    const values = items.map((item) => {
      if (mode === "impact") {
        return item.enough ? clamp(Number(item.impact_value) / 100, 0, 1) : 0;
      }
      return clamp(Number(item.frequency_value) / 100, 0, 1);
    });
    const points = values.map((value, index) => point(index, value));
    add("path", {
      d: path(points),
      class: "mood-radar-area",
    });
    points.forEach(([x, y], index) => {
      const low = mode === "impact" && !items[index].enough;
      add("circle", {
        cx: x,
        cy: y,
        r: low ? 2 : 3.2,
        class: `mood-radar-point${low ? " is-low" : ""}`,
        style: `--point-color: var(${COLORS[index % COLORS.length]})`,
      });
    });

    items.forEach((item, index) => {
      const angle = -Math.PI / 2 + (index * 2 * Math.PI) / axes;
      const lx = cx + Math.cos(angle) * (radius + 29);
      const ly = cy + Math.sin(angle) * (radius + 29);
      const anchor = lx > cx + 7 ? "start" : lx < cx - 7 ? "end" : "middle";
      add("text", {
        x: lx,
        y: ly - 2,
        "text-anchor": anchor,
        class: "mood-radar-label",
      }, item.label);
      const value = mode === "impact"
        ? item.enough
          ? `${String(item.mood_avg).replace(".", ",")}`
          : "—"
        : `${item.count}×`;
      add("text", {
        x: lx,
        y: ly + 10,
        "text-anchor": anchor,
        class: "mood-radar-value",
      }, value);
    });
  }

  function init() {
    document.querySelectorAll("[data-mood-radar]").forEach((node) => {
      const items = readData(node);
      const mode = node.dataset.moodRadar;
      const overall = node.dataset.overall;
      createSvg(node, items, mode, overall);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
