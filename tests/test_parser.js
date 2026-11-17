// 从 tools/index.html 抽取解析相关函数，在 Node 中验证（不依赖浏览器）
const fs = require("fs");
const path = require("path");
const base = path.resolve(__dirname, "..");

const html = fs.readFileSync(path.join(base, "tools", "index.html"), "utf8");
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];

const startMark = "// ---------------- 常量与全局状态 ----------------";
const endMark = "// ---------------- 渲染 ----------------";
const startIdx = script.indexOf(startMark);
const endIdx = script.indexOf(endMark);
if (startIdx === -1 || endIdx === -1) throw new Error("找不到代码区间标记");
const chunk = script.slice(startIdx, endIdx);

// 最小 DOM 桩，仅供代码加载（不执行播放逻辑）
const fakeEl = new Proxy(function () {}, {
  get(t, p) {
    if (p === "classList") return { add() {}, remove() {}, toggle() {}, contains() { return false; } };
    if (p === "style") return {};
    if (p === "dataset") return {};
    if (p === "textContent" || p === "innerHTML" || p === "value" || p === "className") return "";
    return fakeEl;
  },
  set() { return true; },
  apply() { return fakeEl; }
});
const prelude = `
const document = {
  getElementById: () => fakeEl,
  querySelectorAll: () => [],
  createElement: () => fakeEl,
  createDocumentFragment: () => fakeEl,
  addEventListener() {}
};
const localStorage = { getItem: () => null, setItem() {}, removeItem() {} };
const MOVIE_META = { id: "test", title: "测试课文", audioFile: "audio.m4a" };
`;
const epilogue = `module.exports = { parseTimestamp, buildItems, normalizeItems, decodeSubtitleBuffer };`;

const mod = { exports: {} };
new Function("fakeEl", "module", "exports", prelude + chunk + epilogue)(fakeEl, mod, mod.exports);
const { parseTimestamp, buildItems, normalizeItems, decodeSubtitleBuffer } = mod.exports;

const toAB = (buf) => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log("  ✅", name); }
  else { fail++; console.log("  ❌", name, extra !== undefined ? JSON.stringify(extra) : ""); }
}

console.log("== 1. 时间戳解析 ==");
check("SRT 毫秒格式", parseTimestamp("00:01:23,456") === 83.456, parseTimestamp("00:01:23,456"));
check("SRT 带坐标后缀", Math.abs(parseTimestamp("00:00:27,800 X1:100 X2:200") - 27.8) < 1e-9, parseTimestamp("00:00:27,800 X1:100 X2:200"));
check("ASS 百分秒格式", Math.abs(parseTimestamp("0:03:19.14") - 199.14) < 1e-9, parseTimestamp("0:03:19.14"));
check("VTT 点号格式", Math.abs(parseTimestamp("00:00:38.000") - 38) < 1e-9);

console.log("== 2. UTF-16 SRT 解码 + 解析 ==");
const srtPath = path.join(base, "tests", "fixtures", "sample.srt");
const srtBuf = fs.readFileSync(srtPath);
const srtText = decodeSubtitleBuffer(toAB(srtBuf));
check("UTF-16 解码无乱码", srtText.includes("你好") && !srtText.includes("\uFFFD"));
const srtItems = buildItems(srtText, false);
check("解析条数 = 4（已过滤标题卡与署名）", srtItems.length === 4, srtItems.length);
check("首条内容正确", srtItems[0].en === "Hello. My name is Alex." && srtItems[0].zh === "你好，我叫亚历克斯。", srtItems[0]);
check("首条时间正确", srtItems[0].start === 1 && srtItems[0].end === 3.5, [srtItems[0].start, srtItems[0].end]);
check("标题卡已过滤", !srtItems.some(it => it.zh.startsWith("主演") || it.zh.startsWith("片名")));
check("末条内容正确", srtItems[srtItems.length - 1].en.includes("Thank you"), srtItems[srtItems.length - 1]);
check("全部条目时间合法", srtItems.every(it => it.end > it.start && (it.en || it.zh)));

console.log("== 3. UTF-16 ASS 解码 + 解析 ==");
const assPath = path.join(base, "tests", "fixtures", "sample.ass");
const assBuf = fs.readFileSync(assPath);
const assText = decodeSubtitleBuffer(toAB(assBuf));
const assItems = buildItems(assText, true);
check("ASS 解析条数 = 3", assItems.length === 3, assItems.length);
check("ASS 样式标签已清除", !assItems.some(it => /[{}]/.test(it.en + it.zh)));
check("ASS 署名噪声已过滤", !assItems.some(it => /YYeTs|字幕组/.test(it.en + it.zh)));
check("ASS 首条与 SRT 一致", assItems[0].en === srtItems[0].en && assItems[0].start === srtItems[0].start, assItems[0]);

console.log("== 4. 中英混排与破折号 ==");
const mixed = buildItems("1\n00:00:01,000 --> 00:00:03,000\n- Hello. 你好\n- 这是一行中英混排示例\n", false);
check("同行混排拆分正确", mixed[0].en === "Hello." && mixed[0].zh === "你好 这是一行中英混排示例", mixed[0]);

console.log("== 5. JSON 导入规范化 ==");
const norm = normalizeItems([
  { en: "Hi", zh: "嗨" },
  { id: "7", start: "10.5", end: "9", en: "A", zh: "甲" },
  { start: 3, end: 5, en: "", zh: "只有中文" },
  { start: 1, end: 2 }
]);
check("补 id 与类型转换", norm[0].id === 1 && norm[1].id === 7 && norm[1].start === 10.5, norm);
check("非法时间被修正", norm[1].end === 12.5, norm[1]);
check("空条目被过滤", norm.length === 3, norm.length);

console.log("== 6. 演示课文产物 ==");
const packPath = path.join(base, "docs", "movies", "demo", "learning.html");
check("已生成 docs 演示学习页", fs.existsSync(packPath));
if (fs.existsSync(packPath)) {
  const pack = fs.readFileSync(packPath, "utf8");
  check("产物包含偏移注入", /let DEFAULT_OFFSET = 0\.00;/.test(pack), pack.match(/let DEFAULT_OFFSET = [^;]+;/));
  check("产物包含课文元信息", /let MOVIE_META = \{[^;]*"id":"demo"[^;]*\};/.test(pack), pack.match(/let MOVIE_META = [^;]+;/));
  const packData = JSON.parse(pack.match(/let subtitleData = (\[[\s\S]*?\]);/)[1]);
  check("产物条数 = 12", packData.length === 12, packData.length);
  check("产物无 </script> 注入风险", !packData.some(it => (it.en + it.zh).includes("</script>")));
  check("产物不含片源关键词", !/阿甘|Forrest Gump|forrest_gump|电影天堂|dytt89|SiNNERS/i.test(pack));
}

console.log("== 7. 多课文书架 ==");
const metaPath = path.join(base, "docs", "movies", "demo", "meta.json");
check("已生成 docs 演示元信息", fs.existsSync(metaPath));
if (fs.existsSync(metaPath)) {
  const meta = JSON.parse(fs.readFileSync(metaPath, "utf8"));
  check("meta.json 信息完整", meta.id === "demo" && meta.title.includes("每日口语") && meta.lines === 12 && meta.offset === 0, meta);
}
const shelf = fs.readFileSync(path.join(base, "docs", "index.html"), "utf8");
check("书架页包含演示课文", /let library = \[[^;]*demo[^;]*\];/.test(shelf));
check("书架数据包含标题", shelf.includes("每日口语"));
check("书架页链接指向学习页", shelf.includes("movies/${encodeURIComponent(m.id)}/${encodeURIComponent(m.htmlFile"));
check("书架页动态渲染标题", /escapeHtml\(m\.title/.test(shelf));
check("书架页含云端文件夹入口", shelf.includes("import=1&drive=1"));
check("书架页不含片源关键词", !/阿甘|Forrest Gump|forrest_gump|电影天堂|dytt89/i.test(shelf));

console.log(`\n结果：${pass} 通过 / ${fail} 失败`);
process.exit(fail === 0 ? 0 : 1);
