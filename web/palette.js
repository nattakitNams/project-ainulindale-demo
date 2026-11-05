// พาเลทไบแวเรียต: ไล่สีแบบ bilinear ใน OKLab — อัลกอริทึมเดียวกับ app/palettes.py
const Pal = (() => {
  const lin = c => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  const gam = c => c <= 0.0031308 ? 12.92 * c : 1.055 * Math.pow(Math.max(c, 0), 1 / 2.4) - 0.055;
  function hex2rgb(h) { h = h.replace('#', ''); return [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16) / 255); }
  function rgb2hex(c) { return '#' + c.map(v => Math.max(0, Math.min(255, Math.round(v * 255))).toString(16).padStart(2, '0')).join(''); }
  function toLab(h) {
    const [r, g, b] = hex2rgb(h).map(lin);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }
  function fromLab(L) {
    const l = (L[0] + 0.3963377774 * L[1] + 0.2158037573 * L[2]) ** 3;
    const m = (L[0] - 0.1055613458 * L[1] - 0.0638541728 * L[2]) ** 3;
    const s = (L[0] - 0.0894841775 * L[1] - 1.2914855480 * L[2]) ** 3;
    const rgb = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                 -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                 -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s];
    return rgb2hex(rgb.map(v => gam(Math.max(0, Math.min(1, v)))));
  }
  // colors9 = รหัส 1→9 (x + 3y) → nx×ny สี (รหัส = y·nx + x + 1)
  function interpolate(colors9, nx, ny) {
    if (nx === 3 && ny === 3) return colors9.slice();
    const lab = colors9.map(toLab);
    const at = (x, y) => lab[y * 3 + x];
    const out = [];
    for (let y = 0; y < ny; y++) {
      const v = ny === 1 ? 1 : 2 * y / (ny - 1);
      for (let x = 0; x < nx; x++) {
        const u = nx === 1 ? 1 : 2 * x / (nx - 1);
        const x0 = Math.min(Math.floor(u), 1), y0 = Math.min(Math.floor(v), 1);
        const fu = u - x0, fv = v - y0;
        const c = [0, 1, 2].map(i => at(x0, y0)[i] * (1 - fu) * (1 - fv) + at(x0 + 1, y0)[i] * fu * (1 - fv)
          + at(x0, y0 + 1)[i] * (1 - fu) * fv + at(x0 + 1, y0 + 1)[i] * fu * fv);
        out.push(fromLab(c));
      }
    }
    return out;
  }
  return { interpolate };
})();
