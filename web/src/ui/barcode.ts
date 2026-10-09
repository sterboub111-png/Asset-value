/** Code 39 barcodes as SVG (asset labels). Every scanner reads Code 39; it covers A-Z, 0-9 and - . space, which is what
 *  asset codes use. Each character is 9 elements (bar, space, bar ...), 3 of them wide; characters are framed by "*". */
const NS = "http://www.w3.org/2000/svg";

// 1 = wide, 0 = narrow, in the order bar, space, bar, space, bar, space, bar, space, bar
export const CODE39: Record<string, string> = {
  "0": "000110100", "1": "100100001", "2": "001100001", "3": "101100000", "4": "000110001", "5": "100110000", "6": "001110000",
  "7": "000100101", "8": "100100100", "9": "001100100", A: "100001001", B: "001001001", C: "101001000", D: "000011001",
  E: "100011000", F: "001011000", G: "000001101", H: "100001100", I: "001001100", J: "000011100", K: "100000011",
  L: "001000011", M: "101000010", N: "000010011", O: "100010010", P: "001010010", Q: "000000111", R: "100000110",
  S: "001000110", T: "000010110", U: "110000001", V: "011000001", W: "111000000", X: "010010001", Y: "110010000",
  Z: "011010000", "-": "010000101", ".": "110000100", " ": "011000100", "*": "010010100",
};

/** Characters Code 39 cannot carry are left out (asset codes are upper-cased first). */
export const code39Text = (s: string): string => [...s.toUpperCase()].filter((c) => c in CODE39 && c !== "*").join("");

/** The barcode of `text` as an SVG element, `height` px tall; the narrow element is `unit` px. */
export function code39(text: string, height = 46, unit = 1.4): SVGSVGElement {
  const wide = unit * 2.6, quiet = unit * 10;
  const chars = `*${code39Text(text)}*`;
  let x = quiet;
  const bars: [number, number][] = [];
  for (const ch of chars) {
    const p = CODE39[ch];
    for (let i = 0; i < 9; i++) {
      const w = p[i] === "1" ? wide : unit;
      if (i % 2 === 0) bars.push([x, w]);
      x += w;
    }
    x += unit;   // the gap between characters
  }
  const width = x - unit + quiet;
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width.toFixed(2)} ${height}`);
  svg.setAttribute("width", width.toFixed(2)); svg.setAttribute("height", String(height));
  svg.setAttribute("class", "barcode"); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", text);
  svg.setAttribute("shape-rendering", "crispEdges");
  for (const [bx, bw] of bars) {
    const r = document.createElementNS(NS, "rect");
    r.setAttribute("x", bx.toFixed(2)); r.setAttribute("y", "0"); r.setAttribute("width", bw.toFixed(2)); r.setAttribute("height", String(height));
    svg.append(r);
  }
  return svg;
}
