/* ZoteroMCP Bridge — Zotero 7 bootstrap plugin, no UI.
 *
 * Zotero's local API (port 23119) is read-only, so writes have to run inside the Zotero process.
 * This plugin adds three endpoints to Zotero's built-in HTTP server (127.0.0.1 only):
 *   GET  /zmc/ping      -> {version}
 *   POST /zmc/annotate  -> Zotero.Annotations.saveFromJSON(attachment, highlight)
 *   POST /zmc/find-pdf  -> Zotero.Attachments.addAvailableFile(item)
 * Every request must carry X-ZMC-Token equal to the pref extensions.zmc-bridge.token
 * (copy it from the ZoteroMCP control panel). An empty pref rejects everything.
 */
var TOKEN_PREF = "extensions.zmc-bridge.token";
var PATHS = ["/zmc/ping", "/zmc/annotate", "/zmc/find-pdf"];
var pluginVersion = "";

function json(status, obj) {
  return [status, "application/json", JSON.stringify(obj)];
}

function header(requestData, name) {
  var h = requestData.headers || {};
  if (typeof h.get === "function") return h.get(name) || "";
  var lower = name.toLowerCase();
  for (var k in h) {
    if (k.toLowerCase() === lower) return h[k] || "";
  }
  return "";
}

function tokenOK(requestData) {
  var expected = String(Zotero.Prefs.get(TOKEN_PREF, true) || "");
  var got = String(header(requestData, "X-ZMC-Token"));
  if (!expected || got.length !== expected.length) return false;
  var diff = 0;
  for (var i = 0; i < expected.length; i++) diff |= expected.charCodeAt(i) ^ got.charCodeAt(i);
  return diff === 0;
}

function body(requestData) {
  var d = requestData.data;
  if (typeof d === "string") d = d ? JSON.parse(d) : {};
  return d || {};
}

function itemByKey(key, libraryID) {
  if (!key || !/^[A-Z0-9]{8}$/.test(key)) return null;
  return Zotero.Items.getByLibraryAndKey(libraryID || Zotero.Libraries.userLibraryID, key) || null;
}

// Wraps a handler: token check first, then uniform JSON errors.
function endpoint(methods, handler) {
  var E = function () {};
  E.prototype = {
    supportedMethods: methods,
    supportedDataTypes: ["application/json"],
    permitBookmarklet: false,
    init: async function (requestData) {
      if (!tokenOK(requestData)) return json(403, { error: "invalid or missing X-ZMC-Token" });
      try {
        return await handler(requestData);
      } catch (e) {
        Zotero.logError(e);
        return json(500, { error: String((e && e.message) || e) });
      }
    },
  };
  return E;
}

var handlers = {
  "/zmc/ping": endpoint(["GET"], async function () {
    return json(200, { ok: true, version: pluginVersion, zotero: Zotero.version });
  }),

  "/zmc/annotate": endpoint(["POST"], async function (requestData) {
    var d = body(requestData);
    var att = itemByKey(d.attachmentKey, d.libraryID);
    if (!att || !att.isAttachment()) return json(404, { error: "attachment not found: " + d.attachmentKey });
    if (att.attachmentContentType !== "application/pdf") return json(400, { error: "attachment is not a PDF" });
    var a = d.annotation || {};
    if (a.type !== "highlight") return json(400, { error: "only type=highlight is supported" });
    var p = a.position || {};
    if (!Number.isInteger(p.pageIndex) || !Array.isArray(p.rects) || !p.rects.length) {
      return json(400, { error: "position.pageIndex and position.rects are required" });
    }
    var annotation = {
      key: Zotero.DataObjectUtilities.generateKey(),
      type: "highlight",
      text: String(a.text || ""),
      comment: String(a.comment || ""),
      color: /^#[0-9a-fA-F]{6}$/.test(a.color || "") ? a.color.toLowerCase() : "#ffd400",
      pageLabel: String(a.pageLabel || p.pageIndex + 1),
      sortIndex: String(a.sortIndex || ""),
      position: { pageIndex: p.pageIndex, rects: p.rects },
      tags: [],
    };
    if (Array.isArray(p.nextPageRects) && p.nextPageRects.length) annotation.position.nextPageRects = p.nextPageRects;
    var saved = await Zotero.Annotations.saveFromJSON(att, annotation);
    return json(200, { ok: true, key: saved.key, attachmentKey: att.key });
  }),

  "/zmc/find-pdf": endpoint(["POST"], async function (requestData) {
    var d = body(requestData);
    var item = itemByKey(d.itemKey, d.libraryID);
    if (!item) return json(404, { error: "item not found: " + d.itemKey });
    if (item.isAttachment() || item.isNote()) item = item.parentItem || item;
    if (!item.isRegularItem()) return json(400, { error: "not a regular item" });
    var existing = await item.getBestAttachment();
    if (existing && existing.attachmentContentType === "application/pdf" && (await existing.fileExists())) {
      return json(200, { ok: true, found: true, already: true, attachmentKey: existing.key,
                         filename: existing.attachmentFilename });
    }
    var att = await Zotero.Attachments.addAvailableFile(item);
    if (!att) return json(200, { ok: true, found: false });
    return json(200, { ok: true, found: true, already: false, attachmentKey: att.key,
                       filename: att.attachmentFilename, contentType: att.attachmentContentType });
  }),
};

function startup(data) {
  pluginVersion = (data && data.version) || "";
  try {
    // Create the pref (empty) so it shows up in Settings → Advanced → Config Editor.
    Services.prefs.getDefaultBranch("").setStringPref(TOKEN_PREF, "");
  } catch (e) {}
  for (var path of PATHS) Zotero.Server.Endpoints[path] = handlers[path];
  Zotero.debug("ZoteroMCP Bridge " + pluginVersion + " registered " + PATHS.join(", "));
}

function shutdown() {
  for (var path of PATHS) delete Zotero.Server.Endpoints[path];
}

function install() {}
function uninstall() {}
