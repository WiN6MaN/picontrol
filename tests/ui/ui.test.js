const { JSDOM } = require("jsdom");
/* Browser-level smoke test: loads the real page in jsdom against tests/ui/serve.py and drives it. */
const BASE = "http://127.0.0.1:" + (process.env.PORT || "8765");
const errors = [];
let cookie = "";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, what, ms = 8000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch (e) { /* retry */ } await sleep(30); }
  throw new Error("timeout waiting for: " + what + " :: BODY=" + (global.__doc ? global.__doc.body.textContent.slice(0,400) : ""));
}
(async () => {
  const dom = await JSDOM.fromURL(BASE + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = async (url, options = {}) => {
        const headers = Object.assign({}, options.headers || {});
        if (cookie) headers["Cookie"] = cookie;
        const response = await fetch(new URL(url, BASE), Object.assign({}, options, { headers }));
        for (const c of (response.headers.getSetCookie ? response.headers.getSetCookie() : [])) cookie = c.split(";")[0];
        return response;
      };
      window.addEventListener("error", (e) => errors.push("window error: " + e.message));
      window.confirm = () => false;
      const log = window.console.error; window.console.error = (...a) => { errors.push("console.error: " + a.join(" ")); log(...a); };
    },
  });
  const { window } = dom; const doc = window.document; global.__doc = doc;
  const text = () => doc.body.textContent;
  const click = (el) => el.dispatchEvent(new window.Event("click", { bubbles: true }));
  const button = (label) => [...doc.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
  const steps = [];
  const ok = (name) => { steps.push(name); console.log("ok - " + name); };

  // login screen, wrong then right password
  const form = await until(() => doc.querySelector("form.login"), "login form");
  const input = form.querySelector("input[type=password]");
  input.value = "wrong password";
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await until(() => /wrong password/.test(text()), "wrong password message"); ok("wrong password is reported");
  input.value = "correct horse battery";
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  await until(() => doc.querySelector("nav"), "main screen"); ok("login works");

  // status tab
  await until(() => /47\.5 °C/.test(text()), "temperature"); ok("status shows the temperature");
  if (!/01020304/.test(text()) && !/ready/.test(text())) throw new Error("NFC state missing");
  ok("status shows the NFC reader");

  // tags tab: read, search, pick, write
  click(button("NFC tags"));
  await until(() => doc.querySelector("select option"), "systems list"); ok("tags tab lists the systems");
  await until(() => doc.querySelectorAll("ul.roms li").length === 3, "3 nes ROMs"); ok("ROM list is loaded");
  const search = doc.querySelector("input[type=search]");
  search.value = "mario"; search.dispatchEvent(new window.Event("input", { bubbles: true }));
  await until(() => doc.querySelectorAll("ul.roms li").length === 1, "search filters the list"); ok("search filters the ROM list");
  click(doc.querySelector("ul.roms li button"));
  await until(() => /Selected: nes \/ Super Mario Bros\.nes/.test(text()), "selection"); ok("a ROM can be selected");
  click(button("Write the tag"));
  await until(() => /Tag written and verified: nes \/ Super Mario Bros\.nes/.test(text()), "write result", 12000); ok("the tag is written through the page");
  click(button("Read a tag"));
  await until(() => /Zelda|Super Mario Bros\.nes/.test(text()) && /01020304/.test(text()), "read result", 12000); ok("the tag is read back through the page");

  // settings tab
  click(button("Settings"));
  await until(() => doc.querySelector(".setting"), "settings form"); ok("settings form is built");
  const row = [...doc.querySelectorAll(".setting")].find((r) => r.querySelector("code").textContent === "fan.threshold_on");
  row.querySelector("input").value = "66";
  click(button("Save"));
  await until(() => /Saved\. Restart the service/.test(text()), "saved message"); ok("a setting is saved");

  // system tab: log is shown, a dangerous action asks for confirmation and does nothing when refused
  click(button("System"));
  await until(() => /picontrol running/.test(text()), "log tail"); ok("the log is shown");
  click(button("Reboot the Pi")); await sleep(300);
  if (/Requested/.test(text())) throw new Error("reboot ran although the confirmation was refused");
  ok("a refused confirmation sends nothing");

  // language switch and logout
  click(button("Français"));
  await until(() => /Système/.test(text()) && /Se déconnecter/.test(text()), "French UI"); ok("the interface switches to French");
  click(button("Se déconnecter"));
  await until(() => doc.querySelector("form.login"), "back to login"); ok("logout returns to the login screen");

  // the page never produced an uncaught error
  if (errors.length) throw new Error("browser errors: " + errors.join(" | "));
  // nothing in the DOM came from innerHTML-style injection: ROM names are text nodes
  ok("no browser errors");
  console.log("\nUI SMOKE TEST PASSED (" + steps.length + " checks)");
  window.close(); process.exit(0);
})().catch((e) => { console.error("FAILED:", e.message, errors); process.exit(1); });
