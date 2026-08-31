#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const OUT = path.join(ROOT, "kid_coding", "lesson-10-嵌套循环", "images");
fs.mkdirSync(OUT, { recursive: true });

const C = {
  ink: "#263238",
  muted: "#5f6b76",
  blue: "#dbeafe",
  blueStrong: "#2563eb",
  yellow: "#fef3c7",
  orange: "#f59e0b",
  green: "#dcfce7",
  greenStrong: "#16a34a",
  red: "#fee2e2",
  redStrong: "#dc2626",
  paper: "#ffffff",
  grid: "#8b98a5",
};

function write(name, data) {
  fs.writeFileSync(path.join(OUT, name), data);
}

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function svgWrap(body, width = 1200, height = 675, dark = true) {
  const sceneFilter = dark ? "filter:invert(93%) hue-rotate(180deg);" : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<defs>
  <marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto"><path d="M0,0 L12,6 L0,12 Z" fill="${C.ink}"/></marker>
  <filter id="rough"><feTurbulence type="fractalNoise" baseFrequency="0.015" numOctaves="1" seed="7" result="noise"/><feDisplacementMap in="SourceGraphic" in2="noise" scale="0.8"/></filter>
  <style>
    .scene { ${sceneFilter} transform-origin:center; }
    text { font-family:'Noto Sans CJK SC','Microsoft YaHei','Noto Sans',sans-serif; letter-spacing:0; fill:${C.ink}; }
    .title { font-size:36px; font-weight:700; }
    .h2 { font-size:27px; font-weight:700; }
    .body { font-size:21px; }
    .small { font-size:17px; fill:${C.muted}; }
    .mono { font-family:'Noto Sans Mono CJK SC','Noto Sans Mono','DejaVu Sans Mono',monospace; }
    .emoji { font-family:'Noto Color Emoji','Segoe UI Emoji',sans-serif; }
    .rough { filter:url(#rough); }
  </style>
</defs>
<g class="scene"><rect width="${width}" height="${height}" fill="${C.paper}"/>${body}</g></svg>`;
}

function rect(x, y, w, h, fill = "none", stroke = C.ink, sw = 2, rx = 8, extra = "") {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="${fill}" stroke="${stroke}" stroke-width="${sw}" ${extra}/>`;
}

function text(x, y, value, cls = "body", anchor = "start", extra = "") {
  return `<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}" xml:space="preserve" ${extra}>${esc(value)}</text>`;
}

function multiline(x, y, lines, cls = "body", gap = 30, anchor = "start", extra = "") {
  return `<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}" ${extra}>${lines.map((line, i) => `<tspan x="${x}" dy="${i ? gap : 0}">${esc(line)}</tspan>`).join("")}</text>`;
}

function arrow(x1, y1, x2, y2, color = C.ink, sw = 4, dashed = false) {
  return `<path d="M${x1} ${y1} C${x1 + (x2 - x1) * 0.35} ${y1},${x1 + (x2 - x1) * 0.65} ${y2},${x2} ${y2}" fill="none" stroke="${color}" stroke-width="${sw}" ${dashed ? 'stroke-dasharray="9 7"' : ""} marker-end="url(#arrow)" stroke-linecap="round"/>`;
}

let nextSeed = 1000;
function baseEx(id, type, x, y, width, height, strokeColor = C.ink, backgroundColor = "transparent") {
  const seed = nextSeed++;
  return {
    id, type, x, y, width, height, angle: 0, strokeColor, backgroundColor,
    fillStyle: "solid", strokeWidth: 2, strokeStyle: "solid", roughness: 1,
    opacity: 100, groupIds: [], frameId: null, index: `a${seed}`,
    roundness: type === "rectangle" ? { type: 3 } : null, seed,
    version: 1, versionNonce: seed * 17, isDeleted: false,
    boundElements: null, updated: 1, link: null, locked: false,
  };
}

function exRect(id, x, y, w, h, fill = "transparent", stroke = C.ink) {
  return baseEx(id, "rectangle", x, y, w, h, stroke, fill);
}

function exText(id, x, y, value, size = 20, color = C.ink) {
  const lines = value.split("\n");
  const width = Math.max(...lines.map((line) => [...line].length)) * size;
  const height = lines.length * size * 1.25;
  return {
    ...baseEx(id, "text", x, y, width, height, color, "transparent"),
    text: value, fontSize: size, fontFamily: 1, textAlign: "left",
    verticalAlign: "top", containerId: null, originalText: value,
    autoResize: true, lineHeight: 1.25,
  };
}

function exArrow(id, x, y, dx, dy, color = C.ink) {
  return {
    ...baseEx(id, "arrow", x, y, Math.abs(dx), Math.abs(dy), color, "transparent"),
    points: [[0, 0], [dx, dy]], lastCommittedPoint: null,
    startBinding: null, endBinding: null, startArrowhead: null,
    endArrowhead: "arrow", elbowed: false,
  };
}

function writeEx(name, elements) {
  write(name, JSON.stringify({
    type: "excalidraw", version: 2, source: "https://excalidraw.com",
    elements,
    appState: { gridSize: null, viewBackgroundColor: "#ffffff", theme: "dark" },
    files: {},
  }, null, 2));
}

function cover() {
  const wall = [];
  const size = 42;
  for (let r = 0; r < 6; r++) {
    for (let col = 0; col < 10; col++) {
      const x = 665 + col * size;
      const y = 250 + r * size;
      const built = r === 0 || r === 5 || col === 0 || col === 9 || (r < 3 && col < 7);
      wall.push(rect(x, y, size - 3, size - 3, built ? ((r + col) % 2 ? "#71816b" : "#829078") : "#e8eef0", built ? "#536050" : "#a8bbc0", 2, 2, built ? "" : 'stroke-dasharray="6 5"'));
    }
  }
  const clouds = `<g fill="#ffffff" opacity=".92"><rect x="85" y="98" width="190" height="38" rx="18"/><rect x="130" y="72" width="85" height="46" rx="20"/><rect x="935" y="82" width="155" height="32" rx="16"/></g>`;
  const blueprint = `<g transform="translate(455 370) rotate(-8)">${rect(0, 0, 190, 132, "#d9f1f5", "#366b7a", 4, 5)}<g stroke="#70a9b5" stroke-width="2">${[38,76,114,152].map(x => `<line x1="${x}" y1="15" x2="${x}" y2="117"/>`).join("")}${[40,70,100].map(y => `<line x1="15" y1="${y}" x2="175" y2="${y}"/>`).join("")}</g></g>`;
  const builder = `<g transform="translate(330 310)"><rect x="35" y="0" width="94" height="94" fill="#dca477"/><rect x="35" y="0" width="94" height="24" fill="#55402e"/><rect x="53" y="38" width="14" height="14" fill="#20252b"/><rect x="98" y="38" width="14" height="14" fill="#20252b"/><rect x="58" y="70" width="48" height="8" fill="#8e543f"/><rect x="28" y="94" width="110" height="124" fill="#2c8392"/><rect x="4" y="103" width="28" height="103" fill="#dca477"/><rect x="134" y="103" width="28" height="96" fill="#dca477"/><rect x="38" y="218" width="36" height="92" fill="#34495e"/><rect x="94" y="218" width="36" height="92" fill="#34495e"/></g>`;
  const floating = [[710,175],[790,112],[900,176]].map(([x,y],i) => `<g transform="translate(${x} ${y}) rotate(${i*8-6})"><rect width="44" height="44" fill="#7a8b73" stroke="#52634e" stroke-width="3"/><path d="M4 13H40M4 29H40M15 2V42M31 2V42" stroke="#96a38d" stroke-width="2"/></g>`).join("");
  const body = `<rect width="1200" height="675" fill="#8ed0ea"/>${clouds}<circle cx="1080" cy="105" r="58" fill="#ffd65a"/><path d="M0 420 L170 330 L350 430 L540 335 L720 425 L930 338 L1200 420 L1200 675 L0 675 Z" fill="#6d9f5b"/><rect y="512" width="1200" height="163" fill="#74a95f"/><path d="M0 570H1200" stroke="#5b8e4a" stroke-width="6"/>${builder}${blueprint}${wall.join("")}${floating}<rect x="48" y="36" width="710" height="164" rx="7" fill="#173042" opacity=".86"/>${text(78,91,"第 10 课 · 嵌套循环","h2","start",'style="fill:#ffe28a"')}${text(78,145,"一句话盖起一座城墙","title","start",'style="fill:#ffffff;font-size:45px"')}${text(80,184,"外层管行，内层管列，代码一格格铺满地图","body","start",'style="fill:#d8edf3"')}`;
  write("cover.svg", svgWrap(body, 1200, 675, false));
}

function fig02() {
  let body = text(600, 54, "从一维到二维：一根 for 铺一行，两根 for 铺一片", "title", "middle");
  body += rect(50, 92, 465, 455, "#f8fafc", C.ink, 3, 10, 'class="rough"');
  body += rect(685, 92, 465, 455, "#f8fafc", C.ink, 3, 10, 'class="rough"');
  body += text(282, 137, "一维：一个 for", "h2", "middle");
  body += text(917, 137, "二维：for 里套 for", "h2", "middle");
  for (let j = 0; j < 8; j++) {
    body += rect(75 + j * 52, 245, 46, 46, j % 2 ? C.blue : "#bfdbfe", C.blueStrong, 2, 4);
    body += text(98 + j * 52, 276, j, "body", "middle");
  }
  body += text(282, 350, "for j in range(8):", "body mono", "middle");
  const gx = 745, gy = 175, cw = 43, ch = 43;
  for (let i = 0; i < 5; i++) for (let j = 0; j < 8; j++) {
    body += rect(gx + j*cw, gy + i*ch, cw, ch, (i+j)%2 ? "#edf7ee" : C.green, C.grid, 1.5, 2);
    if ((i===0||i===4)&&(j===0||j===7)) body += text(gx+j*cw+cw/2, gy+i*ch+28, `(${i},${j})`, "small", "middle", 'style="font-size:13px"');
  }
  body += multiline(917, 430, ["for i in range(5):", "    for j in range(8):"], "body mono", 31, "middle");
  body += arrow(535, 300, 660, 300, C.orange, 6);
  body += text(598, 272, "升维", "h2", "middle", `style="fill:${C.orange}"`);
  body += rect(125, 577, 950, 62, C.yellow, C.orange, 2, 9);
  body += text(600, 617, "一根 for 铺一行，两根 for 铺一片。", "h2", "middle");
  write("fig02_one_to_two_dimensions.svg", svgWrap(body));

  const ex = [exText("title", 170, 20, "从一维到二维：一根 for 铺一行，两根 for 铺一片", 30), exRect("left",50,92,465,455,"#f8fafc"), exRect("right",685,92,465,455,"#f8fafc"), exText("lh",180,110,"一维：一个 for",26), exText("rh",785,110,"二维：for 里套 for",26)];
  for (let j=0;j<8;j++){ ex.push(exRect(`l${j}`,75+j*52,245,46,46,j%2?C.blue:"#bfdbfe",C.blueStrong)); ex.push(exText(`ln${j}`,90+j*52,255,String(j),18)); }
  for(let i=0;i<5;i++)for(let j=0;j<8;j++)ex.push(exRect(`g${i}_${j}`,gx+j*cw,gy+i*ch,cw,ch,(i+j)%2?"#edf7ee":C.green,C.grid));
  ex.push(exText("lcode",135,340,"for j in range(8):",20),exText("rcode",770,420,"for i in range(5):\n    for j in range(8):",20),exArrow("up",535,300,125,0,C.orange),exText("upt",565,255,"升维",24),exRect("foot",125,577,950,62,C.yellow,C.orange),exText("foott",310,590,"一根 for 铺一行，两根 for 铺一片。",25));
  writeEx("fig02_one_to_two_dimensions.excalidraw", ex);
}

function fig03() {
  let body = text(600, 49, "外层 × 内层 = 总次数", "title", "middle");
  body += text(600, 88, "for i in range(3)    ×    for j in range(4)    =    12 次", "h2 mono", "middle");
  const gx=330, gy=145, cw=125, ch=115;
  const fills=[C.blue,C.yellow,C.green];
  for(let i=0;i<3;i++)for(let j=0;j<4;j++){
    const n=i*4+j+1;
    body += rect(gx+j*cw,gy+i*ch,cw,ch,fills[i],C.ink,2.4,5,'class="rough"');
    body += text(gx+j*cw+cw/2,gy+i*ch+49,n,"h2","middle");
    body += text(gx+j*cw+cw/2,gy+i*ch+81,`(${i},${j})`,"small mono","middle");
  }
  const pts=[];
  for(let i=0;i<3;i++){
    const cols=i%2===0?[0,1,2,3]:[3,2,1,0];
    for(const j of cols)pts.push(`${gx+j*cw+cw/2},${gy+i*ch+ch/2}`);
  }
  body += `<polyline points="${pts.join(" ")}" fill="none" stroke="${C.redStrong}" stroke-width="7" opacity=".62" stroke-linejoin="round" stroke-linecap="round" marker-end="url(#arrow)"/>`;
  for(let i=0;i<3;i++){
    body += text(285,gy+i*ch+53,`i = ${i}`,"h2","end",`style="fill:${[C.blueStrong,C.orange,C.greenStrong][i]}"`);
    body += arrow(292,gy+i*ch+60,322,gy+i*ch+60,[C.blueStrong,C.orange,C.greenStrong][i],3);
  }
  body += rect(855,170,285,276,"#f8fafc",C.ink,2,9);
  body += text(997,215,"每一层 i", "h2","middle");
  body += multiline(890,267,["j 从 0 走到 3","共 4 次","然后 j 回到 0","进入下一行"],"body",42,"start");
  body += rect(110,545,980,78,C.red,C.redStrong,2,9);
  body += text(600,595,"外层每转一圈，内层从头到尾完整跑一遍。","h2","middle");
  write("fig03_outer_inner_walk.svg",svgWrap(body));

  const ex=[exText("title",400,18,"外层 × 内层 = 总次数",32),exText("formula",245,62,"for i in range(3) × for j in range(4) = 12 次",24)];
  for(let i=0;i<3;i++)for(let j=0;j<4;j++){const n=i*4+j+1;ex.push(exRect(`cell${n}`,gx+j*cw,gy+i*ch,cw,ch,fills[i]));ex.push(exText(`n${n}`,gx+j*cw+52,gy+i*ch+28,String(n),26));ex.push(exText(`c${n}`,gx+j*cw+38,gy+i*ch+70,`(${i},${j})`,16));}
  for(let i=0;i<3;i++){ex.push(exText(`i${i}`,220,gy+i*ch+35,`i = ${i}`,24,[C.blueStrong,C.orange,C.greenStrong][i]));ex.push(exArrow(`ia${i}`,292,gy+i*ch+60,30,0,[C.blueStrong,C.orange,C.greenStrong][i]));}
  ex.push(exRect("note",855,170,285,276,"#f8fafc"),exText("notet",890,195,"每一层 i\nj 从 0 走到 3\n共 4 次\n然后 j 回到 0",22),exRect("foot",110,545,980,78,C.red,C.redStrong),exText("foott",260,565,"外层每转一圈，内层从头到尾完整跑一遍。",25));
  writeEx("fig03_outer_inner_walk.excalidraw",ex);
}

function fig04() {
  let body=text(600,55,'end="" 到底做了什么？',"title","middle");
  body+=rect(45,100,525,450,"#f8fafc",C.ink,3,10,'class="rough"')+rect(630,100,525,450,"#f8fafc",C.ink,3,10,'class="rough"');
  body+=text(307,145,"默认 print(x)","h2","middle")+text(307,180,"打完就换行","body","middle");
  body+=text(892,145,'print(x, end="")',"h2 mono","middle")+text(892,180,"不换行，横着接","body","middle");
  for(let i=0;i<3;i++){
    body+=rect(120,225+i*82,150,55,C.blue,C.blueStrong,2,5)+text(195,261+i*82,`print(${i+1})`,"body mono","middle");
    body+=arrow(290,252+i*82,385,252+i*82,C.muted,3)+rect(405,225+i*82,80,55,"#f1f5f9",C.ink,2,5)+text(445,261+i*82,String(i+1),"h2 mono","middle");
  }
  for(let i=0;i<3;i++) body+=rect(675+i*142,238,130,55,C.green,C.greenStrong,2,5)+text(740+i*142,273,`print(${i+1})`,"small mono","middle");
  body+=arrow(685,336,1090,336,C.greenStrong,4)+rect(760,370,265,62,"#f1f5f9",C.ink,2,5)+text(892,409,"1 2 3","h2 mono","middle");
  body+=text(307,510,"每次 print 后自动换行","body","middle")+text(892,485,"末尾接什么，由 end 决定","body","middle");
  body+=rect(95,580,1010,58,C.yellow,C.orange,2,9)+text(600,618,'内层用 end="" 横着接；内层结束后，外层用 print() 主动换行。',"body","middle");
  write("fig04_print_end.svg",svgWrap(body));

  const ex=[exText("title",420,25,'end="" 到底做了什么？',32),exRect("left",45,100,525,450,"#f8fafc"),exRect("right",630,100,525,450,"#f8fafc"),exText("lh",190,120,"默认 print(x)\n打完就换行",24),exText("rh",745,120,'print(x, end="")\n不换行，横着接',24)];
  for(let i=0;i<3;i++){ex.push(exRect(`lp${i}`,120,225+i*82,150,55,C.blue,C.blueStrong),exText(`lpt${i}`,140,240+i*82,`print(${i+1})`,18),exArrow(`la${i}`,290,252+i*82,95,0),exRect(`lo${i}`,405,225+i*82,80,55,"#f1f5f9"),exText(`lot${i}`,435,240+i*82,String(i+1),22));ex.push(exRect(`rp${i}`,675+i*142,238,130,55,C.green,C.greenStrong),exText(`rpt${i}`,692+i*142,254,`print(${i+1})`,16));}
  ex.push(exArrow("run",685,336,405,0,C.greenStrong),exRect("rout",760,370,265,62,"#f1f5f9"),exText("routt",850,386,"1 2 3",26),exRect("foot",95,580,1010,58,C.yellow,C.orange),exText("foott",190,595,'内层用 end="" 横着接；外层用 print() 主动换行。',22));
  writeEx("fig04_print_end.excalidraw",ex);
}

function fig05() {
  let body=text(600,49,"if 判断位置，再决定放什么","title","middle");
  body+=text(600,84,"边界条件：i == 0 or i == rows - 1 or j == 0 or j == cols - 1","body mono","middle");
  const gx=280,gy=165,cw=85,ch=70;
  for(let j=0;j<8;j++) body+=text(gx+j*cw+cw/2,140,String(j),"small mono","middle",(j===7)?`style="fill:${C.redStrong};font-weight:700"`:"");
  for(let i=0;i<5;i++) body+=text(250,gy+i*ch+44,String(i),"small mono","end",(i===4)?`style="fill:${C.redStrong};font-weight:700"`:"");
  body+=text(620,115,"j（列号）","small","middle")+text(150,345,"i（行号）","small","middle",'transform="rotate(-90 150 345)"');
  for(let i=0;i<5;i++)for(let j=0;j<8;j++){
    const edge=i===0||i===4||j===0||j===7;
    body+=rect(gx+j*cw,gy+i*ch,cw,ch,edge?"#7bbf77":"#20252b",C.grid,2,2);
    body+=text(gx+j*cw+cw/2,gy+i*ch+44,edge?"墙":"空","body","middle",`style="fill:${edge?"#123b17":"#ffffff"};font-weight:700"`);
  }
  body+=`<rect x="268" y="153" width="704" height="374" rx="8" fill="none" stroke="${C.redStrong}" stroke-width="4" stroke-dasharray="12 9"/>`;
  body+=arrow(1000,225,953,225,C.greenStrong,4)+multiline(1015,205,["最外一圈","满足任意条件","→ 城墙"],"body",31);
  body+=arrow(1000,390,860,390,C.muted,4)+multiline(1015,373,["中间区域","else","→ 空地"],"body",31);
  body+=rect(255,548,330,56,C.red,C.redStrong,2,8)+text(420,584,"rows - 1 = 4（最后一行）","body mono","middle");
  body+=rect(615,548,330,56,C.red,C.redStrong,2,8)+text(780,584,"cols - 1 = 7（最后一列）","body mono","middle");
  body+=text(600,646,"最后一行不是 rows，而是 rows - 1：小心差 1 错！","h2","middle",`style="fill:${C.redStrong}"`);
  write("fig05_position_border.svg",svgWrap(body));

  const ex=[exText("title",405,18,"if 判断位置，再决定放什么",31),exText("cond",190,65,"i == 0 or i == rows - 1 or j == 0 or j == cols - 1",20)];
  for(let j=0;j<8;j++)ex.push(exText(`cj${j}`,gx+j*cw+34,120,String(j),18,j===7?C.redStrong:C.ink));
  for(let i=0;i<5;i++)ex.push(exText(`ri${i}`,225,gy+i*ch+22,String(i),18,i===4?C.redStrong:C.ink));
  for(let i=0;i<5;i++)for(let j=0;j<8;j++){const edge=i===0||i===4||j===0||j===7;ex.push(exRect(`g${i}_${j}`,gx+j*cw,gy+i*ch,cw,ch,edge?"#7bbf77":"#20252b",C.grid));ex.push(exText(`gt${i}_${j}`,gx+j*cw+28,gy+i*ch+20,edge?"墙":"空",18,edge?"#123b17":"#ffffff"));}
  ex.push(exText("edge",1010,205,"最外一圈\n满足任意条件\n→ 城墙",20),exArrow("ea",1000,225,-47,0,C.greenStrong),exText("inside",1010,373,"中间区域\nelse → 空地",20),exArrow("ia",1000,390,-140,0),exRect("rows",255,548,330,56,C.red,C.redStrong),exText("rowst",280,563,"rows - 1 = 4（最后一行）",19),exRect("cols",615,548,330,56,C.red,C.redStrong),exText("colst",640,563,"cols - 1 = 7（最后一列）",19),exText("warn",290,620,"最后一行不是 rows，而是 rows - 1：小心差 1 错！",24,C.redStrong));
  writeEx("fig05_position_border.excalidraw",ex);
}

function fig06() {
  const code=[
    'rows = 5', 'cols = 8', '',
    'for i in range(rows):', '    for j in range(cols):',
    '        if i == 0 or i == rows - 1 or j == 0 or j == cols - 1:',
    '            print("🟩", end="")', '        else:',
    '            print("⬛", end="")', '    print()'
  ];
  let body=text(50,47,"Python · 5×8 城墙","h2")+text(1140,45,"运行成功  ✓","body","end",`style="fill:${C.greenStrong};font-weight:700"`);
  body+=rect(35,72,715,555,"#f7f9fb",C.grid,2,7)+rect(770,72,395,555,"#f7f9fb",C.grid,2,7);
  body+=rect(35,72,715,48,"#e9eef3",C.grid,1,7)+rect(770,72,395,48,"#e9eef3",C.grid,1,7);
  body+=text(58,104,"main.py","small mono")+text(793,104,"OUTPUT","small mono");
  code.forEach((line,i)=>{
    body+=text(57,155+i*43,String(i+1),"small mono","start",`style="fill:#84919c"`);
    const color=line.includes("if ")||line.includes("else")||line.includes("for ")?C.blueStrong:line.includes("print")?C.greenStrong:C.ink;
    body+=text(95,155+i*43,line||" ","small mono","start",`style="font-size:17px;fill:${color}"`);
  });
  const gx=815,gy=190,s=38;
  body+=text(967,157,"四周是墙，中间是空地","body","middle");
  for(let i=0;i<5;i++)for(let j=0;j<8;j++){
    const edge=i===0||i===4||j===0||j===7;
    body+=rect(gx+j*s,gy+i*s,s-3,s-3,edge?"#4caf50":"#20252b",edge?"#2f7d32":"#111820",1,2);
  }
  body+=multiline(815,430,["🟩🟩🟩🟩🟩🟩🟩🟩","🟩⬛⬛⬛⬛⬛⬛🟩","🟩⬛⬛⬛⬛⬛⬛🟩","🟩⬛⬛⬛⬛⬛⬛🟩","🟩🟩🟩🟩🟩🟩🟩🟩"],"body emoji",34,"start",'style="font-size:22px"');
  body+=rect(805,585,325,36,C.green,C.greenStrong,2,6)+text(967,610,"Process finished · exit code 0","small mono","middle");
  write("fig06_run_wall.svg",svgWrap(body));
}

function fig07() {
  let body=text(600,52,"grid[i][j]：两个中括号分别取行和列","title","middle");
  const gx=300,gy=175,cw=82,ch=72;
  for(let j=0;j<8;j++)body+=text(gx+j*cw+cw/2,148,`j=${j}`,"small mono","middle");
  for(let i=0;i<5;i++)body+=text(270,gy+i*ch+43,`i=${i}`,"small mono","end");
  for(let i=0;i<5;i++)for(let j=0;j<8;j++){
    const edge=i===0||i===4||j===0||j===7;
    body+=rect(gx+j*cw,gy+i*ch,cw,ch,edge?"#7bbf77":"#20252b",C.grid,2,2);
  }
  body+=`<path d="M282 166 q-35 0 -35 22 v50 q0 22 -22 25 q22 3 22 25 v50 q0 22 35 22" fill="none" stroke="${C.blueStrong}" stroke-width="5"/>`;
  body+=multiline(70,210,["grid[0]","第 0 行","= 一个小列表"],"body",34,"start",`style="fill:${C.blueStrong};font-weight:700"`);
  body+=arrow(1070,240,gx+cw/2,gy+ch/2,C.blueStrong,4)+rect(955,190,210,60,C.blue,C.blueStrong,2,7)+text(1060,228,'grid[0][0] = "🟩"',"body mono","middle");
  body+=arrow(1080,365,gx+3*cw+cw/2,gy+ch+ch/2,C.redStrong,4)+rect(930,340,235,60,C.red,C.redStrong,2,7)+text(1047,378,'grid[1][3] = "⬛"',"body mono","middle");
  body+=rect(95,570,1010,67,C.yellow,C.orange,2,8)+text(600,612,'grid 装着 5 个“行小列表”，每行装着 8 个格子：一维套一维就是二维。',"body","middle");
  write("fig07_grid_index.svg",svgWrap(body));

  const ex=[exText("title",310,20,"grid[i][j]：两个中括号分别取行和列",31)];
  for(let j=0;j<8;j++)ex.push(exText(`cj${j}`,gx+j*cw+22,125,`j=${j}`,16));
  for(let i=0;i<5;i++)ex.push(exText(`ri${i}`,230,gy+i*ch+20,`i=${i}`,16));
  for(let i=0;i<5;i++)for(let j=0;j<8;j++){const edge=i===0||i===4||j===0||j===7;ex.push(exRect(`g${i}_${j}`,gx+j*cw,gy+i*ch,cw,ch,edge?"#7bbf77":"#20252b",C.grid));}
  ex.push(exText("row",70,210,"grid[0]\n第 0 行\n= 一个小列表",21,C.blueStrong),exRect("p0",955,190,210,60,C.blue,C.blueStrong),exText("p0t",970,207,'grid[0][0] = "🟩"',18),exArrow("p0a",955,225,-610,-14,C.blueStrong),exRect("p1",930,340,235,60,C.red,C.redStrong),exText("p1t",945,357,'grid[1][3] = "⬛"',18),exArrow("p1a",930,365,-343,-82,C.redStrong),exRect("foot",95,570,1010,67,C.yellow,C.orange),exText("foott",170,587,'grid 装着 5 个“行小列表”，每行装着 8 个格子。',22));
  writeEx("fig07_grid_index.excalidraw",ex);
}

function summary() {
  const items=[
    ["01","嵌套循环","外层 × 内层 = 总次数",C.blue],
    ["02","行与列","外层管行 i，内层管列 j",C.green],
    ["03",'end=""',"打完不换行，print() 主动换行",C.yellow],
    ["04","看位置画图案","if + i, j 决定每格放什么",C.red],
    ["05","二维列表","grid[i][j] 先取行，再取列",C.blue],
    ["06","差 1 错","最后一行是 rows - 1",C.red],
  ];
  let body=rect(0,0,900,1200,"#f4f7f9","none",0,0);
  body+=rect(42,38,816,174,"#e8f2ff",C.blueStrong,3,8);
  body+=text(74,88,"第 10 课 · 知识清单","h2")+text(74,146,"今天你学会了","title","start",'style="font-size:46px"')+text(75,185,"《我的世界里学编程》","body");
  body+=rect(590,68,226,56,C.green,C.greenStrong,2,28)+text(703,104,"第二阶段 · 进阶关","small","middle",'style="font-weight:700"');
  items.forEach((it,i)=>{
    const y=244+i*132;
    body+=rect(58,y,784,108,"#ffffff",C.grid,2,7,'class="rough"');
    body+=`<circle cx="112" cy="${y+54}" r="34" fill="${it[3]}" stroke="${C.ink}" stroke-width="2"/>`;
    body+=text(112,y+62,it[0],"h2 mono","middle",'style="font-size:22px"');
    body+=text(168,y+42,it[1],"h2","start",'style="font-size:24px"')+text(168,y+78,it[2],"body");
  });
  body+=rect(42,1055,816,105,"#263238","#263238",0,7)+text(75,1101,"一句话总结","small","start",'style="fill:#bdd7e5;font-weight:700"')+text(75,1139,"外层管行，内层管列，一小段代码铺满一张地图。","body","start",'style="fill:#ffffff;font-weight:700"');
  body+=text(826,1185,"像素工坊 · 少儿编程课","small","end");
  write("summary.svg",svgWrap(body,900,1200,true));
}

function preview() {
  const ores=[
    ["#43bcd6","#a4edf2",540,445,"钻石"], ["#e3b52d","#ffe48a",660,480,"金"],
    ["#9aa5ad","#e2e8ec",795,430,"铁"], ["#28a66a","#8be0ab",920,480,"绿宝石"],
    ["#bd3b3b","#f28b82",1030,430,"红石"]
  ];
  let body='<rect width="1200" height="675" fill="#9b7149"/><rect x="25" y="25" width="1150" height="625" fill="#b98958" stroke="#60452f" stroke-width="12"/>';
  body+='<path d="M25 190H1175M25 365H1175" stroke="#775336" stroke-width="10"/><path d="M200 25V650M405 25V650" stroke="#775336" stroke-width="10"/>';
  body+='<rect x="55" y="55" width="650" height="125" rx="6" fill="#21313a" opacity=".88"/>'+text(85,105,"下一课 · 字典 dict","h2","start",'style="fill:#ffdb75"')+text(85,154,"给每种矿石贴价签","title","start",'style="fill:#ffffff;font-size:43px"');
  body+='<g transform="translate(235 330)"><rect x="35" width="92" height="92" fill="#dba275"/><rect x="35" width="92" height="25" fill="#543e2d"/><rect x="52" y="40" width="14" height="14" fill="#222"/><rect x="98" y="40" width="14" height="14" fill="#222"/><rect x="62" y="69" width="40" height="7" fill="#8a5442"/><rect x="25" y="92" width="112" height="128" fill="#318193"/><rect x="35" y="220" width="38" height="88" fill="#33485f"/><rect x="92" y="220" width="38" height="88" fill="#33485f"/><path d="M15 112Q-30 80 10 45" stroke="#dba275" stroke-width="25" fill="none"/><text x="80" y="-28" style="font:700 44px Noto Sans;fill:#fff">dict ?</text></g>';
  ores.forEach(([dark,light,x,y,label],i)=>{
    for(let n=0;n<4;n++) body+=`<g transform="translate(${x+(n%2)*43} ${y-Math.floor(n/2)*41})"><rect width="39" height="39" fill="${n%2?light:dark}" stroke="#33404a" stroke-width="3"/><path d="M5 12H34M13 3V36" stroke="${light}" stroke-width="3"/></g>`;
    body+=rect(x+12,y-118,78,52,"#fff3cd","#60452f",3,3)+text(x+51,y-84,"?","h2","middle",'style="font-size:30px"')+text(x+51,y+65,label,"small","middle",'style="fill:#ffffff;font-weight:700"');
  });
  body+=rect(735,77,380,74,"#fff3cd","#60452f",4,5)+text(925,124,"矿石 → 价格，怎么记？","h2","middle");
  write("preview_next.svg",svgWrap(body,1200,675,false));
}

function exportPngs() {
  const candidates=["google-chrome","google-chrome-stable","chromium","chromium-browser"];
  let browser=null;
  for(const name of candidates){const found=spawnSync("which",[name],{encoding:"utf8"});if(found.status===0){browser=found.stdout.trim();break;}}
  if(!browser) throw new Error("No headless Chrome/Chromium executable found");
  const svgs=fs.readdirSync(OUT).filter((f)=>f.endsWith(".svg")).sort();
  for(const svg of svgs){
    const png=svg.replace(/\.svg$/,".png");
    const vertical=svg==="summary.svg";
    const size=vertical?"900,1200":"1200,675";
    const result=spawnSync(browser,["--headless","--disable-gpu","--no-sandbox","--hide-scrollbars",`--window-size=${size}`,`--screenshot=${path.join(OUT,png)}`,`file://${path.join(OUT,svg)}`],{encoding:"utf8"});
    if(result.status!==0) throw new Error(`PNG export failed for ${svg}: ${result.stderr}`);
  }
}

cover();
fig02();
fig03();
fig04();
fig05();
fig06();
fig07();
summary();
preview();
exportPngs();

console.log(`Generated lesson 10 images in ${OUT}`);
