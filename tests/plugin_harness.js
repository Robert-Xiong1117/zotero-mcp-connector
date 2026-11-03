// Loads zotero-plugin/bootstrap.js in a sandbox with a fake Zotero and prints endpoint results as JSON.
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const prefs = { "extensions.zmc-bridge.token": process.argv[2] || "" };
const saved = [];
const att = { key: "ATTKEY01", libraryID: 1, isAttachment: () => true, attachmentContentType: "application/pdf" };
const parent = {
  key: "ITEMKEY1", isAttachment: () => false, isNote: () => false, isRegularItem: () => true,
  getBestAttachment: async () => null,
};
const Zotero = {
  version: "7.0-test",
  Prefs: { get: (k) => prefs[k] },
  Server: { Endpoints: {} },
  Libraries: { userLibraryID: 1 },
  Items: { getByLibraryAndKey: (lib, key) => ({ ATTKEY01: att, ITEMKEY1: parent })[key] || false },
  DataObjectUtilities: { generateKey: () => "NEWANNO1" },
  Annotations: { saveFromJSON: async (a, json) => { saved.push({ attachment: a.key, json }); return { key: json.key }; } },
  Attachments: { addAvailableFile: async () => ({ key: "PDFKEY01", attachmentFilename: "x.pdf", attachmentContentType: "application/pdf" }) },
  debug: () => {}, logError: () => {},
};
const Services = { prefs: { getDefaultBranch: () => ({ setStringPref: () => {} }) } };
const ctx = vm.createContext({ Zotero, Services });
vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "zotero-plugin", "bootstrap.js"), "utf8"), ctx);
ctx.startup({ version: "9.9.9" });

async function call(p, token, data, headersAsMap) {
  const E = Zotero.Server.Endpoints[p];
  const h = token === null ? {} : { "X-ZMC-Token": token };
  const headers = headersAsMap ? new Headers(h) : h;
  const [status, , text] = await new E().init({ headers, data });
  return { status, body: JSON.parse(text) };
}

(async () => {
  const good = process.argv[3] || "";
  const anno = { attachmentKey: "ATTKEY01", annotation: { type: "highlight", text: "t", color: "#FF0000",
    sortIndex: "00000|000000|00000", position: { pageIndex: 0, rects: [[1, 2, 3, 4]] } } };
  const out = {
    endpoints: Object.keys(Zotero.Server.Endpoints),
    ping_ok: await call("/zmc/ping", good),
    ping_ok_headers_map: await call("/zmc/ping", good, undefined, true),
    ping_no_token: await call("/zmc/ping", null),
    ping_bad: await call("/zmc/ping", "wrong"),
    annotate_bad: await call("/zmc/annotate", "wrong", anno),
    annotate_ok: await call("/zmc/annotate", good, anno),
    annotate_missing_att: await call("/zmc/annotate", good, { ...anno, attachmentKey: "NOPE0000" }),
    annotate_no_rects: await call("/zmc/annotate", good, { ...anno, annotation: { type: "highlight", position: { pageIndex: 0, rects: [] } } }),
    find_ok: await call("/zmc/find-pdf", good, { itemKey: "ITEMKEY1" }),
    find_bad: await call("/zmc/find-pdf", "", { itemKey: "ITEMKEY1" }),
    saved,
  };
  ctx.shutdown();
  out.after_shutdown = Object.keys(Zotero.Server.Endpoints);
  console.log(JSON.stringify(out));
})();
