#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { spawnSync } = require('child_process');

const OUT = path.resolve(__dirname, '..', 'kid_coding', 'lesson-20-排序原理', 'images');
fs.mkdirSync(OUT, { recursive: true });
const C = {
  ink: '#263238', muted: '#5f6b76', blue: '#dbeafe', blueStrong: '#2563eb',
  yellow: '#fef3c7', orange: '#f59e0b', green: '#dcfce7', greenStrong: '#16a34a',
  red: '#fee2e2', redStrong: '#dc2626', purple: '#ede9fe', purpleStrong: '#7c3aed',
  paper: '#fff', grid: '#8b98a5', coal: '#44515d', iron: '#aab5bf', gold: '#eabf42', diamond: '#55c7dc'
};
let seed = 2000;
const esc = s => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
const T = (x, y, s, cl = 'body', a = 'start', extra = '') => `<text x="${x}" y="${y}" class="${cl}" text-anchor="${a}" xml:space="preserve" ${extra}>${esc(s)}</text>`;
const ML = (x, y, lines, cl = 'body', gap = 28, a = 'start', extra = '') => `<text x="${x}" y="${y}" class="${cl}" text-anchor="${a}" ${extra}>${lines.map((s, i) => `<tspan x="${x}" dy="${i ? gap : 0}">${esc(s)}</tspan>`).join('')}</text>`;
const R = (x, y, w, h, fill = 'none', stroke = C.ink, sw = 2, rx = 8, extra = '') => `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" ${extra}/>`;
const L = (x1, y1, x2, y2, color = C.ink, sw = 3, dash = '') => `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" stroke-width="${sw}" ${dash ? `stroke-dasharray="${dash}"` : ''}/>`;
const A = (x1, y1, x2, y2, color = C.ink, sw = 4) => `<path d="M${x1} ${y1} C${x1 + (x2 - x1) * .35} ${y1},${x1 + (x2 - x1) * .65} ${y2},${x2} ${y2}" fill="none" stroke="${color}" stroke-width="${sw}" marker-end="url(#arrow)" stroke-linecap="round"/>`;
const credit = (w, h) => T(w - 24, h - 18, '公众号：icey66wang', 'small', 'end', 'style="font-size:16px;fill:#52606b"');
function W(body, w = 1200, h = 675, dark = true) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0 0L12 6L0 12Z" fill="${C.ink}"/></marker><style>.scene{${dark ? 'filter:invert(93%) hue-rotate(180deg);' : ''}}text{font-family:'Noto Sans CJK SC','Microsoft YaHei','Noto Sans',sans-serif;letter-spacing:0;fill:${C.ink}}.title{font-size:36px;font-weight:700}.h2{font-size:27px;font-weight:700}.body{font-size:21px}.small{font-size:17px;fill:${C.muted}}.mono{font-family:'Noto Sans Mono CJK SC','Noto Sans Mono','DejaVu Sans Mono',monospace}</style></defs><g class="scene"><rect width="${w}" height="${h}" fill="${C.paper}"/>${body}</g></svg>`;
}
function write(name, data) { fs.writeFileSync(path.join(OUT, name), data); }
function exBase(id, type, x, y, w, h, stroke = C.ink, fill = 'transparent') {
  const s = seed++;
  return { id, type, x, y, width: w, height: h, angle: 0, strokeColor: stroke, backgroundColor: fill,
    fillStyle: 'solid', strokeWidth: 2, strokeStyle: 'solid', roughness: 1, opacity: 100, groupIds: [],
    frameId: null, index: `a${s}`, roundness: type === 'rectangle' ? { type: 3 } : null, seed: s,
    version: 1, versionNonce: s * 17, isDeleted: false, boundElements: null, updated: 1, locked: false };
}
const ER = (id, x, y, w, h, fill = 'transparent', stroke = C.ink) => exBase(id, 'rectangle', x, y, w, h, stroke, fill);
const ET = (id, x, y, text, size = 20, color = C.ink) => ({ ...exBase(id, 'text', x, y, Math.max(...text.split('\n').map(s => [...s].length)) * size, size * 1.3 * text.split('\n').length, color), text, fontSize: size, fontFamily: 1, textAlign: 'left', verticalAlign: 'top', containerId: null, originalText: text, autoResize: true, lineHeight: 1.25 });
const EA = (id, x, y, dx, dy, color = C.ink) => ({ ...exBase(id, 'arrow', x, y, Math.abs(dx), Math.abs(dy), color), points: [[0, 0], [dx, dy]], lastCommittedPoint: null, startBinding: null, endBinding: null, startArrowhead: null, endArrowhead: 'arrow', elbowed: false });
function EX(name, elements) {
  write(name, JSON.stringify({ type: 'excalidraw', version: 2, source: 'https://excalidraw.com', elements,
    appState: { gridSize: null, viewBackgroundColor: '#ffffff', theme: 'dark' }, files: {} }, null, 2));
}
function ore(x, y, color, label) {
  return R(x, y, 70, 70, color, '#33404a', 4, 4) + L(x + 10, y + 18, x + 60, y + 18, '#fff', 4) + L(x + 25, y + 5, x + 25, y + 62, '#fff', 3) + (label ? T(x + 35, y + 98, label, 'small', 'middle') : '');
}
function cover() {
  let b = `<rect width="1200" height="675" fill="#1d3440"/><path d="M0 505L160 380L330 470L520 345L735 470L955 360L1200 495V675H0Z" fill="#42685f"/>`;
  b += R(48, 42, 790, 140, '#21313a', '#21313a', 0, 7) + T(80, 92, '第 20 课 · 排序原理', 'h2', 'start', 'style="fill:#ffdb75"') + T(80, 151, '给战利品排好队', 'title', 'start', 'style="fill:#fff;font-size:45px"');
  b += R(335, 245, 530, 205, '#15232b', '#79d18b', 4, 8) + T(600, 290, '自动仓库 · SORTING', 'h2 mono', 'middle', 'style="fill:#79d18b"');
  const labels = [['煤炭', C.coal, 7], ['铁锭', C.iron, 2], ['金锭', C.gold, 9], ['钻石', C.diamond, 4]];
  labels.forEach(([name, color, value], i) => { const x = 385 + i * 116; b += ore(x, 322, color, '') + T(x + 35, 419, name, 'small', 'middle', 'style="fill:#cfe6e2"') + T(x + 35, 450, String(value), 'h2 mono', 'middle', 'style="fill:#fff"'); });
  b += A(370, 520, 825, 520, '#ffdb75', 7) + T(600, 565, '比较 · 交换 · 重新排列', 'h2', 'middle', 'style="fill:#fff"') + credit(1200, 675);
  write('cover.svg', W(b, 1200, 675, false));
}
function bubbleRound() {
  const vals = ['7 | 2 | 9 | 4', '2 | 7 | 9 | 4', '2 | 7 | 9 | 4', '2 | 7 | 4 | 9'];
  let b = T(600, 48, '冒泡排序的一轮：最大的数冒到最右边', 'title', 'middle') + T(600, 84, '从左往右比较相邻两格', 'body', 'middle');
  vals.forEach((v, i) => { const y = 125 + i * 112; b += R(85, y, 280, 62, i === 0 ? C.blue : '#f8fafc', C.blueStrong, 3, 6) + T(225, y + 40, v, 'h2 mono', 'middle'); if (i < 3) b += A(420, y + 30, 1040, y + 30, i === 0 || i === 2 ? C.redStrong : C.muted, 4) + T(600, y + 22, i === 0 ? '7 和 2：交换' : i === 1 ? '7 和 9：不换' : '9 和 4：交换', 'body', 'middle', `style="fill:${i === 1 ? C.muted : C.redStrong};font-weight:700"`); });
  b += R(440, 500, 320, 60, C.green, C.greenStrong, 3, 8) + T(600, 538, '最大值 9 已就位', 'h2', 'middle') + credit(1200, 675);
  write('fig02_bubble_round.svg', W(b));
  const e = [ET('title', 260, 18, '冒泡排序的一轮：最大的数冒到最右边', 28), ET('sub', 360, 56, '从左往右比较相邻两格', 18)];
  vals.forEach((v, i) => { const y = 125 + i * 112; e.push(ER(`row${i}`, 85, y, 280, 62, i === 0 ? C.blue : '#f8fafc', C.blueStrong), ET(`val${i}`, 100, y + 18, v, 20)); if (i < 3) e.push(EA(`arrow${i}`, 420, y + 30, 620, 0, i === 0 || i === 2 ? C.redStrong : C.muted), ET(`note${i}`, 455, y - 10, i === 0 ? '7 和 2：交换' : i === 1 ? '7 和 9：不换' : '9 和 4：交换', 17, i === 1 ? C.muted : C.redStrong)); });
  e.push(ER('done', 440, 500, 320, 60, C.green, C.greenStrong), ET('doneText', 468, 518, '最大值 9 已就位', 21), ET('credit', 995, 650, '公众号：icey66wang', 14, C.muted));
  EX('fig02_bubble_round.excalidraw', e);
}
function bubbleVsSelection() {
  let b = T(600, 48, '冒泡 vs 选择：两条整理路线', 'title', 'middle');
  b += R(50, 95, 510, 485, C.blue, C.blueStrong, 3, 10) + R(640, 95, 510, 485, C.yellow, C.orange, 3, 10) + T(305, 140, '冒泡排序', 'h2', 'middle') + T(895, 140, '选择排序', 'h2', 'middle');
  b += T(305, 180, '邻居比赛，较大值向右走', 'body', 'middle') + T(895, 180, '全场挑最小，送到队首', 'body', 'middle');
  const row = (x, y, values, color, mark) => { values.forEach((v, i) => { b += R(x + i * 92, y, 76, 52, color, C.ink, 2, 5) + T(x + 38 + i * 92, y + 34, v, 'h2 mono', 'middle'); if (i < values.length - 1) b += A(x + 76 + i * 92, y + 26, x + 88 + i * 92, y + 26, mark, 3); }); };
  row(95, 245, ['7', '2', '9', '4'], '#fff', C.redStrong); b += T(305, 330, '相邻比较 → 交换', 'body mono', 'middle') + R(410, 382, 92, 52, C.green, C.greenStrong, 3, 5) + T(456, 416, '9', 'h2 mono', 'middle') + T(305, 458, '一轮后最后一格锁定', 'body', 'middle');
  row(685, 245, ['7', '2', '9', '4'], '#fff', C.orange); b += R(710, 330, 300, 58, '#fff', C.orange, 3, 8) + T(860, 366, '圈出最小值：2', 'body mono', 'middle') + A(860, 395, 725, 445, C.orange, 4) + R(685, 445, 76, 52, C.green, C.greenStrong, 3, 5) + T(723, 479, '2', 'h2 mono', 'middle') + T(895, 535, '每轮把最小值送到队首', 'body', 'middle');
  b += R(235, 610, 730, 38, C.green, C.greenStrong, 2, 7) + T(600, 636, '冒泡：邻居比较    选择：全场挑最小', 'h2', 'middle') + credit(1200, 675);
  write('fig03_bubble_vs_selection.svg', W(b));
  const e = [ET('title', 350, 18, '冒泡 vs 选择：两条整理路线', 30), ER('left', 50, 95, 510, 485, C.blue, C.blueStrong), ER('right', 640, 95, 510, 485, C.yellow, C.orange), ET('lh', 180, 122, '冒泡排序', 25), ET('rh', 770, 122, '选择排序', 25), ET('ld', 95, 165, '邻居比赛，较大值向右走', 18), ET('rd', 685, 165, '全场挑最小，送到队首', 18)];
  ['7', '2', '9', '4'].forEach((v, i) => { e.push(ER(`bl${i}`, 95 + i * 92, 245, 76, 52, '#fff'), ET(`bt${i}`, 118 + i * 92, 258, v, 20)); if (i < 3) e.push(EA(`ba${i}`, 171 + i * 92, 271, 12, 0, C.redStrong)); });
  e.push(ET('bn', 145, 330, '相邻比较 → 交换', 18), ER('b9', 410, 382, 92, 52, C.green, C.greenStrong), ET('b9t', 440, 394, '9', 22), ET('bf', 145, 458, '一轮后最后一格锁定', 18));
  ['7', '2', '9', '4'].forEach((v, i) => { e.push(ER(`sl${i}`, 685 + i * 92, 245, 76, 52, '#fff'), ET(`st${i}`, 708 + i * 92, 258, v, 20)); });
  e.push(ER('pick', 710, 330, 300, 58, '#fff', C.orange), ET('pickText', 750, 345, '圈出最小值：2', 18), EA('send', 860, 395, -135, 50, C.orange), ER('s2', 685, 445, 76, 52, C.green, C.greenStrong), ET('s2t', 708, 458, '2', 22), ET('sf', 735, 515, '每轮把最小值送到队首', 18));
  e.push(ER('foot', 235, 610, 730, 38, C.green, C.greenStrong), ET('footText', 260, 617, '冒泡：邻居比较    选择：全场挑最小', 19), ET('credit', 995, 650, '公众号：icey66wang', 14, C.muted));
  EX('fig03_bubble_vs_selection.excalidraw', e);
}
function codeShot(name, title, code, output, highlight = '') {
  let b = T(50, 45, title, 'h2') + T(1145, 45, '运行成功  ✓', 'body', 'end', `style="fill:${C.greenStrong};font-weight:700"`) + R(35, 72, 755, 555, '#f7f9fb', C.grid, 2, 7) + R(810, 72, 355, 555, '#f7f9fb', C.grid, 2, 7) + R(35, 72, 755, 48, '#e9eef3', C.grid, 1, 7) + R(810, 72, 355, 48, '#e9eef3', C.grid, 1, 7) + T(58, 104, 'main.py', 'small mono') + T(833, 104, 'OUTPUT', 'small mono');
  code.forEach((s, i) => { const y = 145 + i * 40; if (highlight && s.includes(highlight)) b += R(88, y - 23, 690, 31, C.yellow, C.orange, 2, 4); b += T(58, y, String(i + 1), 'small mono', 'start', 'style="fill:#84919c"') + T(98, y, s || ' ', 'small mono', 'start', `style="font-size:17px;fill:${s.includes('print') ? C.greenStrong : s.includes('if') || s.includes('for') ? C.blueStrong : C.ink}"`); });
  output.forEach((s, i) => b += T(840, 190 + i * 58, s, 'body mono')); b += R(833, 510, 310, 50, C.green, C.greenStrong, 2, 6) + T(988, 542, 'Process finished · exit code 0', 'small mono', 'middle') + credit(1200, 675); write(`${name}.svg`, W(b));
}
function bubbleRun() { codeShot('fig04_run_bubble', 'Python · 冒泡排序 I-do 运行结果', ['loot = [7, 2, 9, 4]', 'for i in range(len(loot) - 1):', '    for j in range(len(loot) - 1 - i):', '        if loot[j] > loot[j + 1]:', '            loot[j], loot[j + 1] = loot[j + 1], loot[j]', 'print("从小到大：", loot)'], ['从小到大： [2, 4, 7, 9]']); }
function sortVsSorted() {
  let b = T(600, 48, 'sort() 与 sorted()：原地改，还是复制改？', 'title', 'middle') + R(45, 92, 520, 470, C.blue, C.blueStrong, 3, 10) + R(635, 92, 520, 470, C.yellow, C.orange, 3, 10) + L(600, 100, 600, 550, C.muted, 4) + T(305, 135, 'sort() —— 原地修改', 'h2', 'middle') + T(895, 135, 'sorted() —— 返回新列表', 'h2', 'middle');
  b += R(100, 205, 410, 72, '#fff', C.blueStrong, 2, 6) + T(305, 250, 'loot = [7, 2, 9, 4]', 'body mono', 'middle') + A(305, 300, 305, 365, C.blueStrong, 4) + R(150, 395, 310, 70, C.green, C.greenStrong, 3, 8) + T(305, 438, '[2, 4, 7, 9]', 'h2 mono', 'middle') + T(305, 505, '原背包被直接重排', 'body', 'middle') + R(690, 205, 410, 72, '#fff', C.orange, 2, 6) + T(895, 250, 'new_loot = sorted(loot)', 'body mono', 'middle') + R(695, 330, 170, 70, C.blue, C.blueStrong, 3, 8) + T(780, 373, '原 loot', 'body mono', 'middle') + A(865, 365, 925, 365, C.orange, 4) + R(955, 330, 150, 70, C.green, C.greenStrong, 3, 8) + T(1030, 373, '新列表', 'body mono', 'middle') + T(1030, 435, '[2,4,7,9]', 'small mono', 'middle') + T(780, 465, '[7,2,9,4] 保持不变', 'body mono', 'middle') + R(165, 570, 870, 42, C.green, C.greenStrong, 2, 7) + T(600, 598, '要不要保留原列表？保留就用 sorted()。', 'body', 'middle') + credit(1200, 675);
  write('fig05_sort_vs_sorted.svg', W(b));
  const e = [ET('title', 300, 18, 'sort() 与 sorted()：原地改，还是复制改？', 28), ER('l', 45, 92, 520, 470, C.blue, C.blueStrong), ER('r', 635, 92, 520, 470, C.yellow, C.orange), ET('lh', 130, 118, 'sort() —— 原地修改', 23), ET('rh', 700, 118, 'sorted() —— 返回新列表', 23), ER('lc', 100, 205, 410, 72, '#fff', C.blueStrong), ET('lct', 122, 225, 'loot = [7, 2, 9, 4]', 18), EA('la', 305, 300, 0, 65, C.blueStrong), ER('lo', 150, 395, 310, 70, C.green, C.greenStrong), ET('lot', 170, 417, '[2, 4, 7, 9]', 22), ET('ln', 150, 505, '原背包被直接重排', 18), ER('rc', 690, 205, 410, 72, '#fff', C.orange), ET('rct', 712, 225, 'new_loot = sorted(loot)', 17), ER('old', 695, 330, 170, 70, C.blue, C.blueStrong), ET('oldt', 715, 352, '原 loot', 18), EA('copy', 865, 365, 60, 0, C.orange), ER('new', 955, 330, 150, 70, C.green, C.greenStrong), ET('newt', 975, 352, '新列表', 18), ET('newv', 960, 430, '[2,4,7,9]', 16), ET('oldv', 695, 430, '[7,2,9,4] 保持不变', 16), ER('foot', 165, 570, 870, 42, C.green, C.greenStrong), ET('foott', 185, 580, '要不要保留原列表？保留就用 sorted()。', 18), ET('credit', 995, 650, '公众号：icey66wang', 14, C.muted)];
  EX('fig05_sort_vs_sorted.excalidraw', e);
}
function descendingRun() { codeShot('fig06_run_descending', 'Python · We-do 改成降序', ['loot = [7, 2, 9, 4]', 'for i in range(len(loot) - 1):', '    for j in range(len(loot) - 1 - i):', '        if loot[j] < loot[j + 1]:', '            loot[j], loot[j + 1] = loot[j + 1], loot[j]', 'print("从大到小：", loot)'], ['从大到小： [9, 7, 4, 2]'], '<'); }
function summary() {
  const items = [['↕', '排序', '按规则重新排队：升序小到大，降序大到小', C.blue], ['○', '冒泡排序', '比较邻居，较大值逐轮冒到右边', C.green], ['★', '选择排序', '每轮挑出剩余元素里的最小值', C.yellow], ['⇄', '交换', '多重赋值一行交换两个位置', C.purple], ['▣', 'sort()', '修改原列表；sorted() 返回新列表', C.blue], ['⌘', '嵌套循环', '外层管轮次，内层做逐格比较', C.red]];
  let b = R(0, 0, 900, 1200, '#f4f7f9', 'none', 0, 0) + R(42, 38, 816, 174, '#e8f2ff', C.blueStrong, 3, 8) + T(74, 88, '第 20 课 · 知识清单', 'h2') + T(74, 146, '今天你学会了', 'title', 'start', 'style="font-size:46px"') + T(75, 185, '《我的世界里学编程》', 'body') + R(545, 68, 270, 56, C.green, C.greenStrong, 2, 28) + T(680, 104, '第三阶段 · 算法关', 'small', 'middle', 'style="font-weight:700"');
  items.forEach((it, i) => { const y = 244 + i * 132; b += R(58, y, 784, 108, '#fff', C.grid, 2, 7) + T(112, y + 65, it[0], 'body', 'middle', 'style="font-size:28px"') + T(168, y + 42, it[1], 'h2') + T(168, y + 78, it[2], 'body'); });
  b += R(42, 1055, 816, 105, '#263238', '#263238', 0, 7) + T(75, 1101, '一句话总结', 'small', 'start', 'style="fill:#bdd7e5;font-weight:700"') + T(75, 1139, '先手写看懂排序，再用工具处理大量数据。', 'body', 'start', 'style="fill:#fff;font-weight:700"') + credit(900, 1200);
  write('summary.svg', W(b, 900, 1200, true));
}
function preview() {
  let b = `<rect width="1200" height="675" fill="#25394c"/><path d="M0 510L170 395L340 470L545 355L750 470L955 365L1200 500V675H0Z" fill="#3e655e"/>` + R(50, 45, 825, 138, '#21313a', '#21313a', 0, 7) + T(84, 95, '下一课 · 时间复杂度', 'h2', 'start', 'style="fill:#ffdb75"') + T(84, 153, '为什么有的排序会超时？', 'title', 'start', 'style="fill:#fff;font-size:42px"') + R(185, 255, 830, 95, '#101b22', '#79d18b', 4, 8) + T(600, 316, 'O(n²) 还是 O(n)？', 'title', 'middle', 'style="fill:#79d18b;font-family:monospace"') + T(600, 410, '数据变多，工作量怎么长？', 'body', 'middle', 'style="fill:#fff"') + R(230, 475, 300, 58, C.yellow, '#60452f', 3, 4) + T(380, 512, '小数据：很快', 'body', 'middle') + R(670, 475, 300, 58, C.red, C.redStrong, 3, 4) + T(820, 512, '大数据：超时', 'body', 'middle') + credit(1200, 675);
  write('preview_next.svg', W(b, 1200, 675, false));
}
function png() {
  let browser = null;
  for (const name of ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser']) { const q = spawnSync('which', [name], { encoding: 'utf8' }); if (q.status === 0) { browser = q.stdout.trim(); break; } }
  if (!browser) throw new Error('Chrome unavailable');
  for (const f of fs.readdirSync(OUT).filter(x => x.endsWith('.svg')).sort()) {
    const size = f === 'summary.svg' ? '900,1200' : '1200,675';
    const q = spawnSync(browser, ['--headless', '--disable-gpu', '--no-sandbox', '--hide-scrollbars', `--window-size=${size}`, `--screenshot=${path.join(OUT, f.replace('.svg', '.png'))}`, `file://${path.join(OUT, f)}`], { encoding: 'utf8' });
    if (q.status) throw new Error(q.stderr || `Chrome failed for ${f}`);
  }
}
cover(); bubbleRound(); bubbleVsSelection(); bubbleRun(); sortVsSorted(); descendingRun(); summary(); preview(); png();
console.log(`Generated lesson 20 images in ${OUT}`);
