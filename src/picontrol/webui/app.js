"use strict";
/* Pi Control web interface. All text is inserted with textContent / text nodes - never as HTML. */
(function () {
  const STRINGS = {
    en: {
      title: "Pi Control", password: "Password", signIn: "Sign in", signOut: "Sign out", language: "Français",
      tabStatus: "Status", tabTags: "NFC tags", tabSettings: "Settings", tabSystem: "System",
      loading: "Loading…", refresh: "Refresh", done: "Done.",
      temperature: "CPU temperature", fan: "Fan", fanOn: "on", fanOff: "off", fanDisabled: "disabled",
      powerSwitch: "Power switch", game: "Game running", none: "none", nfc: "NFC reader", nfcReady: "ready",
      nfcStarting: "starting…", nfcOff: "disabled", tagPresent: "Tag in the reader", version: "Version",
      consoleUp: "Console up", serviceUp: "Service up", on: "ON", off: "OFF",
      dryRun: "Dry-run mode: nothing is stopped, started or shut down.",
      restartNeeded: "Settings changed: restart the service to apply them.",
      readTag: "Read a tag", readButton: "Read a tag", presentTag: "Present a tag to the reader…",
      uid: "UID", system: "System", rom: "ROM", notOurs: "Not a Pi Control tag: ", useForWriting: "Use for writing",
      writeTag: "Write a tag", searchRom: "Search a game…", noResults: "No game found", found: " found",
      more: "Show more", selected: "Selected", writeButton: "Write the tag", writeCurrent: "Write the running game",
      written: "Tag written and verified: ", chooseFirst: "Choose a game first.",
      settingsIntro: "Only safe settings can be changed here. Pins, commands and paths are edited in the configuration file.",
      save: "Save", saved: "Saved. Restart the service to apply the changes.", nothingChanged: "Nothing changed.",
      restartService: "Restart the service", reboot: "Reboot the Pi", shutdown: "Shut the Pi down",
      confirmRestart: "Restart the Pi Control service?", confirmReboot: "Reboot the Pi now?",
      confirmShutdown: "Shut the Pi down now?", logs: "Log", requested: "Requested. The page will stop answering for a moment.",
    },
    fr: {
      title: "Pi Control", password: "Mot de passe", signIn: "Se connecter", signOut: "Se déconnecter", language: "English",
      tabStatus: "État", tabTags: "Tags NFC", tabSettings: "Réglages", tabSystem: "Système",
      loading: "Chargement…", refresh: "Actualiser", done: "Terminé.",
      temperature: "Température du processeur", fan: "Ventilateur", fanOn: "en marche", fanOff: "arrêté", fanDisabled: "désactivé",
      powerSwitch: "Interrupteur power", game: "Jeu en cours", none: "aucun", nfc: "Lecteur NFC", nfcReady: "prêt",
      nfcStarting: "démarrage…", nfcOff: "désactivé", tagPresent: "Tag dans le lecteur", version: "Version",
      consoleUp: "Console allumée depuis", serviceUp: "Service lancé depuis", on: "ON", off: "OFF",
      dryRun: "Mode simulation : rien n'est arrêté, lancé ni éteint.",
      restartNeeded: "Réglages modifiés : redémarrez le service pour les appliquer.",
      readTag: "Lire un tag", readButton: "Lire un tag", presentTag: "Présentez un tag au lecteur…",
      uid: "UID", system: "Système", rom: "ROM", notOurs: "Ce n'est pas un tag Pi Control : ", useForWriting: "Utiliser pour écrire",
      writeTag: "Écrire un tag", searchRom: "Rechercher un jeu…", noResults: "Aucun jeu trouvé", found: " trouvé(s)",
      more: "Afficher plus", selected: "Sélection", writeButton: "Écrire le tag", writeCurrent: "Écrire le jeu en cours",
      written: "Tag écrit et vérifié : ", chooseFirst: "Choisissez d'abord un jeu.",
      settingsIntro: "Seuls les réglages sûrs sont modifiables ici. Les broches, commandes et chemins se modifient dans le fichier de configuration.",
      save: "Enregistrer", saved: "Enregistré. Redémarrez le service pour appliquer les changements.", nothingChanged: "Rien n'a changé.",
      restartService: "Redémarrer le service", reboot: "Redémarrer le Pi", shutdown: "Éteindre le Pi",
      confirmRestart: "Redémarrer le service Pi Control ?", confirmReboot: "Redémarrer le Pi maintenant ?",
      confirmShutdown: "Éteindre le Pi maintenant ?", logs: "Journal", requested: "Demande envoyée. La page va cesser de répondre un instant.",
    },
  };

  let lang = (localStorage.getItem("picontrol-lang") || (navigator.language || "en").slice(0, 2)) === "fr" ? "fr" : "en";
  const t = (key) => STRINGS[lang][key] || key;
  const state = { csrf: null, tab: "status", timer: null };
  const root = document.getElementById("app");

  // ---------------------------------------------------------------- DOM helpers (no innerHTML anywhere)
  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (["value", "checked", "disabled", "selected"].includes(key)) node[key] = value;
      else if (value !== false && value != null) node.setAttribute(key, value);
    }
    for (const kid of kids.flat(Infinity)) node.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }
  function note(container, text, kind) {
    const old = container.querySelector(".note");
    if (old) old.remove();
    const node = el("div", { class: "note " + (kind || "") }, text);
    container.append(node);
    return node;
  }

  // ---------------------------------------------------------------- API
  async function api(method, path, body) {
    const options = { method, credentials: "same-origin", headers: {} };
    if (method !== "GET") {
      options.headers["Content-Type"] = "application/json";
      options.headers["X-CSRF-Token"] = state.csrf || "";
      options.body = JSON.stringify(body || {});
    }
    const response = await fetch(path, options);
    let data = null;
    try { data = await response.json(); } catch (e) { /* not JSON */ }
    if (response.status === 401 && path !== "/api/login") { showLogin(); throw new Error("login required"); }
    if (!response.ok) throw new Error((data && data.error) || response.statusText);
    return data;
  }
  async function guarded(button, container, work) {
    button.disabled = true;
    try { await work(); } catch (error) { if (error.message !== "login required") note(container, error.message, "err"); }
    finally { button.disabled = false; }
  }

  // ---------------------------------------------------------------- screens
  function showLogin(message) {
    stopPolling();
    clear(root);
    const box = el("div", {});
    const input = el("input", { type: "password", autocomplete: "current-password", required: true, "aria-label": t("password"), placeholder: t("password") });
    const submit = el("button", { class: "primary", type: "submit" }, t("signIn"));
    const form = el("form", { class: "login" }, el("h1", {}, t("title")), el("div", { class: "row" }, input), el("div", { class: "row" }, submit), box);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      await guarded(submit, box, async () => {
        const data = await api("POST", "/api/login", { password: input.value });
        state.csrf = data.csrf;
        showMain();
      });
    });
    root.append(form);
    if (message) note(box, message, "err");
    input.focus();
  }

  function showMain() {
    clear(root);
    const content = el("main", {});
    const tabs = [["status", "tabStatus", renderStatus], ["tags", "tabTags", renderTags],
                  ["settings", "tabSettings", renderSettings], ["system", "tabSystem", renderSystem]];
    const nav = el("nav", {});
    function select(name) {
      stopPolling();
      state.tab = name;
      for (const button of nav.children) button.classList.toggle("active", button.dataset.tab === name);
      clear(content);
      tabs.find((tab) => tab[0] === name)[2](content);
    }
    for (const [name, label] of tabs) {
      nav.append(el("button", { "data-tab": name, onclick: () => select(name) }, t(label)));
    }
    const langButton = el("button", { onclick: () => { lang = lang === "fr" ? "en" : "fr"; localStorage.setItem("picontrol-lang", lang); showMain(); } }, t("language"));
    const logout = el("button", { onclick: async () => { try { await api("POST", "/api/logout"); } catch (e) { /* ignore */ } state.csrf = null; showLogin(); } }, t("signOut"));
    root.append(el("header", {}, el("h1", {}, t("title")), el("div", { class: "row" }, langButton, logout)), nav, content);
    select(state.tab);
  }

  function stopPolling() { if (state.timer) { clearInterval(state.timer); state.timer = null; } }

  // ---------------------------------------------------------------- status
  function duration(seconds) {
    if (seconds == null) return "?";
    const d = Math.floor(seconds / 86400), h = Math.floor(seconds % 86400 / 3600), m = Math.floor(seconds % 3600 / 60);
    return (d ? d + "d " : "") + (h ? h + "h " : "") + m + "m";
  }
  function renderStatus(container) {
    const card = el("div", { class: "card" }, t("loading"));
    const banner = el("div", {});
    container.append(banner, card);
    async function refresh() {
      try {
        const s = await api("GET", "/api/state");
        clear(banner);
        if (s.dry_run) banner.append(el("div", { class: "note warn" }, t("dryRun")));
        if (s.restart_required) banner.append(el("div", { class: "note warn" }, t("restartNeeded")));
        const fan = !s.fan.enabled ? t("fanDisabled") : (s.fan.on ? t("fanOn") : t("fanOff")) + " (" + s.fan.threshold_on + " / " + s.fan.threshold_off + " °C)";
        const game = s.game.running ? (s.game.system ? s.game.system + " / " + s.game.rom : "?") : t("none");
        const nfc = !s.nfc.enabled ? t("nfcOff") : (s.nfc.ready ? t("nfcReady") : t("nfcStarting"));
        const rows = [[t("temperature"), s.temperature == null ? "?" : s.temperature.toFixed(1) + " °C"], [t("fan"), fan],
          [t("powerSwitch"), s.power_switch == null ? "-" : (s.power_switch === "on" ? t("on") : t("off"))], [t("game"), game],
          [t("nfc"), nfc], [t("tagPresent"), s.nfc.tag || t("none")], [t("consoleUp"), duration(s.system_uptime)],
          [t("serviceUp"), duration(s.service_uptime)], [t("version"), s.version]];
        clear(card);
        card.append(el("dl", {}, rows.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])));
      } catch (error) { if (error.message !== "login required") { clear(card); card.append(el("div", { class: "note err" }, error.message)); } }
    }
    refresh();
    state.timer = setInterval(refresh, 3000);
  }

  // ---------------------------------------------------------------- tags
  function renderTags(container) {
    // --- read
    const readOut = el("div", {});
    const readButton = el("button", { class: "primary" }, t("readButton"));
    const chosen = { system: null, rom: null };
    readButton.addEventListener("click", () => guarded(readButton, readOut, async () => {
      note(readOut, t("presentTag"), "warn");
      const r = await api("POST", "/api/tag/read");
      clear(readOut);
      const rows = [[t("uid"), r.uid]];
      if (r.records) rows.push([t("system"), r.records[0]], [t("rom"), r.records[1] || t("none")]);
      readOut.append(el("dl", {}, rows.map(([k, v]) => [el("dt", {}, k), el("dd", {}, v)])));
      if (r.records && r.records.length > 1) {
        readOut.append(el("div", { class: "row" }, el("button", { onclick: () => pick(r.records[0], r.records[1]) }, t("useForWriting"))));
      } else if (r.note) { note(readOut, t("notOurs") + r.note, "warn"); }
    }));

    // --- write
    const writeOut = el("div", {});
    const systemSelect = el("select", { "aria-label": t("system") });
    const search = el("input", { type: "search", placeholder: t("searchRom"), "aria-label": t("searchRom") });
    const list = el("ul", { class: "roms" });
    const summary = el("p", { class: "muted" });
    const moreButton = el("button", {}, t("more"));
    const selection = el("p", {});
    const writeButton = el("button", { class: "primary" }, t("writeButton"));
    const currentButton = el("button", {}, t("writeCurrent"));
    let offset = 0, debounce = null;

    function pick(system, rom) {
      chosen.system = system; chosen.rom = rom;
      if ([...systemSelect.options].some((o) => o.value === system)) systemSelect.value = system;
      selection.textContent = t("selected") + ": " + system + " / " + rom;
    }
    async function load(reset) {
      if (!systemSelect.value) return;
      if (reset) { offset = 0; clear(list); }
      try {
        const q = new URLSearchParams({ system: systemSelect.value, q: search.value, offset: String(offset), limit: "50" });
        const r = await api("GET", "/api/roms?" + q.toString());
        for (const name of r.items) {
          const button = el("button", { onclick: () => { pick(r.system, name); for (const b of list.querySelectorAll("button")) b.classList.remove("selected"); button.classList.add("selected"); } }, name);
          list.append(el("li", {}, button));
        }
        offset += r.items.length;
        summary.textContent = r.total ? r.total + t("found") : t("noResults");
        moreButton.hidden = offset >= r.total;
      } catch (error) { if (error.message !== "login required") note(writeOut, error.message, "err"); }
    }
    systemSelect.addEventListener("change", () => load(true));
    search.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(() => load(true), 250); });
    moreButton.addEventListener("click", () => load(false));
    writeButton.addEventListener("click", () => guarded(writeButton, writeOut, async () => {
      if (!chosen.rom) { note(writeOut, t("chooseFirst"), "err"); return; }
      note(writeOut, t("presentTag"), "warn");
      const r = await api("POST", "/api/tag/write", { system: chosen.system, rom: chosen.rom });
      note(writeOut, t("written") + r.system + " / " + r.rom, "ok");
    }));
    currentButton.addEventListener("click", () => guarded(currentButton, writeOut, async () => {
      note(writeOut, t("presentTag"), "warn");
      const r = await api("POST", "/api/tag/write-current");
      note(writeOut, t("written") + r.system + " / " + r.rom, "ok");
    }));
    container.append(
      el("h2", {}, t("readTag")), el("div", { class: "card" }, el("div", { class: "row" }, readButton), readOut),
      el("h2", {}, t("writeTag")),
      el("div", { class: "card" }, el("div", { class: "row" }, systemSelect), el("div", { class: "row" }, search), summary, list,
        el("div", { class: "row" }, moreButton), selection, el("div", { class: "row" }, writeButton, currentButton), writeOut));
    moreButton.hidden = true;
    api("GET", "/api/systems").then((r) => {
      for (const s of r.systems) systemSelect.append(el("option", { value: s.name }, s.name + " (" + s.count + ")"));
      load(true);
    }).catch((error) => { if (error.message !== "login required") note(writeOut, error.message, "err"); });
  }

  // ---------------------------------------------------------------- settings
  function renderSettings(container) {
    const out = el("div", {});
    const form = el("div", { class: "card" }, t("loading"));
    container.append(el("p", { class: "muted" }, t("settingsIntro")), form, out);
    api("GET", "/api/config").then((c) => {
      clear(form);
      const inputs = [];
      for (const s of c.settings) {
        let input;
        if (s.type === "bool") input = el("input", { type: "checkbox", checked: !!s.value });
        else if (s.choices) input = el("select", {}, s.choices.map((v) => el("option", { value: v, selected: v === s.value }, v)));
        else input = el("input", { type: "number", step: "any", value: s.value });
        inputs.push([s, input]);
        form.append(el("div", { class: "setting" }, el("code", {}, s.name), input));
      }
      const save = el("button", { class: "primary" }, t("save"));
      save.addEventListener("click", () => guarded(save, out, async () => {
        const changes = {};
        for (const [s, input] of inputs) {
          let value;
          if (s.type === "bool") value = input.checked;
          else if (s.type === "int") value = parseInt(input.value, 10);
          else if (s.type === "float") value = parseFloat(input.value);
          else value = input.value;
          if (value !== s.value) changes[s.name] = value;
        }
        if (!Object.keys(changes).length) { note(out, t("nothingChanged")); return; }
        await api("POST", "/api/config", { changes });
        note(out, t("saved"), "ok");
        for (const [s, input] of inputs) s.value = s.type === "bool" ? input.checked : (s.type === "str" ? input.value : Number(input.value));
      }));
      form.append(el("div", { class: "row" }, save));
    }).catch((error) => { if (error.message !== "login required") note(out, error.message, "err"); });
  }

  // ---------------------------------------------------------------- system
  function renderSystem(container) {
    const out = el("div", {});
    const action = (label, path, question, kind) => {
      const button = el("button", { class: kind || "" }, label);
      button.addEventListener("click", () => {
        if (!window.confirm(question)) return;
        guarded(button, out, async () => { await api("POST", path, { confirm: true }); note(out, t("requested"), "ok"); });
      });
      return button;
    };
    const log = el("pre", { class: "log" }, t("loading"));
    const refreshLog = el("button", {}, t("refresh"));
    async function loadLog() {
      try { const r = await api("GET", "/api/log?lines=150"); log.textContent = r.lines.join("\n"); }
      catch (error) { if (error.message !== "login required") log.textContent = error.message; }
    }
    refreshLog.addEventListener("click", loadLog);
    container.append(
      el("div", { class: "card" }, el("div", { class: "row" },
        action(t("restartService"), "/api/service/restart", t("confirmRestart")),
        action(t("reboot"), "/api/system/reboot", t("confirmReboot"), "danger"),
        action(t("shutdown"), "/api/system/shutdown", t("confirmShutdown"), "danger")), out),
      el("h2", {}, t("logs")), el("div", { class: "row" }, refreshLog), log);
    loadLog();
  }

  // ---------------------------------------------------------------- start
  api("GET", "/api/session").then((s) => { if (s.authenticated) { state.csrf = s.csrf; showMain(); } else showLogin(); })
    .catch(() => showLogin());
})();
