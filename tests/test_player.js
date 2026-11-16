// 集成测试：用迷你 DOM 桩驱动 tools/index.html 中的完整播放器逻辑
const fs = require("fs");
const path = require("path");
const base = path.resolve(__dirname, "..");

const html = fs.readFileSync(path.join(base, "tools", "index.html"), "utf8");
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];

// ---------- 迷你 DOM 桩 ----------
function makeEl(id) {
  const listeners = {};
  return {
    id, textContent: "", innerHTML: "", value: "", className: "",
    dataset: {}, style: {}, files: [],
    _classes: new Set(),
    classList: {
      add(c) { this._c.add(c); },
      remove(c) { this._c.delete(c); },
      toggle(c, f) { const s = this._c; if (f === undefined) { s.has(c) ? s.delete(c) : s.add(c); } else { f ? s.add(c) : s.delete(c); } },
      contains(c) { return this._c.has(c); },
      _c: new Set()
    },
    addEventListener(type, fn) { (listeners[type] || (listeners[type] = [])).push(fn); },
    fire(type, evt = {}) { (listeners[type] || []).forEach(fn => fn(evt)); },
    appendChild(c) { (this.children || (this.children = [])).push(c); },
    replaceChildren(c) { this.children = c && c._fragChildren ? c._fragChildren : (c ? [c] : []); },
    querySelectorAll() { return []; },
    scrollIntoView() {}, focus() {},
    click() { this.fire("click", { target: this }); },
    setPointerCapture() {},
    getBoundingClientRect() { return { left: 0, top: 0, bottom: 5, width: 300, height: 5 }; },
    load() {},
    play() { this.paused = false; this.fire("play"); return Promise.resolve(); },
    pause() { this.paused = true; this.fire("pause"); },
    // audio 专有属性
    readyState: 4, duration: 30, currentTime: 0, playbackRate: 1, paused: true, src: "", currentSrc: ""
  };
}
const els = {};
const store = {};
const documentStub = {
  getElementById(id) { return els[id] || (els[id] = makeEl(id)); },
  createElement(tag) { const e = makeEl("el:" + tag); e.tag = tag; return e; },
  createDocumentFragment() { return { _fragChildren: [], appendChild(c) { this._fragChildren.push(c); } }; },
  querySelectorAll() { return []; },
  addEventListener() {}
};
const windowStub = { PointerEvent: function () {}, innerHeight: 800 };
const navigatorStub = {};
const localStorageStub = {
  getItem(k) { return k in store ? store[k] : null; },
  setItem(k, v) { store[k] = String(v); },
  removeItem(k) { delete store[k]; }
};
const URLStub = { createObjectURL() { return "blob:fake-" + Math.random().toString(16).slice(2); }, revokeObjectURL() {} };

const epilogue = `
module.exports = {
  state, playSentence, resumePlayback, renderSubtitles, syncIndexToTime,
  toggleFavorite, parseTimestamp, nudgeOffset,
  defaultOffset: DEFAULT_OFFSET,
  getData: () => subtitleData,
  builtin: BUILTIN_SUBTITLE_DATA
};`;

const mod = { exports: {} };
new Function(
  "document", "window", "navigator", "localStorage", "URL", "module", "exports",
  script + epilogue
)(documentStub, windowStub, navigatorStub, localStorageStub, URLStub, mod, mod.exports);

const api = mod.exports;
const { state, playSentence } = api;
const audio = documentStub.getElementById("audioPlayer");
const badge = documentStub.getElementById("sentenceCountBadge");
const toastEl = documentStub.getElementById("toast");

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log("  ✅", name); }
  else { fail++; console.log("  ❌", name, extra !== undefined ? JSON.stringify(extra) : ""); }
}

console.log("== 1. 初始化 ==");
const data = api.getData();
const OFF = state.offset;
check("注入演示台词 12 条", data.length === 12, data.length);
check("初始渲染 12 张卡片", els.subtitlesList.children.length === 12, els.subtitlesList.children.length);
check("徽标显示句数", badge.textContent === "12 句", badge.textContent);
check("初始未选中句子", state.currentIndex === -1);
check("默认偏移 = 0s", api.defaultOffset === 0 && OFF === 0, [api.defaultOffset, OFF]);
check("校准面板默认值已显示", els.calibValue.textContent === "+0.00s", els.calibValue.textContent);
check("课文标题已注入", els.movieTitle.textContent === "每日口语（演示）", els.movieTitle.textContent);
check("页面标题已设置", String(documentStub.title || "").includes("每日口语"), documentStub.title);
check("收藏初始为空", state.favorites.size === 0, [...state.favorites]);

console.log("== 2. 未载入音频时的保护 ==");
playSentence(0);
check("提示先载入音频", toastEl.textContent.includes("载入音频"), toastEl.textContent);

console.log("== 3. 载入音频后逐句播放（含偏移） ==");
audio.src = "blob:fake";
audio.readyState = 4;
playSentence(4);
const item4 = data[4];
check("跳转 = 句首 + 偏移", Math.abs(audio.currentTime - (item4.start + OFF)) < 1e-9, [audio.currentTime, item4.start + OFF]);
check("开始播放", audio.paused === false);
check("当前句索引 = 4", state.currentIndex === 4, state.currentIndex);
check("底部预览同步", els.previewEn.textContent === item4.en, els.previewEn.textContent);

console.log("== 4. 连续播放自动同步（偏移域） ==");
audio.currentTime = data[6].start + OFF + 0.05;
audio.fire("timeupdate");
check("自动跳到第 7 句", state.currentIndex === 6, state.currentIndex);

console.log("== 5. 句尾停顿 + 恢复续播 ==");
state.autoPause = true;
playSentence(8);
audio.currentTime = data[8].end + OFF;
audio.fire("timeupdate");
check("句尾自动暂停", audio.paused === true);
els.btnPlayPause.fire("click");
check("按播放键续播下一句", state.currentIndex === 9 && audio.paused === false &&
  Math.abs(audio.currentTime - (data[9].start + OFF)) < 1e-9,
  { idx: state.currentIndex, paused: audio.paused, t: audio.currentTime });

console.log("== 6. 单句循环 ==");
state.autoPause = false;
state.loopSentence = true;
playSentence(10);
audio.currentTime = data[10].end + OFF;
audio.fire("timeupdate");
check("到达句尾回到句首重播", Math.abs(audio.currentTime - (data[10].start + OFF)) < 1e-9 && audio.paused === false,
  { t: audio.currentTime, paused: audio.paused });
state.loopSentence = false;

console.log("== 7. 上一句 / 下一句按钮 ==");
audio.currentTime = data[10].start + OFF + 5;
els.btnPrev.fire("click");
check("播放中途按上一句回到本句开头", state.currentIndex === 10, state.currentIndex);
els.btnNext.fire("click");
check("下一句跳转", state.currentIndex === 11, state.currentIndex);

console.log("== 8. 收藏与筛选 ==");
state.favorites.clear();
const star = makeEl("star");
star.dataset.fav = String(data[3].id);
api.toggleFavorite(data[3].id, star);
check("收藏写入本地", JSON.parse(store["movie:demo:favs"]).includes(data[3].id));
check("星标变实心", star.textContent === "★", star.textContent);
state.favoritesOnly = true;
api.renderSubtitles();
check("仅看收藏只剩 1 张卡", els.subtitlesList.children.length === 1, els.subtitlesList.children.length);
state.favoritesOnly = false;

console.log("== 9. 双语搜索 ==");
state.searchKeyword = "afraid";
api.renderSubtitles();
const n1 = els.subtitlesList.children.length;
check("能搜到台词", n1 > 0 && n1 < 12, n1);
check("徽标显示筛选比例", /^\d+\/12 句$/.test(badge.textContent), badge.textContent);
state.searchKeyword = "";
api.renderSubtitles();

console.log("== 10. 倍速与设置持久化 ==");
els.btnSpeed.fire("click");
check("1x -> 1.25x", state.playbackRate === 1.25 && audio.playbackRate === 1.25, state.playbackRate);
check("设置已写入 localStorage", JSON.parse(store["movie:demo:settings"]).playbackRate === 1.25);
els.btnSpeed.fire("click"); els.btnSpeed.fire("click"); els.btnSpeed.fire("click");
check("循环切换回 1x", state.playbackRate === 1.0, state.playbackRate);

console.log("== 11. 进度条 seek 同步 ==");
audio.currentTime = data[6].start + OFF + 0.1;
audio.fire("seeked");
check("seek 后索引同步到第 7 句", state.currentIndex === 6, state.currentIndex);

console.log("== 12. 时间轴微调（应用内校准） ==");
api.nudgeOffset(0.5);
check("微调 +0.5s 生效", Math.abs(state.offset - 0.5) < 1e-9, state.offset);
check("校准面板数值更新", els.calibValue.textContent === "+0.50s", els.calibValue.textContent);
check("微调已持久化且标记为用户修改", (() => {
  const s = JSON.parse(store["movie:demo:settings"]);
  return Math.abs(s.offset - 0.5) < 1e-9 && s.offsetTouched === true;
})(), store["movie:demo:settings"]);
playSentence(4);
check("微调后跳转使用新偏移", Math.abs(audio.currentTime - (data[4].start + 0.5)) < 1e-9, audio.currentTime);
api.nudgeOffset(-0.5);
check("再微调 -0.5s 复原", Math.abs(state.offset - 0) < 1e-9, state.offset);

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail === 0 ? 0 : 1);
