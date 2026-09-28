// A stand-in for the Iris kit, to draw a plugin's window or screen outside a house.
// Same component names and props as the real kit, in English and in Dutch, drawn with the house
// colours as CSS variables. It is not the real kit: it is here to catch crashes, overflow and texts.
import { h, Fragment, render } from "preact";
import { useState, useEffect } from "preact/hooks";

const LANG = window.SIM_LANG || {};
window.SIM_SAID = [];
window.SIM_CLOSED = false;

const pick = (p, a, b) => (p[a] !== undefined ? p[a] : p[b]);

const Screen = (p) => h("main", { class: "k-screen" },
  h("header", null,
    h("h1", null, pick(p, "title", "titel")),
    pick(p, "subtitle", "sub") ? h("p", { class: "k-dim" }, pick(p, "subtitle", "sub")) : null),
  p.children);

const Card = (p) => h("section", { class: "k-card" },
  p.label ? h("div", { class: "k-label" }, p.label) : null,
  pick(p, "title", "titel") ? h("h2", null, pick(p, "title", "titel")) : null,
  p.children);

const Row = (p) => h("div", { class: "k-row" },
  h("span", null, pick(p, "left", "links")), h("span", { class: "k-dim" }, pick(p, "right", "rechts")));

const Stats = (p) => h("div", { class: "k-stats" }, p.children);
const Stat = (p) => h("div", { class: "k-stat" }, h("b", null, pick(p, "value", "waarde")), h("span", { class: "k-dim" }, p.label));
const Buttons = (p) => h("div", { class: "k-buttons" }, p.children);

const say = (s) => { window.SIM_SAID.push(String(s)); };
const Button = (p) => {
  const primary = pick(p, "primary", "primair");
  const off = !!pick(p, "disabled", "uit");
  const [busy, setBusy] = useState(false);
  const press = async () => {
    if (off || busy) return;
    const sentence = pick(p, "say", "zeg");
    if (sentence) say(sentence);
    if (p.onClick) {
      setBusy(true);
      try { await p.onClick(); } finally { setBusy(false); }
    }
  };
  return h("button", { class: "k-btn" + (primary ? " k-primary" : "") + (p.outline ? " k-outline" : ""),
    disabled: off, "aria-busy": busy ? "true" : null, onClick: press }, p.children);
};

const Text = (p) => h("p", { class: p.dim ? "k-dim" : "" }, p.children);
const List = (p) => h("ul", { class: "k-list" }, (p.items || []).map((x, i) => h("li", { key: i }, x)));
const Icon = (p) => h("span", { class: "k-icon", "data-icon": pick(p, "name", "naam"),
  style: { width: `${pick(p, "size", "maat") || 16}px`, height: `${pick(p, "size", "maat") || 16}px` } });

const text = (key, fallback) => (LANG[key] !== undefined ? LANG[key] : fallback);

async function pageApi(payload, method = "POST") {
  // A route page lives at /<route>; its command answers at /<route>/api.
  const base = `/${window.SIM_ROUTE || location.pathname.split("/")[1] || ""}/api`;
  try {
    const r = await fetch(base, { method, body: JSON.stringify(payload || {}) });
    return await r.json();
  } catch (e) {
    return { error: String(e && e.message || e) };
  }
}

Object.assign(window, {
  h, Fragment, render, useState, useEffect, text, tekst: text, say, nova: say, pageApi,
  dicht: () => { window.SIM_CLOSED = true; },
  Screen, Scherm: Screen, Card, Kaart: Card, Row, Rij: Row, Stats, Stat, Buttons, Knoppen: Buttons,
  Button, Knop: Button, Text, Tekst: Text, List, Lijst: List, Icon, Icoon: Icon,
});
